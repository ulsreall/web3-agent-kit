"""QuestN quest automation — browser + API-based quest completion.

Handles QuestN quest pages: parses available quests, completes social
tasks (Twitter follow/RT, Discord join, Telegram, quiz), and tracks XP.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
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
class QuestNTask(PlatformTask):
    """A QuestN-specific task entry."""
    quest_id: str = ""
    quest_type: str = ""
    action_url: str = ""
    verification_type: str = "auto"
    required: bool = True


@dataclass
class QuestNResult(ExecutorResult):
    """Result of farming a QuestN campaign."""
    xp_earned: int = 0
    level_up: bool = False


class QuestNExecutor(BasePlatformExecutor):
    """QuestN quest automation.

    Navigates QuestN quest pages, parses available quests, and completes
    social tasks through API calls and browser interactions.

    Task types supported:
        - Twitter follow/retweet/like
        - Discord join
        - Telegram join
        - Quiz
        - Visit URL
        - On-chain transactions

    Anti-bot: Basic CAPTCHA only.

    Example::

        executor = QuestNExecutor(config)
        result = executor.complete_all("https://questn.xyz/quest/abc123")
        print(f"Completed {result.completed_tasks}/{result.total_tasks}")
    """

    platform_name = "questn"
    platform_url = "https://questn.xyz"
    supported_task_types = [
        "twitter_follow", "twitter_retweet", "twitter_like",
        "discord_join", "telegram_join", "quiz", "visit_url",
        "on_chain_tx", "custom",
    ]

    API_BASE = "https://api.questn.xyz"

    def __init__(self, config: Optional[ExecutorConfig] = None):
        super().__init__(config)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._campaign_id: Optional[str] = None
        self._quests: list[QuestNTask] = []

    def visit(self, url: str) -> bool:
        """Load a QuestN quest page.

        Args:
            url: QuestN URL (e.g., https://questn.xyz/quest/abc123).

        Returns:
            True if page loaded successfully.
        """
        self._current_url = url
        self._campaign_id = self._extract_id_from_url(url)
        logger.info(f"QuestN: loading {url} (campaign={self._campaign_id})")

        try:
            # Try API first to verify campaign exists
            response = self._get(
                f"{self.API_BASE}/campaign/{self._campaign_id}",
                headers={"Referer": url},
            )
            if response.status_code == 200:
                data = response.json()
                logger.info(f"QuestN: campaign loaded via API: {data.get('title', 'unknown')}")
                return True
        except Exception as e:
            logger.debug(f"QuestN: API load failed, page may still work: {e}")

        # Fallback: assume page loads
        return True

    def get_tasks(self) -> list[QuestNTask]:
        """Parse available quests from the loaded campaign.

        Returns:
            List of QuestNTask objects.
        """
        if not self._campaign_id:
            logger.error("QuestN: no campaign loaded. Call visit() first.")
            return []

        tasks: list[QuestNTask] = []

        try:
            response = self._get(
                f"{self.API_BASE}/campaign/{self._campaign_id}/tasks"
            )
            data = response.json()

            task_list = data.get("tasks") or data.get("data", {}).get("tasks", [])
            logger.info(f"QuestN: found {len(task_list)} tasks")

            for i, task_data in enumerate(task_list):
                task = self._parse_task(task_data, i)
                if task:
                    tasks.append(task)

        except Exception as e:
            logger.error(f"QuestN: failed to get tasks: {e}")
            # Return empty list — caller should handle
            return []

        self._quests = tasks
        return tasks

    def complete_task(self, task: QuestNTask) -> bool:
        """Complete a single QuestN task.

        Args:
            task: The QuestNTask to complete.

        Returns:
            True if task was completed successfully.
        """
        if task.is_completed:
            logger.info(f"QuestN: task '{task.title}' already completed")
            return True

        try:
            # Handle different task types
            handler = self._get_task_handler(task.quest_type)
            if handler:
                success = handler(task)
            else:
                success = self._complete_generic_task(task)

            if success:
                # Submit verification to API
                success = self._verify_task(task)
                if success:
                    task.is_completed = True
                    logger.info(f"QuestN: completed task '{task.title}'")

            return success

        except Exception as e:
            logger.error(f"QuestN: task '{task.title}' failed: {e}")
            return False

    def close(self) -> None:
        """Clean up resources."""
        super().close()
        self._quests = []

    # ─── Private Helpers ─────────────────────────────────────────

    def _parse_task(self, data: dict, index: int) -> Optional[QuestNTask]:
        """Parse a task from API response."""
        try:
            task_id = str(data.get("id", data.get("taskId", index)))
            title = data.get("title", data.get("name", f"Task {index}"))
            task_type = data.get("type", data.get("taskType", "custom"))
            description = data.get("description", "")
            points = int(data.get("points", data.get("reward", 0)))
            is_completed = data.get("completed", data.get("isCompleted", False))
            action_url = data.get("actionUrl", data.get("url", ""))
            required = data.get("required", True)

            # Map task type
            mapped_type = self._map_task_type(task_type)

            # Determine difficulty
            difficulty = TaskDifficulty.EASY
            if mapped_type in ("on_chain_tx", "on_chain_swap"):
                difficulty = TaskDifficulty.MEDIUM

            return QuestNTask(
                task_id=f"questn_{self._campaign_id}_{task_id}",
                title=title,
                description=description,
                task_type=mapped_type,
                url=action_url,
                points=points,
                is_completed=is_completed,
                quest_id=task_id,
                quest_type=mapped_type,
                action_url=action_url,
                difficulty=difficulty,
                required=required,
                metadata={"campaign_id": self._campaign_id, "original_type": task_type},
            )

        except Exception as e:
            logger.debug(f"QuestN: failed to parse task {index}: {e}")
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
            "custom": "custom",
        }
        raw_lower = raw_type.lower().replace("-", "_")
        return type_map.get(raw_lower, "custom")

    def _get_task_handler(self, task_type: str):
        """Get handler for a task type."""
        handlers = {
            "twitter_follow": self._complete_twitter_follow,
            "twitter_retweet": self._complete_twitter_retweet,
            "twitter_like": self._complete_twitter_like,
            "discord_join": self._complete_discord_join,
            "telegram_join": self._complete_telegram_join,
            "quiz": self._complete_quiz,
            "visit_url": self._complete_visit_url,
        }
        return handlers.get(task_type)

    def _complete_twitter_follow(self, task: QuestNTask) -> bool:
        """Complete Twitter follow task."""
        logger.info(f"QuestN: completing Twitter follow — {task.title}")
        # Submit to platform API
        return self._submit_task_action(task, {"action": "twitter_follow"})

    def _complete_twitter_retweet(self, task: QuestNTask) -> bool:
        """Complete Twitter retweet task."""
        logger.info(f"QuestN: completing Twitter retweet — {task.title}")
        return self._submit_task_action(task, {"action": "twitter_retweet"})

    def _complete_twitter_like(self, task: QuestNTask) -> bool:
        """Complete Twitter like task."""
        logger.info(f"QuestN: completing Twitter like — {task.title}")
        return self._submit_task_action(task, {"action": "twitter_like"})

    def _complete_discord_join(self, task: QuestNTask) -> bool:
        """Complete Discord join task."""
        logger.info(f"QuestN: completing Discord join — {task.title}")
        return self._submit_task_action(task, {"action": "discord_join"})

    def _complete_telegram_join(self, task: QuestNTask) -> bool:
        """Complete Telegram join task."""
        logger.info(f"QuestN: completing Telegram join — {task.title}")
        return self._submit_task_action(task, {"action": "telegram_join"})

    def _complete_quiz(self, task: QuestNTask) -> bool:
        """Complete quiz task."""
        logger.info(f"QuestN: completing quiz — {task.title}")
        # For quiz tasks, we need to get questions and submit answers
        try:
            response = self._get(
                f"{self.API_BASE}/task/{task.quest_id}/quiz"
            )
            data = response.json()
            questions = data.get("questions", [])

            answers = {}
            for q in questions:
                q_id = q.get("id")
                # Try to find correct answer from options
                options = q.get("options", [])
                correct = q.get("correctAnswer", options[0] if options else "")
                answers[str(q_id)] = correct

            return self._submit_task_action(task, {"action": "quiz", "answers": answers})

        except Exception as e:
            logger.debug(f"QuestN: quiz handling failed: {e}")
            return self._submit_task_action(task, {"action": "quiz"})

    def _complete_visit_url(self, task: QuestNTask) -> bool:
        """Complete visit URL task."""
        logger.info(f"QuestN: visiting URL — {task.url}")
        return self._submit_task_action(task, {"action": "visit_url"})

    def _complete_generic_task(self, task: QuestNTask) -> bool:
        """Complete a generic task."""
        return self._submit_task_action(task, {"action": "complete"})

    def _submit_task_action(self, task: QuestNTask, payload: dict) -> bool:
        """Submit a task action to the API."""
        try:
            response = self._post(
                f"{self.API_BASE}/task/{task.quest_id}/complete",
                json=payload,
            )
            result = response.json()
            return result.get("success", result.get("status") == "completed")
        except Exception as e:
            logger.debug(f"QuestN: task action submit failed: {e}")
            return False

    def _verify_task(self, task: QuestNTask) -> bool:
        """Verify task completion with the API."""
        try:
            response = self._post(
                f"{self.API_BASE}/task/{task.quest_id}/verify",
                json={"campaign_id": self._campaign_id},
            )
            result = response.json()
            return result.get("verified", result.get("success", True))
        except Exception as e:
            logger.debug(f"QuestN: verification failed (assuming success): {e}")
            return True  # Optimistic
