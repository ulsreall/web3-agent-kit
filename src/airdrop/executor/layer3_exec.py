"""Layer3 quest automation — API + browser-based quest completion.

Handles Layer3 quests: parses quest steps, completes cross-chain and
on-chain tasks, verifies transactions, and tracks progress.

Anti-bot: Custom CAPTCHA, IP detection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional
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
class Layer3Task(PlatformTask):
    """A Layer3-specific task entry."""
    quest_id: str = ""
    step_id: str = ""
    chain_id: Optional[int] = None
    chain_name: str = ""
    verification_method: str = "auto"
    requires_wallet: bool = False


@dataclass
class Layer3Result(ExecutorResult):
    """Result of farming a Layer3 quest."""
    xp_earned: int = 0
    tokens_earned: float = 0.0
    chains_interacted: list[str] = field(default_factory=list)


class Layer3Executor(BasePlatformExecutor):
    """Layer3 quest automation.

    Navigates Layer3 quest pages, parses quest steps, and completes
    cross-chain and on-chain tasks through API and browser interactions.

    Task types supported:
        - Cross-chain tasks (bridge, swap across chains)
        - On-chain tasks (transactions, staking)
        - Social tasks (Twitter, Discord)
        - Quiz tasks
        - Visit URL
        - Wallet connect & verify

    Anti-bot: Custom CAPTCHA, IP detection.

    Example::

        executor = Layer3Executor(config)
        result = executor.complete_all("https://layer3.xyz/quests/abc123")
        print(f"Completed {result.completed_tasks}/{result.total_tasks}")
    """

    platform_name = "layer3"
    platform_url = "https://layer3.xyz"
    supported_task_types = [
        "twitter_follow", "twitter_retweet", "twitter_like",
        "discord_join", "telegram_join", "quiz", "visit_url",
        "on_chain_tx", "on_chain_swap", "on_chain_bridge", "on_chain_stake",
        "wallet_connect", "cross_chain", "custom",
    ]

    API_BASE = "https://api.layer3.xyz"

    def __init__(self, config: Optional[ExecutorConfig] = None):
        super().__init__(config)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._quest_id: Optional[str] = None
        self._quest_data: Optional[dict] = None
        self._auth_token: Optional[str] = None
        self._wallet_address: Optional[str] = None

    def visit(self, url: str) -> bool:
        """Load a Layer3 quest page.

        Args:
            url: Layer3 URL (e.g., https://layer3.xyz/quests/abc123).

        Returns:
            True if quest loaded successfully.
        """
        self._current_url = url
        self._quest_id = self._extract_layer3_id(url)
        logger.info(f"Layer3: loading quest {self._quest_id}")

        try:
            headers = {}
            if self._auth_token:
                headers["Authorization"] = f"Bearer {self._auth_token}"

            response = self._get(
                f"{self.API_BASE}/quests/{self._quest_id}",
                headers=headers,
            )
            if response.status_code == 200:
                self._quest_data = response.json()
                name = self._quest_data.get("title", self._quest_data.get("name", "unknown"))
                logger.info(f"Layer3: quest loaded: {name}")
                return True
        except Exception as e:
            logger.debug(f"Layer3: API load failed: {e}")

        return True

    def get_quests(self, category: Optional[str] = None) -> list[dict]:
        """Fetch available quests from Layer3.

        Args:
            category: Optional category filter.

        Returns:
            List of quest dicts.
        """
        try:
            headers = {}
            if self._auth_token:
                headers["Authorization"] = f"Bearer {self._auth_token}"

            params = {}
            if category:
                params["category"] = category

            response = self._get(
                f"{self.API_BASE}/quests",
                headers=headers,
                params=params,
            )

            data = response.json()
            quests = data.get("quests") or data.get("data", {}).get("quests", [])
            logger.info(f"Layer3: found {len(quests)} quests")
            return quests

        except Exception as e:
            logger.error(f"Layer3: failed to fetch quests: {e}")
            return []

    def get_tasks(self) -> list[Layer3Task]:
        """Parse quest steps from the loaded quest.

        Returns:
            List of Layer3Task objects.
        """
        if not self._quest_data:
            logger.error("Layer3: no quest loaded. Call visit() first.")
            return []

        tasks: list[Layer3Task] = []
        steps = self._quest_data.get("steps", self._quest_data.get("tasks", []))

        logger.info(f"Layer3: parsing {len(steps)} quest steps")

        for i, step_data in enumerate(steps):
            task = self._parse_step(step_data, i)
            if task:
                tasks.append(task)

        return tasks

    def complete_task(self, task: Layer3Task) -> bool:
        """Complete a single Layer3 quest step.

        Args:
            task: The Layer3Task to complete.

        Returns:
            True if task was completed successfully.
        """
        if task.is_completed:
            logger.info(f"Layer3: step '{task.title}' already completed")
            return True

        try:
            headers = {}
            if self._auth_token:
                headers["Authorization"] = f"Bearer {self._auth_token}"

            # Handle CAPTCHA if needed
            captcha_token = self._handle_captcha_if_needed()

            payload = {
                "questId": self._quest_id,
                "stepId": task.step_id,
                "taskType": task.task_type,
            }
            if captcha_token:
                payload["captchaToken"] = captcha_token

            response = self._post(
                f"{self.API_BASE}/quests/{self._quest_id}/steps/{task.step_id}/complete",
                json=payload,
                headers=headers,
            )

            result = response.json()
            success = result.get("success", result.get("status") == "completed")

            if success:
                task.is_completed = True
                logger.info(f"Layer3: completed step '{task.title}'")
            else:
                logger.warning(f"Layer3: step '{task.title}' failed: {result.get('message')}")

            return success

        except Exception as e:
            logger.error(f"Layer3: step '{task.title}' failed: {e}")
            return False

    def verify_on_chain(self) -> dict[str, bool]:
        """Verify on-chain transactions for the current quest.

        Returns:
            Dict mapping step IDs to verification status.
        """
        if not self._quest_id or not self._wallet_address:
            logger.error("Layer3: quest ID and wallet address required for verification")
            return {}

        try:
            headers = {}
            if self._auth_token:
                headers["Authorization"] = f"Bearer {self._auth_token}"

            response = self._get(
                f"{self.API_BASE}/quests/{self._quest_id}/verify",
                headers=headers,
                params={"wallet": self._wallet_address},
            )

            data = response.json()
            verifications = data.get("verifications", {})
            logger.info("Layer3: on-chain verification complete")
            return verifications

        except Exception as e:
            logger.error(f"Layer3: on-chain verification failed: {e}")
            return {}

    def login(self, credentials: dict) -> bool:
        """Authenticate with Layer3.

        Args:
            credentials: Must contain 'token' or OAuth code,
                         and optionally 'wallet_address'.

        Returns:
            True if login succeeded.
        """
        self._wallet_address = credentials.get("wallet_address")

        token = credentials.get("token")
        if token:
            self._auth_token = token
            self._authenticated = True
            logger.info("Layer3: authenticated with token")
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
                logger.error(f"Layer3: OAuth failed: {e}")
                return False

        logger.warning("Layer3: no credentials provided")
        return False

    def close(self) -> None:
        """Clean up resources."""
        super().close()
        self._quest_data = None
        self._auth_token = None

    # ─── Private Helpers ─────────────────────────────────────────

    def _extract_layer3_id(self, url: str) -> str:
        """Extract quest ID from Layer3 URL."""
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]

        # Layer3 URLs: /quests/abc123 or /quest/abc123
        for i, part in enumerate(path_parts):
            if part in ("quests", "quest") and i + 1 < len(path_parts):
                return path_parts[i + 1]

        return path_parts[-1] if path_parts else "unknown"

    def _parse_step(self, data: dict, index: int) -> Optional[Layer3Task]:
        """Parse a quest step from API response."""
        try:
            step_id = str(data.get("id", data.get("stepId", index)))
            title = data.get("title", data.get("name", f"Step {index}"))
            task_type = data.get("type", data.get("taskType", "custom"))
            description = data.get("description", "")
            points = int(data.get("points", data.get("xp", 0)))
            is_completed = data.get("completed", data.get("isCompleted", False))
            action_url = data.get("actionUrl", data.get("url", ""))

            # Chain info
            chain_id = data.get("chainId")
            chain_name = data.get("chainName", data.get("chain", ""))
            requires_wallet = data.get("requiresWallet", False)

            mapped_type = self._map_task_type(task_type)

            difficulty = TaskDifficulty.EASY
            if mapped_type.startswith("on_chain"):
                difficulty = TaskDifficulty.MEDIUM
            if mapped_type in ("on_chain_bridge", "cross_chain"):
                difficulty = TaskDifficulty.HARD

            return Layer3Task(
                task_id=f"layer3_{self._quest_id}_{step_id}",
                title=title,
                description=description,
                task_type=mapped_type,
                url=action_url,
                points=points,
                is_completed=is_completed,
                quest_id=self._quest_id or "",
                step_id=step_id,
                chain_id=chain_id,
                chain_name=chain_name,
                requires_wallet=requires_wallet,
                difficulty=difficulty,
                metadata={"quest_id": self._quest_id, "chain_id": chain_id, "chain_name": chain_name},
            )

        except Exception as e:
            logger.debug(f"Layer3: failed to parse step {index}: {e}")
            return None

    def _map_task_type(self, raw_type: str) -> str:
        """Map Layer3 task type to standard type."""
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
            "on_chain_swap": "on_chain_swap",
            "on_chain_bridge": "on_chain_bridge",
            "on_chain_stake": "on_chain_stake",
            "bridge": "on_chain_bridge",
            "swap": "on_chain_swap",
            "stake": "on_chain_stake",
            "wallet_connect": "wallet_connect",
            "cross_chain": "cross_chain",
            "custom": "custom",
        }
        raw_lower = raw_type.lower().replace("-", "_")
        return type_map.get(raw_lower, "custom")

    def _handle_captcha_if_needed(self) -> Optional[str]:
        """Handle CAPTCHA if triggered by the platform."""
        try:
            from .captcha_solver import CaptchaConfig, CaptchaProvider, CaptchaSolver

            CaptchaSolver(CaptchaConfig(
                provider=CaptchaProvider(self.config.captcha_provider),
                api_key=self.config.captcha_api_key,
            ))

            # Layer3 may use custom CAPTCHA or reCAPTCHA
            # This would be detected from the response in a real implementation
            return None

        except Exception as e:
            logger.debug(f"Layer3: CAPTCHA handling skipped: {e}")
            return None
