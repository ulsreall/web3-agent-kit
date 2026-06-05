"""Base airdrop platform abstraction — common interface for all platforms."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Types of airdrop tasks."""
    SOCIAL_TWITTER_FOLLOW = "twitter_follow"
    SOCIAL_TWITTER_RETWEET = "twitter_retweet"
    SOCIAL_TWITTER_LIKE = "twitter_like"
    SOCIAL_TWITTER_COMMENT = "twitter_comment"
    SOCIAL_DISCORD_JOIN = "discord_join"
    SOCIAL_DISCORD_VERIFY = "discord_verify"
    SOCIAL_TELEGRAM_JOIN = "telegram_join"
    SOCIAL_YOUTUBE_SUBSCRIBE = "youtube_subscribe"
    SOCIAL_GITHUB_STAR = "github_star"
    SOCIAL_GITHUB_FORK = "github_fork"
    ON_CHAIN_TX = "on_chain_tx"
    ON_CHAIN_SWAP = "on_chain_swap"
    ON_CHAIN_BRIDGE = "on_chain_bridge"
    ON_CHAIN_STAKE = "on_chain_stake"
    QUIZ = "quiz"
    VISIT_URL = "visit_url"
    WALLET_CONNECT = "wallet_connect"
    REFERRAL = "referral"
    CUSTOM = "custom"


class TaskStatus(Enum):
    """Status of a task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AirdropTask:
    """A single airdrop task."""
    task_id: str
    platform: str
    task_type: TaskType
    title: str
    description: str = ""
    url: str = ""
    points: float = 0
    status: TaskStatus = TaskStatus.PENDING
    completed_at: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    @property
    def is_social(self) -> bool:
        return self.task_type.name.startswith("SOCIAL_")

    @property
    def is_on_chain(self) -> bool:
        return self.task_type.name.startswith("ON_CHAIN_")


@dataclass
class AirdropCampaign:
    """An airdrop campaign listing."""
    campaign_id: str
    platform: str
    name: str
    description: str = ""
    url: str = ""
    total_points: float = 0
    earned_points: float = 0
    deadline: Optional[float] = None
    tasks: list[AirdropTask] = field(default_factory=list)
    is_active: bool = True
    metadata: dict = field(default_factory=dict)

    @property
    def progress(self) -> float:
        if self.total_points == 0:
            return 0.0
        return self.earned_points / self.total_points

    @property
    def is_expired(self) -> bool:
        if self.deadline is None:
            return False
        return time.time() > self.deadline


@dataclass
class PlatformConfig:
    """Configuration for an airdrop platform."""
    api_key: Optional[str] = None
    session_cookie: Optional[str] = None
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    rate_limit_delay: float = 2.0
    max_retries: int = 3
    retry_delay: float = 5.0
    timeout: int = 30
    proxy: Optional[str] = None


class BaseAirdropPlatform(ABC):
    """Abstract base class for all airdrop platform integrations.

    Provides common functionality: session management, rate limiting,
    retry logic, and the standard interface every platform must implement.

    Example::

        class MyPlatform(BaseAirdropPlatform):
            platform_name = "my_platform"

            def login(self, credentials):
                ...

            def get_tasks(self, campaign_id):
                ...

            def complete_task(self, task):
                ...

            def verify_completion(self, task):
                ...
    """

    platform_name: str = "unknown"

    def __init__(self, config: Optional[PlatformConfig] = None):
        self.config = config or PlatformConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.config.user_agent,
        })
        if self.config.session_cookie:
            self.session.cookies.set("session", self.config.session_cookie)
        if self.config.proxy:
            self.session.proxies = {"http": self.config.proxy, "https": self.config.proxy}
        self._last_request_time: float = 0
        self._authenticated: bool = False
        logger.info(f"Initialized {self.platform_name} platform")

    @abstractmethod
    def login(self, credentials: dict) -> bool:
        """Authenticate with the platform.

        Args:
            credentials: Platform-specific credentials.

        Returns:
            True if login succeeded.
        """
        ...

    @abstractmethod
    def get_tasks(self, campaign_id: str) -> list[AirdropTask]:
        """Get available tasks for a campaign.

        Args:
            campaign_id: Platform-specific campaign identifier.

        Returns:
            List of AirdropTask objects.
        """
        ...

    @abstractmethod
    def complete_task(self, task: AirdropTask) -> bool:
        """Attempt to complete a task.

        Args:
            task: The task to complete.

        Returns:
            True if task was completed successfully.
        """
        ...

    @abstractmethod
    def verify_completion(self, task: AirdropTask) -> bool:
        """Verify that a task is completed.

        Args:
            task: The task to verify.

        Returns:
            True if verified as completed.
        """
        ...

    def discover_campaigns(self) -> list[AirdropCampaign]:
        """Discover available campaigns. Override in subclasses.

        Returns:
            List of AirdropCampaign objects.
        """
        return []

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.config.rate_limit_delay:
            sleep_time = self.config.rate_limit_delay - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> requests.Response:
        """Make an HTTP request with rate limiting and retry logic.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Request URL.
            **kwargs: Passed to requests.

        Returns:
            Response object.

        Raises:
            requests.RequestException: After all retries exhausted.
        """
        kwargs.setdefault("timeout", self.config.timeout)
        last_error = None

        for attempt in range(self.config.max_retries):
            self._rate_limit()
            try:
                response = self.session.request(method, url, **kwargs)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", self.config.retry_delay))
                    logger.warning(f"Rate limited, waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                last_error = e
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (attempt + 1))

        raise last_error  # type: ignore[misc]

    def _get(self, url: str, **kwargs) -> requests.Response:
        return self._request("GET", url, **kwargs)

    def _post(self, url: str, **kwargs) -> requests.Response:
        return self._request("POST", url, **kwargs)
