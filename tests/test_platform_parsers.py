"""The four remaining platform parsers, exercised the same way.

Port3, Intract, QuestN and TaskOn share one parse shape and one bare ``except``
that returns ``None`` — so a ``""`` or ``null`` points value silently removed the
task, and a ``null`` id became the string ``"None"``. All four are tested
together so the fix cannot come back in one of them.
"""

from __future__ import annotations

import time

import pytest
import requests

from web3_agent_kit.airdrop.executor import base_executor
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


class _Resp:
    def __init__(self, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self.ok = status < 400
        self.text = ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def request(self, *a, **k):
        self.calls += 1
        item = self._responses[min(self.calls - 1, len(self._responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        pass


class _Executor(base_executor.BasePlatformExecutor):
    platform_name = "unit"

    def __init__(self, responses, **cfg):
        self.session = _FakeSession(responses)
        self.config = base_executor.ExecutorConfig(
            max_retries=3, retry_delay=0, rate_limit_delay=0, **cfg
        )
        self._last_request_time = 0.0
        self._progress_callback = None
        self._results = base_executor.ExecutorResult(platform="unit", url="https://x.example")

    def visit(self, url):
        return True

    def get_tasks(self):
        return []

    def complete_task(self, task):
        return True


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(base_executor.time, "sleep", lambda s: slept.append(s))
    return slept


class TestRetryAfterParsing:
    @pytest.mark.parametrize(
        "header,expected",
        [(None, 5.0), ("", 5.0), ("  ", 5.0), ("abc", 5.0), ("7", 7.0), ("2.5", 2.5)],
    )
    def test_values(self, header, expected):
        assert base_executor.parse_retry_after(header, 5.0) == expected

    def test_an_http_date_is_converted(self):
        from datetime import datetime, timedelta, timezone
        from email.utils import format_datetime

        soon = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30))
        assert 20 <= base_executor.parse_retry_after(soon, 5.0) <= 31

    def test_a_past_date_falls_back(self):
        from datetime import datetime, timedelta, timezone
        from email.utils import format_datetime

        past = format_datetime(datetime.now(timezone.utc) - timedelta(seconds=30))
        assert base_executor.parse_retry_after(past, 5.0) == 5.0

    @pytest.mark.parametrize("header", ["0", "-3", "100000"])
    def test_out_of_range_falls_back(self, header):
        assert base_executor.parse_retry_after(header, 5.0) == 5.0


class TestRequestLoop:
    def test_a_200_returns(self):
        executor = _Executor([_Resp(200)])
        assert executor._get("https://x.example").status_code == 200

    def test_a_429_is_retried_and_the_header_honoured(self, _no_sleep):
        executor = _Executor([_Resp(429, {"Retry-After": "2"}), _Resp(200)])
        assert executor._get("https://x.example").status_code == 200
        assert _no_sleep == [2.0]
        assert executor.session.calls == 2

    def test_a_429_without_the_header_uses_the_retry_delay(self, _no_sleep):
        executor = _Executor([_Resp(429), _Resp(200)])
        executor.config.retry_delay = 1.5
        assert executor._get("https://x.example").status_code == 200
        assert _no_sleep == [1.5]

    def test_persistent_429_raises_http_error_not_type_error(self):
        # `raise last_error` used to hit `last_error is None` here.
        executor = _Executor([_Resp(429)])
        with pytest.raises(requests.HTTPError, match="still rate limited after 3"):
            executor._get("https://x.example")
        assert executor.session.calls == 3

    def test_a_429_on_the_last_attempt_does_not_sleep(self, _no_sleep):
        executor = _Executor([_Resp(429)])
        with pytest.raises(requests.HTTPError):
            executor._get("https://x.example")
        # Two of the three attempts waited; the last one gave up immediately.
        assert len(_no_sleep) == 2

    def test_a_4xx_raises_after_the_retries(self):
        executor = _Executor([_Resp(500)])
        with pytest.raises(requests.HTTPError):
            executor._get("https://x.example")

    def test_a_connection_error_then_200_recovers(self):
        executor = _Executor([requests.ConnectionError("boom"), _Resp(200)])
        assert executor._get("https://x.example").status_code == 200
        assert executor.session.calls == 2

    def test_a_non_requests_error_is_not_retried(self):
        # Only requests exceptions are caught; a programming error should surface
        # immediately rather than after three sleeps.
        executor = _Executor([RuntimeError("boom"), _Resp(200)])
        with pytest.raises(RuntimeError, match="boom"):
            executor._get("https://x.example")
        assert executor.session.calls == 1

    def test_exhausted_connection_errors_raise_the_last(self):
        executor = _Executor([requests.ConnectionError("first"), requests.ConnectionError("last")])
        with pytest.raises(requests.ConnectionError, match="last"):
            executor._get("https://x.example")

    def test_the_configured_timeout_defaults_in(self):
        seen = {}

        class _S(_FakeSession):
            def request(self, *a, **k):
                seen.update(k)
                return _Resp(200)

        executor = _Executor([])
        executor.session = _S([])
        executor.config.timeout = 12
        executor._post("https://x.example", json={})
        assert seen["timeout"] == 12


class _Task(base_executor.PlatformTask):
    pass


class _LoopExecutor(_Executor):
    def __init__(self, tasks=None, visit=True, outcomes=None, boom=False):
        super().__init__([])
        self._tasks = tasks or []
        self._visit = visit
        self._outcomes = list(outcomes or [])
        self._boom = boom

    def visit(self, url):
        return self._visit

    def get_tasks(self):
        if self._boom:
            raise RuntimeError("listing broke")
        return self._tasks

    def complete_task(self, task):
        return self._outcomes.pop(0) if self._outcomes else True


class _Tracker:
    def __init__(self):
        self.marked = []

    def mark_task_completed(self, task):
        self.marked.append(task)


class TestCompleteAll:
    def test_a_failed_visit_stops_before_listing(self):
        executor = _LoopExecutor(tasks=[_Task("1", "t")], visit=False)
        result = executor.complete_all("https://x.example")
        assert result.errors == ["Failed to load https://x.example"]
        assert result.total_tasks == 0
        assert result.elapsed_seconds >= 0

    def test_no_tasks_is_reported_not_silent(self):
        result = _LoopExecutor().complete_all("https://x.example")
        assert result.errors == ["No tasks found"]
        assert result.completed_tasks == 0

    def test_completed_tasks_are_skipped(self):
        done = _Task("1", "done")
        done.is_completed = True
        result = _LoopExecutor(tasks=[done, _Task("2", "todo")]).complete_all("https://x.example")
        assert (result.skipped_tasks, result.completed_tasks) == (1, 1)

    def test_points_and_tracker_only_on_success(self):
        tracker = _Tracker()
        tasks = [_Task("1", "ok", points=40), _Task("2", "no", points=90)]
        result = _LoopExecutor(tasks=tasks, outcomes=[True, False]).complete_all(
            "https://x.example", tracker=tracker
        )
        assert result.points_earned == 40
        assert (result.completed_tasks, result.failed_tasks) == (1, 1)
        assert result.errors == ["Failed: no"]
        assert [t.title for t in tracker.marked] == ["ok"]
        assert tasks[0].is_completed and not tasks[1].is_completed

    def test_a_failed_task_is_not_marked_complete(self):
        task = _Task("1", "no", points=10)
        _LoopExecutor(tasks=[task], outcomes=[False]).complete_all("https://x.example")
        assert task.is_completed is False

    def test_the_progress_callback_receives_position_and_total(self):
        seen = []
        executor = _LoopExecutor(tasks=[_Task("1", "a"), _Task("2", "b")])
        executor.set_progress_callback(lambda i, total, title: seen.append((i, total, title)))
        executor.complete_all("https://x.example")
        assert seen == [(0, 2, "a"), (1, 2, "b")]

    def test_an_unexpected_error_is_captured_and_elapsed_is_still_set(self):
        result = _LoopExecutor(boom=True).complete_all("https://x.example")
        assert result.errors == ["Unexpected error: listing broke"]
        assert result.elapsed_seconds >= 0
        assert result.total_tasks == 0

    def test_get_results_returns_the_last_run(self):
        executor = _LoopExecutor()
        result = executor.complete_all("https://x.example")
        assert executor.get_results() is result


class TestDefaults:
    def test_verify_login_and_close(self):
        executor = _LoopExecutor()
        assert executor.verify() is True
        assert executor.login({}) is True
        executor.close()

    def test_the_context_manager_closes(self):
        closed = []
        executor = _LoopExecutor()
        executor.close = lambda: closed.append(1)
        with executor as handle:
            assert handle is executor
        assert closed == [1]

    def test_rate_limit_sleeps_only_when_too_soon(self):
        slept = []
        executor = _LoopExecutor()
        executor.config.rate_limit_delay = 2.0
        executor._last_request_time = time.time()
        executor._rate_limit()
        executor._last_request_time = time.time() - 10
        executor._rate_limit()
        assert slept == []

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://x.example/c/0123456789abcdef01234567", "0123456789abcdef01234567"),
            ("https://x.example/quest/abc", "abc"),
            ("https://x.example", "unknown"),
        ],
    )
    def test_extract_id_from_url(self, url, expected):
        assert _LoopExecutor()._extract_id_from_url(url) == expected
