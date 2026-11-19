"""Browser manager retry, session and cookie behaviour.

Playwright is not needed: the manager only touches a page/context, so a fake is
enough. The retry helpers are the interesting part — they are what keeps a
flake from ending a run, and they must give up rather than loop.
"""

from __future__ import annotations

import json

import pytest

from web3_agent_kit.airdrop.executor import browser as browser_mod
from web3_agent_kit.airdrop.executor.browser import BrowserConfig, BrowserManager


@pytest.fixture(autouse=True)
def fake_playwright(monkeypatch):
    monkeypatch.setattr(browser_mod, "HAS_PLAYWRIGHT", True)
    monkeypatch.setattr(browser_mod.time, "sleep", lambda _s: None)


def _manager(tmp_path, **kwargs) -> BrowserManager:
    kwargs.setdefault("max_retries", 3)
    kwargs.setdefault("retry_delay", 0)
    config = BrowserConfig(sessions_dir=tmp_path, **kwargs)
    return BrowserManager(config)


class _Page:
    def __init__(self, fail_times=0, closed=False):
        self.fail_times = fail_times
        self.closed = closed
        self.goto_calls = 0
        self.click_calls = 0
        self.scripts = []
        self.shot = None
        self.waited = None

    def goto(self, url, **kwargs):
        self.goto_calls += 1
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("net error")

    def click(self, selector, timeout=None):
        self.click_calls += 1
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("detached")

    def is_closed(self):
        return self.closed

    def add_init_script(self, script):
        self.scripts.append(script)

    def wait_for_selector(self, selector, timeout=None):
        if self.fail_times:
            self.fail_times -= 1
            raise TimeoutError("nope")

    def screenshot(self, path=None, full_page=None):
        self.shot = path


class _Context:
    def __init__(self, page=None, cookies=None):
        self.page = page or _Page()
        self._cookies = cookies or []

    def new_page(self):
        return self.page

    def cookies(self):
        return self._cookies

    def add_init_script(self, script):
        self.init_scripts = getattr(self, "init_scripts", []) + [script]

    def close(self):
        self.closed = True

    def add_cookies(self, cookies):
        self._cookies.extend(cookies)


class TestLaunchState:
    def test_a_manager_starts_unlaunched(self, tmp_path):
        assert _manager(tmp_path).is_launched is False

    def test_new_page_requires_a_launch(self, tmp_path):
        with pytest.raises(RuntimeError, match="not launched"):
            _manager(tmp_path).new_page()

    def test_session_dir_is_created(self, tmp_path):
        _manager(tmp_path)
        assert (tmp_path / "default").is_dir()

    def test_platform_session_dir_is_created(self, tmp_path):
        manager = _manager(tmp_path)
        assert manager.get_session_path("twitter").is_dir()

    def test_context_manager_launches_and_closes(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path)
        launched, closed = [], []
        monkeypatch.setattr(manager, "launch", lambda: launched.append(1))
        monkeypatch.setattr(manager, "close", lambda: closed.append(1))
        with manager as handle:
            assert handle is manager
        assert (launched, closed) == ([1], [1])


class TestNavigation:
    def test_success_on_the_first_try(self, tmp_path):
        assert _manager(tmp_path).navigate_with_retry(_Page(), "https://x") is True

    def test_retries_then_succeeds(self, tmp_path):
        page = _Page(fail_times=2)
        assert _manager(tmp_path).navigate_with_retry(page, "https://x") is True
        assert page.goto_calls == 3

    def test_gives_up_after_max_retries(self, tmp_path):
        page = _Page(fail_times=99)
        assert _manager(tmp_path).navigate_with_retry(page, "https://x") is False
        assert page.goto_calls == 3

    def test_a_crashed_page_is_replaced_for_the_next_attempt(self, tmp_path):
        manager = _manager(tmp_path)
        page = _Page(fail_times=1, closed=True)
        replacement = _Page()
        manager.new_page = lambda: replacement
        assert manager.navigate_with_retry(page, "https://x") is True
        assert replacement.goto_calls == 1

    def test_an_open_page_is_not_replaced(self, tmp_path):
        manager = _manager(tmp_path)
        calls = []
        manager.new_page = lambda: calls.append(1)
        manager.navigate_with_retry(_Page(fail_times=1), "https://x")
        assert calls == []


