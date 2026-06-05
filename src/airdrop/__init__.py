"""Airdrop automation module — discover, track, and complete airdrop campaigns."""

from .base import (
    BaseAirdropPlatform,
    PlatformConfig,
    AirdropTask,
    AirdropCampaign,
    TaskType,
    TaskStatus,
)
from .gleam import GleamCampaign
from .zealy import ZealyPlatform, ZealyQuest, ZealyLeaderboardEntry
from .galxe import GalxePlatform, GalxeCredential, GalxePoints
from .social import (
    SocialTaskManager,
    SocialAccount,
    SocialPlatform,
    SocialTaskResult,
    TwitterHelper,
    DiscordHelper,
    TelegramHelper,
    YouTubeHelper,
    GitHubHelper,
)
from .tracker import AirdropTracker, AirdropReward, AirdropSummary
from .multi_wallet import AirdropFarmer, SybilAvoidanceConfig, FarmResult, WalletFarmProgress

__all__ = [
    # Base
    "BaseAirdropPlatform",
    "PlatformConfig",
    "AirdropTask",
    "AirdropCampaign",
    "TaskType",
    "TaskStatus",
    # Gleam
    "GleamCampaign",
    # Zealy
    "ZealyPlatform",
    "ZealyQuest",
    "ZealyLeaderboardEntry",
    # Galxe
    "GalxePlatform",
    "GalxeCredential",
    "GalxePoints",
    # Social
    "SocialTaskManager",
    "SocialAccount",
    "SocialPlatform",
    "SocialTaskResult",
    "TwitterHelper",
    "DiscordHelper",
    "TelegramHelper",
    "YouTubeHelper",
    "GitHubHelper",
    # Tracker
    "AirdropTracker",
    "AirdropReward",
    "AirdropSummary",
    # Multi-wallet farming
    "AirdropFarmer",
    "SybilAvoidanceConfig",
    "FarmResult",
    "WalletFarmProgress",
]
