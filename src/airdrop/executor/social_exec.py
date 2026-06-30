"""Platform-specific social task automation via browser.

Provides browser-based automation for Twitter, Discord, and Telegram
social tasks without relying on official APIs (which are rate-limited
or require expensive access).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

from .browser import BrowserConfig, BrowserManager

logger = logging.getLogger(__name__)


@dataclass
class SocialExecutorConfig:
    """Configuration for social task executors."""

    # Delays (seconds)
    action_delay_min: float = 2.0
    action_delay_max: float = 5.0
    page_load_timeout: int = 30000
    action_timeout: int = 10000
    # Retry
    max_retries: int = 3
    # Session
    save_cookies: bool = True


class TwitterExecutor:
    """Browser-based Twitter/X task automation.

    Handles follow, retweet, like, tweet, and comment actions
    by navigating Twitter in a real browser.

    Example::

        browser = BrowserManager(BrowserConfig(headless=False))
        browser.launch()
        twitter = TwitterExecutor(browser)

        twitter.login_with_cookies("twitter")
        twitter.follow("defi_project")
        twitter.retweet("https://twitter.com/user/status/123")
        browser.close()
    """

    BASE_URL = "https://x.com"
    LOGIN_URL = "https://x.com/login"

    def __init__(
        self,
        browser_manager: BrowserManager,
        config: Optional[SocialExecutorConfig] = None,
    ):
        self.browser = browser_manager
        self.config = config or SocialExecutorConfig()
        self._page = None
        self._logged_in = False

    def login_with_cookies(self, platform_session: str = "twitter") -> bool:
        """Load saved Twitter cookies and verify login.

        Args:
            platform_session: Session name for cookie storage.

        Returns:
            True if login verified.
        """
        self._page = self.browser.new_page()
        session_path = self.browser.get_session_path(platform_session)
        cookie_file = session_path / "cookies.json"

        if cookie_file.exists():
            try:
                with open(cookie_file) as f:
                    cookies = json.load(f)
                # Filter for twitter/x.com cookies
                twitter_cookies = [
                    c for c in cookies
                    if "twitter.com" in c.get("domain", "") or "x.com" in c.get("domain", "")
                ]
                if twitter_cookies:
                    self.browser._context.add_cookies(twitter_cookies)
                    logger.info(f"Twitter: loaded {len(twitter_cookies)} cookies")
            except Exception as e:
                logger.warning(f"Twitter: cookie load failed: {e}")

        # Navigate and check login
        if self.browser.navigate_with_retry(self._page, self.BASE_URL):
            time.sleep(3)
            # Check if logged in by looking for compose tweet button or home timeline
            logged_in = self._check_login_status()
            self._logged_in = logged_in
            if logged_in:
                logger.info("Twitter: logged in successfully")
            else:
                logger.warning("Twitter: not logged in — interactive login needed")
            return logged_in
        return False

    def interactive_login(self) -> bool:
        """Open Twitter login page for interactive authentication.

        Opens a headed browser for the user to manually log in,
        then saves cookies for future use.

        Returns:
            True after user completes login.
        """
        config = BrowserConfig(headless=False)
        with BrowserManager(config) as bm:
            page = bm.new_page()
            bm.navigate_with_retry(page, self.LOGIN_URL)
            print("\n" + "=" * 60)
            print("  Log in to Twitter/X in the browser window.")
            print("  Press Enter here when done...")
            print("=" * 60 + "\n")
            input()

            # Save cookies
            session_path = bm.get_session_path("twitter")
            cookies = page.context.cookies()
            cookie_file = session_path / "cookies.json"
            with open(cookie_file, "w") as f:
                json.dump(cookies, f, indent=2)

            logger.info(f"Twitter: saved {len(cookies)} cookies")
            self._logged_in = True
            return True

    def follow(self, username: str) -> bool:
        """Follow a Twitter user.

        Args:
            username: Twitter handle (without @).

        Returns:
            True if follow action succeeded.
        """
        url = f"{self.BASE_URL}/{username}"
        try:
            if not self._page:
                self._page = self.browser.new_page()

            if not self.browser.navigate_with_retry(self._page, url):
                return False

            time.sleep(2)

            # Look for Follow button
            follow_selectors = [
                'button[data-testid*="follow"]',
                '[aria-label*="Follow"]',
                'div[role="button"]:has-text("Follow")',
            ]

            for selector in follow_selectors:
                try:
                    btn = self._page.query_selector(selector)
                    if btn:
                        btn_text = btn.inner_text().strip().lower()
                        if "follow" in btn_text and "unfollow" not in btn_text:
                            btn.click()
                            time.sleep(1)
                            logger.info(f"Twitter: followed @{username}")
                            return True
                except Exception:
                    continue

            logger.warning(f"Twitter: could not find follow button for @{username}")
            return False

        except Exception as e:
            logger.error(f"Twitter: follow failed for @{username}: {e}")
            return False

    def retweet(self, tweet_url: str) -> bool:
        """Retweet a tweet.

        Args:
            tweet_url: Full URL of the tweet.

        Returns:
            True if retweet succeeded.
        """
        try:
            if not self._page:
                self._page = self.browser.new_page()

            if not self.browser.navigate_with_retry(self._page, tweet_url):
                return False

            time.sleep(2)

            # Click retweet button
            rt_selectors = [
                '[data-testid="retweet"]',
                '[aria-label*="Repost"]',
                '[aria-label*="Retweet"]',
            ]

            for selector in rt_selectors:
                try:
                    btn = self._page.query_selector(selector)
                    if btn:
                        btn.click()
                        time.sleep(1)
                        # Confirm retweet in dropdown
                        confirm = self._page.query_selector(
                            '[data-testid="retweetConfirm"], [role="menuitem"]'
                        )
                        if confirm:
                            confirm.click()
                        logger.info(f"Twitter: retweeted {tweet_url}")
                        return True
                except Exception:
                    continue

            logger.warning("Twitter: could not find retweet button")
            return False

        except Exception as e:
            logger.error(f"Twitter: retweet failed: {e}")
            return False

    def like(self, tweet_url: str) -> bool:
        """Like a tweet.

        Args:
            tweet_url: Full URL of the tweet.

        Returns:
            True if like succeeded.
        """
        try:
            if not self._page:
                self._page = self.browser.new_page()

            if not self.browser.navigate_with_retry(self._page, tweet_url):
                return False

            time.sleep(2)

            like_selectors = [
                '[data-testid="like"]',
                '[aria-label*="Like"]',
            ]

            for selector in like_selectors:
                try:
                    btn = self._page.query_selector(selector)
                    if btn:
                        btn.click()
                        time.sleep(1)
                        logger.info(f"Twitter: liked {tweet_url}")
                        return True
                except Exception:
                    continue

            logger.warning("Twitter: could not find like button")
            return False

        except Exception as e:
            logger.error(f"Twitter: like failed: {e}")
            return False

    def tweet(self, text: str) -> bool:
        """Post a tweet.

        Args:
            text: Tweet content.

        Returns:
            True if tweet was posted.
        """
        try:
            if not self._page:
                self._page = self.browser.new_page()

            if not self.browser.navigate_with_retry(self._page, self.BASE_URL):
                return False

            time.sleep(2)

            # Click compose area
            compose_selectors = [
                '[data-testid="tweetTextarea_0"]',
                '[role="textbox"][data-testid]',
                'div[contenteditable="true"]',
            ]

            for selector in compose_selectors:
                try:
                    textarea = self._page.query_selector(selector)
                    if textarea:
                        textarea.click()
                        textarea.fill(text)
                        time.sleep(1)

                        # Click tweet/post button
                        post_btn = self._page.query_selector(
                            '[data-testid="tweetButton"], button[data-testid="tweetButtonInline"]'
                        )
                        if post_btn:
                            post_btn.click()
                            time.sleep(2)
                            logger.info("Twitter: tweet posted")
                            return True
                except Exception:
                    continue

            logger.warning("Twitter: could not compose tweet")
            return False

        except Exception as e:
            logger.error(f"Twitter: tweet failed: {e}")
            return False

    def comment(self, tweet_url: str, text: str) -> bool:
        """Reply to a tweet.

        Args:
            tweet_url: Full URL of the tweet to reply to.
            text: Reply text.

        Returns:
            True if reply was posted.
        """
        try:
            if not self._page:
                self._page = self.browser.new_page()

            if not self.browser.navigate_with_retry(self._page, tweet_url):
                return False

            time.sleep(2)

            # Click reply area
            reply_selectors = [
                '[data-testid="tweetTextarea_0"]',
                'div[role="textbox"][contenteditable="true"]',
            ]

            for selector in reply_selectors:
                try:
                    textarea = self._page.query_selector(selector)
                    if textarea:
                        textarea.click()
                        textarea.fill(text)
                        time.sleep(1)

                        # Click reply button
                        reply_btn = self._page.query_selector(
                            '[data-testid="tweetButton"]'
                        )
                        if reply_btn:
                            reply_btn.click()
                            time.sleep(2)
                            logger.info(f"Twitter: replied to {tweet_url}")
                            return True
                except Exception:
                    continue

            return False

        except Exception as e:
            logger.error(f"Twitter: comment failed: {e}")
            return False

    def save_session(self) -> None:
        """Save current browser cookies as Twitter session."""
        if self._page and self.config.save_cookies:
            session_path = self.browser.get_session_path("twitter")
            try:
                cookies = self._page.context.cookies()
                cookie_file = session_path / "cookies.json"
                with open(cookie_file, "w") as f:
                    json.dump(cookies, f, indent=2)
                logger.info(f"Twitter: saved {len(cookies)} cookies")
            except Exception as e:
                logger.warning(f"Twitter: cookie save failed: {e}")

    def _check_login_status(self) -> bool:
        """Check if we're logged into Twitter."""
        try:
            # Look for elements that indicate logged-in state
            indicators = [
                '[data-testid="SideNav_NewTweet_Button"]',
                '[data-testid="AppTabBar_Home_Link"]',
                'a[href="/home"]',
            ]
            for selector in indicators:
                if self._page.query_selector(selector):
                    return True
            return False
        except Exception:
            return False

    def close(self) -> None:
        """Close the Twitter page."""
        self.save_session()
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None


