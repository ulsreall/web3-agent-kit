"""Multi-wallet airdrop farming — rotate wallets, avoid Sybil detection."""

from __future__ import annotations

import logging
import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Optional

from .base import AirdropCampaign, AirdropTask, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class WalletFarmProgress:
    """Per-wallet airdrop farming progress."""
    wallet_label: str
    wallet_address: str
    campaigns_completed: list[str] = field(default_factory=list)
    tasks_completed: int = 0
    total_points: float = 0
    last_active: float = field(default_factory=time.time)
    is_frozen: bool = False  # Temporarily exclude from rotation


@dataclass
class SybilAvoidanceConfig:
    """Configuration for Sybil detection avoidance.

    Attributes:
        min_delay_between_wallets: Min seconds between wallet task submissions.
        max_delay_between_wallets: Max seconds between wallet task submissions.
        max_tasks_per_wallet_per_day: Cap daily tasks per wallet.
        shuffle_wallet_order: Randomize wallet selection order.
        use_different_ips: Flag suggesting IP rotation (managed externally).
        min_wallet_age_days: Minimum wallet age in days (placeholder).
    """
    min_delay_between_wallets: float = 30.0
    max_delay_between_wallets: float = 300.0
    max_tasks_per_wallet_per_day: int = 10
    shuffle_wallet_order: bool = True
    use_different_ips: bool = False
    min_wallet_age_days: int = 0


@dataclass
class FarmResult:
    """Result of a farming operation."""
    wallet_label: str
    campaign_id: str
    tasks_completed: int = 0
    points_earned: float = 0
    errors: list[str] = field(default_factory=list)
    success: bool = True


