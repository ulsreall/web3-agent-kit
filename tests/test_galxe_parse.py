"""Galxe GraphQL parsing and task-type mapping.

Every method swallows its exception and returns an empty result, so a broken
parse fails silently — a task list that comes back empty is indistinguishable
from a campaign with no tasks. The tests pin the mapping table and the parse of
a well-formed response so a regression shows up here first.
"""

from __future__ import annotations

import pytest

from web3_agent_kit.airdrop.base import AirdropTask, TaskStatus, TaskType
from web3_agent_kit.airdrop.galxe import GalxeCredential, GalxePlatform


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _platform(monkeypatch, payload) -> GalxePlatform:
    platform = GalxePlatform()
    monkeypatch.setattr(platform, "_post", lambda url, **kwargs: _Resp(payload), raising=False)
    return platform


class TestLogin:
    def test_api_key_sets_a_bearer_header(self):
        platform = GalxePlatform()
        assert platform.login({"api_key": "k"}) is True
        assert platform.session.headers["Authorization"] == "Bearer k"

    def test_access_token_is_accepted(self):
        platform = GalxePlatform()
        assert platform.login({"access_token": "t"}) is True

    def test_empty_credentials_fail(self):
        assert GalxePlatform().login({}) is False


class TestTaskTypeMapping:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("twitter_follow", TaskType.SOCIAL_TWITTER_FOLLOW),
            ("twitter_retweet", TaskType.SOCIAL_TWITTER_RETWEET),
            ("twitter_like", TaskType.SOCIAL_TWITTER_LIKE),
            ("discord", TaskType.SOCIAL_DISCORD_JOIN),
            ("telegram", TaskType.SOCIAL_TELEGRAM_JOIN),
            ("on_chain", TaskType.ON_CHAIN_TX),
            ("swap", TaskType.ON_CHAIN_SWAP),
            ("bridge", TaskType.ON_CHAIN_BRIDGE),
            ("stake", TaskType.ON_CHAIN_STAKE),
            ("quiz", TaskType.QUIZ),
            ("visit", TaskType.VISIT_URL),
            ("github", TaskType.SOCIAL_GITHUB_STAR),
            ("something_else", TaskType.CUSTOM),
        ],
    )
    def test_mapping(self, raw, expected):
        assert GalxePlatform()._map_task_type(raw) == expected

    def test_uppercase_api_enums_map_the_same(self):
        assert GalxePlatform()._map_task_type("TWITTER_FOLLOW") == TaskType.SOCIAL_TWITTER_FOLLOW


class TestGetTasks:
    def test_tasks_are_parsed(self, monkeypatch):
        payload = {
            "data": {
                "campaign": {
                    "name": "Camp",
                    "description": "d",
                    "tasks": [
                        {"id": "1", "name": "Follow", "type": "twitter_follow", "points": 5},
                        {"id": "2", "name": "Swap", "type": "swap", "points": 10},
                    ],
                }
            }
        }
        platform = _platform(monkeypatch, payload)
        tasks = platform.get_tasks("c1")
        assert [t.title for t in tasks] == ["Follow", "Swap"]
        assert tasks[0].task_type is TaskType.SOCIAL_TWITTER_FOLLOW
        assert tasks[0].task_id == "galxe_c1_1"

    def test_campaign_total_points_is_the_task_sum(self, monkeypatch):
        payload = {
            "data": {
                "campaign": {
                    "tasks": [{"id": "1", "points": 5}, {"id": "2", "points": 7}],
                }
            }
        }
        platform = _platform(monkeypatch, payload)
        platform.get_tasks("c1")
        assert platform._campaigns["c1"].total_points == 12

    def test_missing_fields_get_positional_defaults(self, monkeypatch):
        platform = _platform(monkeypatch, {"data": {"campaign": {"tasks": [{}]}}})
        task = platform.get_tasks("c1")[0]
        assert task.title == "Task 0"
        assert task.task_id == "galxe_c1_0"

    def test_a_transport_error_yields_an_empty_list(self, monkeypatch):
        platform = GalxePlatform()

        def boom(*a, **k):
            raise RuntimeError("offline")

        monkeypatch.setattr(platform, "_post", boom, raising=False)
        assert platform.get_tasks("c1") == []


