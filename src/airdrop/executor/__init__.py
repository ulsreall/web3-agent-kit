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

# New platform executors
from .base_executor import (
    BasePlatformExecutor,
    ExecutorConfig,
    ExecutorResult,
    PlatformTask,
    TaskDifficulty,
)
from .captcha_solver import (
    CaptchaSolver,
    CaptchaConfig,
    CaptchaProvider,
    CaptchaSolvingError,
)
from .questn import QuestNExecutor, QuestNTask, QuestNResult
from .taskon import TaskOnExecutor, TaskOnTask, TaskOnResult
from .intract_exec import IntractExecutor, IntractTask, IntractResult
from .port3_exec import Port3Executor, Port3Task, Port3Result
from .galxe_exec import GalxeExecutor, GalxeTask, GalxeResult
from .layer3_exec import Layer3Executor, Layer3Task, Layer3Result
from .plugin_registry import PlatformPluginRegistry

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
    # Base executor
    "BasePlatformExecutor",
    "ExecutorConfig",
    "ExecutorResult",
    "PlatformTask",
    "TaskDifficulty",
    # CAPTCHA
    "CaptchaSolver",
    "CaptchaConfig",
    "CaptchaProvider",
    "CaptchaSolvingError",
    # QuestN
    "QuestNExecutor",
    "QuestNTask",
    "QuestNResult",
    # TaskOn
    "TaskOnExecutor",
    "TaskOnTask",
    "TaskOnResult",
    # Intract
    "IntractExecutor",
    "IntractTask",
    "IntractResult",
    # Port3
    "Port3Executor",
    "Port3Task",
    "Port3Result",
    # Galxe
    "GalxeExecutor",
    "GalxeTask",
    "GalxeResult",
    # Layer3
    "Layer3Executor",
    "Layer3Task",
    "Layer3Result",
    # Plugin Registry
    "PlatformPluginRegistry",
]