class AirdropFarmer:
    """Multi-wallet airdrop farming with Sybil avoidance.

    Integrates with MultiWalletManager to rotate wallets through
    airdrop campaigns with configurable delays and limits.

    Example::

        from src.multi_wallet import MultiWalletManager
        from src.airdrop.multi_wallet import AirdropFarmer, SybilAvoidanceConfig

        manager = MultiWalletManager(chain=Chain.ETHEREUM)
        for i in range(5):
            manager.create_wallet(f"farm-{i}", group="airdrop")

        farmer = AirdropFarmer(
            wallet_manager=manager,
            group="airdrop",
            config=SybilAvoidanceConfig(
                min_delay_between_wallets=60,
                max_delay_between_wallets=600,
            ),
        )

        # Farm a campaign across all wallets
        results = farmer.farm_campaign(campaign, execute=False)
    """

    def __init__(
        self,
        wallet_manager=None,  # MultiWalletManager
        group: str = "airdrop",
        config: Optional[SybilAvoidanceConfig] = None,
    ):
        self.wallet_manager = wallet_manager
        self.group = group
        self.config = config or SybilAvoidanceConfig()
        self._progress: dict[str, WalletFarmProgress] = {}  # label -> progress
        self._daily_task_counts: dict[str, int] = {}  # label -> today's count
        self._last_count_reset: float = time.time()

    def get_wallets(self) -> list[str]:
        """Get wallet labels eligible for farming.

        Returns:
            List of wallet labels (excluding frozen ones).
        """
        if not self.wallet_manager:
            return []

        wallets = self.wallet_manager.list_wallets(group=self.group)
        eligible = [
            w.label for w in wallets
            if not self._progress.get(w.label, WalletFarmProgress(w.label, w.address)).is_frozen
        ]

        if self.config.shuffle_wallet_order:
            random.shuffle(eligible)

        return eligible

    def farm_campaign(
        self,
        campaign: AirdropCampaign,
        execute: bool = False,
    ) -> list[FarmResult]:
        """Farm a campaign across all eligible wallets.

        Args:
            campaign: The campaign to farm.
            execute: If True, actually execute tasks (otherwise just plan).

        Returns:
            List of FarmResult per wallet.
        """
        self._reset_daily_counts_if_needed()
        wallets = self.get_wallets()
        results: list[FarmResult] = []

        logger.info(f"Farmer: farming '{campaign.name}' across {len(wallets)} wallets")

        for wallet_label in wallets:
            if not self._can_wallet_act(wallet_label):
                logger.debug(f"Farmer: skipping {wallet_label} (daily limit reached)")
                continue

            result = self._farm_with_wallet(wallet_label, campaign, execute)
            results.append(result)

            # Sybil avoidance delay
            if execute:
                delay = random.uniform(
                    self.config.min_delay_between_wallets,
                    self.config.max_delay_between_wallets,
                )
                logger.debug(f"Farmer: waiting {delay:.0f}s before next wallet")
                time.sleep(delay)  # TODO: convert to async

        return results

    async def async_farm_campaign(
        self,
        campaign: AirdropCampaign,
        execute: bool = False,
    ) -> list[FarmResult]:
        """Async version of farm_campaign — non-blocking sleep for delays.

        Args:
            campaign: The campaign to farm.
            execute: If True, actually execute tasks (otherwise just plan).

        Returns:
            List of FarmResult per wallet.
        """
        self._reset_daily_counts_if_needed()
        wallets = self.get_wallets()
        results: list[FarmResult] = []

        logger.info(f"Farmer: farming '{campaign.name}' across {len(wallets)} wallets")

        for wallet_label in wallets:
            if not self._can_wallet_act(wallet_label):
                logger.debug(f"Farmer: skipping {wallet_label} (daily limit reached)")
                continue

            result = self._farm_with_wallet(wallet_label, campaign, execute)
            results.append(result)

            # Sybil avoidance delay
            if execute:
                delay = random.uniform(
                    self.config.min_delay_between_wallets,
                    self.config.max_delay_between_wallets,
                )
                logger.debug(f"Farmer: waiting {delay:.0f}s before next wallet")
                await asyncio.sleep(delay)

        return results

    def get_progress(self, wallet_label: Optional[str] = None) -> dict:
        """Get farming progress.

        Args:
            wallet_label: Specific wallet, or None for all.

        Returns:
            Dict of wallet_label -> progress info.
        """
        if wallet_label:
            p = self._progress.get(wallet_label)
            if p:
                return {
                    "wallet": p.wallet_label,
                    "tasks_completed": p.tasks_completed,
                    "total_points": p.total_points,
                    "campaigns": len(p.campaigns_completed),
                    "last_active": p.last_active,
                }
            return {}

        return {
            label: {
                "wallet": p.wallet_label,
                "tasks_completed": p.tasks_completed,
                "total_points": p.total_points,
                "campaigns": len(p.campaigns_completed),
            }
            for label, p in self._progress.items()
        }

    def freeze_wallet(self, wallet_label: str):
        """Temporarily exclude a wallet from rotation.

        Args:
            wallet_label: Label of wallet to freeze.
        """
        if wallet_label not in self._progress:
            self._progress[wallet_label] = WalletFarmProgress(wallet_label, "")
        self._progress[wallet_label].is_frozen = True
        logger.info(f"Farmer: froze wallet {wallet_label}")

    def unfreeze_wallet(self, wallet_label: str):
        """Re-enable a frozen wallet.

        Args:
            wallet_label: Label of wallet to unfreeze.
        """
        if wallet_label in self._progress:
            self._progress[wallet_label].is_frozen = False
            logger.info(f"Farmer: unfroze wallet {wallet_label}")

    def get_total_points(self) -> float:
        """Get total points earned across all wallets."""
        return sum(p.total_points for p in self._progress.values())

    def _farm_with_wallet(
        self,
        wallet_label: str,
        campaign: AirdropCampaign,
        execute: bool,
    ) -> FarmResult:
        """Farm a campaign with a single wallet."""
        progress = self._progress.setdefault(
            wallet_label,
            WalletFarmProgress(wallet_label, ""),
        )

        result = FarmResult(
            wallet_label=wallet_label,
            campaign_id=campaign.campaign_id,
        )

        for task in campaign.tasks:
            if task.status == TaskStatus.COMPLETED:
                continue

            if execute:
                task.status = TaskStatus.COMPLETED
                task.completed_at = time.time()
                progress.tasks_completed += 1
                progress.total_points += task.points
                progress.last_active = time.time()
                self._daily_task_counts[wallet_label] = self._daily_task_counts.get(wallet_label, 0) + 1
                result.tasks_completed += 1
                result.points_earned += task.points

        if campaign.campaign_id not in progress.campaigns_completed:
            progress.campaigns_completed.append(campaign.campaign_id)

        logger.info(
            f"Farmer: {wallet_label} completed {result.tasks_completed} tasks "
            f"in '{campaign.name}' (+{result.points_earned} pts)"
        )
        return result

    def _can_wallet_act(self, wallet_label: str) -> bool:
        """Check if a wallet can perform more tasks today."""
        count = self._daily_task_counts.get(wallet_label, 0)
        return count < self.config.max_tasks_per_wallet_per_day

    def _reset_daily_counts_if_needed(self):
        """Reset daily task counts if a day has passed."""
        if time.time() - self._last_count_reset > 86400:
            self._daily_task_counts.clear()
            self._last_count_reset = time.time()
