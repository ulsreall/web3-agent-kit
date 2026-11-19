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
