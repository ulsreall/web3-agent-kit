"""TaskOn campaign automation — API + browser-based task completion.

Handles TaskOn campaigns: parses tasks, completes social and on-chain
tasks, and verifies completion.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .base_executor import (
    BasePlatformExecutor,
    ExecutorConfig,
    ExecutorResult,
    PlatformTask,
    TaskDifficulty,
)

logger = logging.getLogger(__name__)


@dataclass
class TaskOnTask(PlatformTask):
    """A TaskOn-specific task entry."""
    campaign_id: str = ""
    task_type_raw: str = ""
    action_data: dict = field(default_factory=dict)
    verification_url: str = ""


@dataclass
class TaskOnResult(ExecutorResult):
    """Result of farming a TaskOn campaign."""
    campaign_name: str = ""
    rewards_claimed: int = 0


class TaskOnExecutor(BasePlatformExecutor):
    """TaskOn campaign automation.

    Navigates TaskOn campaigns, parses available tasks, and completes
    social and on-chain tasks through API interactions.

    Task types supported:
        - Social tasks (Twitter, Discord, Telegram)
        - On-chain tasks (transactions, swaps)
        - Quiz tasks
        - Visit URL
        - Wallet connect

    Anti-bot: Basic protection.

    Example::

        executor = TaskOnExecutor(config)
        result = executor.complete_all("https://taskon.xyz/campaign/abc123")
        print(f"Completed {result.completed_tasks}/{result.total_tasks}")
    """

    platform_name = "taskon"
    platform_url = "https://taskon.xyz"
    supported_task_types = [
        "twitter_follow", "twitter_retweet", "twitter_like",
        "discord_join", "telegram_join", "quiz", "visit_url",
        "on_chain_tx", "wallet_connect", "custom",
    ]

    API_BASE = "https://api.taskon.xyz"

    def __init__(self, config: Optional[ExecutorConfig] = None):
        super().__init__(config)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._campaign_id: Optional[str] = None
        self._campaign_data: Optional[dict] = None

    def visit(self, url: str) -> bool:
        """Load a TaskOn campaign page.

        Args:
            url: TaskOn URL (e.g., https://taskon.xyz/campaign/abc123).

        Returns:
            True if page loaded successfully.
        """
        self._current_url = url
        self._campaign_id = self._extract_id_from_url(url)
        logger.info(f"TaskOn: loading {url} (campaign={self._campaign_id})")

        try:
            response = self._get(
                f"{self.API_BASE}/campaign/{self._campaign_id}",
            )
            if response.status_code == 200:
                self._campaign_data = response.json()
                name = self._campaign_data.get("name", self._campaign_data.get("title", "unknown"))
                logger.info(f"TaskOn: campaign loaded: {name}")
                return True
        except Exception as e:
            logger.debug(f"TaskOn: API load failed: {e}")

        return True

    def get_tasks(self) -> list[TaskOnTask]:
        """Parse available tasks from the loaded campaign.

        Returns:
            List of TaskOnTask objects.
        """
        if not self._campaign_id:
            logger.error("TaskOn: no campaign loaded. Call visit() first.")
            return []

        tasks: list[TaskOnTask] = []

        try:
            response = self._get(
                f"{self.API_BASE}/campaign/{self._campaign_id}/tasks"
            )
            data = response.json()

            task_list = data.get("tasks") or data.get("data", {}).get("tasks", [])
            logger.info(f"TaskOn: found {len(task_list)} tasks")

            for i, task_data in enumerate(task_list):
                task = self._parse_task(task_data, i)
                if task:
                    tasks.append(task)

        except Exception as e:
            logger.error(f"TaskOn: failed to get tasks: {e}")

        return tasks

    def complete_task(self, task: TaskOnTask) -> bool:
        """Complete a single TaskOn task.

        Args:
            task: The TaskOnTask to complete.

        Returns:
            True if task was completed successfully.
        """
        if task.is_completed:
            logger.info(f"TaskOn: task '{task.title}' already completed")
            return True

        try:
            # Submit task completion
            response = self._post(
                f"{self.API_BASE}/task/{task.task_id}/complete",
                json={
                    "campaign_id": self._campaign_id,
                    "task_type": task.task_type,
                    "action_data": task.action_data,
                },
            )

            result = response.json()
            success = result.get("success", result.get("status") == "completed")

            if success:
                task.is_completed = True
                logger.info(f"TaskOn: completed task '{task.title}'")
            else:
                logger.warning(f"TaskOn: task '{task.title}' not verified: {result}")

            return success

        except Exception as e:
            logger.error(f"TaskOn: task '{task.title}' failed: {e}")
            return False

    def close(self) -> None:
        """Clean up resources."""
        super().close()
        self._campaign_data = None

    # ─── Private Helpers ─────────────────────────────────────────

    def _parse_task(self, data: dict, index: int) -> Optional[TaskOnTask]:
        """Parse a task from API response."""
        try:
            task_id = str(data.get("id", data.get("taskId", index)))
            title = data.get("title", data.get("name", f"Task {index}"))
            task_type = data.get("type", data.get("taskType", "custom"))
            description = data.get("description", "")
            points = int(data.get("points", data.get("reward", 0)))
            is_completed = data.get("completed", data.get("isCompleted", False))
            action_url = data.get("actionUrl", data.get("url", ""))

            mapped_type = self._map_task_type(task_type)

            difficulty = TaskDifficulty.EASY
            if mapped_type in ("on_chain_tx", "on_chain_swap", "wallet_connect"):
                difficulty = TaskDifficulty.MEDIUM

            return TaskOnTask(
                task_id=f"taskon_{self._campaign_id}_{task_id}",
                title=title,
                description=description,
                task_type=mapped_type,
                url=action_url,
                points=points,
                is_completed=is_completed,
                campaign_id=self._campaign_id or "",
                task_type_raw=task_type,
                action_data=data.get("actionData", {}),
                verification_url=data.get("verificationUrl", ""),
                difficulty=difficulty,
                metadata={"campaign_id": self._campaign_id},
            )

        except Exception as e:
            logger.debug(f"TaskOn: failed to parse task {index}: {e}")
            return None

    def _map_task_type(self, raw_type: str) -> str:
        """Map raw task type to standard type."""
        type_map = {
            "twitter_follow": "twitter_follow",
            "twitter_retweet": "twitter_retweet",
            "twitter_like": "twitter_like",
            "twitter_tweet": "twitter_comment",
            "discord_join": "discord_join",
            "telegram_join": "telegram_join",
            "quiz": "quiz",
            "visit_url": "visit_url",
            "on_chain": "on_chain_tx",
            "on_chain_tx": "on_chain_tx",
            "wallet_connect": "wallet_connect",
            "custom": "custom",
        }
        raw_lower = raw_type.lower().replace("-", "_")
        return type_map.get(raw_lower, "custom")
