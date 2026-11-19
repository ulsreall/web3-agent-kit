"""Galxe executor: URL ids, task-type mapping and task parsing.

Parsing is wrapped in a bare ``except`` that returns ``None``, so a field that
fails to coerce silently drops the task from the campaign instead of erroring.
The tests pin the fields that used to do that.
"""

from __future__ import annotations

import json

import pytest

from web3_agent_kit.airdrop.executor.galxe_exec import GalxeExecutor


def _executor() -> GalxeExecutor:
    executor = GalxeExecutor()
    executor._campaign_id = "camp1"
    return executor


class TestCampaignId:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://app.galxe.com/quest/abc123", "abc123"),
            ("https://app.galxe.com/campaign/xyz", "xyz"),
            ("https://app.galxe.com/quest/abc/extra", "abc"),
            ("https://app.galxe.com/other/seg", "seg"),
            ("https://app.galxe.com", "unknown"),
        ],
    )
    def test_id_is_extracted(self, url, expected):
        assert _executor()._extract_galxe_id(url) == expected


class TestTaskTypeMapping:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("twitter_follow", "twitter_follow"),
            ("twitter_tweet", "twitter_comment"),
            ("discord_join", "discord_join"),
            ("on_chain", "on_chain_tx"),
            ("on-chain-swap", "on_chain_swap"),
            ("ON_CHAIN_BRIDGE", "on_chain_bridge"),
            ("nft_hold", "custom"),
            ("something_new", "custom"),
        ],
    )
    def test_mapping(self, raw, expected):
        assert _executor()._map_task_type(raw) == expected


class TestParseTask:
    def test_a_full_task_is_parsed(self):
        data = {
            "id": "t9",
            "name": "Swap on Base",
            "type": "on_chain_swap",
            "description": "d",
            "status": "COMPLETED",
            "credential": {"id": 12},
            "attribute": {"points": "15", "chainId": 8453, "contractAddress": "0xabc"},
        }
        task = _executor()._parse_task(data, 0)
        assert task.task_id == "galxe_camp1_t9"
        assert task.points == 15
        assert task.is_completed is True
        assert task.credential_id == "12"
        assert task.chain_id == 8453

    def test_on_chain_tasks_are_medium_and_bridges_are_hard(self):
        assert _executor()._parse_task({"type": "on_chain_swap"}, 0).difficulty.value == "medium"
        assert _executor()._parse_task({"type": "on_chain_bridge"}, 0).difficulty.value == "hard"
        assert _executor()._parse_task({"type": "quiz"}, 0).difficulty.value == "easy"

    @pytest.mark.parametrize("points", ["", None, "not-a-number", {}, 0])
    def test_unusable_points_do_not_drop_the_task(self, points):
        # int(None) and int("") raise, and the bare except used to swallow the
        # whole task instead of just the points.
        task = _executor()._parse_task({"id": "t", "attribute": {"points": points}}, 0)
        assert task is not None
        assert task.points == 0

    def test_a_null_id_falls_back_to_the_index(self):
        task = _executor()._parse_task({"id": None}, 4)
        assert task.task_id == "galxe_camp1_4"
        assert task.task_id_galxe == "4"

    def test_attribute_as_a_json_string_is_decoded(self):
        task = _executor()._parse_task({"attribute": json.dumps({"points": 7})}, 0)
        assert task.points == 7

    def test_a_broken_attribute_string_becomes_empty(self):
        task = _executor()._parse_task({"attribute": "{not json"}, 0)
        assert task.points == 0

    def test_unverified_status_is_not_completed(self):
        assert _executor()._parse_task({"status": "active"}, 0).is_completed is False

    def test_metadata_carries_the_campaign(self):
        task = _executor()._parse_task({"attribute": {"points": 1}}, 0)
        assert task.metadata["campaign_id"] == "camp1"


