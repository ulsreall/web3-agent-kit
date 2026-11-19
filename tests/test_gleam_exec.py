"""Gleam task classification and entry parsing.

The classification decides which handler runs, and a handler for the wrong
network opens the wrong tab and burns the task. Parsing has to survive the
decorative bits of a real entry: an empty title, a ``javascript:`` link, no
action button at all.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from web3_agent_kit.airdrop.executor.gleam_exec import (
    GleamExecutor,
    GleamResult,
    GleamTaskType,
)


def _executor() -> GleamExecutor:
    return GleamExecutor(SimpleNamespace())


class TestClassification:
    @pytest.mark.parametrize(
        ("title", "method", "url", "expected"),
        [
            ("Follow us on Twitter", "", "", GleamTaskType.TWITTER_FOLLOW),
            ("Retweet the post", "", "", GleamTaskType.TWITTER_RETWEET),
            ("Like on Twitter", "", "", GleamTaskType.TWITTER_LIKE),
            ("Tweet about us", "", "", GleamTaskType.TWITTER_TWEET),
            ("Subscribe on YouTube", "", "", GleamTaskType.YOUTUBE_SUBSCRIBE),
            ("Join Discord", "", "", GleamTaskType.DISCORD_JOIN),
            ("Join Telegram", "", "", GleamTaskType.TELEGRAM_JOIN),
            ("Visit the page", "", "", GleamTaskType.VISIT_URL),
            ("Refer a friend", "", "", GleamTaskType.REFERRAL),
            ("Something else", "", "", GleamTaskType.CUSTOM_ACTION),
        ],
    )
    def test_text_selects_the_handler(self, title, method, url, expected):
        assert _executor()._classify_task(title, method, url) == expected

    def test_follow_beats_a_bare_tweet_mention(self):
        assert (
            _executor()._classify_task("Follow and tweet on Twitter", "", "")
            is GleamTaskType.TWITTER_FOLLOW
        )

    def test_url_alone_can_make_it_telegram_or_visit(self):
        assert _executor()._classify_task("Join", "", "https://t.me/x") is (
            GleamTaskType.TELEGRAM_JOIN
        )
        # A bare URL is not enough on its own; Gleam marks those with method=url.
        assert _executor()._classify_task("Join", "url", "https://example.com") is (
            GleamTaskType.VISIT_URL
        )

    def test_follow_on_x_is_a_twitter_follow(self):
        assert _executor()._classify_task("Follow on X", "", "https://x.com/team") is (
            GleamTaskType.TWITTER_FOLLOW
        )

    def test_classification_is_case_insensitive(self):
        assert _executor()._classify_task("JOIN DISCORD", "", "") is GleamTaskType.DISCORD_JOIN


class _Entry:
    def __init__(self, title=None, completed=False, href=None, entry_id=None, button=None):
        self._title = title
        self._completed = completed
        self._href = href
        self._entry_id = entry_id
        self._button = button

    def query_selector(self, selector):
        if "title" in selector:
            return SimpleNamespace(inner_text=lambda: self._title) if self._title else None
        if "completed" in selector or "done" in selector or "check" in selector:
            return object() if self._completed else None
        if selector.startswith("a[href"):
            return SimpleNamespace(get_attribute=lambda name: self._href) if self._href else None
        if self._button and selector == "button":
            return object()
        return None

    def get_attribute(self, name):
        if name == "data-entry-id":
            return self._entry_id
        return ""


class TestParseEntry:
    def test_full_entry_is_parsed(self):
        entry = _Entry(title="Follow on Twitter", href="https://x.com/x", entry_id="e1")
        task = _executor()._parse_entry(entry, 0)
        assert task.title == "Follow on Twitter"
        assert task.task_type is GleamTaskType.TWITTER_FOLLOW
        assert task.url == "https://x.com/x"
        assert task.entry_id == "e1"

    def test_missing_title_gets_a_positional_name(self):
        assert _executor()._parse_entry(_Entry(), 4).title == "Task 4"

    def test_javascript_and_anchor_links_are_dropped(self):
        for href in ("javascript:void(0)", "#panel"):
            assert _executor()._parse_entry(_Entry(title="Visit", href=href), 0).url == ""

    def test_completed_badge_is_recorded(self):
        assert _executor()._parse_entry(_Entry(title="Visit", completed=True), 0).is_completed

    def test_entry_id_falls_back_to_the_index(self):
        assert _executor()._parse_entry(_Entry(title="Visit"), 6).entry_id == "6"

    def test_button_selector_is_found(self):
        task = _executor()._parse_entry(_Entry(title="Visit", button=True), 0)
        assert task.selector == "button"

    def test_a_broken_entry_returns_none(self):
        class Broken:
            def query_selector(self, selector):
                raise RuntimeError("detached")

        assert _executor()._parse_entry(Broken(), 0) is None


class TestResultSummary:
    def test_empty_result(self):
        result = GleamResult(campaign_url="u", campaign_id="c")
        assert result.success_rate == 0.0
        assert result.is_fully_completed is False

    def test_partial_result_is_not_fully_completed(self):
        result = GleamResult(campaign_url="u", campaign_id="c", total_tasks=4, completed_tasks=1)
        assert result.success_rate == 0.25
        assert result.is_fully_completed is False

    def test_all_done_is_fully_completed(self):
        result = GleamResult(campaign_url="u", campaign_id="c", total_tasks=2, completed_tasks=2)
        assert result.is_fully_completed is True


class TestCompleteAll:
    """The campaign loop: what it counts, skips and reports."""

    def _executor(self, monkeypatch, tasks, complete=True, visit=True):
        from web3_agent_kit.airdrop.executor.gleam_exec import GleamTaskEntry

        executor = GleamExecutor(SimpleNamespace())
        monkeypatch.setattr(executor, "visit", lambda url: visit)
        monkeypatch.setattr(executor, "get_tasks", lambda: tasks)
        monkeypatch.setattr(executor, "complete_task", lambda task: complete)
        monkeypatch.setattr(executor, "_random_delay", lambda: None)
        monkeypatch.setattr(executor, "_verify_entries", lambda tasks: None)
        assert GleamTaskEntry  # imported for the type used below
        return executor

    def _task(self, title, completed=False):
        from web3_agent_kit.airdrop.executor.gleam_exec import GleamTaskEntry, GleamTaskType

        return GleamTaskEntry(
            entry_id=title,
            task_type=GleamTaskType.VISIT_URL,
            title=title,
            is_completed=completed,
        )

    def test_a_failed_visit_stops_before_parsing(self, monkeypatch):
        result = self._executor(monkeypatch, [], visit=False).complete_all("https://gleam.io/a")
        assert result.total_tasks == 0
        assert "Failed to load" in result.errors[0]

    def test_a_page_without_tasks_is_reported(self, monkeypatch):
        result = self._executor(monkeypatch, []).complete_all("https://gleam.io/a")
        assert result.errors == ["No tasks found on page"]

    def test_completed_entries_are_skipped(self, monkeypatch):
        tasks = [self._task("done", completed=True), self._task("todo")]
        result = self._executor(monkeypatch, tasks).complete_all("https://gleam.io/a")
        assert result.skipped_tasks == 1
        assert result.completed_tasks == 1
        assert result.total_tasks == 2

    def test_a_failure_is_counted_and_named(self, monkeypatch):
        result = self._executor(monkeypatch, [self._task("x")], complete=False).complete_all(
            "https://gleam.io/a"
        )
        assert result.failed_tasks == 1
        assert result.errors == ["Failed: x"]

    def test_a_tracker_is_notified_only_on_success(self, monkeypatch):
        marked = []

        class Tracker:
            def mark_task_completed(self, task):
                marked.append(task.title)

        tasks = [self._task("ok"), self._task("bad")]
        executor = GleamExecutor(SimpleNamespace())
        monkeypatch.setattr(executor, "visit", lambda url: True)
        monkeypatch.setattr(executor, "get_tasks", lambda: tasks)
        monkeypatch.setattr(executor, "complete_task", lambda task: task.title == "ok")
        monkeypatch.setattr(executor, "_random_delay", lambda: None)
        monkeypatch.setattr(executor, "_verify_entries", lambda tasks: None)
        executor.complete_all("https://gleam.io/a", tracker=Tracker())
        assert marked == ["ok"]

    def test_an_unexpected_error_is_captured(self, monkeypatch):
        executor = self._executor(monkeypatch, [])
        monkeypatch.setattr(
            executor, "visit", lambda url: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        result = executor.complete_all("https://gleam.io/a")
        assert "boom" in result.errors[0]
        assert result.elapsed_seconds is not None


class TestVerifyEntries:
    def test_no_page_gives_an_empty_map(self):
        assert GleamExecutor(SimpleNamespace()).verify_entry_status() == {}

    def test_titles_map_to_completion(self):
        from web3_agent_kit.airdrop.executor.gleam_exec import GleamExecutor as G

        done = SimpleNamespace(
            query_selector=lambda sel: (
                object() if "completed" in sel or "done" in sel else _Text("A")
            )
        )
        todo = SimpleNamespace(query_selector=lambda sel: _Text("B") if "title" in sel else None)
        executor = G(SimpleNamespace())
        executor._page = SimpleNamespace(query_selector_all=lambda sel: [done, todo])
        assert executor.verify_entry_status() == {"A": True, "B": False}

    def test_a_broken_page_gives_an_empty_map(self):
        executor = GleamExecutor(SimpleNamespace())
        executor._page = SimpleNamespace(
            query_selector_all=lambda sel: (_ for _ in ()).throw(RuntimeError("detached"))
        )
        assert executor.verify_entry_status() == {}


class _Text:
    def __init__(self, text):
        self._text = text

    def inner_text(self):
        return self._text


class _Drv:
    """Minimal browser: new_page/navigate/wait."""

    def __init__(self, navigate=True, wait=True, page=None):
        self._page = page or SimpleNamespace(wait_for_selector=lambda *a, **k: None)
        self._navigate = navigate
        self._wait = wait
        self.waits = []

    def new_page(self):
        return self._page

    def navigate_with_retry(self, page, url, timeout=None):
        return self._navigate

    def wait_for_element(self, page, selector, timeout=None):
        self.waits.append(selector)
        return self._wait

    def click_with_retry(self, page, selector, timeout=None):
        return True


class TestVisit:
    def test_a_loaded_page_waits_for_the_widget(self, monkeypatch):
        monkeypatch.setattr(
            "web3_agent_kit.airdrop.executor.gleam_exec.time.sleep", lambda _s: None
        )
        driver = _Drv()
        executor = GleamExecutor(driver)
        assert executor.visit("https://gleam.io/a") is True
        assert driver.waits == [executor.SELECTORS["widget_container"]]

    def test_a_failed_navigation_returns_false(self, monkeypatch):
        monkeypatch.setattr(
            "web3_agent_kit.airdrop.executor.gleam_exec.time.sleep", lambda _s: None
        )
        driver = _Drv(navigate=False)
        assert GleamExecutor(driver).visit("https://gleam.io/a") is False
        assert driver.waits == []


class TestGetTasks:
    def test_no_page_gives_an_empty_list(self):
        assert GleamExecutor(_Drv()).get_tasks() == []

    def test_entries_are_parsed(self):
        page = SimpleNamespace(
            wait_for_selector=lambda *a, **k: None,
            query_selector_all=lambda sel: [_Entry(title="Follow on Twitter")],
        )
        executor = GleamExecutor(_Drv(page=page))
        executor._page = page
        tasks = executor.get_tasks()
        assert [t.title for t in tasks] == ["Follow on Twitter"]

    def test_a_broken_entry_is_skipped_not_fatal(self):
        page = SimpleNamespace(
            wait_for_selector=lambda *a, **k: None,
            query_selector_all=lambda sel: [_Broken(), _Entry(title="Ok")],
        )
        executor = GleamExecutor(_Drv(page=page))
        executor._page = page
        assert [t.title for t in executor.get_tasks()] == ["Ok"]

    def test_a_selector_timeout_gives_an_empty_list(self):
        page = SimpleNamespace(
            wait_for_selector=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("timeout")),
            query_selector_all=lambda sel: [],
        )
        executor = GleamExecutor(_Drv(page=page))
        executor._page = page
        assert executor.get_tasks() == []


class _Broken:
    def query_selector(self, selector):
        raise RuntimeError("detached")


class TestCompleteTask:
    def test_no_page_is_false(self):
        from web3_agent_kit.airdrop.executor.gleam_exec import GleamTaskEntry, GleamTaskType

        task = GleamTaskEntry(entry_id="1", task_type=GleamTaskType.VISIT_URL, title="t")
        assert GleamExecutor(_Drv()).complete_task(task) is False

    def test_an_already_completed_task_is_true_without_work(self, monkeypatch):
        from web3_agent_kit.airdrop.executor.gleam_exec import GleamTaskEntry, GleamTaskType

        executor = GleamExecutor(_Drv())
        executor._page = object()
        called = []
        monkeypatch.setattr(executor, "_handle_visit_url", lambda t: called.append(1))
        task = GleamTaskEntry(
            entry_id="1", task_type=GleamTaskType.VISIT_URL, title="t", is_completed=True
        )
        assert executor.complete_task(task) is True
        assert called == []

    def test_the_matching_handler_runs_and_marks_the_task(self, monkeypatch):
        from web3_agent_kit.airdrop.executor.gleam_exec import GleamTaskEntry, GleamTaskType

        executor = GleamExecutor(_Drv())
        executor._page = object()
        monkeypatch.setattr(executor, "_handle_visit_url", lambda t: True)
        task = GleamTaskEntry(entry_id="1", task_type=GleamTaskType.VISIT_URL, title="t")
        assert executor.complete_task(task) is True
        assert task.is_completed is True

    def test_a_handler_failure_leaves_the_task_open(self, monkeypatch):
        from web3_agent_kit.airdrop.executor.gleam_exec import GleamTaskEntry, GleamTaskType

        executor = GleamExecutor(_Drv())
        executor._page = object()
        monkeypatch.setattr(executor, "_handle_visit_url", lambda t: False)
        task = GleamTaskEntry(entry_id="1", task_type=GleamTaskType.VISIT_URL, title="t")
        assert executor.complete_task(task) is False
        assert task.is_completed is False

    def test_a_throwing_handler_is_false(self, monkeypatch):
        from web3_agent_kit.airdrop.executor.gleam_exec import GleamTaskEntry, GleamTaskType

        executor = GleamExecutor(_Drv())
        executor._page = object()

        def boom(t):
            raise RuntimeError("nope")

        monkeypatch.setattr(executor, "_handle_visit_url", boom)
        task = GleamTaskEntry(entry_id="1", task_type=GleamTaskType.VISIT_URL, title="t")
        assert executor.complete_task(task) is False


class TestDelay:
    def test_delay_sits_inside_the_configured_window(self, monkeypatch):
        slept = []
        monkeypatch.setattr(
            "web3_agent_kit.airdrop.executor.gleam_exec.time.sleep", lambda s: slept.append(s)
        )
        GleamExecutor(_Drv())._random_delay()
        assert len(slept) == 1
        lo, hi = GleamExecutor.TASK_DELAY_MIN, GleamExecutor.TASK_DELAY_MAX
        assert lo <= slept[0] <= hi


class _ClickDrv:
    """Browser whose click result is scriptable per selector."""

    def __init__(self, results=None, context=None, navigate=True, new_page=None):
        self.results = results or {}
        self._context = context
        self._navigate = navigate
        self._new_page = new_page or SimpleNamespace(close=lambda: None)
        self.clicks = []
        self.pages_created = 0

    def new_page(self):
        self.pages_created += 1
        return self._new_page

    def navigate_with_retry(self, page, url, timeout=None):
        return self._navigate

    def click_with_retry(self, page, selector, timeout=None):
        self.clicks.append(selector)
        return self.results.get(selector, False)


def _entry(**kwargs):
    from web3_agent_kit.airdrop.executor.gleam_exec import GleamTaskEntry, GleamTaskType

    data = {"entry_id": "1", "task_type": GleamTaskType.VISIT_URL, "title": "t", **kwargs}
    return GleamTaskEntry(**data)


class TestVisitHandler:
    def test_a_url_opens_and_closes_a_tab(self, monkeypatch):
        monkeypatch.setattr(
            "web3_agent_kit.airdrop.executor.gleam_exec.time.sleep", lambda _s: None
        )
        closed = []
        page = SimpleNamespace(close=lambda: closed.append(1))
        driver = _ClickDrv(new_page=page)
        executor = GleamExecutor(driver)
        assert executor._handle_visit_url(_entry(url="https://example.com")) is True
        assert closed == [1]

    def test_a_failed_navigation_still_closes_the_tab(self, monkeypatch):
        # The close lives in a finally: a raising navigation used to orphan it.
        monkeypatch.setattr(
            "web3_agent_kit.airdrop.executor.gleam_exec.time.sleep", lambda _s: None
        )
        closed = []
        page = SimpleNamespace(close=lambda: closed.append(1))
        driver = _ClickDrv(new_page=page, navigate=False)
        executor = GleamExecutor(driver)
        assert executor._handle_visit_url(_entry(url="https://example.com")) is False
        assert closed == [1]

    def test_a_throwing_navigation_still_closes_the_tab(self, monkeypatch):
        monkeypatch.setattr(
            "web3_agent_kit.airdrop.executor.gleam_exec.time.sleep", lambda _s: None
        )
        closed = []
        page = SimpleNamespace(close=lambda: closed.append(1))
        driver = _ClickDrv(new_page=page)

        def boom(*a, **k):
            raise RuntimeError("crash")

        driver.navigate_with_retry = boom
        executor = GleamExecutor(driver)
        assert executor._handle_visit_url(_entry(url="https://example.com")) is False
        assert closed == [1]

    def test_without_a_url_the_widget_action_is_clicked(self, monkeypatch):
        driver = _ClickDrv(results={"[data-entry-index='0'] a": True})
        executor = GleamExecutor(driver)
        executor._page = object()
        assert executor._handle_visit_url(_entry()) is True
        assert driver.pages_created == 0


class TestSocialPopup:
    def test_without_a_context_it_is_false(self):
        assert GleamExecutor(_ClickDrv())._handle_social_popup(_entry(), "twitter.com") is False

    def test_a_click_without_a_popup_still_counts(self, monkeypatch):
        # Documented optimism: the widget may track the click itself.
        monkeypatch.setattr(
            "web3_agent_kit.airdrop.executor.gleam_exec.time.sleep", lambda _s: None
        )
        context = SimpleNamespace(pages=[object()])
        executor = GleamExecutor(_ClickDrv(results={"#go": True}, context=context))
        executor._page = object()
        assert executor._handle_social_popup(_entry(selector="#go"), "twitter.com") is True

    def test_a_failed_click_is_false(self, monkeypatch):
        monkeypatch.setattr(
            "web3_agent_kit.airdrop.executor.gleam_exec.time.sleep", lambda _s: None
        )
        context = SimpleNamespace(pages=[object()])
        executor = GleamExecutor(_ClickDrv(context=context))
        executor._page = object()
        assert executor._handle_social_popup(_entry(selector="#go"), "twitter.com") is False

    def test_a_matching_popup_is_closed_and_counted(self, monkeypatch):
        monkeypatch.setattr(
            "web3_agent_kit.airdrop.executor.gleam_exec.time.sleep", lambda _s: None
        )
        closed = []
        popup = SimpleNamespace(
            wait_for_load_state=lambda *a, **k: None,
            url="https://twitter.com/intent/follow",
            close=lambda: closed.append(1),
        )
        context = SimpleNamespace(pages=[object(), popup])
        executor = GleamExecutor(_ClickDrv(results={"#go": True}, context=context))
        executor._page = object()
        assert executor._handle_social_popup(_entry(selector="#go"), "twitter.com") is True
        assert closed == [1]

    def test_an_unrelated_popup_is_closed_and_the_click_still_counts(self, monkeypatch):
        monkeypatch.setattr(
            "web3_agent_kit.airdrop.executor.gleam_exec.time.sleep", lambda _s: None
        )
        closed = []
        popup = SimpleNamespace(
            wait_for_load_state=lambda *a, **k: None,
            url="https://elsewhere.example",
            close=lambda: closed.append(1),
        )
        context = SimpleNamespace(pages=[object(), popup])
        executor = GleamExecutor(_ClickDrv(results={"#go": True}, context=context))
        executor._page = object()
        assert executor._handle_social_popup(_entry(selector="#go"), "twitter.com") is True
        assert closed == [1]

    def test_a_popup_that_never_loads_is_closed_anyway(self, monkeypatch):
        monkeypatch.setattr(
            "web3_agent_kit.airdrop.executor.gleam_exec.time.sleep", lambda _s: None
        )
        closed = []
        popup = SimpleNamespace(
            wait_for_load_state=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stuck")),
            url="",
            close=lambda: closed.append(1),
        )
        context = SimpleNamespace(pages=[object(), popup])
        executor = GleamExecutor(_ClickDrv(results={"#go": True}, context=context))
        executor._page = object()
        assert executor._handle_social_popup(_entry(selector="#go"), "twitter.com") is True
        assert closed == [1]


class TestClickEntryAction:
    def test_no_page_is_false(self):
        assert GleamExecutor(_ClickDrv())._click_entry_action(_entry(selector="#a")) is False

    def test_the_task_selector_is_tried_first(self):
        driver = _ClickDrv(results={"#a": True})
        executor = GleamExecutor(driver)
        executor._page = object()
        assert executor._click_entry_action(_entry(selector="#a")) is True
        assert driver.clicks == ["#a"]

    def test_the_indexed_selectors_are_tried_next(self):
        driver = _ClickDrv(results={"[data-entry-index='0'] a": True})
        executor = GleamExecutor(driver)
        executor._page = object()
        assert executor._click_entry_action(_entry()) is True

    def test_the_link_scan_is_the_last_resort(self):
        link = SimpleNamespace(get_attribute=lambda n: "https://x.example", click=lambda: None)
        entry_el = SimpleNamespace(query_selector_all=lambda sel: [link])
        page = SimpleNamespace(query_selector_all=lambda sel: [entry_el])
        executor = GleamExecutor(_ClickDrv())
        executor._page = page
        assert executor._click_entry_action(_entry()) is True

    def test_a_first_element_is_clicked_when_it_has_no_real_href(self):
        clicked = []
        link = SimpleNamespace(get_attribute=lambda n: "#", click=lambda: clicked.append(1))
        entry_el = SimpleNamespace(query_selector_all=lambda sel: [link])
        page = SimpleNamespace(query_selector_all=lambda sel: [entry_el])
        executor = GleamExecutor(_ClickDrv())
        executor._page = page
        assert executor._click_entry_action(_entry()) is True
        assert clicked == [1]