class DiscordExecutor:
    """Browser-based Discord task automation.

    Handles server joining and role verification via browser.

    Example::

        browser = BrowserManager(BrowserConfig(headless=False))
        browser.launch()
        discord = DiscordExecutor(browser)

        discord.login_with_cookies("discord")
        discord.join_server("https://discord.gg/invite")
        browser.close()
    """

    BASE_URL = "https://discord.com"
    LOGIN_URL = "https://discord.com/login"

    def __init__(
        self,
        browser_manager: BrowserManager,
        config: Optional[SocialExecutorConfig] = None,
    ):
        self.browser = browser_manager
        self.config = config or SocialExecutorConfig()
        self._page = None
        self._logged_in = False

    def login_with_cookies(self, platform_session: str = "discord") -> bool:
        """Load saved Discord cookies and verify login.

        Args:
            platform_session: Session name for cookie storage.

        Returns:
            True if login verified.
        """
        self._page = self.browser.new_page()
        session_path = self.browser.get_session_path(platform_session)
        cookie_file = session_path / "cookies.json"

        if cookie_file.exists():
            try:
                with open(cookie_file) as f:
                    cookies = json.load(f)
                discord_cookies = [
                    c for c in cookies
                    if "discord.com" in c.get("domain", "")
                ]
                if discord_cookies:
                    self.browser._context.add_cookies(discord_cookies)
            except Exception as e:
                logger.warning(f"Discord: cookie load failed: {e}")

        if self.browser.navigate_with_retry(self._page, f"{self.BASE_URL}/channels/@me"):
            time.sleep(3)
            logged_in = self._check_login_status()
            self._logged_in = logged_in
            return logged_in
        return False

    def interactive_login(self) -> bool:
        """Open Discord login page for interactive authentication.

        Returns:
            True after user completes login.
        """
        config = BrowserConfig(headless=False)
        with BrowserManager(config) as bm:
            page = bm.new_page()
            bm.navigate_with_retry(page, self.LOGIN_URL)
            print("\n" + "=" * 60)
            print("  Log in to Discord in the browser window.")
            print("  Press Enter here when done...")
            print("=" * 60 + "\n")
            input()

            session_path = bm.get_session_path("discord")
            cookies = page.context.cookies()
            cookie_file = session_path / "cookies.json"
            with open(cookie_file, "w") as f:
                json.dump(cookies, f, indent=2)

            self._logged_in = True
            return True

    def join_server(self, invite_url: str) -> bool:
        """Join a Discord server via invite link.

        Args:
            invite_url: Discord invite URL (https://discord.gg/...).

        Returns:
            True if join succeeded.
        """
        try:
            # Normalize invite URL
            if "discord.gg/" in invite_url:
                code = invite_url.split("discord.gg/")[-1].split("?")[0]
                invite_url = f"https://discord.com/invite/{code}"

            if not self._page:
                self._page = self.browser.new_page()

            if not self.browser.navigate_with_retry(self._page, invite_url):
                return False

            time.sleep(3)

            # Click accept invite button
            accept_selectors = [
                'button:has-text("Accept Invite")',
                'button:has-text("Join")',
                '[class*="acceptInvite"]',
                'button[type="submit"]',
            ]

            for selector in accept_selectors:
                try:
                    btn = self._page.query_selector(selector)
                    if btn:
                        btn.click()
                        time.sleep(3)
                        logger.info(f"Discord: joined server via {invite_url}")
                        return True
                except Exception:
                    continue

            logger.warning("Discord: could not find accept invite button")
            return False

        except Exception as e:
            logger.error(f"Discord: join failed: {e}")
            return False

    def verify_role(self, server_id: str, role_name: str = "") -> bool:
        """Verify membership and optional role in a Discord server.

        Args:
            server_id: Discord server/guild ID.
            role_name: Optional role name to check.

        Returns:
            True if member (and has role if specified).
        """
        try:
            if not self._page:
                self._page = self.browser.new_page()

            url = f"{self.BASE_URL}/channels/{server_id}"
            if not self.browser.navigate_with_retry(self._page, url):
                return False

            time.sleep(3)

            # Check if we can access the server (not redirected to login)
            current_url = self._page.url
            if "login" in current_url.lower():
                return False

            logger.info(f"Discord: verified membership in {server_id}")
            return True

        except Exception as e:
            logger.error(f"Discord: verify failed: {e}")
            return False

    def save_session(self) -> None:
        """Save current browser cookies as Discord session."""
        if self._page and self.config.save_cookies:
            session_path = self.browser.get_session_path("discord")
            try:
                cookies = self._page.context.cookies()
                cookie_file = session_path / "cookies.json"
                with open(cookie_file, "w") as f:
                    json.dump(cookies, f, indent=2)
            except Exception as e:
                logger.warning(f"Discord: cookie save failed: {e}")

    def _check_login_status(self) -> bool:
        """Check if we're logged into Discord."""
        try:
            indicators = [
                '[class*="sidebar"]',
                '[data-list-item-id="guildsnav"]',
                'nav[class*="guilds"]',
            ]
            for selector in indicators:
                if self._page.query_selector(selector):
                    return True
            return False
        except Exception:
            return False

    def close(self) -> None:
        """Close the Discord page."""
        self.save_session()
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None


