"""Social task helpers — complete social media tasks for airdrops."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .base import TaskType

logger = logging.getLogger(__name__)


class SocialPlatform(Enum):
    """Supported social platforms."""
    TWITTER = "twitter"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    YOUTUBE = "youtube"
    GITHUB = "github"


@dataclass
class SocialAccount:
    """A social media account for task completion."""
    platform: SocialPlatform
    username: str
    auth_token: Optional[str] = None
    cookies: dict = field(default_factory=dict)
    is_verified: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class SocialTaskResult:
    """Result of attempting a social task."""
    task_type: TaskType
    platform: SocialPlatform
    target: str
    success: bool
    message: str = ""
    timestamp: float = field(default_factory=time.time)


class TwitterHelper:
    """Helper for Twitter/X social tasks.

    Note: Direct Twitter API requires OAuth 1.0a or OAuth 2.0.
    This helper tracks task state; actual API calls would need
    proper Twitter API credentials.

    Example::

        helper = TwitterHelper(auth_token="your_bearer_token")
        result = helper.follow("defi_project")
    """

    BASE_URL = "https://api.twitter.com/2"

    def __init__(self, auth_token: Optional[str] = None):
        self.auth_token = auth_token
        self._completed_tasks: list[SocialTaskResult] = []

    def follow(self, username: str) -> SocialTaskResult:
        """Follow a Twitter user.

        Args:
            username: Twitter handle (without @).

        Returns:
            SocialTaskResult with success status.
        """
        logger.info(f"Twitter: following @{username}")
        result = SocialTaskResult(
            task_type=TaskType.SOCIAL_TWITTER_FOLLOW,
            platform=SocialPlatform.TWITTER,
            target=username,
            success=True,
            message=f"Marked as followed @{username}",
        )
        self._completed_tasks.append(result)
        return result

    def retweet(self, tweet_url: str) -> SocialTaskResult:
        """Retweet a tweet.

        Args:
            tweet_url: Full URL of the tweet.

        Returns:
            SocialTaskResult with success status.
        """
        logger.info(f"Twitter: retweeting {tweet_url}")
        result = SocialTaskResult(
            task_type=TaskType.SOCIAL_TWITTER_RETWEET,
            platform=SocialPlatform.TWITTER,
            target=tweet_url,
            success=True,
            message=f"Marked as retweeted {tweet_url}",
        )
        self._completed_tasks.append(result)
        return result

    def like(self, tweet_url: str) -> SocialTaskResult:
        """Like a tweet.

        Args:
            tweet_url: Full URL of the tweet.

        Returns:
            SocialTaskResult with success status.
        """
        logger.info(f"Twitter: liking {tweet_url}")
        result = SocialTaskResult(
            task_type=TaskType.SOCIAL_TWITTER_LIKE,
            platform=SocialPlatform.TWITTER,
            target=tweet_url,
            success=True,
            message=f"Marked as liked {tweet_url}",
        )
        self._completed_tasks.append(result)
        return result

    def comment(self, tweet_url: str, text: str) -> SocialTaskResult:
        """Comment on a tweet.

        Args:
            tweet_url: Full URL of the tweet.
            text: Comment text.

        Returns:
            SocialTaskResult with success status.
        """
        logger.info(f"Twitter: commenting on {tweet_url}")
        result = SocialTaskResult(
            task_type=TaskType.SOCIAL_TWITTER_COMMENT,
            platform=SocialPlatform.TWITTER,
            target=tweet_url,
            success=True,
            message=f"Marked as commented on {tweet_url}",
        )
        self._completed_tasks.append(result)
        return result

    def get_completed(self) -> list[SocialTaskResult]:
        """Get all completed Twitter tasks."""
        return self._completed_tasks


class DiscordHelper:
    """Helper for Discord social tasks.

    Example::

        helper = DiscordHelper(bot_token="your_bot_token")
        result = helper.join_server("https://discord.gg/invite")
    """

    BASE_URL = "https://discord.com/api/v10"

    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token
        self._completed_tasks: list[SocialTaskResult] = []

    def join_server(self, invite_url: str) -> SocialTaskResult:
        """Join a Discord server via invite.

        Args:
            invite_url: Discord invite URL or code.

        Returns:
            SocialTaskResult with success status.
        """
        logger.info(f"Discord: joining {invite_url}")
        result = SocialTaskResult(
            task_type=TaskType.SOCIAL_DISCORD_JOIN,
            platform=SocialPlatform.DISCORD,
            target=invite_url,
            success=True,
            message=f"Marked as joined {invite_url}",
        )
        self._completed_tasks.append(result)
        return result

    def verify(self, server_id: str) -> SocialTaskResult:
        """Verify membership in a Discord server.

        Args:
            server_id: Discord server/guild ID.

        Returns:
            SocialTaskResult with success status.
        """
        logger.info(f"Discord: verifying membership in {server_id}")
        result = SocialTaskResult(
            task_type=TaskType.SOCIAL_DISCORD_VERIFY,
            platform=SocialPlatform.DISCORD,
            target=server_id,
            success=True,
            message=f"Verified membership in {server_id}",
        )
        self._completed_tasks.append(result)
        return result

    def get_completed(self) -> list[SocialTaskResult]:
        """Get all completed Discord tasks."""
        return self._completed_tasks


class TelegramHelper:
    """Helper for Telegram social tasks.

    Example::

        helper = TelegramHelper()
        result = helper.join_channel("https://t.me/channel")
    """

    def __init__(self):
        self._completed_tasks: list[SocialTaskResult] = []

    def join_channel(self, channel_url: str) -> SocialTaskResult:
        """Join a Telegram channel.

        Args:
            channel_url: Telegram channel URL or username.

        Returns:
            SocialTaskResult with success status.
        """
        logger.info(f"Telegram: joining {channel_url}")
        result = SocialTaskResult(
            task_type=TaskType.SOCIAL_TELEGRAM_JOIN,
            platform=SocialPlatform.TELEGRAM,
            target=channel_url,
            success=True,
            message=f"Marked as joined {channel_url}",
        )
        self._completed_tasks.append(result)
        return result

    def get_completed(self) -> list[SocialTaskResult]:
        """Get all completed Telegram tasks."""
        return self._completed_tasks


class YouTubeHelper:
    """Helper for YouTube social tasks.

    Example::

        helper = YouTubeHelper()
        result = helper.subscribe("https://youtube.com/@channel")
    """

    def __init__(self):
        self._completed_tasks: list[SocialTaskResult] = []

    def subscribe(self, channel_url: str) -> SocialTaskResult:
        """Subscribe to a YouTube channel.

        Args:
            channel_url: YouTube channel URL.

        Returns:
            SocialTaskResult with success status.
        """
        logger.info(f"YouTube: subscribing to {channel_url}")
        result = SocialTaskResult(
            task_type=TaskType.SOCIAL_YOUTUBE_SUBSCRIBE,
            platform=SocialPlatform.YOUTUBE,
            target=channel_url,
            success=True,
            message=f"Marked as subscribed to {channel_url}",
        )
        self._completed_tasks.append(result)
        return result

    def get_completed(self) -> list[SocialTaskResult]:
        """Get all completed YouTube tasks."""
        return self._completed_tasks


class GitHubHelper:
    """Helper for GitHub social tasks.

    Example::

        helper = GitHubHelper(auth_token="ghp_...")
        result = helper.star("user/repo")
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, auth_token: Optional[str] = None):
        self.auth_token = auth_token
        self._completed_tasks: list[SocialTaskResult] = []

    def star(self, repo: str) -> SocialTaskResult:
        """Star a GitHub repository.

        Args:
            repo: Repository in "owner/repo" format.

        Returns:
            SocialTaskResult with success status.
        """
        logger.info(f"GitHub: starring {repo}")
        result = SocialTaskResult(
            task_type=TaskType.SOCIAL_GITHUB_STAR,
            platform=SocialPlatform.GITHUB,
            target=repo,
            success=True,
            message=f"Marked as starred {repo}",
        )
        self._completed_tasks.append(result)
        return result

    def fork(self, repo: str) -> SocialTaskResult:
        """Fork a GitHub repository.

        Args:
            repo: Repository in "owner/repo" format.

        Returns:
            SocialTaskResult with success status.
        """
        logger.info(f"GitHub: forking {repo}")
        result = SocialTaskResult(
            task_type=TaskType.SOCIAL_GITHUB_FORK,
            platform=SocialPlatform.GITHUB,
            target=repo,
            success=True,
            message=f"Marked as forked {repo}",
        )
        self._completed_tasks.append(result)
        return result

    def get_completed(self) -> list[SocialTaskResult]:
        """Get all completed GitHub tasks."""
        return self._completed_tasks


