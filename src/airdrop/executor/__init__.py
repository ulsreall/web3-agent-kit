"""Executor layer — browser automation for airdrop task completion.

Provides real browser-based automation for Gleam.io, Zealy, and social
platform tasks using Playwright with anti-detect capabilities.
"""

from .browser import BrowserManager, BrowserConfig
from .gleam_exec import GleamExecutor, GleamResult, GleamTaskEntry
from .social_exec import (
    TwitterExecutor,
    DiscordExecutor,
    TelegramExecutor,
    SocialExecutorConfig,
)
from .zealy_exec import ZealyExecutor, ZealyResult

__all__ = [
    # Browser
    "BrowserManager",
    "BrowserConfig",
    # Gleam
    "GleamExecutor",
    "GleamResult",
    "GleamTaskEntry",
    # Social
    "TwitterExecutor",
    "DiscordExecutor",
    "TelegramExecutor",
    "SocialExecutorConfig",
    # Zealy
    "ZealyExecutor",
    "ZealyResult",
]
