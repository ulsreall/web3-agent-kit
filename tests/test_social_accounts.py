"""Account handling for all three platforms: cookie load/save and login probes.

The cookie writer is shared, so a truncated write would take out every platform
at once. These tests pin the atomic path and the domain filtering that keeps a
platform from loading another's cookies.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from web3_agent_kit.airdrop.executor import social_exec
from web3_agent_kit.airdrop.executor.social_exec import (
    DiscordExecutor,
    TelegramExecutor,
    TwitterExecutor,
    write_cookies,
)


class _Page:
    def __init__(self, cookies=None, selectors=None):
        self.context = SimpleNamespace(cookies=lambda: cookies or [])
        self._selectors = selectors or {}
        self.closed = False

    def query_selector(self, selector):
        return self._selectors.get(selector)

    def close(self):
        self.closed = True


class _Browser:
    def __init__(self, page=None, session_dir=None, navigate=True):
        self.page = page or _Page()
        self._session_dir = session_dir or Path("/tmp/none")
        self._navigate = navigate
        self.added = []

    def new_page(self):
        return self.page

    def navigate_with_retry(self, page, url):
        return self._navigate

    def get_session_path(self, platform=""):
        path = Path(self._session_dir) / platform
        path.mkdir(parents=True, exist_ok=True)
        return path

    def add_cookies(self, cookies):
        self.added.extend(cookies)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(social_exec.time, "sleep", lambda _s: None)


class TestWriteCookies:
    def test_the_file_is_written_and_replaced(self, tmp_path):
        target = tmp_path / "cookies.json"
        write_cookies(target, [{"name": "a"}])
        assert json.loads(target.read_text()) == [{"name": "a"}]

    def test_no_tmp_file_is_left_behind(self, tmp_path):
        target = tmp_path / "cookies.json"
        write_cookies(target, [])
        assert [p.name for p in tmp_path.iterdir()] == ["cookies.json"]

    def test_a_previous_file_survives_a_failed_write(self, tmp_path, monkeypatch):
        target = tmp_path / "cookies.json"
        write_cookies(target, [{"name": "old"}])

        def boom(*a, **k):
            raise RuntimeError("disk full")

        monkeypatch.setattr(social_exec.os, "replace", boom)
        with pytest.raises(RuntimeError):
            write_cookies(target, [{"name": "new"}])
        assert json.loads(target.read_text()) == [{"name": "old"}]


class TestCookieRoundTrip:
    @pytest.mark.parametrize(
        "cls,platform,keep,drop",
        [
            (TwitterExecutor, "twitter", "twitter.com", "discord.com"),
            (DiscordExecutor, "discord", "discord.com", "twitter.com"),
            (TelegramExecutor, "telegram", "telegram.org", "twitter.com"),
        ],
    )
    def test_only_own_domain_cookies_are_loaded(self, tmp_path, cls, platform, keep, drop):
        cookies = [{"domain": f".{keep}"}, {"domain": f".{drop}"}]
        (tmp_path / platform).mkdir()
        (tmp_path / platform / "cookies.json").write_text(json.dumps(cookies))

        browser = _Browser(session_dir=tmp_path)
        executor = cls.__new__(cls)
        executor.browser = browser
        executor.config = SimpleNamespace(save_cookies=True)
        executor._page = browser.page
        executor.login_with_cookies(platform)

        assert browser.added == [{"domain": f".{keep}"}]

    def test_an_unreadable_jar_is_a_warning_not_a_crash(self, tmp_path, caplog):
        (tmp_path / "twitter").mkdir()
        (tmp_path / "twitter" / "cookies.json").write_text("{not json")
        browser = _Browser(session_dir=tmp_path)
        executor = TwitterExecutor(browser)
        with caplog.at_level("WARNING"):
            executor.login_with_cookies("twitter")
        assert "cookie load failed" in caplog.text


class TestTwitterLogin:
    def test_a_successful_navigation_with_the_indicator_logs_in(self, tmp_path):
        page = _Page(selectors={'[data-testid="SideNav_NewTweet_Button"]': object()})
        executor = TwitterExecutor(_Browser(page, tmp_path))
        assert executor.login_with_cookies("twitter") is True
        assert executor._logged_in is True

    def test_a_navigation_failure_is_false(self, tmp_path):
        executor = TwitterExecutor(_Browser(session_dir=tmp_path, navigate=False))
        assert executor.login_with_cookies("twitter") is False

    def test_save_session_writes_the_jar(self, tmp_path):
        executor = TwitterExecutor(_Browser(_Page(), tmp_path))
        executor._page = _Page([{"name": "auth"}])
        executor.save_session()
        written = json.loads((tmp_path / "twitter" / "cookies.json").read_text())
        assert written == [{"name": "auth"}]

    def test_save_session_respects_the_config_flag(self, tmp_path):
        executor = TwitterExecutor(_Browser(_Page(), tmp_path))
        executor._page = _Page([{"name": "auth"}])
        executor.config.save_cookies = False
        executor.save_session()
        assert not (tmp_path / "twitter" / "cookies.json").exists()

    def test_save_session_without_a_page_does_nothing(self, tmp_path):
        executor = TwitterExecutor(_Browser(session_dir=tmp_path))
        executor.save_session()
        assert not (tmp_path / "twitter" / "cookies.json").exists()

    def test_close_saves_then_drops_the_page(self, tmp_path):
        executor = TwitterExecutor(_Browser(_Page(), tmp_path))
        page = _Page([{"name": "auth"}])
        executor._page = page
        executor.close()
        assert page.closed is True and executor._page is None


class TestDiscordSession:
    def test_close_saves_the_jar(self, tmp_path):
        executor = DiscordExecutor(_Browser(_Page(), tmp_path))
        executor._page = _Page([{"name": "d"}])
        executor.close()
        assert json.loads((tmp_path / "discord" / "cookies.json").read_text()) == [{"name": "d"}]

    def test_close_survives_a_throwing_page(self, tmp_path):
        executor = DiscordExecutor(_Browser(_Page(), tmp_path))
        page = _Page()

        def boom():
            raise RuntimeError("gone")

        page.close = boom
        executor._page = page
        executor.close()
        assert executor._page is None

    def test_login_status_needs_an_indicator(self):
        executor = DiscordExecutor(_Browser(_Page()))
        executor._page = _Page()
        assert executor._check_login_status() is False

    def test_login_status_is_true_with_the_sidebar(self):
        page = _Page(selectors={'nav[class*="guilds"]': object()})
        executor = DiscordExecutor(_Browser(page))
        executor._page = page
        assert executor._check_login_status() is True

    def test_a_throwing_probe_is_false(self):
        page = _Page()

        def boom(_s):
            raise RuntimeError("gone")

        page.query_selector = boom
        executor = DiscordExecutor(_Browser(page))
        executor._page = page
        assert executor._check_login_status() is False


class TestTelegramSession:
    def test_close_saves_the_jar(self, tmp_path):
        executor = TelegramExecutor(_Browser(_Page(), tmp_path))
        executor._page = _Page([{"name": "t"}])
        executor.close()
        assert json.loads((tmp_path / "telegram" / "cookies.json").read_text()) == [{"name": "t"}]

    def test_a_missing_jar_returns_false(self, tmp_path):
        executor = TelegramExecutor(_Browser(session_dir=tmp_path))
        assert executor.login_with_cookies("telegram") is False

    def test_a_jar_with_no_matching_domain_returns_false(self, tmp_path):
        (tmp_path / "telegram").mkdir()
        (tmp_path / "telegram" / "cookies.json").write_text(json.dumps([{"domain": ".x.com"}]))
        executor = TelegramExecutor(_Browser(session_dir=tmp_path))
        assert executor.login_with_cookies("telegram") is False


class _FakeManager:
    instance = None

    def __init__(self, config=None):
        self.config = config
        self.page = _Page([{"domain": ".x.com"}])
        self.navigated = []
        _FakeManager.instance = self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def new_page(self):
        return self.page

    def navigate_with_retry(self, page, url):
        self.navigated.append(url)
        return True

    def get_session_path(self, platform=""):
        from pathlib import Path

        path = Path(self._dir) / platform
        path.mkdir(parents=True, exist_ok=True)
        return path


@pytest.fixture
def fake_manager(monkeypatch, tmp_path):
    _FakeManager._dir = str(tmp_path)

    def _bs(config=None):
        return _FakeManager(config)

    monkeypatch.setattr(social_exec, "BrowserManager", _bs)
    monkeypatch.setattr("builtins.input", lambda: "")
    return tmp_path


@pytest.mark.parametrize(
    "cls,platform,headless",
    [(TwitterExecutor, "twitter", False), (DiscordExecutor, "discord", False)],
)
def test_interactive_login_saves_the_jar(fake_manager, cls, platform, headless):
    executor = cls.__new__(cls)
    executor.browser = _Browser()
    assert executor.interactive_login() is True
    assert _FakeManager.instance.config.headless is headless
    saved = json.loads((fake_manager / platform / "cookies.json").read_text())
    assert saved == [{"domain": ".x.com"}]


def test_telegram_interactive_login_opens_the_web_app(fake_manager):
    executor = TelegramExecutor.__new__(TelegramExecutor)
    executor.browser = _Browser()
    assert executor.interactive_login() is True
    assert _FakeManager.instance.navigated[0].endswith("/k/")
    assert json.loads((fake_manager / "telegram" / "cookies.json").read_text())


class _Btn:
    def __init__(self, text="Join", fail=False):
        self.text = text
        self.clicks = 0
        self._fail = fail

    def inner_text(self):
        return self.text

    def click(self):
        if self._fail:
            raise RuntimeError("gone")
        self.clicks += 1


class _UrlPage(_Page):
    def __init__(self, url="https://discord.com/channels/1", selectors=None, cookies=None):
        super().__init__(cookies=cookies, selectors=selectors)
        self.url = url


class TestDiscordJoin:
    def test_an_invite_slash_command_keeps_the_code(self):
        btn = _Btn()
        browser = _Browser(_Page(selectors={'button:has-text("Join")': btn}))
        executor = DiscordExecutor(browser)
        assert executor.join_server("https://discord.gg/abc?event=1") is True
        assert browser.page and btn.clicks == 1

    def test_the_invite_code_is_normalised(self):
        browser = _Browser(_Page(selectors={'button:has-text("Join")': _Btn()}))
        executor = DiscordExecutor(browser)
        seen = []
        browser.navigate_with_retry = lambda page, url: seen.append(url) or True
        executor.join_server("discord.gg/xyz")
        assert seen == ["https://discord.com/invite/xyz"]

    def test_a_navigation_failure_is_false(self):
        executor = DiscordExecutor(_Browser(_Page(), navigate=False))
        assert executor.join_server("https://discord.gg/abc") is False

    def test_no_button_is_false(self):
        executor = DiscordExecutor(_Browser(_Page()))
        assert executor.join_server("https://discord.gg/abc") is False

    def test_a_throwing_button_is_skipped(self):
        failing = _Btn(fail=True)
        working = _Btn()
        page = _Page(
            selectors={
                'button:has-text("Accept Invite")': failing,
                'button:has-text("Join")': working,
            }
        )
        executor = DiscordExecutor(_Browser(page))
        assert executor.join_server("https://discord.gg/abc") is True
        assert working.clicks == 1

    def test_a_throwing_page_is_false(self):
        executor = DiscordExecutor(_Browser(_Page()))

        def boom():
            raise RuntimeError("gone")

        executor._require_page = boom  # type: ignore[method-assign]
        assert executor.join_server("https://discord.gg/abc") is False


class TestDiscordVerify:
    def test_a_login_redirect_is_not_membership(self):
        page = _UrlPage(url="https://discord.com/login")
        executor = DiscordExecutor(_Browser(page))
        executor._page = page
        assert executor.verify_role("srv") is False

    def test_a_channel_url_is_membership(self):
        page = _UrlPage(url="https://discord.com/channels/srv")
        executor = DiscordExecutor(_Browser(page))
        executor._page = page
        assert executor.verify_role("srv") is True

    def test_a_navigation_failure_is_false(self):
        executor = DiscordExecutor(_Browser(_Page(), navigate=False))
        assert executor.verify_role("srv") is False
