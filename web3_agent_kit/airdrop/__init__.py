"""Airdrop automation module — discover, track, and complete airdrop campaigns."""

import asyncio
import time as _time

from .base import (
    AirdropCampaign,
    AirdropTask,
    BaseAirdropPlatform,
    PlatformConfig,
    TaskStatus,
    TaskType,
)
from .dashboard import DashboardConfig, PlatformPoints, PointsDashboard, PointsSnapshot

# Discovery & Automation
from .discovery import CampaignDiscovery, DiscoveredCampaign, DiscoveryConfig
from .faucet import FAUCETS, ClaimResult, FaucetClaimer, FaucetConfig

# Real Execution
from .form_filler import FillResult, FormField, FormFiller, FormProfile
from .galxe import GalxeCredential, GalxePlatform, GalxePoints
from .gleam import GleamCampaign
from .multi_wallet import AirdropFarmer, FarmResult, SybilAvoidanceConfig, WalletFarmProgress
from .onchain import (
    FARMING_PLANS,
    Chain,
    DeFiProtocol,
    OnChainAirdropFarmer,
    OnChainConfig,
    TransactionResult,
)
from .referral import ReferralLink, ReferralManager, ReferralPlatform, ReferralStats
from .scheduler import AirdropScheduler, ScheduledTask, ScheduleFrequency, SchedulerConfig
from .social import (
    DiscordHelper,
    GitHubHelper,
    SocialAccount,
    SocialPlatform,
    SocialTaskManager,
    SocialTaskResult,
    TelegramHelper,
    TwitterHelper,
    YouTubeHelper,
)
from .tracker import AirdropReward, AirdropSummary, AirdropTracker
from .wl_grinder import WLGrinder, WLJob, WLProfile, WLResult
from .zealy import ZealyLeaderboardEntry, ZealyPlatform, ZealyQuest

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

# ─── Sleep helpers ─────────────────────────────────────────────

async def async_sleep(seconds: float) -> None:
    """Async sleep wrapper — non-blocking sleep."""
    await asyncio.sleep(seconds)


def sleep(seconds: float) -> None:
    """Sync-compatible fallback sleep.

    Uses asyncio.sleep if an event loop is running and we can
    safely await, otherwise falls back to time.sleep for pure sync
    contexts.
    """
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            raise RuntimeError(
                "Use await async_sleep() instead of sleep() in async context"
            )
    except RuntimeError:
        pass
    _time.sleep(seconds)


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