class TestCheckCredential:
    def test_eligibility_is_parsed(self, monkeypatch):
        payload = {
            "data": {"credential": {"id": "cr", "name": "Holder", "eligible": True, "type": "t"}}
        }
        platform = _platform(monkeypatch, payload)
        credential = platform.check_credential("cr", "0xabc")
        assert credential.is_eligible is True
        assert credential.name == "Holder"

    def test_a_failure_returns_a_not_eligible_placeholder(self, monkeypatch):
        platform = GalxePlatform()

        def boom(*a, **k):
            raise RuntimeError("offline")

        monkeypatch.setattr(platform, "_post", boom, raising=False)
        credential = platform.check_credential("cr", "0xabc")
        assert credential == GalxeCredential(credential_id="cr", name="Unknown", is_eligible=False)


class TestPoints:
    def test_one_campaign(self):
        platform = GalxePlatform()
        platform._points["c1"] = 7
        assert platform.get_points("c1") == {"c1": 7}
        assert platform.get_points("missing") == {"missing": 0}

    def test_all_campaigns(self):
        platform = GalxePlatform()
        platform._points.update({"c1": 7, "c2": 3})
        assert platform.get_points() == {"c1": 7, "c2": 3}

    def test_the_returned_dict_is_a_copy(self):
        platform = GalxePlatform()
        platform._points["c1"] = 7
        platform.get_points().clear()
        assert platform._points == {"c1": 7}


class TestTaskObject:
    def test_defaults(self):
        task = AirdropTask(task_id="t", platform="p", task_type=TaskType.CUSTOM, title="x")
        assert task.points == 0
        assert task.status is TaskStatus.PENDING


class TestCompleteAndVerify:
    def _task(self, points=5, campaign="c1"):
        return AirdropTask(
            task_id="t1",
            platform="galxe",
            task_type=TaskType.CUSTOM,
            title="x",
            points=points,
            metadata={"campaign_id": campaign},
        )

    def test_completing_marks_and_tracks_points(self):
        platform = GalxePlatform()
        task = self._task()
        assert platform.complete_task(task) is True
        assert task.status is TaskStatus.COMPLETED
        assert task.completed_at is not None
        assert platform.get_points("c1") == {"c1": 5}
        assert platform.verify_completion(task) is True

    def test_points_accumulate(self):
        platform = GalxePlatform()
        platform.complete_task(self._task(points=3))
        platform.complete_task(self._task(points=4))
        assert platform.get_points("c1") == {"c1": 7}

    def test_a_task_without_a_campaign_does_not_touch_points(self):
        platform = GalxePlatform()
        platform.complete_task(self._task(campaign=""))
        assert platform.get_points() == {}

    def test_an_uncompleted_task_does_not_verify(self):
        assert GalxePlatform().verify_completion(self._task()) is False


class TestDiscoverCampaigns:
    def test_campaigns_are_parsed(self, monkeypatch):
        payload = {"data": {"campaigns": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]}}
        platform = _platform(monkeypatch, payload)
        campaigns = platform.discover_campaigns()
        assert [c.campaign_id for c in campaigns] == ["a", "b"]
        assert campaigns[0].url == "https://galxe.com/campaign/a"
        assert set(platform._campaigns) == {"a", "b"}

    def test_an_entry_without_an_id_is_skipped_not_fatal(self, monkeypatch):
        payload = {
            "data": {"campaigns": [{"name": "no id"}, {"id": "b", "name": "B"}]},
        }
        platform = _platform(monkeypatch, payload)
        assert [c.campaign_id for c in platform.discover_campaigns()] == ["b"]

    def test_a_failure_returns_what_is_cached(self, monkeypatch):
        platform = GalxePlatform()

        def boom(*a, **k):
            raise RuntimeError("offline")

        monkeypatch.setattr(platform, "_post", boom, raising=False)
        platform._campaigns["cached"] = None
        assert list(platform.discover_campaigns()) == [None]