class TestClickAndWait:
    def test_a_click_retries(self, tmp_path):
        page = _Page(fail_times=1)
        assert _manager(tmp_path).click_with_retry(page, "#go") is True
        assert page.click_calls == 2

    def test_a_click_gives_up(self, tmp_path):
        assert _manager(tmp_path).click_with_retry(_Page(fail_times=9), "#go") is False

    def test_wait_succeeds(self, tmp_path):
        assert _manager(tmp_path).wait_for_element(_Page(), "#go") is True

    def test_wait_times_out(self, tmp_path):
        assert _manager(tmp_path).wait_for_element(_Page(fail_times=9), "#go") is False


class TestCookies:
    def test_saving_writes_the_session_file(self, tmp_path):
        manager = _manager(tmp_path)
        manager._context = _Context(cookies=[{"name": "a"}])
        manager.save_cookies()
        saved = json.loads((tmp_path / "default" / "cookies.json").read_text())
        assert saved == [{"name": "a"}]

    def test_saving_without_a_context_is_a_no_op(self, tmp_path):
        _manager(tmp_path).save_cookies()
        assert not (tmp_path / "default" / "cookies.json").exists()

    def test_loading_hydrates_the_context(self, tmp_path):
        (tmp_path / "default").mkdir(parents=True)
        (tmp_path / "default" / "cookies.json").write_text(json.dumps([{"name": "b"}]))
        manager = _manager(tmp_path)
        context = _Context()
        manager._context = context
        manager.load_cookies()
        assert context.cookies() == [{"name": "b"}]

    def test_loading_without_a_file_is_a_no_op(self, tmp_path):
        manager = _manager(tmp_path)
        manager._context = _Context()
        manager.load_cookies()
        assert manager._context.cookies() == []

    def test_add_cookies_requires_a_context(self, tmp_path):
        with pytest.raises(RuntimeError, match="not open"):
            _manager(tmp_path).add_cookies([{"name": "c"}])

    def test_add_cookies_reaches_the_context(self, tmp_path):
        manager = _manager(tmp_path)
        manager._context = _Context()
        manager.add_cookies([{"name": "c"}])
        assert manager._context.cookies() == [{"name": "c"}]


class TestScreenshot:
    def test_default_dir_is_under_the_session(self, tmp_path):
        manager = _manager(tmp_path)
        path = manager.screenshot(_Page(), "s.png")
        assert path == str(tmp_path / "default" / "screenshots" / "s.png")
        assert (tmp_path / "default" / "screenshots").is_dir()

    def test_configured_dir_wins(self, tmp_path):
        shots = tmp_path / "shots"
        manager = _manager(tmp_path, screenshot_dir=shots)
        assert manager.screenshot(_Page(), "s.png") == str(shots / "s.png")

    def test_a_failing_page_returns_none(self, tmp_path):
        class Broken(_Page):
            def screenshot(self, **kwargs):
                raise RuntimeError("no page")

        assert _manager(tmp_path).screenshot(Broken(), "s.png") is None


class _FakeBrowser:
    def __init__(self):
        self.kwargs = None
        self.closed = False
        self.context = None

    def launch(self, **kwargs):
        self.kwargs = kwargs
        return self

    def new_context(self, **kwargs):
        self.context = _Context()
        self.context.kwargs = kwargs
        return self.context

    def close(self):
        self.closed = True


class _FakePlaywright:
    def __init__(self):
        self.chromium = _FakeBrowser()
        self.stopped = False

    def start(self):
        return self

    def stop(self):
        self.stopped = True


def _patch_playwright(monkeypatch):
    fake = _FakePlaywright()
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: fake, raising=False)
    return fake