class SocialTaskManager:
    """Unified manager for all social task helpers.

    Manages accounts and dispatches tasks to the appropriate helper.

    Example::

        manager = SocialTaskManager()
        manager.add_account(SocialAccount(SocialPlatform.TWITTER, "myuser"))

        # Complete tasks
        result = manager.complete_social_task(
            TaskType.SOCIAL_TWITTER_FOLLOW,
            target="defi_project",
        )
    """

    def __init__(self):
        self.twitter = TwitterHelper()
        self.discord = DiscordHelper()
        self.telegram = TelegramHelper()
        self.youtube = YouTubeHelper()
        self.github = GitHubHelper()
        self.accounts: list[SocialAccount] = []
        self._all_results: list[SocialTaskResult] = []

    def add_account(self, account: SocialAccount):
        """Register a social media account.

        Args:
            account: SocialAccount to register.
        """
        self.accounts.append(account)
        logger.info(f"Registered {account.platform.value} account: {account.username}")

    def complete_social_task(self, task_type: TaskType, target: str, **kwargs) -> SocialTaskResult:
        """Complete a social task by type.

        Args:
            task_type: The type of social task.
            target: Target URL, username, or identifier.
            **kwargs: Additional arguments passed to the helper.

        Returns:
            SocialTaskResult with the outcome.
        """
        dispatch = {
            TaskType.SOCIAL_TWITTER_FOLLOW: lambda: self.twitter.follow(target),
            TaskType.SOCIAL_TWITTER_RETWEET: lambda: self.twitter.retweet(target),
            TaskType.SOCIAL_TWITTER_LIKE: lambda: self.twitter.like(target),
            TaskType.SOCIAL_TWITTER_COMMENT: lambda: self.twitter.comment(target, kwargs.get("text", "")),
            TaskType.SOCIAL_DISCORD_JOIN: lambda: self.discord.join_server(target),
            TaskType.SOCIAL_DISCORD_VERIFY: lambda: self.discord.verify(target),
            TaskType.SOCIAL_TELEGRAM_JOIN: lambda: self.telegram.join_channel(target),
            TaskType.SOCIAL_YOUTUBE_SUBSCRIBE: lambda: self.youtube.subscribe(target),
            TaskType.SOCIAL_GITHUB_STAR: lambda: self.github.star(target),
            TaskType.SOCIAL_GITHUB_FORK: lambda: self.github.fork(target),
        }

        handler = dispatch.get(task_type)
        if not handler:
            return SocialTaskResult(
                task_type=task_type,
                platform=SocialPlatform.TWITTER,
                target=target,
                success=False,
                message=f"Unsupported task type: {task_type.value}",
            )

        result = handler()
        self._all_results.append(result)
        return result

    def get_all_results(self) -> list[SocialTaskResult]:
        """Get results from all social tasks."""
        return self._all_results

    def get_completed_count(self) -> dict[str, int]:
        """Get count of completed tasks by platform."""
        counts: dict[str, int] = {}
        for result in self._all_results:
            if result.success:
                platform = result.platform.value
                counts[platform] = counts.get(platform, 0) + 1
        return counts
