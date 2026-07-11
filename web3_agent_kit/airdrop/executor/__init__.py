"""Executor layer — browser automation for airdrop task completion.

Provides real browser-based automation for Gleam.io, Zealy, and social
platform tasks using Playwright with anti-detect capabilities.
"""

# New platform executors
from .base_executor import (
    BasePlatformExecutor,
    ExecutorConfig,
    ExecutorResult,
    PlatformTask,
    TaskDifficulty,
)
from .browser import BrowserConfig, BrowserManager
from .captcha_solver import (
    CaptchaConfig,
    CaptchaProvider,
    CaptchaSolver,
    CaptchaSolvingError,
)
from .galxe_exec import GalxeExecutor, GalxeResult, GalxeTask
from .gleam_exec import GleamExecutor, GleamResult, GleamTaskEntry
from .intract_exec import IntractExecutor, IntractResult, IntractTask
from .layer3_exec import Layer3Executor, Layer3Result, Layer3Task
from .plugin_registry import PlatformPluginRegistry
from .port3_exec import Port3Executor, Port3Result, Port3Task
from .questn import QuestNExecutor, QuestNResult, QuestNTask
from .social_exec import (
    DiscordExecutor,
    SocialExecutorConfig,
    TelegramExecutor,
    TwitterExecutor,
)
from .taskon import TaskOnExecutor, TaskOnResult, TaskOnTask
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
