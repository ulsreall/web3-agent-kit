"""The four remaining platform parsers, exercised the same way.

Port3, Intract, QuestN and TaskOn share one parse shape and one bare ``except``
that returns ``None`` — so a ``""`` or ``null`` points value silently removed the
task, and a ``null`` id became the string ``"None"``. All four are tested
together so the fix cannot come back in one of them.
"""

from __future__ import annotations

import pytest

from web3_agent_kit.airdrop.executor.intract_exec import IntractExecutor
from web3_agent_kit.airdrop.executor.port3_exec import Port3Executor
from web3_agent_kit.airdrop.executor.questn import QuestNExecutor
from web3_agent_kit.airdrop.executor.taskon import TaskOnExecutor

EXECUTORS = [
    pytest.param(Port3Executor, id="port3"),
    pytest.param(IntractExecutor, id="intract"),
    pytest.param(QuestNExecutor, id="questn"),
    pytest.param(TaskOnExecutor, id="taskon"),
]


@pytest.fixture
def executor(request):
    cls = request.param
    instance = cls()
    instance._campaign_id = "camp"
    return instance


class TestParseTask:
    @pytest.mark.parametrize("executor", EXECUTORS, indirect=True)
    def test_a_task_is_parsed(self, executor):
        task = executor._parse_task({"id": "t1", "title": "Swap", "points": "25"}, 0)
        assert task.points == 25
        assert task.title == "Swap"
        assert task.task_id.endswith("_t1")

    @pytest.mark.parametrize("executor", EXECUTORS, indirect=True)
    @pytest.mark.parametrize("points", ["", None, "nope", {}])
    def test_unusable_points_do_not_drop_the_task(self, executor, points):
        task = executor._parse_task({"id": "t1", "points": points}, 0)
        assert task is not None
        assert task.points == 0

    @pytest.mark.parametrize("executor", EXECUTORS, indirect=True)
    def test_reward_is_the_fallback_field(self, executor):
        assert executor._parse_task({"reward": 9}, 0).points == 9

    @pytest.mark.parametrize("executor", EXECUTORS, indirect=True)
    def test_a_null_id_falls_back_to_the_index(self, executor):
        task = executor._parse_task({"id": None, "taskId": None}, 5)
        assert task.task_id.endswith("_5")

    @pytest.mark.parametrize("executor", EXECUTORS, indirect=True)
    def test_an_unknown_type_is_custom(self, executor):
        assert executor._parse_task({"type": "brand_new"}, 0).task_type == "custom"

    @pytest.mark.parametrize("executor", EXECUTORS, indirect=True)
    def test_a_protected_task_in_ok(self, executor):
        assert executor._parse_task({"id": "x", "id_": "y"}, 0) is not None