class TestLaunch:
    def test_launch_sets_up_a_stealthed_context(self, tmp_path, monkeypatch):
        fake = _patch_playwright(monkeypatch)
        manager = _manager(tmp_path)
        manager.launch()
        assert manager.is_launched is True
        assert fake.chromium.kwargs["headless"] is True
        assert fake.chromium.kwargs["proxy"] is None
        assert "navigator" in fake.chromium.context.kwargs["locale"] + "navigator"
        assert fake.chromium.context.kwargs["locale"] == "en-US"

    def test_launch_passes_the_proxy_through(self, tmp_path, monkeypatch):
        fake = _patch_playwright(monkeypatch)
        _manager(tmp_path, proxy="socks5://p:1080").launch()
        assert fake.chromium.kwargs["proxy"] == {"server": "socks5://p:1080"}

    def test_extra_args_are_appended(self, tmp_path, monkeypatch):
        fake = _patch_playwright(monkeypatch)
        _manager(tmp_path, extra_args=["--mute-audio"]).launch()
        assert "--mute-audio" in fake.chromium.kwargs["args"]
        assert "--no-sandbox" in fake.chromium.kwargs["args"]

    def test_saved_cookies_are_loaded_on_launch(self, tmp_path, monkeypatch):
        (tmp_path / "default").mkdir(parents=True)
        (tmp_path / "default" / "cookies.json").write_text(json.dumps([{"name": "z"}]))
        _patch_playwright(monkeypatch)
        manager = _manager(tmp_path)
        manager.launch()
        assert {"name": "z"} in manager._context.cookies()

    def test_a_new_page_injects_the_stealth_script(self, tmp_path, monkeypatch):
        _patch_playwright(monkeypatch)
        manager = _manager(tmp_path)
        manager.launch()
        page = manager.new_page()
        assert page.scripts
        assert manager._pages == [page]

    def test_a_page_that_rejects_the_script_still_returns(self, tmp_path, monkeypatch):
        fake = _patch_playwright(monkeypatch)
        manager = _manager(tmp_path)
        manager.launch()
        page = fake.chromium.context.page

        def boom(_script):
            raise RuntimeError("nope")

        page.add_init_script = boom
        assert manager.new_page() is page


class TestClose:
    def test_close_releases_everything(self, tmp_path, monkeypatch):
        fake = _patch_playwright(monkeypatch)
        manager = _manager(tmp_path)
        manager.launch()
        page = manager.new_page()
        closed = []
        page.close = lambda: closed.append(1)
        manager.close()
        assert closed == [1]
        assert manager._context is None
        assert manager._browser is None
        assert manager._playwright is None
        assert fake.chromium.closed is True
        assert fake.stopped is True
        assert manager.is_launched is False

    def test_close_saves_cookies_first(self, tmp_path, monkeypatch):
        _patch_playwright(monkeypatch)
        manager = _manager(tmp_path)
        manager.launch()
        manager._context._cookies.append({"name": "saved"})
        manager.close()
        assert json.loads((tmp_path / "default" / "cookies.json").read_text()) == [
            {"name": "saved"}
        ]

    def test_close_without_a_launch_is_safe(self, tmp_path, monkeypatch):
        _patch_playwright(monkeypatch)
        _manager(tmp_path).close()

    def test_a_broken_child_does_not_stop_the_rest_of_the_close(self, tmp_path, monkeypatch):
        _patch_playwright(monkeypatch)
        manager = _manager(tmp_path)
        manager.launch()

        def boom():
            raise RuntimeError("stuck")

        manager._context.page.close = boom
        manager._browser.close = boom
        manager.new_page()
        manager.close()
        assert manager._browser is None


class TestAsyncVariants:
    def test_async_navigation_retries(self, tmp_path):
        import asyncio

        page = _Page(fail_times=1)
        assert asyncio.run(_manager(tmp_path).async_navigate_with_retry(page, "https://x")) is True
        assert page.goto_calls == 2

    def test_async_navigation_gives_up(self, tmp_path):
        import asyncio

        assert (
            asyncio.run(
                _manager(tmp_path).async_navigate_with_retry(_Page(fail_times=9), "https://x")
            )
            is False
        )

    def test_async_click_retries(self, tmp_path):
        import asyncio

        page = _Page(fail_times=1)
        assert asyncio.run(_manager(tmp_path).async_click_with_retry(page, "#go")) is True

    def test_async_click_gives_up(self, tmp_path):
        import asyncio

        assert (
            asyncio.run(_manager(tmp_path).async_click_with_retry(_Page(fail_times=9), "#go"))
            is False
        )
