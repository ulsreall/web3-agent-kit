"""Base platform executor — abstract class for all airdrop platform executors.

Provides a common interface with built-in rate limiting, retry logic,
logging, and progress tracking. All platform executors extend this class.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import requests

from ..base import AirdropTask, TaskStatus, TaskType

logger = logging.getLogger(__name__)


class TaskDifficulty(Enum):
    """Difficulty level of a platform task."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class PlatformTask:
    """A task discovered on a platform."""
    task_id: str
    title: str
    description: str = ""
    task_type: str = "custom"
    url: str = ""
    points: int = 0
    is_completed: bool = False
    is_claimable: bool = False
    difficulty: TaskDifficulty = TaskDifficulty.EASY
    metadata: dict = field(default_factory=dict)

    def to_airdrop_task(self, platform: str) -> AirdropTask:
        """Convert to an AirdropTask."""
        type_map = {
            "twitter_follow": TaskType.SOCIAL_TWITTER_FOLLOW,
            "twitter_retweet": TaskType.SOCIAL_TWITTER_RETWEET,
            "twitter_like": TaskType.SOCIAL_TWITTER_LIKE,
            "twitter_comment": TaskType.SOCIAL_TWITTER_COMMENT,
            "discord_join": TaskType.SOCIAL_DISCORD_JOIN,
            "discord_verify": TaskType.SOCIAL_DISCORD_VERIFY,
            "telegram_join": TaskType.SOCIAL_TELEGRAM_JOIN,
            "youtube_subscribe": TaskType.SOCIAL_YOUTUBE_SUBSCRIBE,
            "github_star": TaskType.SOCIAL_GITHUB_STAR,
            "github_fork": TaskType.SOCIAL_GITHUB_FORK,
            "on_chain_tx": TaskType.ON_CHAIN_TX,
            "on_chain_swap": TaskType.ON_CHAIN_SWAP,
            "on_chain_bridge": TaskType.ON_CHAIN_BRIDGE,
            "on_chain_stake": TaskType.ON_CHAIN_STAKE,
            "quiz": TaskType.QUIZ,
            "visit_url": TaskType.VISIT_URL,
            "wallet_connect": TaskType.WALLET_CONNECT,
            "referral": TaskType.REFERRAL,
        }
        return AirdropTask(
            task_id=f"{platform}_{self.task_id}",
            platform=platform,
            task_type=type_map.get(self.task_type, TaskType.CUSTOM),
            title=self.title,
            description=self.description,
            url=self.url,
            points=self.points,
            status=TaskStatus.COMPLETED if self.is_completed else TaskStatus.PENDING,
            metadata=self.metadata,
        )


@dataclass
class ExecutorResult:
    """Result of running an executor."""
    platform: str
    url: str
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    points_earned: int = 0
    tasks: list[PlatformTask] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_tasks == 0:
            return 0.0
        return self.completed_tasks / self.total_tasks

    @property
    def is_fully_completed(self) -> bool:
        """Check if all tasks are completed."""
        return self.completed_tasks == self.total_tasks and self.total_tasks > 0


@dataclass
class ExecutorConfig:
    """Configuration for a platform executor."""
    rate_limit_delay: float = 2.0
    max_retries: int = 3
    retry_delay: float = 5.0
    timeout: int = 30
    proxy: Optional[str] = None
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    captcha_api_key: Optional[str] = None
    captcha_provider: str = "anticaptcha"
    verbose: bool = False


