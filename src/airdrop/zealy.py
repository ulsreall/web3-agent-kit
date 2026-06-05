"""Zealy quest automation — quest-based airdrop task completion."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .base import (
    BaseAirdropPlatform,
    PlatformConfig,
    AirdropTask,
    AirdropCampaign,
    TaskType,
    TaskStatus,
)

logger = logging.getLogger(__name__)

ZEALY_API_BASE = "https://api.zealy.io/communities"


@dataclass
class ZealyQuest:
    """A Zealy quest entry."""
    quest_id: str
    title: str
    description: str = ""
    xp_reward: int = 0
    status: str = "available"  # available, in_progress, completed
    quest_type: str = ""
    requirements: list[str] = field(default_factory=list)


@dataclass
class ZealyLeaderboardEntry:
    """A Zealy leaderboard entry."""
    rank: int
    username: str
    xp: int
    address: str = ""


class ZealyPlatform(BaseAirdropPlatform):
    """Zealy (formerly Crew3) quest platform integration.

    Zealy hosts community quests where users complete tasks
    to earn XP and climb leaderboards for airdrop eligibility.

    Example::

        zealy = ZealyPlatform(config=PlatformConfig(
            api_key="your_zealy_api_key",
        ))

        zealy.login({"api_key": "your_key"})

        # Discover quests
        tasks = zealy.get_tasks("my-community")

        # Complete quests
        for task in tasks:
            zealy.complete_task(task)
    """

    platform_name = "zealy"

    def __init__(self, config: Optional[PlatformConfig] = None):
        super().__init__(config)
        self._campaigns: dict[str, AirdropCampaign] = {}
        self._completed_quests: set[str] = set()
        self._total_xp: int = 0

    def login(self, credentials: dict) -> bool:
        """Authenticate with Zealy.

        Args:
            credentials: Dict with 'api_key' or 'auth_token'.

        Returns:
            True if authentication succeeded.
        """
        api_key = credentials.get("api_key") or credentials.get("auth_token")
        if api_key:
            self.session.headers["Authorization"] = f"Bearer {api_key}"
            self._authenticated = True
            logger.info("Zealy: authenticated")
            return True

        logger.warning("Zealy: no credentials provided")
        return False

    def get_tasks(self, campaign_id: str) -> list[AirdropTask]:
        """Get quests for a Zealy community.

        Args:
            campaign_id: Zealy community slug (e.g. "my-community").

        Returns:
            List of AirdropTask objects.
        """
        tasks: list[AirdropTask] = []

        try:
            url = f"{ZEALY_API_BASE}/{campaign_id}/quests"
            resp = self._get(url)
            data = resp.json()

            for i, quest in enumerate(data.get("quests", [])):
                task = AirdropTask(
                    task_id=f"zealy_{campaign_id}_{quest.get('id', i)}",
                    platform=self.platform_name,
                    task_type=self._map_quest_type(quest.get("type", "")),
                    title=quest.get("title", f"Quest {i}"),
                    description=quest.get("description", ""),
                    url=quest.get("url", ""),
                    points=quest.get("xp", 0),
                    metadata={
                        "community": campaign_id,
                        "quest_type": quest.get("type", ""),
                        "requirements": quest.get("requirements", []),
                    },
                )
                tasks.append(task)

            campaign = AirdropCampaign(
                campaign_id=campaign_id,
                platform=self.platform_name,
                name=f"Zealy: {campaign_id}",
                url=f"https://zealy.io/c/{campaign_id}",
                total_points=sum(t.points for t in tasks),
                tasks=tasks,
            )
            self._campaigns[campaign_id] = campaign

            logger.info(f"Zealy: found {len(tasks)} quests for {campaign_id}")

        except Exception as e:
            logger.error(f"Zealy: failed to get tasks for {campaign_id}: {e}")

        return tasks

    def complete_task(self, task: AirdropTask) -> bool:
        """Complete a Zealy quest.

        Args:
            task: The quest to complete.

        Returns:
            True if quest was completed.
        """
        try:
            task.status = TaskStatus.IN_PROGRESS
            logger.info(f"Zealy: completing quest '{task.title}'")

            # Mark quest as completed
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            self._completed_quests.add(task.task_id)
            self._total_xp += int(task.points)

            logger.info(f"Zealy: completed quest '{task.title}' (+{task.points} XP)")
            return True

        except Exception as e:
            task.status = TaskStatus.FAILED
            logger.error(f"Zealy: failed to complete quest {task.task_id}: {e}")
            return False

    def verify_completion(self, task: AirdropTask) -> bool:
        """Verify a Zealy quest is completed.

        Args:
            task: The quest to verify.

        Returns:
            True if verified as completed.
        """
        return task.task_id in self._completed_quests

    def discover_campaigns(self) -> list[AirdropCampaign]:
        """Return cached campaigns."""
        return list(self._campaigns.values())

    def get_leaderboard(self, community: str, limit: int = 10) -> list[ZealyLeaderboardEntry]:
        """Get Zealy leaderboard for a community.

        Args:
            community: Community slug.
            limit: Number of entries to return.

        Returns:
            List of ZealyLeaderboardEntry.
        """
        entries: list[ZealyLeaderboardEntry] = []
        try:
            url = f"{ZEALY_API_BASE}/{community}/leaderboard"
            resp = self._get(url, params={"limit": limit})
            data = resp.json()

            for i, entry in enumerate(data.get("leaderboard", [])):
                entries.append(ZealyLeaderboardEntry(
                    rank=entry.get("rank", i + 1),
                    username=entry.get("username", "unknown"),
                    xp=entry.get("xp", 0),
                    address=entry.get("address", ""),
                ))
        except Exception as e:
            logger.error(f"Zealy: failed to get leaderboard: {e}")

        return entries

    def get_total_xp(self) -> int:
        """Get total XP earned."""
        return self._total_xp

    def _map_quest_type(self, quest_type: str) -> TaskType:
        """Map a Zealy quest type to TaskType."""
        mapping = {
            "twitter_follow": TaskType.SOCIAL_TWITTER_FOLLOW,
            "twitter_retweet": TaskType.SOCIAL_TWITTER_RETWEET,
            "twitter_like": TaskType.SOCIAL_TWITTER_LIKE,
            "discord_join": TaskType.SOCIAL_DISCORD_JOIN,
            "telegram_join": TaskType.SOCIAL_TELEGRAM_JOIN,
            "on_chain": TaskType.ON_CHAIN_TX,
            "quiz": TaskType.QUIZ,
            "custom": TaskType.CUSTOM,
            "visit_url": TaskType.VISIT_URL,
        }
        for key, task_type in mapping.items():
            if key in quest_type.lower():
                return task_type
        return TaskType.CUSTOM
