"""Twitter executor behaviour against a fake page.

Each action is a selector hunt with a click, and the interesting cases are the
ones that decide whether a click happens at all: an already-following account
whose button says "Unfollow", a failed navigation, a missing button, and a
browser that hands back no page.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from web3_agent_kit.airdrop.executor.social_exec import SocialExecutorConfig, TwitterExecutor

USER = "defi_project"
TWEET = "https://x.com/user/status/1"


class _Btn:
    def __init__(self, text="Follow", fail=False):
        self._text = text
        self._fail = fail
        self.clicked = 0

    def inner_text(self):
        return self._text

    def click(self):
        if self._fail:
            raise RuntimeError("click failed")
        self.clicked += 1


class _Textarea:
    def __init__(self):
        self.filled = None
        self.clicked = 0

    def click(self):
        self.clicked += 1

    def fill(self, text):
        self.filled = text


class _Page:
    def __init__(self, selectors=None, logged_in=False):
        self._selectors = selectors or {}
        self._logged_in = logged_in
        self.closed = False
        self.context = SimpleNamespace(cookies=lambda: [{"name": "auth", "value": "1"}])

    def query_selector(self, selector):
        if self._logged_in and selector in (
            '[data-testid="SideNav_NewTweet_Button"]',
            '[data-testid="AppTabBar_Home_Link"]',
            'a[href="/home"]',
        ):
            return object()
        return self._selectors.get(selector)

    def close(self):
        self.closed = True


class _Browser:
    def __init__(self, page, navigate=True, session_dir: Path | None = None):
        self.page = page
        self._navigate = navigate
        self._session_dir = session_dir
        self.navigated = []
        self.added_cookies = []

    def new_page(self):
        return self.page

    def navigate_with_retry(self, page, url):
        self.navigated.append(url)
        return self._navigate

    def get_session_path(self, platform=""):
        path = self._session_dir / platform
        path.mkdir(parents=True, exist_ok=True)
        return path

    def add_cookies(self, cookies):
        self.added_cookies.extend(cookies)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("web3_agent_kit.airdrop.executor.social_exec.time.sleep", lambda _s: None)


def _executor(page=None, **kwargs) -> tuple[TwitterExecutor, _Browser]:
    browser = _Browser(page or _Page(), **kwargs)
    return TwitterExecutor(browser), browser


class TestRequirePage:
    def test_page_is_created_lazily(self):
        executor, browser = _executor()
        assert executor._require_page() is browser.page

    def test_a_browser_that_returns_nothing_raises(self):
        executor, _ = _executor()
        executor.browser.new_page = lambda: None
        with pytest.raises(RuntimeError, match="did not create a page"):
            executor._require_page()


class TestFollow:
    def test_follow_clicks_the_button(self):
        btn = _Btn("Follow")
        executor, browser = _executor(_Page({'button[data-testid*="follow"]': btn}))
        assert executor.follow(USER) is True
        assert btn.clicked == 1
        assert browser.navigated == [f"https://x.com/{USER}"]

    def test_already_following_is_not_clicked_again(self):
        btn = _Btn("Unfollow")
        executor, _ = _executor(_Page({'button[data-testid*="follow"]': btn}))
        assert executor.follow(USER) is False
        assert btn.clicked == 0

    def test_missing_button_reports_false(self):
        executor, _ = _executor()
        assert executor.follow(USER) is False

    def test_failed_navigation_short_circuits(self):
        btn = _Btn("Follow")
        executor, _ = _executor(_Page({'button[data-testid*="follow"]': btn}), navigate=False)
        assert executor.follow(USER) is False
        assert btn.clicked == 0

    def test_a_throwing_button_is_skipped(self):
        executor, _ = _executor(_Page({'button[data-testid*="follow"]': _Btn(fail=True)}))
        assert executor.follow(USER) is False


class TestRetweet:
    def test_retweet_clicks_and_confirms(self):
        rt, confirm = _Btn(), _Btn()
        executor, _ = _executor(
            _Page(
                {
                    '[data-testid="retweet"]': rt,
                    '[data-testid="retweetConfirm"], [role="menuitem"]': confirm,
                }
            )
        )
        assert executor.retweet(TWEET) is True
        assert rt.clicked == 1
        assert confirm.clicked == 1

    def test_retweet_without_a_confirm_dialog_still_succeeds(self):
        executor, _ = _executor(_Page({'[data-testid="retweet"]': _Btn()}))
        assert executor.retweet(TWEET) is True

    def test_missing_retweet_button(self):
        executor, _ = _executor()
        assert executor.retweet(TWEET) is False


class TestLike:
    def test_like_clicks(self):
        btn = _Btn()
        executor, _ = _executor(_Page({'[data-testid="like"]': btn}))
        assert executor.like(TWEET) is True
        assert btn.clicked == 1

    def test_missing_like_button(self):
        executor, _ = _executor()
        assert executor.like(TWEET) is False


class TestTweet:
    def test_tweet_fills_and_posts(self):
        box, post = _Textarea(), _Btn()
        executor, browser = _executor(
            _Page(
                {
                    '[data-testid="tweetTextarea_0"]': box,
                    '[data-testid="tweetButton"], button[data-testid="tweetButtonInline"]': post,
                }
            )
        )
        assert executor.tweet("hello") is True
        assert box.filled == "hello"
        assert post.clicked == 1
        assert browser.navigated == ["https://x.com"]

    def test_text_without_a_post_button_is_not_reported_as_posted(self):
        executor, _ = _executor(_Page({'[data-testid="tweetTextarea_0"]': _Textarea()}))
        assert executor.tweet("hello") is False

    def test_no_compose_box(self):
        executor, _ = _executor()
        assert executor.tweet("hello") is False


class TestComment:
    def test_reply_fills_and_posts(self):
        box, post = _Textarea(), _Btn()
        executor, _ = _executor(
            _Page({'[data-testid="tweetTextarea_0"]': box, '[data-testid="tweetButton"]': post})
        )
        assert executor.comment(TWEET, "nice") is True
        assert box.filled == "nice"
        assert post.clicked == 1

    def test_reply_without_button(self):
        executor, _ = _executor(_Page({'[data-testid="tweetTextarea_0"]': _Textarea()}))
        assert executor.comment(TWEET, "nice") is False


class TestLogin:
    def test_only_twitter_and_x_cookies_are_loaded(self, tmp_path):
        session = tmp_path / "twitter"
        session.mkdir()
        (session / "cookies.json").write_text(
            json.dumps(
                [
                    {"name": "a", "domain": ".twitter.com"},
                    {"name": "b", "domain": ".x.com"},
                    {"name": "c", "domain": ".discord.com"},
                ]
            )
        )
        executor, browser = _executor(_Page(logged_in=True), session_dir=tmp_path)
        assert executor.login_with_cookies() is True
        assert [c["name"] for c in browser.added_cookies] == ["a", "b"]

    def test_unreadable_cookie_file_does_not_abort_the_login(self, tmp_path):
        session = tmp_path / "twitter"
        session.mkdir()
        (session / "cookies.json").write_text("{not json")
        executor, browser = _executor(_Page(logged_in=True), session_dir=tmp_path)
        assert executor.login_with_cookies() is True
        assert browser.added_cookies == []

    def test_not_logged_in_is_reported(self, tmp_path):
        executor, _ = _executor(_Page(logged_in=False), session_dir=tmp_path)
        assert executor.login_with_cookies() is False
        assert executor._logged_in is False

    def test_failed_navigation_reports_false(self, tmp_path):
        executor, _ = _executor(_Page(logged_in=True), navigate=False, session_dir=tmp_path)
        assert executor.login_with_cookies() is False


class TestSession:
    def test_save_writes_the_cookie_file(self, tmp_path):
        page = _Page()
        executor, _ = _executor(page, session_dir=tmp_path)
        executor._page = page
        executor.save_session()
        saved = json.loads((tmp_path / "twitter" / "cookies.json").read_text())
        assert saved == [{"name": "auth", "value": "1"}]

    def test_save_is_skipped_without_a_page(self, tmp_path):
        executor, _ = _executor(session_dir=tmp_path)
        executor.save_session()
        assert not (tmp_path / "twitter" / "cookies.json").exists()

    def test_save_is_skipped_when_disabled(self, tmp_path):
        executor, _ = _executor(_Page(), session_dir=tmp_path)
        executor.config = SocialExecutorConfig(save_cookies=False)
        executor.save_session()
        assert not (tmp_path / "twitter" / "cookies.json").exists()

    def test_close_saves_and_closes(self, tmp_path):
        page = _Page()
        executor, _ = _executor(page, session_dir=tmp_path)
        executor._page = page
        executor.close()
        assert page.closed is True
        assert (tmp_path / "twitter" / "cookies.json").exists()

    def test_close_without_a_page_is_safe(self):
        executor, _ = _executor()
        executor.close()


class TestDiscordJoin:
    def _executor(self, page, navigate=True):
        from web3_agent_kit.airdrop.executor.social_exec import DiscordExecutor

        browser = _Browser(page, navigate=navigate)
        return DiscordExecutor(browser), browser

    def test_discord_gg_invite_is_normalised(self):
        btn = _Btn("Accept Invite")
        executor, browser = self._executor(_Page({'button:has-text("Accept Invite")': btn}))
        assert executor.join_server("https://discord.gg/abc?event=1") is True
        assert browser.navigated == ["https://discord.com/invite/abc"]
        assert btn.clicked == 1

    def test_missing_accept_button(self):
        executor, _ = self._executor(_Page())
        assert executor.join_server("https://discord.gg/abc") is False

    def test_failed_navigation(self):
        executor, _ = self._executor(_Page(), navigate=False)
        assert executor.join_server("https://discord.gg/abc") is False


class TestTelegramJoin:
    def _executor(self, page, navigate=True):
        from web3_agent_kit.airdrop.executor.social_exec import TelegramExecutor

        browser = _Browser(page, navigate=navigate)
        return TelegramExecutor(browser), browser

    def test_bare_handle_becomes_a_tme_url(self):
        btn = _Btn("Join Channel")
        executor, browser = self._executor(_Page({'button:has-text("Join")': btn}))
        assert executor.join_channel("@channel") is True
        assert browser.navigated == ["https://t.me/channel"]

    def test_button_without_join_text_is_not_clicked_but_the_visit_counts(self):
        # join_channel treats a reached page as success even with no join
        # button; the caller cannot tell joined from merely opened.
        btn = _Btn("Preview")
        executor, _ = self._executor(_Page({'button:has-text("Join")': btn}))
        assert executor.join_channel("https://t.me/channel") is True
        assert btn.clicked == 0

    def test_open_in_web_link_is_clicked(self):
        link = _Btn()
        executor, _ = self._executor(_Page({'a:has-text("Open in Web")': link}))
        assert executor.join_channel("https://t.me/channel") is True
        assert link.clicked == 1

    def test_failed_navigation(self):
        executor, _ = self._executor(_Page(), navigate=False)
        assert executor.join_channel("https://t.me/channel") is False
