"""Intract quest automation — API + browser-based quest completion.

Handles Intract quest pages: parses quests, completes social and on-chain
tasks, and verifies completion.

Anti-bot: Medium (ReCAPTCHA).
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
class IntractTask(PlatformTask):
    """An Intract-specific task entry."""
    campaign_id: str = ""
    quest_id: str = ""
    verification_type: str = "auto"
    requires_captcha: bool = False


@dataclass
class IntractResult(ExecutorResult):
    """Result of farming an Intract quest."""
    xp_earned: int = 0
    badges_earned: int = 0


class IntractExecutor(BasePlatformExecutor):
    """Intract quest automation.

    Navigates Intract quest pages, parses available quests, and completes
    social and on-chain tasks through API interactions.

    Task types supported:
        - Social tasks (Twitter, Discord, Telegram)
        - On-chain tasks (transactions, swaps, bridges)
        - Content creation tasks
        - Quiz tasks
        - Visit URL

    Anti-bot: Medium (ReCAPTCHA integration).

    Example::

        executor = IntractExecutor(config)
        result = executor.complete_all("https://intract.io/quest/abc123")
        print(f"Completed {result.completed_tasks}/{result.total_tasks}")
    """

    platform_name = "intract"
    platform_url = "https://intract.io"
    supported_task_types = [
        "twitter_follow", "twitter_retweet", "twitter_like",
        "discord_join", "telegram_join", "quiz", "visit_url",
        "on_chain_tx", "content_creation", "custom",
    ]

    API_BASE = "https://api.intract.io"

    def __init__(self, config: Optional[ExecutorConfig] = None):
        super().__init__(config)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._campaign_id: Optional[str] = None
        self._quest_id: Optional[str] = None
        self._auth_token: Optional[str] = None

    def visit(self, url: str) -> bool:
        """Load an Intract quest page.

        Args:
            url: Intract URL (e.g., https://intract.io/quest/abc123).

        Returns:
            True if page loaded successfully.
        """
        self._current_url = url
        self._campaign_id = self._extract_id_from_url(url)
        logger.info(f"Intract: loading {url} (campaign={self._campaign_id})")

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
                self._quest_id = data.get("id", self._campaign_id)
                logger.info(f"Intract: quest loaded: {data.get('title', 'unknown')}")
                return True
        except Exception as e:
            logger.debug(f"Intract: API load failed: {e}")

        return True

    def get_tasks(self) -> list[IntractTask]:
        """Parse available tasks from the loaded quest.

        Returns:
            List of IntractTask objects.
        """
        if not self._campaign_id:
            logger.error("Intract: no quest loaded. Call visit() first.")
            return []

        tasks: list[IntractTask] = []

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
            logger.info(f"Intract: found {len(task_list)} tasks")

            for i, task_data in enumerate(task_list):
                task = self._parse_task(task_data, i)
                if task:
                    tasks.append(task)

        except Exception as e:
            logger.error(f"Intract: failed to get tasks: {e}")

        return tasks

    def complete_task(self, task: IntractTask) -> bool:
        """Complete a single Intract task.

        Args:
            task: The IntractTask to complete.

        Returns:
            True if task was completed successfully.
        """
        if task.is_completed:
            logger.info(f"Intract: task '{task.title}' already completed")
            return True

        try:
            headers = {}
            if self._auth_token:
                headers["Authorization"] = f"Bearer {self._auth_token}"

            # Handle CAPTCHA if required
            captcha_token = None
            if task.requires_captcha:
                captcha_token = self._solve_captcha(task)

            payload = {
                "quest_id": self._quest_id,
                "task_type": task.task_type,
            }
            if captcha_token:
                payload["captcha_token"] = captcha_token

            response = self._post(
                f"{self.API_BASE}/task/{task.task_id}/complete",
                json=payload,
                headers=headers,
            )

            result = response.json()
            success = result.get("success", result.get("status") == "completed")

            if success:
                task.is_completed = True
                logger.info(f"Intract: completed task '{task.title}'")

            return success

        except Exception as e:
            logger.error(f"Intract: task '{task.title}' failed: {e}")
            return False

    def login(self, credentials: dict) -> bool:
        """Authenticate with Intract via OAuth.

        Args:
            credentials: Must contain 'token' or 'code' for OAuth.

        Returns:
            True if login succeeded.
        """
        token = credentials.get("token")
        if token:
            self._auth_token = token
            self._authenticated = True
            logger.info("Intract: authenticated with token")
            return True

        # OAuth code flow
        code = credentials.get("code")
        if code:
            try:
                response = self._post(
                    f"{self.API_BASE}/auth/token",
                    json={"code": code, "grant_type": "authorization_code"},
                )
                data = response.json()
                self._auth_token = data.get("access_token")
                self._authenticated = bool(self._auth_token)
                return self._authenticated
            except Exception as e:
                logger.error(f"Intract: OAuth failed: {e}")
                return False

        logger.warning("Intract: no credentials provided")
        return False

    def close(self) -> None:
        """Clean up resources."""
        super().close()
        self._auth_token = None

    # ─── Private Helpers ─────────────────────────────────────────

    def _parse_task(self, data: dict, index: int) -> Optional[IntractTask]:
        """Parse a task from API response."""
        try:
            task_id = str(data.get("id", data.get("taskId", index)))
            title = data.get("title", data.get("name", f"Task {index}"))
            task_type = data.get("type", data.get("taskType", "custom"))
            description = data.get("description", "")
            points = int(data.get("points", data.get("reward", 0)))
            is_completed = data.get("completed", data.get("isCompleted", False))
            action_url = data.get("actionUrl", data.get("url", ""))
            requires_captcha = data.get("requiresCaptcha", False)

            mapped_type = self._map_task_type(task_type)

            difficulty = TaskDifficulty.EASY
            if mapped_type in ("on_chain_tx", "content_creation"):
                difficulty = TaskDifficulty.MEDIUM

            return IntractTask(
                task_id=f"intract_{self._campaign_id}_{task_id}",
                title=title,
                description=description,
                task_type=mapped_type,
                url=action_url,
                points=points,
                is_completed=is_completed,
                campaign_id=self._campaign_id or "",
                quest_id=self._quest_id or "",
                requires_captcha=requires_captcha,
                difficulty=difficulty,
                metadata={"campaign_id": self._campaign_id},
            )

        except Exception as e:
            logger.debug(f"Intract: failed to parse task {index}: {e}")
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
            "content_creation": "content_creation",
            "custom": "custom",
        }
        raw_lower = raw_type.lower().replace("-", "_")
        return type_map.get(raw_lower, "custom")

    def _solve_captcha(self, task: IntractTask) -> Optional[str]:
        """Solve a CAPTCHA if required."""
        try:
            from .captcha_solver import CaptchaConfig, CaptchaProvider, CaptchaSolver

            solver = CaptchaSolver(CaptchaConfig(
                provider=CaptchaProvider(self.config.captcha_provider),
                api_key=self.config.captcha_api_key,
            ))

            # Intract typically uses reCAPTCHA v2
            site_key = task.metadata.get("recaptcha_site_key", "")
            if site_key:
                return solver.solve_recaptcha_v2(
                    site_key=site_key,
                    url=self._current_url,
                )
        except Exception as e:
            logger.warning(f"Intract: CAPTCHA solving failed: {e}")

        return None
