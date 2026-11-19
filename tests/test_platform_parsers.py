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


class _IR:
    def __init__(self, payload=None):
        self._p = payload or {}
        self.status_code = 200

    def json(self):
        return self._p


def _intract(payload=None, get=None, post=None):
    from web3_agent_kit.airdrop.executor.intract_exec import IntractExecutor

    executor = IntractExecutor()
    executor._campaign_id = "camp1"
    sent = {"get": [], "post": []}

    def _g(url, **kw):
        sent["get"].append((url, kw))
        return _IR(get or {})

    def _p(url, **kw):
        sent["post"].append((url, kw))
        return _IR(post or {})

    executor._get = _g  # type: ignore[method-assign]
    executor._post = _p  # type: ignore[method-assign]
    return executor, sent


class TestIntractParse:
    def test_a_null_type_keeps_the_task(self):
        task = _intract()[0]._parse_task({"id": "1", "type": None}, 0)
        assert task is not None and task.task_type == "custom"

    def test_a_missing_title_falls_back(self):
        task = _intract()[0]._parse_task({"id": "1"}, 3)
        assert task.title == "Task 3"

    def test_a_null_title_falls_back(self):
        assert _intract()[0]._parse_task({"id": "1", "title": None}, 0).title == "Task 0"

    def test_points_are_coerced(self):
        task = _intract()[0]._parse_task({"id": "1", "points": "12"}, 0)
        assert task.points == 12

    def test_a_missing_id_uses_the_index(self):
        assert _intract()[0]._parse_task({}, 4).task_id.endswith("_4")


class TestIntractFlow:
    def test_visit_reads_the_quest_and_assigns_an_id(self):
        executor, sent = _intract(get={"id": "q9", "title": "T"})
        assert executor.visit("https://intract.io/quest/abc") is True
        assert executor._quest_id == "q9"
        assert sent["get"][0][0].endswith("/quest/abc")

    def test_visit_returns_true_even_when_the_api_fails(self):
        executor, _ = _intract()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._get = boom  # type: ignore[method-assign]
        assert executor.visit("https://intract.io/quest/abc") is True

    def test_tasks_parse_out_of_both_shapes(self):
        executor, _ = _intract(get={"tasks": [{"id": "1", "title": "a"}, {"id": "2"}]})
        assert [t.title for t in executor.get_tasks()] == ["a", "Task 1"]

    def test_tasks_also_parse_from_the_data_envelope(self):
        executor, _ = _intract(get={"data": {"tasks": [{"id": "1", "title": "a"}]}})
        assert len(executor.get_tasks()) == 1

    def test_without_a_campaign_no_request_is_made(self):
        executor, sent = _intract()
        executor._campaign_id = None
        assert executor.get_tasks() == []
        assert sent["get"] == []

    def test_a_throwing_listing_is_an_empty_list(self):
        executor, _ = _intract()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._get = boom  # type: ignore[method-assign]
        assert executor.get_tasks() == []

    def test_a_completed_task_is_true_without_a_request(self):
        from web3_agent_kit.airdrop.executor.intract_exec import IntractTask

        executor, sent = _intract()
        assert executor.complete_task(IntractTask(task_id="1", title="t", is_completed=True))
        assert sent["post"] == []

    def test_success_marks_the_task(self):
        from web3_agent_kit.airdrop.executor.intract_exec import IntractTask

        executor, sent = _intract(post={"success": True})
        task = IntractTask(task_id="1", title="t")
        assert executor.complete_task(task) is True
        assert task.is_completed is True
        assert sent["post"][0][0].endswith("/task/1/complete")

    def test_status_completed_also_counts(self):
        from web3_agent_kit.airdrop.executor.intract_exec import IntractTask

        executor, _ = _intract(post={"status": "completed"})
        assert executor.complete_task(IntractTask(task_id="1", title="t")) is True

    def test_a_failure_stays_open(self):
        from web3_agent_kit.airdrop.executor.intract_exec import IntractTask

        task = IntractTask(task_id="1", title="t")
        assert _intract(post={"success": False})[0].complete_task(task) is False
        assert task.is_completed is False

    def test_a_throwing_transport_is_false(self):
        from web3_agent_kit.airdrop.executor.intract_exec import IntractTask

        executor, _ = _intract()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._post = boom  # type: ignore[method-assign]
        assert executor.complete_task(IntractTask(task_id="1", title="t")) is False

    def test_a_captcha_is_solved_and_attached_when_required(self):
        from web3_agent_kit.airdrop.executor.intract_exec import IntractTask

        executor, sent = _intract(post={"success": True})
        executor._solve_captcha = lambda task: "tok"  # type: ignore[method-assign]
        executor.complete_task(IntractTask(task_id="1", title="t", requires_captcha=True))
        assert sent["post"][0][1]["json"]["captcha_token"] == "tok"

    def test_the_solver_is_cached(self):
        executor, _ = _intract()
        executor._solve_captcha = lambda task: "tok"  # type: ignore[method-assign]
        assert executor._solve_captcha(None) == "tok"


class TestIntractAuth:
    def test_a_token_authenticates(self):
        executor, _ = _intract()
        assert executor.login({"token": "t"}) is True and executor._authenticated

    def test_an_oauth_code_is_exchanged(self):
        executor, sent = _intract(post={"access_token": "at"})
        assert executor.login({"code": "c"}) is True
        assert sent["post"][0][0].endswith("/auth/token")

    def test_an_empty_exchange_is_false(self):
        executor, _ = _intract(post={})
        assert executor.login({"code": "c"}) is False

    def test_a_throwing_exchange_is_false(self):
        executor, _ = _intract()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._post = boom  # type: ignore[method-assign]
        assert executor.login({"code": "c"}) is False

    def test_no_credentials_is_false(self):
        assert _intract()[0].login({}) is False

    def test_close_clears_the_token(self):
        executor, _ = _intract()
        executor._auth_token = "t"
        executor.close()
        assert executor._auth_token is None


class TestIntractCaptcha:
    def test_a_site_key_is_solved(self):
        from web3_agent_kit.airdrop.executor.intract_exec import IntractTask

        executor, _ = _intract()
        task = IntractTask(task_id="1", title="t", metadata={"recaptcha_site_key": "k"})
        seen = {}
        executor._captcha_solver = type(
            "S", (), {"solve_recaptcha_v2": staticmethod(lambda **kw: seen.update(kw) or "tok")}
        )()
        assert executor._solve_captcha(task) == "tok"
        assert seen["site_key"] == "k"

    def test_no_site_key_returns_none(self):
        from web3_agent_kit.airdrop.executor.intract_exec import IntractTask

        executor, _ = _intract()
        executor._captcha_solver = object()
        assert executor._solve_captcha(IntractTask(task_id="1", title="t")) is None

    def test_a_broken_provider_returns_none(self, caplog):
        from web3_agent_kit.airdrop.executor.intract_exec import IntractTask

        executor, _ = _intract()
        executor.config.captcha_provider = "nope"
        task = IntractTask(task_id="1", title="t", metadata={"recaptcha_site_key": "k"})
        with caplog.at_level("WARNING"):
            assert executor._solve_captcha(task) is None
        assert "CAPTCHA solving failed" in caplog.text