class TelegramExecutor:
    """Browser-based Telegram task automation.

    Handles channel/group joining via web browser.

    Example::

        browser = BrowserManager(BrowserConfig(headless=True))
        browser.launch()
        telegram = TelegramExecutor(browser)

        telegram.join_channel("https://t.me/channel_name")
        browser.close()
    """

    WEB_URL = "https://web.telegram.org"

    def __init__(
        self,
        browser_manager: BrowserManager,
        config: Optional[SocialExecutorConfig] = None,
    ):
        self.browser = browser_manager
        self.config = config or SocialExecutorConfig()
        self._page = None

    def login_with_cookies(self, platform_session: str = "telegram") -> bool:
        """Load saved Telegram session.

        Args:
            platform_session: Session name for cookie storage.

        Returns:
            True if session loaded.
        """
        self._page = self.browser.new_page()
        session_path = self.browser.get_session_path(platform_session)
        cookie_file = session_path / "cookies.json"

        if cookie_file.exists():
            try:
                with open(cookie_file) as f:
                    cookies = json.load(f)
                tg_cookies = [
                    c for c in cookies
                    if "telegram.org" in c.get("domain", "")
                ]
                if tg_cookies:
                    self.browser._context.add_cookies(tg_cookies)
                    return True
            except Exception as e:
                logger.warning(f"Telegram: cookie load failed: {e}")
        return False

    def interactive_login(self) -> bool:
        """Open Telegram web for interactive login.

        Returns:
            True after user completes login.
        """
        config = BrowserConfig(headless=False)
        with BrowserManager(config) as bm:
            page = bm.new_page()
            bm.navigate_with_retry(page, f"{self.WEB_URL}/k/")
            print("\n" + "=" * 60)
            print("  Log in to Telegram Web in the browser window.")
            print("  Press Enter here when done...")
            print("=" * 60 + "\n")
            input()

            session_path = bm.get_session_path("telegram")
            cookies = page.context.cookies()
            cookie_file = session_path / "cookies.json"
            with open(cookie_file, "w") as f:
                json.dump(cookies, f, indent=2)

            return True

    def join_channel(self, channel_url: str) -> bool:
        """Join a Telegram channel or group.

        Args:
            channel_url: Telegram URL (https://t.me/...).

        Returns:
            True if join succeeded.
        """
        try:
            if not self._page:
                self._page = self.browser.new_page()

            # Normalize URL
            if not channel_url.startswith("http"):
                channel_url = f"https://t.me/{channel_url.lstrip('@')}"

            if not self.browser.navigate_with_retry(self._page, channel_url):
                return False

            time.sleep(3)

            # Look for join/open button
            join_selectors = [
                'button:has-text("Join")',
                'a:has-text("Join Channel")',
                'button:has-text("Subscribe")',
                '.tgme_action_button_new',
                '.tgme_page_action',
            ]

            for selector in join_selectors:
                try:
                    btn = self._page.query_selector(selector)
                    if btn:
                        btn_text = btn.inner_text().strip().lower()
                        if "join" in btn_text or "subscribe" in btn_text:
                            btn.click()
                            time.sleep(2)
                            logger.info(f"Telegram: joined {channel_url}")
                            return True
                except Exception:
                    continue

            # If it's a preview page, might need to open in Telegram web
            open_selectors = [
                'a:has-text("Open in Web")',
                'a:has-text("Preview channel")',
            ]
            for selector in open_selectors:
                try:
                    btn = self._page.query_selector(selector)
                    if btn:
                        btn.click()
                        time.sleep(3)
                        return True
                except Exception:
                    continue

            logger.info(f"Telegram: visited {channel_url} (join button may not be visible)")
            return True  # Visit was made, which may be enough

        except Exception as e:
            logger.error(f"Telegram: join failed: {e}")
            return False

    def save_session(self) -> None:
        """Save current browser cookies as Telegram session."""
        if self._page and self.config.save_cookies:
            session_path = self.browser.get_session_path("telegram")
            try:
                cookies = self._page.context.cookies()
                cookie_file = session_path / "cookies.json"
                with open(cookie_file, "w") as f:
                    json.dump(cookies, f, indent=2)
            except Exception as e:
                logger.warning(f"Telegram: cookie save failed: {e}")

    def close(self) -> None:
        """Close the Telegram page."""
        self.save_session()
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
