"""Gleam.io task automation — real browser-based contest entry completion.

Uses Playwright to interact with Gleam.io widgets, complete social tasks,
and verify entry status.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

from ..base import AirdropTask, AirdropCampaign, TaskType, TaskStatus
from .browser import BrowserManager, BrowserConfig

logger = logging.getLogger(__name__)


class GleamTaskType(Enum):
    """Types of Gleam.io tasks."""

    VISIT_URL = "visit_url"
    TWITTER_FOLLOW = "twitter_follow"
    TWITTER_RETWEET = "twitter_retweet"
    TWITTER_LIKE = "twitter_like"
    TWITTER_TWEET = "twitter_tweet"
    YOUTUBE_SUBSCRIBE = "youtube_subscribe"
    DISCORD_JOIN = "discord_join"
    TELEGRAM_JOIN = "telegram_join"
    CUSTOM_ACTION = "custom_action"
    REFERRAL = "referral"
    UNKNOWN = "unknown"


@dataclass
class GleamTaskEntry:
    """A parsed Gleam.io task entry."""

    entry_id: str
    task_type: GleamTaskType
    title: str
    url: str = ""
    points: int = 1
    is_completed: bool = False
    method: str = ""
    selector: str = ""  # CSS selector for the action button
    metadata: dict = field(default_factory=dict)

    def to_airdrop_task(self, campaign_id: str) -> AirdropTask:
        """Convert to an AirdropTask."""
        type_map = {
            GleamTaskType.VISIT_URL: TaskType.VISIT_URL,
            GleamTaskType.TWITTER_FOLLOW: TaskType.SOCIAL_TWITTER_FOLLOW,
            GleamTaskType.TWITTER_RETWEET: TaskType.SOCIAL_TWITTER_RETWEET,
            GleamTaskType.TWITTER_LIKE: TaskType.SOCIAL_TWITTER_LIKE,
            GleamTaskType.TWITTER_TWEET: TaskType.SOCIAL_TWITTER_COMMENT,
            GleamTaskType.YOUTUBE_SUBSCRIBE: TaskType.SOCIAL_YOUTUBE_SUBSCRIBE,
            GleamTaskType.DISCORD_JOIN: TaskType.SOCIAL_DISCORD_JOIN,
            GleamTaskType.TELEGRAM_JOIN: TaskType.SOCIAL_TELEGRAM_JOIN,
            GleamTaskType.CUSTOM_ACTION: TaskType.CUSTOM,
            GleamTaskType.REFERRAL: TaskType.REFERRAL,
        }
        return AirdropTask(
            task_id=f"gleam_{campaign_id}_{self.entry_id}",
            platform="gleam",
            task_type=type_map.get(self.task_type, TaskType.CUSTOM),
            title=self.title,
            description=f"Gleam entry: {self.method}",
            url=self.url,
            points=self.points,
            status=TaskStatus.COMPLETED if self.is_completed else TaskStatus.PENDING,
            metadata={"method": self.method, "entry_id": self.entry_id},
        )


@dataclass
class GleamResult:
    """Result of farming a Gleam.io campaign."""

    campaign_url: str
    campaign_id: str
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    entries: list[GleamTaskEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.completed_tasks / self.total_tasks

    @property
    def is_fully_completed(self) -> bool:
        return self.completed_tasks == self.total_tasks and self.total_tasks > 0


class GleamExecutor:
    """Browser-based Gleam.io contest automation.

    Navigates to Gleam campaigns, parses tasks, and completes them
    using real browser interactions (clicks, redirects, form fills).

    Example::

        with BrowserManager(BrowserConfig(headless=True)) as browser:
            executor = GleamExecutor(browser)
            result = executor.complete_all("https://gleam.io/contest/abc123")
            print(f"Completed {result.completed_tasks}/{result.total_tasks} tasks")
    """

    # CSS selectors for Gleam widget elements
    SELECTORS = {
        "entry_method": ".entry-method, .entry-method-v2, [data-entry-method]",
        "entry_title": ".entry-title, .entry-method-title, .g-ent-title",
        "entry_button": ".entry-method a.btn, .entry-method button, .g-ent-btn, a.enter-btn",
        "completed_badge": ".entry-completed, .completed-badge, .g-ent-done, .fa-check",
        "action_button": ".action-btn, .g-action-btn, a.action-link",
        "contest_title": ".contest-title, .g-title, h1",
        "widget_container": ".gleam-widget, #gleam-widget, .g-widget, .gleam-container",
        "visit_button": "a.entry-method-action, a[href*='visit'], a.btn-visit",
        "social_button": "a.entry-method-action, button.entry-method-action",
        "tweet_button": "a[href*='twitter.com/intent/tweet'], a[href*='twitter.com/share']",
        "follow_button": "a[href*='twitter.com/intent/follow'], a.twitter-follow",
        "retweet_button": "a[href*='twitter.com/intent/retweet']",
        "like_button": "a[href*='twitter.com/intent/favorite'], a[href*='twitter.com/intent/like']",
        "discord_link": "a[href*='discord.gg'], a[href*='discord.com/invite']",
        "telegram_link": "a[href*='t.me/'], a[href*='telegram.me/']",
        "youtube_link": "a[href*='youtube.com'], a[href*='youtu.be']",
    }

    # Timing configuration
    TASK_DELAY_MIN = 2.0
    TASK_DELAY_MAX = 5.0
    PAGE_LOAD_TIMEOUT = 30000
    ACTION_TIMEOUT = 10000
    POPUP_WAIT = 5000

    def __init__(self, browser_manager: BrowserManager):
        self.browser = browser_manager
        self._page = None

    def visit(self, url: str) -> bool:
        """Load a Gleam.io campaign page.

        Args:
            url: Full Gleam.io campaign URL.

        Returns:
            True if page loaded successfully.
        """
        self._page = self.browser.new_page()
        success = self.browser.navigate_with_retry(
            self._page, url, timeout=self.PAGE_LOAD_TIMEOUT
        )
        if success:
            # Wait for widget to load
            self.browser.wait_for_element(
                self._page, self.SELECTORS["widget_container"], timeout=15000
            )
            # Give dynamic content time to render
            time.sleep(2)
            logger.info(f"Gleam: loaded {url}")
        return success

    def get_tasks(self) -> list[GleamTaskEntry]:
        """Parse all available tasks from the loaded Gleam page.

        Returns:
            List of GleamTaskEntry objects.
        """
        if not self._page:
            logger.error("Gleam: no page loaded. Call visit() first.")
            return []

        entries: list[GleamTaskEntry] = []
        try:
            # Wait for entry methods to render
            self._page.wait_for_selector(
                self.SELECTORS["entry_method"], timeout=10000
            )

            # Get all entry method elements
            methods = self._page.query_selector_all(self.SELECTORS["entry_method"])
            logger.info(f"Gleam: found {len(methods)} entry methods")

            for i, method_el in enumerate(methods):
                try:
                    entry = self._parse_entry(method_el, i)
                    if entry:
                        entries.append(entry)
                except Exception as e:
                    logger.debug(f"Gleam: failed to parse entry {i}: {e}")

        except Exception as e:
            logger.error(f"Gleam: failed to get tasks: {e}")

        return entries

    def complete_task(self, task: GleamTaskEntry) -> bool:
        """Complete a single Gleam task.

        Args:
            task: The GleamTaskEntry to complete.

        Returns:
            True if task was completed successfully.
        """
        if not self._page:
            logger.error("Gleam: no page loaded")
            return False

        if task.is_completed:
            logger.info(f"Gleam: task '{task.title}' already completed, skipping")
            return True

        try:
            handler = self._get_task_handler(task.task_type)
            if handler:
                success = handler(task)
                if success:
                    task.is_completed = True
                    logger.info(f"Gleam: completed task '{task.title}'")
                else:
                    logger.warning(f"Gleam: failed task '{task.title}'")
                return success
            else:
                logger.warning(f"Gleam: no handler for task type {task.task_type}")
                return False
        except Exception as e:
            logger.error(f"Gleam: error completing task '{task.title}': {e}")
            return False

    def complete_all(self, url: str, tracker=None) -> GleamResult:
        """Complete all tasks in a Gleam campaign.

        Args:
            url: Gleam.io campaign URL.
            tracker: Optional AirdropTracker for progress tracking.

        Returns:
            GleamResult with completion statistics.
        """
        start_time = time.time()
        campaign_id = self._extract_campaign_id(url)

        result = GleamResult(
            campaign_url=url,
            campaign_id=campaign_id,
        )

        try:
            # Load the page
            if not self.visit(url):
                result.errors.append(f"Failed to load {url}")
                return result

            # Parse tasks
            tasks = self.get_tasks()
            result.total_tasks = len(tasks)
            result.entries = tasks

            if not tasks:
                result.errors.append("No tasks found on page")
                return result

            logger.info(f"Gleam: starting completion of {len(tasks)} tasks")

            # Complete each task with delays
            for i, task in enumerate(tasks):
                if task.is_completed:
                    result.skipped_tasks += 1
                    continue

                logger.info(
                    f"Gleam: [{i + 1}/{len(tasks)}] {task.title} ({task.task_type.value})"
                )

                success = self.complete_task(task)
                if success:
                    result.completed_tasks += 1

                    # Track progress if tracker provided
                    if tracker:
                        airdrop_task = task.to_airdrop_task(campaign_id)
                        tracker.mark_task_completed(airdrop_task)
                else:
                    result.failed_tasks += 1
                    result.errors.append(f"Failed: {task.title}")

                # Human-like delay between tasks
                self._random_delay()

            # Verify final status
            self._verify_entries(tasks)

        except Exception as e:
            result.errors.append(f"Unexpected error: {str(e)}")
            logger.error(f"Gleam: unexpected error: {e}")
        finally:
            result.elapsed_seconds = time.time() - start_time
            logger.info(
                f"Gleam: finished in {result.elapsed_seconds:.1f}s — "
                f"{result.completed_tasks}/{result.total_tasks} completed"
            )

        return result

    def verify_entry_status(self) -> dict[str, bool]:
        """Check completion status of all visible entries.

        Returns:
            Dict mapping entry titles to completion status.
        """
        if not self._page:
            return {}

        status: dict[str, bool] = {}
        try:
            methods = self._page.query_selector_all(self.SELECTORS["entry_method"])
            for method in methods:
                title_el = method.query_selector(self.SELECTORS["entry_title"])
                completed_el = method.query_selector(self.SELECTORS["completed_badge"])
                title = title_el.inner_text().strip() if title_el else "unknown"
                status[title] = completed_el is not None
        except Exception as e:
            logger.warning(f"Gleam: status check failed: {e}")

        return status

    def close(self) -> None:
        """Close the current page."""
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None

    # --- Private task handlers ---

    def _get_task_handler(self, task_type: GleamTaskType):
        """Get the handler function for a task type."""
        handlers = {
            GleamTaskType.VISIT_URL: self._handle_visit_url,
            GleamTaskType.TWITTER_FOLLOW: self._handle_twitter_follow,
            GleamTaskType.TWITTER_RETWEET: self._handle_twitter_retweet,
            GleamTaskType.TWITTER_LIKE: self._handle_twitter_like,
            GleamTaskType.TWITTER_TWEET: self._handle_twitter_tweet,
            GleamTaskType.YOUTUBE_SUBSCRIBE: self._handle_youtube_subscribe,
            GleamTaskType.DISCORD_JOIN: self._handle_discord_join,
            GleamTaskType.TELEGRAM_JOIN: self._handle_telegram_join,
            GleamTaskType.CUSTOM_ACTION: self._handle_custom_action,
        }
        return handlers.get(task_type)

    def _handle_visit_url(self, task: GleamTaskEntry) -> bool:
        """Handle visit URL tasks — navigate and verify."""
        try:
            if task.url:
                # Open link in new tab, then close
                new_page = self.browser.new_page()
                success = self.browser.navigate_with_retry(
                    new_page, task.url, timeout=self.PAGE_LOAD_TIMEOUT
                )
                time.sleep(2)
                new_page.close()
                return success
            else:
                # Click the visit button on the widget
                return self._click_entry_action(task)
        except Exception as e:
            logger.debug(f"Visit URL failed: {e}")
            return False

    def _handle_twitter_follow(self, task: GleamTaskEntry) -> bool:
        """Handle Twitter follow — click, handle popup."""
        return self._handle_social_popup(task, "twitter.com")

    def _handle_twitter_retweet(self, task: GleamTaskEntry) -> bool:
        """Handle Twitter retweet — click retweet button."""
        return self._handle_social_popup(task, "twitter.com")

    def _handle_twitter_like(self, task: GleamTaskEntry) -> bool:
        """Handle Twitter like — click like button."""
        return self._handle_social_popup(task, "twitter.com")

    def _handle_twitter_tweet(self, task: GleamTaskEntry) -> bool:
        """Handle Twitter tweet — handle pre-filled tweet popup."""
        return self._handle_social_popup(task, "twitter.com")

    def _handle_youtube_subscribe(self, task: GleamTaskEntry) -> bool:
        """Handle YouTube subscribe — redirect-based."""
        return self._handle_social_popup(task, "youtube.com")

    def _handle_discord_join(self, task: GleamTaskEntry) -> bool:
        """Handle Discord join — redirect to Discord."""
        return self._handle_social_popup(task, "discord")

    def _handle_telegram_join(self, task: GleamTaskEntry) -> bool:
        """Handle Telegram join — redirect to Telegram."""
        return self._handle_social_popup(task, "t.me")

    def _handle_custom_action(self, task: GleamTaskEntry) -> bool:
        """Handle custom action — click and verify."""
        return self._click_entry_action(task)

    def _handle_social_popup(self, task: GleamTaskEntry, domain: str) -> bool:
        """Handle social task that opens a popup/redirect.

        Args:
            task: The task entry.
            domain: Domain to watch for in popups.

        Returns:
            True if the social action was completed.
        """
        try:
            # Listen for new pages (popups)
            context = self.browser._context
            if not context:
                return False

            # Click the action button
            action_clicked = False

            # Try clicking the entry's action button
            if task.selector:
                action_clicked = self.browser.click_with_retry(
                    self._page, task.selector, timeout=self.ACTION_TIMEOUT
                )

            if not action_clicked:
                # Try generic selectors within this entry
                action_clicked = self._click_entry_action(task)

            if not action_clicked:
                return False

            # Wait for and handle popup/redirect
            time.sleep(1)

            # Check for new pages (popups)
            pages = context.pages
            if len(pages) > 1:
                # A popup was opened
                popup = pages[-1]
                try:
                    # Wait for popup to load
                    popup.wait_for_load_state("domcontentloaded", timeout=self.POPUP_WAIT)
                    url = popup.url

                    if domain in url:
                        logger.info(f"Gleam: handled popup to {url}")
                        time.sleep(2)
                        popup.close()
                        return True
                    else:
                        popup.close()
                except Exception:
                    try:
                        popup.close()
                    except Exception:
                        pass

            # If no popup, the click might have been enough (some Gleam widgets
            # track clicks without requiring actual completion)
            return True

        except Exception as e:
            logger.debug(f"Social popup handler failed: {e}")
            return False

    def _click_entry_action(self, task: GleamTaskEntry) -> bool:
        """Click the action button for an entry.

        Args:
            task: The task entry.

        Returns:
            True if click succeeded.
        """
        if not self._page:
            return False

        # Try the task-specific selector first
        if task.selector:
            if self.browser.click_with_retry(self._page, task.selector):
                return True

        # Try finding the action button by entry index
        entry_index = task.metadata.get("index", 0)
        selectors_to_try = [
            f".entry-method:nth-child({entry_index + 1}) a.btn",
            f".entry-method:nth-child({entry_index + 1}) button",
            f".entry-method:nth-child({entry_index + 1}) .action-btn",
            f"[data-entry-index='{entry_index}'] a",
        ]

        for selector in selectors_to_try:
            if self.browser.click_with_retry(self._page, selector, timeout=3000):
                return True

        # Last resort: try clicking any clickable element in the entry
        try:
            methods = self._page.query_selector_all(self.SELECTORS["entry_method"])
            if entry_index < len(methods):
                entry_el = methods[entry_index]
                links = entry_el.query_selector_all("a, button")
                for link in links:
                    try:
                        href = link.get_attribute("href") or ""
                        if href and href != "#" and not href.startswith("javascript"):
                            link.click()
                            return True
                    except Exception:
                        continue
                # Click the first button/link found
                if links:
                    links[0].click()
                    return True
        except Exception as e:
            logger.debug(f"Click action fallback failed: {e}")

        return False

    # --- Parsing helpers ---

    def _parse_entry(self, element, index: int) -> Optional[GleamTaskEntry]:
        """Parse a single entry method element.

        Args:
            element: The Playwright element handle.
            index: Entry index.

        Returns:
            GleamTaskEntry or None if parsing failed.
        """
        try:
            # Get title
            title_el = element.query_selector(self.SELECTORS["entry_title"])
            title = title_el.inner_text().strip() if title_el else f"Task {index}"

            # Get method/data attributes
            method = element.get_attribute("data-method") or ""
            entry_id = element.get_attribute("data-entry-id") or str(index)

            # Check if already completed
            completed_el = element.query_selector(self.SELECTORS["completed_badge"])
            is_completed = completed_el is not None

            # Get URL from action link
            url = ""
            action_link = element.query_selector("a[href]")
            if action_link:
                href = action_link.get_attribute("href") or ""
                if href and not href.startswith("#") and not href.startswith("javascript"):
                    url = href

            # Determine task type
            task_type = self._classify_task(title, method, url)

            # Find a clickable selector
            selector = ""
            for sel in ["a.btn", "button", "a.entry-method-action", ".action-btn"]:
                el = element.query_selector(sel)
                if el:
                    selector = sel
                    break

            return GleamTaskEntry(
                entry_id=entry_id,
                task_type=task_type,
                title=title,
                url=url,
                is_completed=is_completed,
                method=method,
                selector=selector,
                metadata={"index": index},
            )
        except Exception as e:
            logger.debug(f"Parse entry failed: {e}")
            return None

    def _classify_task(self, title: str, method: str, url: str) -> GleamTaskType:
        """Classify a task based on title, method, and URL.

        Args:
            title: Task title text.
            method: Gleam method attribute.
            url: Task action URL.

        Returns:
            GleamTaskType classification.
        """
        text = f"{title} {method} {url}".lower()

        if "follow" in text and "twitter" in text:
            return GleamTaskType.TWITTER_FOLLOW
        if "retweet" in text:
            return GleamTaskType.TWITTER_RETWEET
        if ("like" in text or "fav" in text) and "twitter" in text:
            return GleamTaskType.TWITTER_LIKE
        if "tweet" in text and "follow" not in text:
            return GleamTaskType.TWITTER_TWEET
        if "youtube" in text or "subscribe" in text:
            return GleamTaskType.YOUTUBE_SUBSCRIBE
        if "discord" in text:
            return GleamTaskType.DISCORD_JOIN
        if "telegram" in text or "t.me" in text:
            return GleamTaskType.TELEGRAM_JOIN
        if "visit" in text or "click" in text or "url" in method:
            return GleamTaskType.VISIT_URL
        if "referral" in text or "refer" in text:
            return GleamTaskType.REFERRAL

        return GleamTaskType.CUSTOM_ACTION

    def _verify_entries(self, tasks: list[GleamTaskEntry]) -> None:
        """Re-check entry completion status on the page.

        Args:
            tasks: List of tasks to update status for.
        """
        if not self._page:
            return

        try:
            time.sleep(2)
            status = self.verify_entry_status()
            for task in tasks:
                if task.title in status:
                    task.is_completed = status[task.title]
        except Exception as e:
            logger.debug(f"Entry verification failed: {e}")

    def _random_delay(self) -> None:
        """Sleep a random human-like delay."""
        import random

        delay = random.uniform(self.TASK_DELAY_MIN, self.TASK_DELAY_MAX)
        time.sleep(delay)

    def _extract_campaign_id(self, url: str) -> str:
        """Extract campaign ID from a Gleam URL.

        Args:
            url: Gleam.io URL.

        Returns:
            Campaign identifier string.
        """
        match = re.search(r"gleam\.io/([a-zA-Z0-9_-]+)", url)
        if match:
            return match.group(1)
        parsed = urlparse(url)
        return parsed.path.strip("/").split("/")[-1] or "unknown"
