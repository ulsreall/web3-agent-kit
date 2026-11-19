"""The legacy Gleam and Zealy API clients.

Both mark tasks completed locally rather than posting, which the docstrings now
say. Their parsers share the null-value class fixed in the executors, and a null
there used to take the whole listing down with it rather than dropping one row.
"""

from __future__ import annotations

import pytest

from web3_agent_kit.airdrop import gleam as gleam_mod
from web3_agent_kit.airdrop import zealy as zealy_mod
from web3_agent_kit.airdrop.base import AirdropTask, TaskStatus, TaskType
from web3_agent_kit.airdrop.gleam import GleamCampaign
from web3_agent_kit.airdrop.zealy import ZealyPlatform


class _Resp:
    def __init__(self, text="", payload=None):
        self.text = text
        self._p = payload or {}

    def json(self):
        return self._p


def _platform(cls, text="", payload=None):
    platform = cls()
    sent = []

    def _get(url, **kw):
        sent.append((url, kw))
        return _Resp(text, payload)

    platform._get = _get  # type: ignore[method-assign]
    return platform, sent


HTML = """
<div data-method="twitter_follow"><span class="entry-title">Follow on X</span></div>
<div data-method="visit_url"><span class="entry-title">Visit the site</span></div>
"""


class TestGleam:
    def test_entries_parse_into_tasks(self):
        platform, _ = _platform(GleamCampaign, text=HTML)
        tasks = platform.get_tasks("https://gleam.io/abc123")
        assert [t.task_type for t in tasks] == [
            TaskType.SOCIAL_TWITTER_FOLLOW,
            TaskType.VISIT_URL,
        ]
        assert tasks[0].title == "Follow on X"

    def test_a_bare_id_is_expanded_to_a_url(self):
        platform, sent = _platform(GleamCampaign, text="")
        platform.get_tasks("abc123")
        assert sent[0][0] == "https://gleam.io/abc123"

    def test_the_campaign_is_cached_for_discovery(self):
        platform, _ = _platform(GleamCampaign, text=HTML)
        platform.get_tasks("https://gleam.io/abc123")
        assert [c.campaign_id for c in platform.discover_campaigns()] == ["abc123"]

    def test_a_fetch_error_is_an_empty_list(self):
        platform, _ = _platform(GleamCampaign)

        def boom(*a, **k):
            raise RuntimeError("down")

        platform._get = boom  # type: ignore[method-assign]
        assert platform.get_tasks("abc123") == []

    def test_completion_is_local_and_needs_an_entry_index(self):
        platform, _ = _platform(GleamCampaign, text=HTML)
        task = platform.get_tasks("https://gleam.io/abc123")[0]
        assert platform.complete_task(task) is True
        assert task.status is TaskStatus.COMPLETED
        assert task.completed_at is not None
        assert platform.verify_completion(task) is True

    def test_a_task_without_an_index_fails(self):
        platform, _ = _platform(GleamCampaign)
        task = AirdropTask("1", "gleam", TaskType.CUSTOM, "t")
        assert platform.complete_task(task) is False

    def test_verify_is_false_before_completion(self):
        platform, _ = _platform(GleamCampaign)
        assert platform.verify_completion(AirdropTask("x", "gleam", TaskType.CUSTOM, "t")) is False

    def test_login_without_credentials_is_false(self):
        platform, _ = _platform(GleamCampaign)
        assert platform.login({}) is False

    def test_a_cookie_authenticates(self):
        platform, _ = _platform(GleamCampaign)
        assert platform.login({"session_cookie": "c"}) is True

    @pytest.mark.parametrize(
        "method,expected",
        [
            ("twitter_retweet", TaskType.SOCIAL_TWITTER_RETWEET),
            ("discord_join", TaskType.SOCIAL_DISCORD_JOIN),
            ("youtube_subscribe", TaskType.SOCIAL_YOUTUBE_SUBSCRIBE),
            ("referral", TaskType.REFERRAL),
            ("unknown_method", TaskType.CUSTOM),
        ],
    )
    def test_method_mapping(self, method, expected):
        platform, _ = _platform(GleamCampaign)
        assert platform._map_method_to_task_type(method) is expected


class TestZealy:
    def test_quests_parse(self):
        platform, _ = _platform(ZealyPlatform, payload={"quests": [{"id": "1", "title": "Follow"}]})
        tasks = platform.get_tasks("comm")
        assert tasks[0].title == "Follow" and tasks[0].task_type is TaskType.CUSTOM

    def test_a_null_type_keeps_the_quest(self):
        platform, _ = _platform(
            ZealyPlatform, payload={"quests": [{"id": "1", "type": None, "title": None}]}
        )
        assert [t.title for t in platform.get_tasks("comm")] == ["Quest 0"]

    def test_a_string_xp_is_coerced(self):
        platform, _ = _platform(ZealyPlatform, payload={"quests": [{"id": "1", "xp": "25"}]})
        assert platform.get_tasks("comm")[0].points == 25.0

    def test_a_null_xp_is_zero(self):
        platform, _ = _platform(ZealyPlatform, payload={"quests": [{"id": "1", "xp": None}]})
        assert platform.get_tasks("comm")[0].points == 0.0

    def test_a_null_quest_list_is_empty(self):
        platform, _ = _platform(ZealyPlatform, payload={"quests": None})
        assert platform.get_tasks("comm") == []

    def test_completion_adds_xp(self):
        platform, _ = _platform(ZealyPlatform, payload={"quests": [{"id": "1", "xp": 30}]})
        task = platform.get_tasks("comm")[0]
        assert platform.complete_task(task) is True
        assert platform.get_total_xp() == 30
        assert platform.verify_completion(task) is True

    def test_the_leaderboard_parses(self):
        platform, sent = _platform(
            ZealyPlatform,
            payload={"leaderboard": [{"rank": 3, "username": "a", "xp": "40"}]},
        )
        entries = platform.get_leaderboard("comm", limit=5)
        assert entries[0].rank == 3 and entries[0].xp == 40
        assert sent[0][1]["params"] == {"limit": 5}

    def test_a_leaderboard_entry_without_a_rank_uses_the_position(self):
        platform, _ = _platform(ZealyPlatform, payload={"leaderboard": [{"username": None}]})
        entry = platform.get_leaderboard("comm")[0]
        assert entry.rank == 1 and entry.username == "unknown"

    def test_a_leaderboard_error_is_an_empty_list(self):
        platform, _ = _platform(ZealyPlatform)

        def boom(*a, **k):
            raise RuntimeError("down")

        platform._get = boom  # type: ignore[method-assign]
        assert platform.get_leaderboard("comm") == []

    def test_login_without_credentials_is_false(self):
        assert _platform(ZealyPlatform)[0].login({}) is False

    def test_platform_name_comes_from_the_module(self):
        assert ZealyPlatform.platform_name == "zealy"
        assert GleamCampaign.platform_name == "gleam"

    def test_the_api_bases_are_https(self):
        assert zealy_mod.ZEALY_API_BASE.startswith("https://")
        assert gleam_mod.__name__.endswith("gleam")
