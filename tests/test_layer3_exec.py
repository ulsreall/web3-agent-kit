"""Layer3 executor: unit parse and the numeric fields that used to drop it.

``_parse_step`` is wrapped in a bare ``except`` returning ``None``, so a points
value of ``""`` or ``None`` (Galxe and Layer3 both send them) silently removed
the step from the quest instead of defaulting to zero.
"""

from __future__ import annotations

import pytest

from web3_agent_kit.airdrop.executor.base_executor import coerce_int
from web3_agent_kit.airdrop.executor.layer3_exec import Layer3Executor


def _executor() -> Layer3Executor:
    executor = Layer3Executor()
    executor._quest_id = "q1"
    return executor


class TestCoerceInt:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("12", 12),
            (12, 12),
            (0, 0),
            ("", 0),
            (None, 0),
            ("x", 0),
            ({}, 0),
            ("7.9", 0),
            (True, 1),
        ],
    )
    def test_shapes(self, value, expected):
        assert coerce_int(value, 0) == expected


class TestQuestId:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://layer3.xyz/quests/abc", "abc"),
            ("https://layer3.xyz/quest/abc", "abc"),
            ("https://layer3.xyz/other/seg", "seg"),
            ("https://layer3.xyz", "unknown"),
        ],
    )
    def test_id_is_extracted(self, url, expected):
        assert _executor()._extract_layer3_id(url) == expected


class TestParseStep:
    def test_a_full_step_is_parsed(self):
        data = {
            "id": "s1",
            "title": "Bridge to Base",
            "type": "on_chain_bridge",
            "description": "d",
            "points": "30",
            "completed": True,
            "actionUrl": "https://bridge.example",
            "chainId": 8453,
            "chainName": "base",
            "requiresWallet": True,
        }
        step = _executor()._parse_step(data, 0)
        assert step.task_id == "layer3_q1_s1"
        assert step.points == 30
        assert step.is_completed is True
        assert step.difficulty.value == "hard"
        assert step.requires_wallet is True
        assert step.metadata["chain_name"] == "base"

    def test_a_bridge_outranks_a_plain_on_chain_step(self):
        assert _executor()._parse_step({"type": "on_chain_bridge"}, 0).difficulty.value == "hard"
        assert _executor()._parse_step({"type": "on_chain_swap"}, 0).difficulty.value == "medium"

    @pytest.mark.parametrize("points", ["", None, "nope", {}])
    def test_unusable_points_do_not_drop_the_step(self, points):
        step = _executor()._parse_step({"id": "s", "points": points}, 0)
        assert step is not None
        assert step.points == 0

    def test_xp_is_used_when_points_is_absent(self):
        assert _executor()._parse_step({"xp": 5}, 0).points == 5

    def test_a_null_id_falls_back_to_the_index(self):
        step = _executor()._parse_step({"id": None, "stepId": None}, 3)
        assert step.step_id == "3"

    def test_an_unknown_type_is_custom(self):
        assert _executor()._parse_step({"type": "brand_new"}, 0).task_type == "custom"


class _LR:
    def __init__(self, payload=None, status=200):
        self._p = payload or {}
        self.status_code = status

    def json(self):
        return self._p


def _l3(get=None, post=None):
    from web3_agent_kit.airdrop.executor.layer3_exec import Layer3Executor

    executor = Layer3Executor()
    executor._quest_id = "quest1"
    sent = {"get": [], "post": []}

    def _g(url, **kw):
        sent["get"].append((url, kw))
        return _LR(get or {})

    def _p(url, **kw):
        sent["post"].append((url, kw))
        return _LR(post or {})

    executor._get = _g  # type: ignore[method-assign]
    executor._post = _p  # type: ignore[method-assign]
    return executor, sent


def _step(step_id="s1", title="Do", done=False):
    from web3_agent_kit.airdrop.executor.layer3_exec import Layer3Task

    task = Layer3Task(task_id=step_id, title=title, step_id=step_id)
    task.is_completed = done
    return task


class TestLayer3Parse:
    def test_a_null_type_keeps_the_step(self):
        step = _l3()[0]._parse_step({"id": "1", "type": None}, 0)
        assert step is not None and step.task_type == "custom"

    def test_a_null_title_falls_back(self):
        assert _l3()[0]._parse_step({"id": "1", "title": None}, 2).title == "Step 2"

    def test_difficulty_follows_the_type(self):
        executor = _l3()[0]
        assert executor._parse_step({"id": "1", "type": "swap"}, 0).difficulty.value == "medium"
        assert executor._parse_step({"id": "1", "type": "bridge"}, 0).difficulty.value == "hard"

    def test_null_steps_and_data_do_not_raise(self):
        executor, _ = _l3()
        executor._quest_data = {"steps": None, "tasks": None}
        assert executor.get_tasks() == []

    def test_a_list_under_tasks_still_parses(self):
        executor, _ = _l3()
        executor._quest_data = {"tasks": [{"id": "1", "title": "a"}]}
        assert [t.title for t in executor.get_tasks()] == ["a"]


