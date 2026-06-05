"""Anti-detect browser management using Playwright.

Provides stealth browsing with viewport randomization, user-agent rotation,
timezone spoofing, cookie persistence, and proxy support.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Graceful import — playwright is optional
try:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        Page,
        Playwright,
        sync_playwright,
    )

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    # Type stubs for when playwright isn't installed
    Browser = Any  # type: ignore[misc,assignment]
    BrowserContext = Any  # type: ignore[misc,assignment]
    Page = Any  # type: ignore[misc,assignment]
    Playwright = Any  # type: ignore[misc,assignment]

SESSIONS_DIR = Path.home() / ".web3-agent-kit" / "sessions"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]

TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Berlin",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Australia/Sydney",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
    {"width": 2560, "height": 1440},
]


@dataclass
class BrowserConfig:
    """Configuration for the anti-detect browser."""

    headless: bool = True
    proxy: Optional[str] = None  # http://host:port or socks5://host:port
    user_agent: Optional[str] = None  # None = random
    timezone: Optional[str] = None  # None = random
    viewport: Optional[dict[str, int]] = None  # None = random
    session_name: str = "default"
    sessions_dir: Path = SESSIONS_DIR
    screenshot_dir: Optional[Path] = None
    max_retries: int = 3
    retry_delay: float = 2.0
    slow_mo: int = 0  # ms delay between actions
    extra_args: list[str] = field(default_factory=list)


class BrowserManager:
    """Anti-detect browser manager using Playwright.

    Manages browser lifecycle with stealth features: viewport randomization,
    user-agent rotation, timezone spoofing, cookie persistence, and proxy support.

    Example::

        config = BrowserConfig(headless=True, proxy="socks5://proxy:1080")
        manager = BrowserManager(config)

        manager.launch()
        page = manager.new_page()
        page.goto("https://gleam.io/contest/abc123")
        manager.screenshot(page, "contest.png")
        manager.close()
    """

    def __init__(self, config: Optional[BrowserConfig] = None):
        if not HAS_PLAYWRIGHT:
            raise ImportError(
                "playwright is required for browser automation. "
                "Install with: pip install playwright && playwright install chromium"
            )
        self.config = config or BrowserConfig()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._pages: list[Page] = []
        self._session_dir = self.config.sessions_dir / self.config.session_name
        self._session_dir.mkdir(parents=True, exist_ok=True)

    def launch(self) -> None:
        """Launch the browser with stealth configuration.

        Sets up anti-detect measures including randomized viewport,
        user-agent, timezone, and proxy if configured.
        """
        self._playwright = sync_playwright().start()

        # Build launch args with stealth flags
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            "--disable-gpu",
        ]
        launch_args.extend(self.config.extra_args)

        # Proxy configuration
        proxy_settings = None
        if self.config.proxy:
            proxy_settings = {"server": self.config.proxy}

        self._browser = self._playwright.chromium.launch(
            headless=self.config.headless,
            args=launch_args,
            proxy=proxy_settings,
            slow_mo=self.config.slow_mo,
        )

        # Create context with stealth settings
        self._context = self._create_stealth_context()

        # Load saved cookies if they exist
        self._load_cookies()

        logger.info(
            f"Browser launched (headless={self.config.headless}, "
            f"proxy={'yes' if self.config.proxy else 'no'})"
        )

    def new_page(self) -> Page:
        """Create a new browser page.

        Returns:
            A new Playwright Page object.

        Raises:
            RuntimeError: If browser is not launched.
        """
        if not self._context:
            raise RuntimeError("Browser not launched. Call launch() first.")

        page = self._context.new_page()
        self._pages.append(page)

        # Inject stealth scripts
        self._inject_stealth_scripts(page)

        logger.debug("New page created")
        return page

    def close(self) -> None:
        """Close all pages, context, browser, and playwright.

        Saves cookies before closing.
        """
        try:
            self._save_cookies()
        except Exception as e:
            logger.warning(f"Failed to save cookies on close: {e}")

        for page in self._pages:
            try:
                page.close()
            except Exception:
                pass
        self._pages.clear()

        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        logger.info("Browser closed")

    def screenshot(self, page: Page, name: str) -> Optional[str]:
        """Take a screenshot of the current page.

        Args:
            page: The Playwright Page to screenshot.
            name: Filename for the screenshot.

        Returns:
            Path to saved screenshot, or None if failed.
        """
        try:
            if self.config.screenshot_dir:
                ss_dir = self.config.screenshot_dir
            else:
                ss_dir = self._session_dir / "screenshots"
            ss_dir.mkdir(parents=True, exist_ok=True)

            path = ss_dir / name
            page.screenshot(path=str(path), full_page=True)
            logger.debug(f"Screenshot saved: {path}")
            return str(path)
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")
            return None

    def save_cookies(self) -> None:
        """Explicitly save current cookies to disk."""
        self._save_cookies()

    def load_cookies(self) -> None:
        """Explicitly load cookies from disk."""
        self._load_cookies()

    def get_session_path(self, platform: str = "") -> Path:
        """Get the session directory path for a platform.

        Args:
            platform: Platform name (e.g., 'twitter', 'discord').

        Returns:
            Path to the session directory.
        """
        if platform:
            p = self._session_dir / platform
            p.mkdir(parents=True, exist_ok=True)
            return p
        return self._session_dir

    def navigate_with_retry(self, page: Page, url: str, timeout: int = 30000) -> bool:
        """Navigate to a URL with retry on failure.

        Args:
            page: The Playwright Page.
            url: URL to navigate to.
            timeout: Navigation timeout in milliseconds.

        Returns:
            True if navigation succeeded.
        """
        for attempt in range(self.config.max_retries):
            try:
                page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                return True
            except Exception as e:
                logger.warning(f"Navigation failed (attempt {attempt + 1}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (attempt + 1))
                    # Try to recover from crash
                    try:
                        if page.is_closed():
                            page = self.new_page()
                    except Exception:
                        pass
        return False

    def wait_for_element(
        self,
        page: Page,
        selector: str,
        timeout: int = 10000,
    ) -> bool:
        """Wait for an element to appear on the page.

        Args:
            page: The Playwright Page.
            selector: CSS selector to wait for.
            timeout: Max wait time in milliseconds.

        Returns:
            True if element appeared.
        """
        try:
            page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    def click_with_retry(self, page: Page, selector: str, timeout: int = 10000) -> bool:
        """Click an element with retry.

        Args:
            page: The Playwright Page.
            selector: CSS selector to click.
            timeout: Max wait time in milliseconds.

        Returns:
            True if click succeeded.
        """
        for attempt in range(self.config.max_retries):
            try:
                page.click(selector, timeout=timeout)
                return True
            except Exception as e:
                logger.debug(f"Click failed (attempt {attempt + 1}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(1)
        return False

    @property
    def is_launched(self) -> bool:
        """Check if the browser is currently launched."""
        return self._browser is not None and self._context is not None

    def __enter__(self):
        self.launch()
        return self

    def __exit__(self, *args):
        self.close()

    # --- Private helpers ---

    def _create_stealth_context(self) -> BrowserContext:
        """Create a browser context with stealth settings."""
        ua = self.config.user_agent or random.choice(USER_AGENTS)
        tz = self.config.timezone or random.choice(TIMEZONES)
        vp = self.config.viewport or random.choice(VIEWPORTS)

        context = self._browser.new_context(  # type: ignore[union-attr]
            user_agent=ua,
            viewport=vp,
            locale="en-US",
            timezone_id=tz,
            # Reduce detection signals
            java_script_enabled=True,
            has_touch=False,
            is_mobile=False,
            color_scheme="light",
        )

        # Override navigator.webdriver
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            window.chrome = { runtime: {} };
        """)

        return context

    def _inject_stealth_scripts(self, page: Page) -> None:
        """Inject additional stealth scripts into a page."""
        try:
            page.add_init_script("""
                // Fake notification permission
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) =>
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : originalQuery(parameters);
            """)
        except Exception:
            pass

    def _save_cookies(self) -> None:
        """Save context cookies to disk."""
        if not self._context:
            return
        try:
            cookies = self._context.cookies()
            cookie_file = self._session_dir / "cookies.json"
            cookie_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cookie_file, "w") as f:
                json.dump(cookies, f, indent=2)
            logger.debug(f"Saved {len(cookies)} cookies to {cookie_file}")
        except Exception as e:
            logger.warning(f"Cookie save failed: {e}")

    def _load_cookies(self) -> None:
        """Load cookies from disk into context."""
        cookie_file = self._session_dir / "cookies.json"
        if not cookie_file.exists():
            return
        try:
            with open(cookie_file) as f:
                cookies = json.load(f)
            if cookies and self._context:
                self._context.add_cookies(cookies)
                logger.debug(f"Loaded {len(cookies)} cookies from {cookie_file}")
        except Exception as e:
            logger.warning(f"Cookie load failed: {e}")
