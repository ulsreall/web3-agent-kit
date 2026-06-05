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

# Discovery & Automation
from .discovery import CampaignDiscovery, DiscoveryConfig, DiscoveredCampaign
from .onchain import OnChainAirdropFarmer, OnChainConfig, TransactionResult, Chain, DeFiProtocol, FARMING_PLANS
from .scheduler import AirdropScheduler, SchedulerConfig, ScheduledTask, ScheduleFrequency
from .dashboard import PointsDashboard, DashboardConfig, PlatformPoints, PointsSnapshot
from .referral import ReferralManager, ReferralLink, ReferralPlatform, ReferralStats
from .faucet import FaucetClaimer, FaucetConfig, ClaimResult, FAUCETS

# Real Execution
from .form_filler import FormFiller, FormProfile, FormField, FillResult
from .wl_grinder import WLGrinder, WLProfile, WLResult, WLJob

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
    # Multi-wallet
    "AirdropFarmer",
    "SybilAvoidanceConfig",
    "FarmResult",
    "WalletFarmProgress",
    # Discovery
    "CampaignDiscovery",
    "DiscoveryConfig",
    "DiscoveredCampaign",
    # On-chain
    "OnChainAirdropFarmer",
    "OnChainConfig",
    "TransactionResult",
    "Chain",
    "DeFiProtocol",
    "FARMING_PLANS",
    # Scheduler
    "AirdropScheduler",
    "SchedulerConfig",
    "ScheduledTask",
    "ScheduleFrequency",
    # Dashboard
    "PointsDashboard",
    "DashboardConfig",
    "PlatformPoints",
    "PointsSnapshot",
    # Referral
    "ReferralManager",
    "ReferralLink",
    "ReferralPlatform",
    "ReferralStats",
    # Faucet
    "FaucetClaimer",
    "FaucetConfig",
    "ClaimResult",
    "FAUCETS",
    # Form Filler
    "FormFiller",
    "FormProfile",
    "FormField",
    "FillResult",
    # WL Grinder
    "WLGrinder",
    "WLProfile",
    "WLResult",
    "WLJob",
]

__all__ = [
    # Base
    "BaseAirdropPlatform",
    "PlatformConfig",
    "AirdropTask",
    "AirdropCampaign",
    "TaskType",
    "TaskStatus",
    # Platforms
    "GleamCampaign",
    "ZealyPlatform",
    "ZealyQuest",
    "ZealyLeaderboardEntry",
    "GalxePlatform",
    "GalxeCredential",
    "GalxePoints",
    # Social
    "SocialTaskManager",
    "SocialAccount",
    "SocialPlatform",
    "SocialTaskResult",
    # Tracker
    "AirdropTracker",
    "AirdropReward",
    "AirdropSummary",
    # Multi-wallet
    "AirdropFarmer",
    "SybilAvoidanceConfig",
    "FarmResult",
    "WalletFarmProgress",
    # Discovery
    "CampaignDiscovery",
    "DiscoveryConfig",
    "DiscoveredCampaign",
    # On-chain
    "OnChainAirdropFarmer",
    "OnChainConfig",
    "TransactionResult",
    # Scheduler
    "AirdropScheduler",
    "SchedulerConfig",
    "ScheduledTask",
    "ScheduleFrequency",
    # Dashboard
    "PointsDashboard",
    "DashboardConfig",
    "PlatformPoints",
    "PointsSnapshot",
    # Referral
    "ReferralManager",
    "ReferralLink",
    "ReferralPlatform",
    "ReferralStats",
    # Faucet
    "FaucetClaimer",
    "FaucetConfig",
    "ClaimResult",
    # Execution
    "FormFiller",
    "FormProfile",
    "FormField",
    "FillResult",
    "WLGrinder",
    "WLProfile",
    "WLResult",
    "WLJob",
]