class TestLayer3Flow:
    def test_visit_loads_the_quest(self):
        executor, sent = _l3(get={"title": "T"})
        assert executor.visit("https://layer3.xyz/quests/abc") is True
        assert executor._quest_id == "abc"
        assert executor._quest_data == {"title": "T"}

    def test_visit_is_true_even_when_the_api_fails(self):
        executor, _ = _l3()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._get = boom  # type: ignore[method-assign]
        assert executor.visit("https://layer3.xyz/quests/abc") is True

    def test_quests_parse_and_the_category_is_passed(self):
        executor, sent = _l3(get={"quests": [{"id": "1"}]})
        assert executor.get_quests("defi") == [{"id": "1"}]
        assert sent["get"][0][1]["params"] == {"category": "defi"}

    def test_a_null_data_envelope_is_an_empty_list(self):
        executor, _ = _l3(get={"data": None})
        assert executor.get_quests() == []

    def test_without_a_quest_nothing_is_parsed(self):
        executor, _ = _l3()
        executor._quest_data = None
        assert executor.get_tasks() == []

    def test_a_completed_step_is_true_without_a_request(self):
        executor, sent = _l3()
        assert executor.complete_task(_step(done=True)) is True
        assert sent["post"] == []

    def test_success_marks_the_step(self):
        executor, sent = _l3(post={"success": True})
        step = _step()
        assert executor.complete_task(step) is True
        assert step.is_completed is True
        assert sent["post"][0][0].endswith("/steps/s1/complete")

    def test_status_completed_counts(self):
        assert _l3(post={"status": "completed"})[0].complete_task(_step()) is True

    def test_a_failure_stays_open(self):
        step = _step()
        assert _l3(post={"success": False})[0].complete_task(step) is False
        assert step.is_completed is False

    def test_a_throwing_transport_is_false(self):
        executor, _ = _l3()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._post = boom  # type: ignore[method-assign]
        assert executor.complete_task(_step()) is False

    def test_verification_needs_a_quest_and_wallet(self):
        executor, _ = _l3()
        assert executor.verify_on_chain() == {}
        executor._wallet_address = "0xabc"
        executor._quest_id = None
        assert executor.verify_on_chain() == {}

    def test_verification_returns_the_map(self):
        executor, sent = _l3(get={"verifications": {"s1": True}})
        executor._wallet_address = "0xabc"
        assert executor.verify_on_chain() == {"s1": True}
        assert sent["get"][0][1]["params"] == {"wallet": "0xabc"}

    def test_verification_failure_is_empty(self):
        executor, _ = _l3()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._get = boom  # type: ignore[method-assign]
        executor._wallet_address = "0xabc"
        assert executor.verify_on_chain() == {}


class TestLayer3Auth:
    def test_a_token_authenticates_and_records_the_wallet(self):
        executor, _ = _l3()
        assert executor.login({"token": "t", "wallet_address": "0xabc"}) is True
        assert executor._wallet_address == "0xabc" and executor._authenticated

    def test_an_oauth_code_is_exchanged(self):
        executor, sent = _l3(post={"access_token": "at"})
        assert executor.login({"code": "c"}) is True
        assert sent["post"][0][0].endswith("/auth/token")

    def test_an_empty_exchange_is_false(self):
        assert _l3(post={})[0].login({"code": "c"}) is False

    def test_a_throwing_exchange_is_false(self):
        executor, _ = _l3()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._post = boom  # type: ignore[method-assign]
        assert executor.login({"code": "c"}) is False

    def test_no_credentials_is_false(self):
        assert _l3()[0].login({}) is False

    def test_close_clears_state_and_solver(self):
        executor, _ = _l3()
        executor._auth_token = "t"
        executor._handle_captcha_if_needed()
        executor.close()
        assert executor._quest_data is None
        assert executor._auth_token is None
        assert executor._captcha_solver is None


class TestLayer3Captcha:
    def test_the_solver_is_cached(self):
        executor, _ = _l3()
        assert executor._handle_captcha_if_needed() is None
        cached = executor._captcha_solver
        assert cached is not None
        executor._handle_captcha_if_needed()
        assert executor._captcha_solver is cached

    def test_an_unknown_provider_returns_none(self):
        executor, _ = _l3()
        executor.config.captcha_provider = "nope"
        assert executor._handle_captcha_if_needed() is None
        assert executor._captcha_solver is None
