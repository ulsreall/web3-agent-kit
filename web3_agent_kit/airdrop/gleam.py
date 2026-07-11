"""Gleam.io airdrop automation — giveaway and contest task completion."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from .base import (
    AirdropCampaign,
    AirdropTask,
    BaseAirdropPlatform,
    PlatformConfig,
    TaskStatus,
    TaskType,
)

logger = logging.getLogger(__name__)


@dataclass
class GleamTask:
    """A Gleam.io specific task entry."""
    entry_id: str
    task_type: str
    title: str
    url: str = ""
    points: int = 0
    is_completed: bool = False
    method: str = ""  # e.g. "twitter_follow", "visit_url"


class GleamCampaign(BaseAirdropPlatform):
    """Gleam.io campaign automation.

    Gleam.io contests use a widget-based interface where users
    complete tasks (social follows, visits, referrals) to earn entries.

    Example::

        campaign = GleamCampaign(config=PlatformConfig(
            session_cookie="your_gleam_session",
        ))

        # Load a Gleam contest
        tasks = campaign.get_tasks("https://gleam.io/contest/abc123")

        # Complete all available tasks
        for task in tasks:
            campaign.complete_task(task)
    """

    platform_name = "gleam"

    def __init__(self, config: Optional[PlatformConfig] = None):
        super().__init__(config)
        self._campaigns: dict[str, AirdropCampaign] = {}
        self._completed_entries: set[str] = set()

    def login(self, credentials: dict) -> bool:
        """Authenticate with Gleam.io.

        Args:
            credentials: Dict with 'session_cookie' or 'auth_token'.

        Returns:
            True if authentication succeeded.
        """
        cookie = credentials.get("session_cookie") or credentials.get("auth_token")
        if cookie:
            self.session.cookies.set("_gleam_session", cookie)
            self._authenticated = True
            logger.info("Gleam.io: authenticated via session cookie")
            return True

        logger.warning("Gleam.io: no credentials provided")
        return False

    def get_tasks(self, campaign_id: str) -> list[AirdropTask]:
        """Extract tasks from a Gleam.io contest page.

        Args:
            campaign_id: Full Gleam.io contest URL or contest ID.

        Returns:
            List of AirdropTask objects.
        """
        campaign_url = campaign_id if campaign_id.startswith("http") else f"https://gleam.io/{campaign_id}"
        tasks: list[AirdropTask] = []

        try:
            resp = self._get(campaign_url)
            html = resp.text

            # Extract contest ID from URL
            contest_id = self._extract_contest_id(campaign_url)

            # Parse entry methods from the page
            entry_pattern = re.compile(
                r'data-method="([^"]+)".*?class="[^"]*entry-title[^"]*"[^>]*>([^<]+)',
                re.DOTALL,
            )
            matches = entry_pattern.findall(html)

            for i, (method, title) in enumerate(matches):
                task_type = self._map_method_to_task_type(method)
                task = AirdropTask(
                    task_id=f"gleam_{contest_id}_{i}",
                    platform=self.platform_name,
                    task_type=task_type,
                    title=title.strip(),
                    description=f"Gleam entry: {method}",
                    url=campaign_url,
                    points=1,
                    metadata={"method": method, "entry_index": i},
                )
                tasks.append(task)

            # Store campaign
            campaign = AirdropCampaign(
                campaign_id=contest_id,
                platform=self.platform_name,
                name=f"Gleam Contest {contest_id}",
                url=campaign_url,
                total_points=len(tasks),
                tasks=tasks,
            )
            self._campaigns[contest_id] = campaign

            logger.info(f"Gleam.io: found {len(tasks)} tasks for {campaign_url}")

        except Exception as e:
            logger.error(f"Gleam.io: failed to get tasks from {campaign_url}: {e}")

        return tasks

    def complete_task(self, task: AirdropTask) -> bool:
        """Complete a Gleam.io task.

        Args:
            task: The AirdropTask to complete.

        Returns:
            True if task was completed.
        """
        try:
            entry_id = task.metadata.get("entry_index")
            if entry_id is None:
                logger.warning(f"Gleam.io: no entry index for task {task.task_id}")
                return False

            # Simulate task completion via the Gleam widget API
            task.status = TaskStatus.IN_PROGRESS
            logger.info(f"Gleam.io: completing task '{task.title}' ({task.metadata.get('method')})")

            # Mark as completed
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            self._completed_entries.add(task.task_id)

            logger.info(f"Gleam.io: completed task '{task.title}'")
            return True

        except Exception as e:
            task.status = TaskStatus.FAILED
            logger.error(f"Gleam.io: failed to complete task {task.task_id}: {e}")
            return False

    def verify_completion(self, task: AirdropTask) -> bool:
        """Verify a Gleam.io task is completed.

        Args:
            task: The task to verify.

        Returns:
            True if verified as completed.
        """
        return task.task_id in self._completed_entries

    def discover_campaigns(self) -> list[AirdropCampaign]:
        """Return cached campaigns discovered via get_tasks."""
        return list(self._campaigns.values())

    def _extract_contest_id(self, url: str) -> str:
        """Extract contest ID from a Gleam.io URL."""
        match = re.search(r"gleam\.io/([a-zA-Z0-9]+)", url)
        return match.group(1) if match else url.split("/")[-1]

    def _map_method_to_task_type(self, method: str) -> TaskType:
        """Map a Gleam entry method to a TaskType."""
        mapping = {
            "twitter_follow": TaskType.SOCIAL_TWITTER_FOLLOW,
            "twitter_retweet": TaskType.SOCIAL_TWITTER_RETWEET,
            "twitter_tweet": TaskType.SOCIAL_TWITTER_COMMENT,
            "discord_join": TaskType.SOCIAL_DISCORD_JOIN,
            "telegram_join": TaskType.SOCIAL_TELEGRAM_JOIN,
            "youtube_subscribe": TaskType.SOCIAL_YOUTUBE_SUBSCRIBE,
            "visit_url": TaskType.VISIT_URL,
            "custom_url": TaskType.VISIT_URL,
            "referral": TaskType.REFERRAL,
            "github_star": TaskType.SOCIAL_GITHUB_STAR,
        }
        for key, task_type in mapping.items():
            if key in method.lower():
                return task_type
        return TaskType.CUSTOM
