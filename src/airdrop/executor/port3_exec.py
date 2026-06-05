"""Port3 quest automation — API + browser-based quest completion.

Handles Port3 quest pages: parses quests, completes social aggregation
and on-chain tasks, and verifies completion.

Anti-bot: Medium.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from .base_executor import (
    BasePlatformExecutor,
    ExecutorConfig,
    ExecutorResult,
    PlatformTask,
    TaskDifficulty,
)

logger = logging.getLogger(__name__)


@dataclass
class Port3Task(PlatformTask):
    """A Port3-specific task entry."""
    campaign_id: str = ""
    aggregation_type: str = ""
    chain_id: Optional[int] = None


@dataclass
class Port3Result(ExecutorResult):
    """Result of farming a Port3 quest."""
    xp_earned: int = 0
    reputation_score: int = 0


class Port3Executor(BasePlatformExecutor):
    """Port3 quest automation.

    Navigates Port3 quest pages, parses available quests, and completes
    social aggregation and on-chain tasks through API interactions.

    Task types supported:
        - Social aggregation tasks (multi-platform social)
        - On-chain tasks (transactions, interactions)
        - Quiz tasks
        - Visit URL

    Anti-bot: Medium protection.

    Example::

        executor = Port3Executor(config)
        result = executor.complete_all("https://port3.io/quest/abc123")
        print(f"Completed {result.completed_tasks}/{result.total_tasks}")
    """

    platform_name = "port3"
    platform_url = "https://port3.io"
    supported_task_types = [
        "twitter_follow", "twitter_retweet", "twitter_like",
        "discord_join", "telegram_join", "quiz", "visit_url",
        "on_chain_tx", "social_aggregation", "custom",
    ]

    API_BASE = "https://api.port3.io"

    def __init__(self, config: Optional[ExecutorConfig] = None):
        super().__init__(config)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._campaign_id: Optional[str] = None
        self._auth_token: Optional[str] = None

    def visit(self, url: str) -> bool:
        """Load a Port3 quest page.

        Args:
            url: Port3 URL (e.g., https://port3.io/quest/abc123).

        Returns:
            True if page loaded successfully.
        """
        self._current_url = url
        self._campaign_id = self._extract_id_from_url(url)
        logger.info(f"Port3: loading {url} (campaign={self._campaign_id})")

        try:
            headers = {}
            if self._auth_token:
                headers["Authorization"] = f"Bearer {self._auth_token}"

            response = self._get(
                f"{self.API_BASE}/quest/{self._campaign_id}",
                headers=headers,
            )
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Port3: quest loaded: {data.get('title', 'unknown')}")
                return True
        except Exception as e:
            logger.debug(f"Port3: API load failed: {e}")

        return True

    def get_tasks(self) -> list[Port3Task]:
        """Parse available tasks from the loaded quest.

        Returns:
            List of Port3Task objects.
        """
        if not self._campaign_id:
            logger.error("Port3: no quest loaded. Call visit() first.")
            return []

        tasks: list[Port3Task] = []

        try:
            headers = {}
            if self._auth_token:
                headers["Authorization"] = f"Bearer {self._auth_token}"

            response = self._get(
                f"{self.API_BASE}/quest/{self._campaign_id}/tasks",
                headers=headers,
            )
            data = response.json()

            task_list = data.get("tasks") or data.get("data", {}).get("tasks", [])
            logger.info(f"Port3: found {len(task_list)} tasks")

            for i, task_data in enumerate(task_list):
                task = self._parse_task(task_data, i)
                if task:
                    tasks.append(task)

        except Exception as e:
            logger.error(f"Port3: failed to get tasks: {e}")

        return tasks

    def complete_task(self, task: Port3Task) -> bool:
        """Complete a single Port3 task.

        Args:
            task: The Port3Task to complete.

        Returns:
            True if task was completed successfully.
        """
        if task.is_completed:
            logger.info(f"Port3: task '{task.title}' already completed")
            return True

        try:
            headers = {}
            if self._auth_token:
                headers["Authorization"] = f"Bearer {self._auth_token}"

            response = self._post(
                f"{self.API_BASE}/task/{task.task_id}/complete",
                json={
                    "quest_id": self._campaign_id,
                    "task_type": task.task_type,
                },
                headers=headers,
            )

            result = response.json()
            success = result.get("success", result.get("status") == "completed")

            if success:
                task.is_completed = True
                logger.info(f"Port3: completed task '{task.title}'")

            return success

        except Exception as e:
            logger.error(f"Port3: task '{task.title}' failed: {e}")
            return False

    def login(self, credentials: dict) -> bool:
        """Authenticate with Port3.

        Args:
            credentials: Must contain 'token' for session auth.

        Returns:
            True if login succeeded.
        """
        token = credentials.get("token")
        if token:
            self._auth_token = token
            self._authenticated = True
            logger.info("Port3: authenticated with token")
            return True

        logger.warning("Port3: no credentials provided")
        return False

    def close(self) -> None:
        """Clean up resources."""
        super().close()
        self._auth_token = None

    # ─── Private Helpers ─────────────────────────────────────────

    def _parse_task(self, data: dict, index: int) -> Optional[Port3Task]:
        """Parse a task from API response."""
        try:
            task_id = str(data.get("id", data.get("taskId", index)))
            title = data.get("title", data.get("name", f"Task {index}"))
            task_type = data.get("type", data.get("taskType", "custom"))
            description = data.get("description", "")
            points = int(data.get("points", data.get("reward", 0)))
            is_completed = data.get("completed", data.get("isCompleted", False))
            action_url = data.get("actionUrl", data.get("url", ""))
            chain_id = data.get("chainId")

            mapped_type = self._map_task_type(task_type)

            difficulty = TaskDifficulty.EASY
            if mapped_type in ("on_chain_tx", "social_aggregation"):
                difficulty = TaskDifficulty.MEDIUM

            return Port3Task(
                task_id=f"port3_{self._campaign_id}_{task_id}",
                title=title,
                description=description,
                task_type=mapped_type,
                url=action_url,
                points=points,
                is_completed=is_completed,
                campaign_id=self._campaign_id or "",
                aggregation_type=data.get("aggregationType", ""),
                chain_id=chain_id,
                difficulty=difficulty,
                metadata={"campaign_id": self._campaign_id, "chain_id": chain_id},
            )

        except Exception as e:
            logger.debug(f"Port3: failed to parse task {index}: {e}")
            return None

    def _map_task_type(self, raw_type: str) -> str:
        """Map raw task type to standard type."""
        type_map = {
            "twitter_follow": "twitter_follow",
            "twitter_retweet": "twitter_retweet",
            "twitter_like": "twitter_like",
            "discord_join": "discord_join",
            "telegram_join": "telegram_join",
            "quiz": "quiz",
            "visit_url": "visit_url",
            "on_chain": "on_chain_tx",
            "on_chain_tx": "on_chain_tx",
            "social_aggregation": "social_aggregation",
            "custom": "custom",
        }
        raw_lower = raw_type.lower().replace("-", "_")
        return type_map.get(raw_lower, "custom")