class BasePlatformExecutor(ABC):
    """Abstract base class for all platform executors.

    Provides common functionality: session management, rate limiting,
    retry logic, logging, and progress tracking.

    Subclasses must implement:
        - visit(url): Navigate to the platform
        - get_tasks(): Discover available tasks
        - complete_task(task): Execute a single task

    Optional overrides:
        - complete_all(): Complete all tasks (has default implementation)
        - verify(): Verify task completion
        - get_results(): Return results
        - login(credentials): Authenticate

    Example::

        class MyPlatform(BasePlatformExecutor):
            platform_name = "my_platform"

            def visit(self, url):
                self._url = url
                return True

            def get_tasks(self):
                return [PlatformTask(task_id="1", title="Do something")]

            def complete_task(self, task):
                return True
    """

    platform_name: str = "unknown"
    platform_url: str = ""
    supported_task_types: list[str] = []

    def __init__(self, config: Optional[ExecutorConfig] = None):
        """Initialize the executor.

        Args:
            config: Optional executor configuration.
        """
        self.config = config or ExecutorConfig()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.config.user_agent})
        if self.config.proxy:
            self.session.proxies = {
                "http": self.config.proxy,
                "https": self.config.proxy,
            }
        self._last_request_time: float = 0
        self._current_url: str = ""
        self._tasks: list[PlatformTask] = []
        self._results: ExecutorResult = ExecutorResult(platform=self.platform_name, url="")
        self._progress_callback: Optional[Any] = None
        logger.info(f"Initialized {self.platform_name} executor")

    @abstractmethod
    def visit(self, url: str) -> bool:
        """Navigate to the platform URL.

        Args:
            url: The platform or campaign URL.

        Returns:
            True if navigation succeeded.
        """
        ...

    @abstractmethod
    def get_tasks(self) -> list[PlatformTask]:
        """Discover available tasks on the platform.

        Returns:
            List of PlatformTask objects.
        """
        ...

    @abstractmethod
    def complete_task(self, task: PlatformTask) -> bool:
        """Execute a single task.

        Args:
            task: The task to complete.

        Returns:
            True if task was completed successfully.
        """
        ...

    def complete_all(
        self,
        url: str,
        tracker: Optional[Any] = None,
    ) -> ExecutorResult:
        """Complete all tasks at the given URL.

        Default implementation: visit → get_tasks → complete each task.

        Args:
            url: Platform or campaign URL.
            tracker: Optional AirdropTracker for progress tracking.

        Returns:
            ExecutorResult with completion statistics.
        """
        start_time = time.time()
        self._results = ExecutorResult(platform=self.platform_name, url=url)

        try:
            # Visit the platform
            if not self.visit(url):
                self._results.errors.append(f"Failed to load {url}")
                return self._results

            # Get available tasks
            tasks = self.get_tasks()
            self._results.total_tasks = len(tasks)
            self._results.tasks = tasks

            if not tasks:
                self._results.errors.append("No tasks found")
                return self._results

            logger.info(f"{self.platform_name}: starting {len(tasks)} tasks")

            # Complete each task
            for i, task in enumerate(tasks):
                if task.is_completed:
                    self._results.skipped_tasks += 1
                    continue

                logger.info(
                    f"{self.platform_name}: [{i + 1}/{len(tasks)}] {task.title}"
                )

                # Notify progress callback
                if self._progress_callback:
                    self._progress_callback(i, len(tasks), task.title)

                success = self.complete_task(task)
                if success:
                    self._results.completed_tasks += 1
                    self._results.points_earned += task.points
                    task.is_completed = True

                    if tracker:
                        airdrop_task = task.to_airdrop_task(self.platform_name)
                        tracker.mark_task_completed(airdrop_task)
                else:
                    self._results.failed_tasks += 1
                    self._results.errors.append(f"Failed: {task.title}")

                # Rate limiting between tasks
                self._rate_limit()

        except Exception as e:
            self._results.errors.append(f"Unexpected error: {str(e)}")
            logger.error(f"{self.platform_name}: unexpected error: {e}")
        finally:
            self._results.elapsed_seconds = time.time() - start_time
            logger.info(
                f"{self.platform_name}: finished in {self._results.elapsed_seconds:.1f}s — "
                f"{self._results.completed_tasks}/{self._results.total_tasks} completed"
            )

        return self._results

    def verify(self) -> bool:
        """Verify completion status. Override in subclasses.

        Returns:
            True if verification succeeded.
        """
        return True

    def get_results(self) -> ExecutorResult:
        """Get the current results.

        Returns:
            ExecutorResult object.
        """
        return self._results

    def login(self, credentials: dict) -> bool:
        """Authenticate with the platform. Override if needed.

        Args:
            credentials: Platform-specific credentials.

        Returns:
            True if login succeeded.
        """
        logger.info(f"{self.platform_name}: login not required")
        return True

    def set_progress_callback(self, callback: Any) -> None:
        """Set a progress callback function.

        Args:
            callback: Function(current, total, task_name) called on progress.
        """
        self._progress_callback = callback

    def close(self) -> None:
        """Clean up resources."""
        self.session.close()
        logger.debug(f"{self.platform_name}: closed")

    # ─── Helper Methods ──────────────────────────────────────────

    def _rate_limit(self) -> None:
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
                    retry_after = int(
                        response.headers.get("Retry-After", self.config.retry_delay)
                    )
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
        """Make a GET request."""
        return self._request("GET", url, **kwargs)

    def _post(self, url: str, **kwargs) -> requests.Response:
        """Make a POST request."""
        return self._request("POST", url, **kwargs)

    def _extract_id_from_url(self, url: str) -> str:
        """Extract an ID from a URL. Override for platform-specific parsing."""
        import re
        # Try to find a UUID or alphanumeric ID in the URL
        match = re.search(r"[0-9a-f]{24}", url)
        if match:
            return match.group(0)
        # Fallback: use last path segment
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        return path_parts[-1] if path_parts else "unknown"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
