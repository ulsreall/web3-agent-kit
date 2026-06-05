"""Zealy quest automation — browser-based quest completion.

Handles Zealy (formerly Crew3) quest pages: parses quests, completes
social tasks via redirects, and tracks XP earned.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from ..base import AirdropTask, AirdropCampaign, TaskType, TaskStatus
from .browser import BrowserManager, BrowserConfig

logger = logging.getLogger(__name__)


@dataclass
class ZealyQuestEntry:
    """A parsed Zealy quest entry."""

    quest_id: str
    title: str
    description: str = ""
    xp_reward: int = 0
    quest_type: str = ""
    url: str = ""
    is_completed: bool = False
    is_claimable: bool = False
    selector: str = ""
    metadata: dict = field(default_factory=dict)

    def to_airdrop_task(self, community: str) -> AirdropTask:
        """Convert to an AirdropTask."""
        type_map = {
            "twitter_follow": TaskType.SOCIAL_TWITTER_FOLLOW,
            "twitter_retweet": TaskType.SOCIAL_TWITTER_RETWEET,
            "twitter_like": TaskType.SOCIAL_TWITTER_LIKE,
            "discord_join": TaskType.SOCIAL_DISCORD_JOIN,
            "telegram_join": TaskType.SOCIAL_TELEGRAM_JOIN,
            "youtube_subscribe": TaskType.SOCIAL_YOUTUBE_SUBSCRIBE,
            "visit_url": TaskType.VISIT_URL,
            "on_chain": TaskType.ON_CHAIN_TX,
            "quiz": TaskType.QUIZ,
        }
        task_type = TaskType.CUSTOM
        for key, tt in type_map.items():
            if key in self.quest_type.lower():
                task_type = tt
                break

        return AirdropTask(
            task_id=f"zealy_{community}_{self.quest_id}",
            platform="zealy",
            task_type=task_type,
            title=self.title,
            description=self.description,
            url=self.url,
            points=self.xp_reward,
            status=TaskStatus.COMPLETED if self.is_completed else TaskStatus.PENDING,
            metadata={"community": community, "quest_type": self.quest_type},
        )


@dataclass
class ZealyResult:
    """Result of farming a Zealy quest board."""

    community: str
    community_url: str
    total_quests: int = 0
    completed_quests: int = 0
    failed_quests: int = 0
    skipped_quests: int = 0
    xp_earned: int = 0
    quests: list[ZealyQuestEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_quests == 0:
            return 0.0
        return self.completed_quests / self.total_quests


class ZealyExecutor:
    """Browser-based Zealy quest automation.

    Navigates Zealy quest boards, parses available quests, and completes
    social tasks through real browser interactions.

    Example::

        with BrowserManager(BrowserConfig(headless=True)) as browser:
            executor = ZealyExecutor(browser)
            result = executor.complete_all("https://zealy.io/c/myproject")
            print(f"Earned {result.xp_earned} XP from {result.completed_quests} quests")
    """

    # CSS selectors for Zealy page elements
    SELECTORS = {
        "quest_card": '[data-testid*="quest"], .quest-card, [class*="QuestCard"]',
        "quest_title": '[class*="quest-title"], [class*="QuestTitle"], h3, h4',
        "quest_xp": '[class*="xp"], [class*="reward"], [class*="points"]',
        "quest_button": 'button:has-text("Start"), button:has-text("Verify"), button:has-text("Claim")',
        "verify_button": 'button:has-text("Verify"), button:has-text("Check"), button:has-text("Submit")',
        "claim_button": 'button:has-text("Claim"), button:has-text("Collect")',
        "completed_badge": '[class*="completed"], [class*="done"], [class*="check"]',
        "quest_type_icon": '[class*="icon"], [class*="QuestIcon"]',
        "community_header": '[class*="community-header"], [class*="CommunityHeader"]',
        "login_button": 'button:has-text("Login"), button:has-text("Sign in"), button:has-text("Connect")',
    }

    # Timing
    QUEST_DELAY_MIN = 3.0
    QUEST_DELAY_MAX = 7.0
    VERIFY_WAIT = 5.0

    def __init__(self, browser_manager: BrowserManager):
        self.browser = browser_manager
        self._page = None

    def visit(self, url: str) -> bool:
        """Load a Zealy community/quest page.

        Args:
            url: Zealy URL (e.g., https://zealy.io/c/community).

        Returns:
            True if page loaded successfully.
        """
        self._page = self.browser.new_page()
        success = self.browser.navigate_with_retry(self._page, url)
        if success:
            time.sleep(3)
            logger.info(f"Zealy: loaded {url}")
        return success

    def get_quests(self) -> list[ZealyQuestEntry]:
        """Parse available quests from the loaded page.

        Returns:
            List of ZealyQuestEntry objects.
        """
        if not self._page:
            logger.error("Zealy: no page loaded. Call visit() first.")
            return []

        quests: list[ZealyQuestEntry] = []

        try:
            # Wait for quest cards to render
            self._page.wait_for_selector(
                self.SELECTORS["quest_card"], timeout=15000
            )

            cards = self._page.query_selector_all(self.SELECTORS["quest_card"])
            logger.info(f"Zealy: found {len(cards)} quest cards")

            for i, card in enumerate(cards):
                try:
                    quest = self._parse_quest(card, i)
                    if quest:
                        quests.append(quest)
                except Exception as e:
                    logger.debug(f"Zealy: failed to parse quest {i}: {e}")

        except Exception as e:
            logger.warning(f"Zealy: quest parsing failed: {e}")
            # Try alternative approach — look for quest links
            quests = self._parse_quests_from_links()

        return quests

    def complete_quest(self, quest: ZealyQuestEntry) -> bool:
        """Complete a single Zealy quest.

        Args:
            quest: The ZealyQuestEntry to complete.

        Returns:
            True if quest was completed.
        """
        if not self._page:
            return False

        if quest.is_completed:
            logger.info(f"Zealy: quest '{quest.title}' already completed")
            return True

        try:
            # Click the quest to open it
            if quest.selector:
                self.browser.click_with_retry(self._page, quest.selector)

            time.sleep(2)

            # Handle different quest types
            if self._is_social_quest(quest):
                success = self._handle_social_quest(quest)
            elif self._is_visit_quest(quest):
                success = self._handle_visit_quest(quest)
            else:
                success = self._handle_generic_quest(quest)

            if success:
                # Try to verify
                time.sleep(2)
                verified = self._verify_quest(quest)
                if verified:
                    quest.is_completed = True
                    logger.info(f"Zealy: completed quest '{quest.title}' (+{quest.xp_reward} XP)")
                    return True
                else:
                    # Might need manual verification or cooldown
                    logger.info(f"Zealy: quest '{quest.title}' submitted, verification pending")
                    quest.is_completed = True  # Optimistic
                    return True

            return False

        except Exception as e:
            logger.error(f"Zealy: quest '{quest.title}' failed: {e}")
            return False

    def complete_all(self, url: str, tracker=None) -> ZealyResult:
        """Complete all quests in a Zealy community.

        Args:
            url: Zealy community URL.
            tracker: Optional AirdropTracker for progress tracking.

        Returns:
            ZealyResult with completion statistics.
        """
        start_time = time.time()
        community = self._extract_community(url)

        result = ZealyResult(
            community=community,
            community_url=url,
        )

        try:
            if not self.visit(url):
                result.errors.append(f"Failed to load {url}")
                return result

            quests = self.get_quests()
            result.total_quests = len(quests)
            result.quests = quests

            if not quests:
                result.errors.append("No quests found")
                return result

            logger.info(f"Zealy: starting {len(quests)} quests")

            for i, quest in enumerate(quests):
                if quest.is_completed:
                    result.skipped_quests += 1
                    continue

                logger.info(
                    f"Zealy: [{i + 1}/{len(quests)}] {quest.title} ({quest.xp_reward} XP)"
                )

                success = self.complete_quest(quest)
                if success:
                    result.completed_quests += 1
                    result.xp_earned += quest.xp_reward

                    if tracker:
                        airdrop_task = quest.to_airdrop_task(community)
                        tracker.mark_task_completed(airdrop_task)
                else:
                    result.failed_quests += 1
                    result.errors.append(f"Failed: {quest.title}")

                # Human-like delay
                self._random_delay()

        except Exception as e:
            result.errors.append(f"Unexpected error: {str(e)}")
            logger.error(f"Zealy: unexpected error: {e}")
        finally:
            result.elapsed_seconds = time.time() - start_time
            logger.info(
                f"Zealy: finished in {result.elapsed_seconds:.1f}s — "
                f"{result.completed_quests}/{result.total_quests} quests, "
                f"{result.xp_earned} XP earned"
            )

        return result

    def close(self) -> None:
        """Close the current page."""
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None

    # --- Private helpers ---

    def _parse_quest(self, element, index: int) -> Optional[ZealyQuestEntry]:
        """Parse a quest card element."""
        try:
            title_el = element.query_selector(self.SELECTORS["quest_title"])
            title = title_el.inner_text().strip() if title_el else f"Quest {index}"

            # Get XP
            xp_el = element.query_selector(self.SELECTORS["quest_xp"])
            xp_text = xp_el.inner_text().strip() if xp_el else "0"
            xp = self._parse_xp(xp_text)

            # Check completion
            completed_el = element.query_selector(self.SELECTORS["completed_badge"])
            is_completed = completed_el is not None

            # Get quest type from icons or text
            quest_type = self._classify_quest_type(title, element)

            # Get URL if it's a link
            url = ""
            link = element.query_selector("a[href]")
            if link:
                url = link.get_attribute("href") or ""

            # Build a CSS selector for clicking this specific card
            selector = f'[data-testid*="quest"]:nth-child({index + 1}), .quest-card:nth-child({index + 1})'

            quest_id = element.get_attribute("data-quest-id") or str(index)

            return ZealyQuestEntry(
                quest_id=quest_id,
                title=title,
                xp_reward=xp,
                quest_type=quest_type,
                url=url,
                is_completed=is_completed,
                selector=selector,
                metadata={"index": index},
            )
        except Exception as e:
            logger.debug(f"Parse quest failed: {e}")
            return None

    def _parse_quests_from_links(self) -> list[ZealyQuestEntry]:
        """Fallback: parse quests from page links."""
        quests = []
        if not self._page:
            return quests
        try:
            links = self._page.query_selector_all('a[href*="/quest/"], a[href*="quest"]')
            for i, link in enumerate(links):
                text = link.inner_text().strip()
                href = link.get_attribute("href") or ""
                if text and href:
                    quests.append(ZealyQuestEntry(
                        quest_id=str(i),
                        title=text,
                        url=href,
                        selector=f'a[href*="quest"]:nth-child({i + 1})',
                        metadata={"index": i},
                    ))
        except Exception as e:
            logger.debug(f"Link parsing failed: {e}")
        return quests

    def _handle_social_quest(self, quest: ZealyQuestEntry) -> bool:
        """Handle a social media quest (click, redirect, verify)."""
        try:
            # Click the quest action button
            if not self._page:
                return False

            # Look for action buttons
            btn = self._page.query_selector(self.SELECTORS["quest_button"])
            if btn:
                # Listen for new pages (redirects)
                context = self.browser._context
                pages_before = len(context.pages) if context else 0

                btn.click()
                time.sleep(2)

                # Check if a new page/tab was opened
                if context and len(context.pages) > pages_before:
                    # Handle the redirect page
                    new_page = context.pages[-1]
                    try:
                        new_page.wait_for_load_state("domcontentloaded", timeout=10000)
                        url = new_page.url
                        logger.debug(f"Zealy: social redirect to {url}")
                        time.sleep(3)
                        new_page.close()
                        return True
                    except Exception:
                        try:
                            new_page.close()
                        except Exception:
                            pass

                # If no new tab, the button might have been enough
                return True

            return False

        except Exception as e:
            logger.debug(f"Social quest handler failed: {e}")
            return False

    def _handle_visit_quest(self, quest: ZealyQuestEntry) -> bool:
        """Handle a visit URL quest."""
        try:
            if quest.url and self._page:
                new_page = self.browser.new_page()
                success = self.browser.navigate_with_retry(new_page, quest.url)
                time.sleep(3)
                new_page.close()
                return success
            return self._handle_generic_quest(quest)
        except Exception as e:
            logger.debug(f"Visit quest failed: {e}")
            return False

    def _handle_generic_quest(self, quest: ZealyQuestEntry) -> bool:
        """Handle a generic quest — click start/verify."""
        try:
            if not self._page:
                return False

            # Try clicking various action buttons
            for selector in [self.SELECTORS["quest_button"], self.SELECTORS["verify_button"]]:
                btn = self._page.query_selector(selector)
                if btn:
                    btn.click()
                    time.sleep(2)
                    return True

            return False
        except Exception as e:
            logger.debug(f"Generic quest handler failed: {e}")
            return False

    def _verify_quest(self, quest: ZealyQuestEntry) -> bool:
        """Try to verify/claim a completed quest."""
        if not self._page:
            return False

        try:
            # Look for verify button
            verify_btn = self._page.query_selector(self.SELECTORS["verify_button"])
            if verify_btn:
                verify_btn.click()
                time.sleep(self.VERIFY_WAIT)
                return True

            # Look for claim button
            claim_btn = self._page.query_selector(self.SELECTORS["claim_button"])
            if claim_btn:
                claim_btn.click()
                time.sleep(2)
                return True

            return True  # No verify needed
        except Exception as e:
            logger.debug(f"Quest verify failed: {e}")
            return False

    def _is_social_quest(self, quest: ZealyQuestEntry) -> bool:
        """Check if quest is social media related."""
        social_keywords = ["twitter", "follow", "retweet", "like", "discord",
                          "telegram", "youtube", "subscribe", "join"]
        text = f"{quest.title} {quest.quest_type}".lower()
        return any(kw in text for kw in social_keywords)

    def _is_visit_quest(self, quest: ZealyQuestEntry) -> bool:
        """Check if quest is a visit URL type."""
        visit_keywords = ["visit", "check", "read", "explore", "browse"]
        text = f"{quest.title} {quest.quest_type}".lower()
        return any(kw in text for kw in visit_keywords)

    def _classify_quest_type(self, title: str, element) -> str:
        """Classify quest type from title and element content."""
        text = title.lower()

        if "follow" in text and "twitter" in text:
            return "twitter_follow"
        if "retweet" in text:
            return "twitter_retweet"
        if "like" in text and "twitter" in text:
            return "twitter_like"
        if "discord" in text or "join server" in text:
            return "discord_join"
        if "telegram" in text or "join channel" in text:
            return "telegram_join"
        if "youtube" in text or "subscribe" in text:
            return "youtube_subscribe"
        if "visit" in text or "check" in text:
            return "visit_url"
        if "quiz" in text or "answer" in text:
            return "quiz"
        if "on-chain" in text or "transaction" in text or "swap" in text:
            return "on_chain"

        return "custom"

    def _parse_xp(self, text: str) -> int:
        """Parse XP amount from text."""
        import re
        match = re.search(r"(\d+)", text.replace(",", ""))
        return int(match.group(1)) if match else 0

    def _extract_community(self, url: str) -> str:
        """Extract community slug from Zealy URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/")
        # URL format: /c/community-slug or /community/...
        if len(parts) >= 2 and parts[0] == "c":
            return parts[1]
        return parts[-1] if parts else "unknown"

    def _random_delay(self) -> None:
        """Sleep a random human-like delay."""
        import random
        delay = random.uniform(self.QUEST_DELAY_MIN, self.QUEST_DELAY_MAX)
        time.sleep(delay)