class TestGraphql:
    def test_auth_token_becomes_a_bearer_header(self, monkeypatch):
        executor = _executor()
        executor._auth_token = "tok"
        captured = {}

        def post(url, **kwargs):
            captured.update(kwargs)
            return type("R", (), {"json": lambda s: {"data": {}}})()

        monkeypatch.setattr(executor, "_post", post, raising=False)
        executor._graphql_query("query {}", {"a": 1})
        assert captured["headers"]["Authorization"] == "Bearer tok"
        assert captured["json"]["variables"] == {"a": 1}

    def test_without_a_token_there_is_no_auth_header(self, monkeypatch):
        executor = _executor()
        executor._auth_token = ""
        captured = {}

        def post(url, **kwargs):
            captured.update(kwargs)
            return type("R", (), {"json": lambda s: {}})()

        monkeypatch.setattr(executor, "_post", post, raising=False)
        executor._graphql_query("query {}", {})
        assert "Authorization" not in captured["headers"]


class _Resp:
    def __init__(self, payload=None, status=200):
        self._payload = payload if payload is not None else {}
        self.status_code = status
        self.headers = {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def _exec(payload=None, graph=None):
    """Executor with the transport stubbed, so only logic is exercised."""
    executor = GalxeExecutor()
    executor._campaign_id = "camp1"
    sent = {"post": [], "query": []}

    def _post(url, **kwargs):
        sent["post"].append((url, kwargs.get("json")))
        return _Resp(payload or {})

    def _query(query, variables=None):
        sent["query"].append((query, variables))
        return graph if graph is not None else {}

    executor._post = _post  # type: ignore[method-assign]
    executor._graphql_query = _query  # type: ignore[method-assign]
    return executor, sent


def _task(task_id="t1", title="Follow", done=False, task_type="twitter_follow"):
    from web3_agent_kit.airdrop.executor.galxe_exec import GalxeTask

    task = GalxeTask(task_id=task_id, title=title, task_type=task_type)
    task.task_id_galxe = task_id
    task.is_completed = done
    return task


class TestVisit:
    def test_a_loaded_campaign_is_stored(self):
        executor, _ = _exec(graph={"data": {"campaign": {"name": "C", "tasks": []}}})
        assert executor.visit("https://app.galxe.com/quest/abc") is True
        assert executor._campaign_data["name"] == "C"
        assert executor._campaign_id == "abc"

    def test_a_missing_campaign_is_false(self):
        executor, _ = _exec(graph={"data": {}})
        assert executor.visit("https://app.galxe.com/quest/abc") is False
        assert executor._campaign_data is None

    def test_a_throwing_query_is_false(self):
        executor, _ = _exec()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._graphql_query = boom  # type: ignore[method-assign]
        assert executor.visit("https://app.galxe.com/quest/abc") is False


class TestCampaigns:
    def test_edges_become_nodes(self):
        executor, sent = _exec(graph={"data": {"campaignList": {"edges": [{"node": {"id": "1"}}]}}})
        assert executor.get_campaigns() == [{"id": "1"}]
        assert sent["query"][0][1]["filter"] == {"status": "Active"}

    def test_a_space_filter_is_added(self):
        executor, sent = _exec(graph={"data": {"campaignList": {"edges": []}}})
        executor.get_campaigns(space_id="space-1", first=5)
        assert sent["query"][0][1] == {
            "first": 5,
            "filter": {"status": "Active", "spaceId": "space-1"},
        }

    def test_a_throwing_query_is_an_empty_list(self):
        executor, _ = _exec()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._graphql_query = boom  # type: ignore[method-assign]
        assert executor.get_campaigns() == []


class TestTasks:
    def test_without_a_campaign_nothing_is_parsed(self):
        executor, _ = _exec()
        assert executor.get_tasks() == []

    def test_a_broken_entry_does_not_drop_the_rest(self):
        # A task with no usable fields becomes a positional placeholder rather
        # than vanishing, so the campaign length still matches the platform.
        executor, _ = _exec()
        executor._campaign_data = {
            "tasks": [{"id": "a", "name": "ok", "type": "twitter_follow"}, {"nope": 1}]
        }
        tasks = executor.get_tasks()
        assert [t.title for t in tasks] == ["ok", "Task 1"]
        assert tasks[1].task_type == "custom"

    def test_already_completed_returns_true_without_a_request(self):
        executor, sent = _exec()
        assert executor.complete_task(_task(done=True)) is True
        assert sent["post"] == []

    def test_a_successful_completion_marks_the_task(self):
        executor, sent = _exec(payload={"success": True})
        task = _task()
        assert executor.complete_task(task) is True
        assert task.is_completed is True
        url, body = sent["post"][0]
        assert url.endswith("/task/complete")
        assert body["taskId"] == "t1" and body["campaignId"] == "camp1"

    def test_an_explicit_failure_is_false_and_stays_open(self):
        executor, _ = _exec(payload={"success": False, "message": "not eligible"})
        task = _task()
        assert executor.complete_task(task) is False
        assert task.is_completed is False

    def test_a_throwing_transport_is_false(self):
        executor, _ = _exec()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._post = boom  # type: ignore[method-assign]
        assert executor.complete_task(_task()) is False

    def test_the_captcha_payload_is_attached_when_solved(self):
        executor, sent = _exec(payload={"success": True})
        executor._handle_geetest_if_needed = lambda: {"token": "x"}  # type: ignore[method-assign]
        executor.complete_task(_task())
        assert sent["post"][0][1]["captcha"] == {"token": "x"}


class TestCredentialsAndClaim:
    def test_verification_needs_a_wallet_and_campaign(self):
        executor, _ = _exec()
        assert executor.verify_credentials() == {}
        executor._wallet_address = "0xabc"
        executor._campaign_id = None
        assert executor.verify_credentials() == {}

    def test_verification_counts_the_eligible_only(self):
        executor, _ = _exec(
            graph={
                "data": {
                    "userCredentials": [
                        {"name": "a", "eligible": True},
                        {"name": "b", "eligible": False},
                    ]
                }
            }
        )
        executor._wallet_address = "0xabc"
        assert executor.verify_credentials() == {"a": True, "b": False}
        assert executor._galxe_results.credentials_verified == 1

    def test_verification_failure_is_empty(self):
        executor, _ = _exec()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._graphql_query = boom  # type: ignore[method-assign]
        executor._wallet_address = "0xabc"
        assert executor.verify_credentials() == {}

    def test_claim_needs_a_wallet(self):
        executor, _ = _exec()
        assert executor.claim_reward() is False

    def test_a_successful_claim_records_it(self):
        executor, _ = _exec(graph={"data": {"claimReward": {"success": True, "txHash": "0x1"}}})
        executor._wallet_address = "0xabc"
        assert executor.claim_reward() is True
        assert executor._galxe_results.reward_claimed is True

    def test_a_failed_claim_is_false(self):
        executor, _ = _exec(graph={"data": {"claimReward": {"success": False, "message": "no"}}})
        executor._wallet_address = "0xabc"
        assert executor.claim_reward() is False
        assert executor._galxe_results.reward_claimed is False

    def test_a_throwing_claim_is_false(self):
        executor, _ = _exec()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._graphql_query = boom  # type: ignore[method-assign]
        executor._wallet_address = "0xabc"
        assert executor.claim_reward() is False


class TestLoginAndSolver:
    def test_a_token_becomes_a_bearer_header(self):
        executor, _ = _exec()
        assert executor.login({"wallet_address": "0xabc", "auth_token": "tok"}) is True
        assert executor.session.headers["Authorization"] == "Bearer tok"

    def test_without_a_wallet_login_fails(self):
        executor, _ = _exec()
        assert executor.login({}) is False

    def test_the_solver_is_built_once_and_reused(self):
        executor, _ = _exec()
        assert executor._handle_geetest_if_needed() is None
        assert executor._captcha_solver is not None
        cached = executor._captcha_solver
        assert executor._handle_geetest_if_needed() is None
        assert executor._captcha_solver is cached

    def test_an_unknown_provider_is_reported_not_raised(self, caplog):
        executor, _ = _exec()
        executor.config.captcha_provider = "nope"
        with caplog.at_level("WARNING"):
            assert executor._handle_geetest_if_needed() is None
        assert "CAPTCHA solver unavailable" in caplog.text
        assert executor._captcha_solver is None

    def test_close_clears_campaign_and_solver(self):
        executor, _ = _exec()
        executor._campaign_data = {"a": 1}
        executor._handle_geetest_if_needed()
        executor.close()
        assert executor._campaign_data is None and executor._captcha_solver is None
