"""Referral Automation — automate referral chains for airdrops.

Generates and manages referral links, tracks referral trees,
and automates referral-based tasks across platforms.

Usage::

    from web3_agent_kit.airdrop.referral import ReferralManager

    manager = ReferralManager()
    manager.add_platform("galxe", base_url="https://galxe.com/quest/abc", referral_param="ref")
    manager.generate_links(count=10)
    manager.track_referrals()
"""

from __future__ import annotations

import json
import logging
import random
import string
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class ReferralLink:
    """A referral link for a platform."""
    platform: str
    url: str
    code: str
    wallet: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    clicks: int = 0
    conversions: int = 0
    points_earned: int = 0
    is_active: bool = True
    metadata: dict = field(default_factory=dict)

    @property
    def conversion_rate(self) -> float:
        """Calculate conversion rate."""
        if self.clicks == 0:
            return 0.0
        return self.conversions / self.clicks

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "url": self.url,
            "code": self.code,
            "wallet": self.wallet,
            "created_at": self.created_at.isoformat(),
            "clicks": self.clicks,
            "conversions": self.conversions,
            "points_earned": self.points_earned,
            "is_active": self.is_active,
        }


@dataclass
class ReferralPlatform:
    """Platform referral configuration."""
    name: str
    base_url: str
    referral_param: str = "ref"
    reward_per_referral: int = 0
    max_referrals: int = 1000
    requires_wallet: bool = True
    requires_social: bool = False
    min_account_age_days: int = 0
    supported_chains: list[str] = field(default_factory=list)
    api_endpoint: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "referral_param": self.referral_param,
            "reward_per_referral": self.reward_per_referral,
            "max_referrals": self.max_referrals,
            "requires_wallet": self.requires_wallet,
        }


@dataclass
class ReferralStats:
    """Aggregated referral statistics."""
    total_links: int = 0
    active_links: int = 0
    total_clicks: int = 0
    total_conversions: int = 0
    total_points: int = 0
    platforms: dict[str, dict] = field(default_factory=dict)

    @property
    def overall_conversion_rate(self) -> float:
        if self.total_clicks == 0:
            return 0.0
        return self.total_conversions / self.total_clicks

    def to_dict(self) -> dict:
        return {
            "total_links": self.total_links,
            "active_links": self.active_links,
            "total_clicks": self.total_clicks,
            "total_conversions": self.total_conversions,
            "total_points": self.total_points,
            "conversion_rate": round(self.overall_conversion_rate * 100, 2),
            "platforms": self.platforms,
        }


# Known referral platforms
KNOWN_PLATFORMS: dict[str, ReferralPlatform] = {
    "galxe": ReferralPlatform(
        name="Galxe",
        base_url="https://app.galxe.com/quest",
        referral_param="ref",
        reward_per_referral=10,
        max_referrals=500,
        requires_wallet=True,
    ),
    "zealy": ReferralPlatform(
        name="Zealy",
        base_url="https://zealy.io/c",
        referral_param="ref",
        reward_per_referral=5,
        max_referrals=1000,
        requires_wallet=False,
    ),
    "layer3": ReferralPlatform(
        name="Layer3",
        base_url="https://layer3.xyz/quests",
        referral_param="ref",
        reward_per_referral=15,
        max_referrals=200,
        requires_wallet=True,
    ),
    "questn": ReferralPlatform(
        name="QuestN",
        base_url="https://questn.com/detail",
        referral_param="ref",
        reward_per_referral=5,
        max_referrals=500,
        requires_wallet=True,
    ),
    "taskon": ReferralPlatform(
        name="TaskOn",
        base_url="https://taskon.xyz/campaign",
        referral_param="ref",
        reward_per_referral=10,
        max_referrals=300,
        requires_wallet=True,
    ),
    "intract": ReferralPlatform(
        name="Intract",
        base_url="https://intract.io/quest",
        referral_param="ref",
        reward_per_referral=5,
        max_referrals=500,
        requires_wallet=True,
    ),
    "gleam": ReferralPlatform(
        name="Gleam",
        base_url="https://gleam.io",
        referral_param="ref",
        reward_per_referral=0,
        max_referrals=100,
        requires_wallet=False,
        requires_social=True,
    ),
}


class ReferralManager:
    """Manage referral links for airdrop platforms.

    Generates, tracks, and optimizes referral links across platforms.
    Supports referral chains, deduplication, and analytics.

    Example::

        manager = ReferralManager()
        manager.add_platform("galxe", "https://app.galxe.com/quest/abc", "ref")
        links = manager.generate_links(count=10)
        manager.print_stats()
    """

    def __init__(self, wallets: Optional[list[str]] = None):
        """Initialize referral manager.

        Args:
            wallets: List of wallet addresses for referral generation.
        """
        self._wallets = wallets or []
        self._platforms: dict[str, ReferralPlatform] = {}
        self._links: list[ReferralLink] = []
        self._session = requests.Session()
        self._load_state()
        logger.info("ReferralManager initialized")

    def add_platform(
        self,
        name: str,
        base_url: str,
        referral_param: str = "ref",
        reward_per_referral: int = 0,
        **kwargs,
    ) -> ReferralPlatform:
        """Add or configure a referral platform.

        Args:
            name: Platform name.
            base_url: Base URL for referral links.
            referral_param: URL parameter name for referral code.
            reward_per_referral: Points per successful referral.
            **kwargs: Additional platform config.

        Returns:
            The configured ReferralPlatform.
        """
        platform = ReferralPlatform(
            name=name,
            base_url=base_url,
            referral_param=referral_param,
            reward_per_referral=reward_per_referral,
            **kwargs,
        )
        self._platforms[name] = platform
        logger.info(f"Added platform: {name}")
        return platform

    def add_known_platform(self, name: str) -> Optional[ReferralPlatform]:
        """Add a platform from the known platforms list.

        Args:
            name: Platform name (e.g., 'galxe', 'zealy').

        Returns:
            The ReferralPlatform, or None if not found.
        """
        platform = KNOWN_PLATFORMS.get(name)
        if platform:
            self._platforms[name] = platform
            logger.info(f"Added known platform: {name}")
            return platform
        logger.warning(f"Unknown platform: {name}")
        return None

    def generate_links(
        self,
        platform: Optional[str] = None,
        count: int = 1,
        wallet: Optional[str] = None,
    ) -> list[ReferralLink]:
        """Generate referral links.

        Args:
            platform: Specific platform, or None for all.
            count: Number of links per platform.
            wallet: Specific wallet address.

        Returns:
            List of generated ReferralLinks.
        """
        platforms = (
            {platform: self._platforms[platform]}
            if platform and platform in self._platforms
            else self._platforms
        )

        new_links = []
        for name, plat in platforms.items():
            for i in range(count):
                code = self._generate_code()
                w = wallet or (
                    self._wallets[i % len(self._wallets)]
                    if self._wallets
                    else ""
                )
                url = self._build_url(plat, code, w)
                link = ReferralLink(
                    platform=name,
                    url=url,
                    code=code,
                    wallet=w,
                )
                self._links.append(link)
                new_links.append(link)
                logger.info(f"Generated: {name} → {url}")

        self._save_state()
        return new_links

    def generate_chain(
        self,
        platforms: list[str],
        wallet: str,
    ) -> list[ReferralLink]:
        """Generate a referral chain across multiple platforms.

        Creates linked referrals where each platform referral feeds
        into the next, maximizing exposure.

        Args:
            platforms: List of platform names in chain order.
            wallet: Wallet address.

        Returns:
            List of chained ReferralLinks.
        """
        chain = []
        for platform_name in platforms:
            plat = self._platforms.get(platform_name)
            if not plat:
                continue

            code = self._generate_code()
            url = self._build_url(plat, code, wallet)
            link = ReferralLink(
                platform=platform_name,
                url=url,
                code=code,
                wallet=wallet,
                metadata={"chain_position": len(chain)},
            )
            chain.append(link)
            self._links.append(link)

        logger.info(f"Generated chain: {' → '.join(platforms)}")
        self._save_state()
        return chain

    def get_links(
        self,
        platform: Optional[str] = None,
        active_only: bool = True,
    ) -> list[ReferralLink]:
        """Get referral links.

        Args:
            platform: Filter by platform.
            active_only: Only return active links.

        Returns:
            List of ReferralLinks.
        """
        links = self._links
        if platform:
            links = [l for l in links if l.platform == platform]
        if active_only:
            links = [l for l in links if l.is_active]
        return links

    def record_click(self, code: str) -> bool:
        """Record a click on a referral link.

        Args:
            code: Referral code.

        Returns:
            True if code was found and recorded.
        """
        for link in self._links:
            if link.code == code:
                link.clicks += 1
                self._save_state()
                return True
        return False

    def record_conversion(self, code: str, points: int = 0) -> bool:
        """Record a successful referral conversion.

        Args:
            code: Referral code.
            points: Points earned from this referral.

        Returns:
            True if code was found and recorded.
        """
        for link in self._links:
            if link.code == code:
                link.conversions += 1
                link.points_earned += points
                self._save_state()
                return True
        return False

    def deactivate_link(self, code: str) -> bool:
        """Deactivate a referral link.

        Args:
            code: Referral code.

        Returns:
            True if link was deactivated.
        """
        for link in self._links:
            if link.code == code:
                link.is_active = False
                self._save_state()
                return True
        return False

    def get_stats(self) -> ReferralStats:
        """Get aggregated referral statistics.

        Returns:
            ReferralStats with aggregated data.
        """
        stats = ReferralStats(
            total_links=len(self._links),
            active_links=sum(1 for l in self._links if l.is_active),
            total_clicks=sum(l.clicks for l in self._links),
            total_conversions=sum(l.conversions for l in self._links),
            total_points=sum(l.points_earned for l in self._links),
        )

        # Per-platform stats
        for platform in set(l.platform for l in self._links):
            plat_links = [l for l in self._links if l.platform == platform]
            stats.platforms[platform] = {
                "links": len(plat_links),
                "clicks": sum(l.clicks for l in plat_links),
                "conversions": sum(l.conversions for l in plat_links),
                "points": sum(l.points_earned for l in plat_links),
            }

        return stats

    def print_stats(self) -> str:
        """Print formatted referral statistics.

        Returns:
            Formatted stats string.
        """
        stats = self.get_stats()
        lines = [
            "╔══════════════════════════════════════════╗",
            "║         🔗 REFERRAL DASHBOARD            ║",
            "╠══════════════════════════════════════════╣",
            f"║  Links: {stats.total_links} total, {stats.active_links} active",
            f"║  Clicks: {stats.total_clicks}",
            f"║  Conversions: {stats.total_conversions}",
            f"║  Points: {stats.total_points:,}",
            f"║  Rate: {stats.overall_conversion_rate:.1%}",
            "╠══════════════════════════════════════════╣",
        ]

        for platform, data in sorted(
            stats.platforms.items(),
            key=lambda x: x[1]["points"],
            reverse=True,
        ):
            lines.append(
                f"║  {platform:12} │ {data['conversions']:>4} conv │ "
                f"{data['points']:>6,} pts"
            )

        lines.append("╚══════════════════════════════════════════╝")
        summary = "\n".join(lines)
        print(summary)
        return summary

    def export_json(self, path: Optional[str] = None) -> str:
        """Export referral data to JSON.

        Args:
            path: Optional file path to save.

        Returns:
            JSON string.
        """
        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "stats": self.get_stats().to_dict(),
            "links": [l.to_dict() for l in self._links],
            "platforms": {k: v.to_dict() for k, v in self._platforms.items()},
        }
        json_str = json.dumps(data, indent=2, default=str)

        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json_str)
            logger.info(f"Exported referrals to {path}")

        return json_str

    # ─── Helpers ──────────────────────────────────────────────────

    def _generate_code(self, length: int = 8) -> str:
        """Generate a random referral code."""
        chars = string.ascii_letters + string.digits
        return "".join(random.choices(chars, k=length))

    def _build_url(
        self, platform: ReferralPlatform, code: str, wallet: str
    ) -> str:
        """Build a referral URL."""
        separator = "&" if "?" in platform.base_url else "?"
        url = f"{platform.base_url}{separator}{platform.referral_param}={code}"
        if wallet and platform.requires_wallet:
            url += f"&wallet={wallet}"
        return url

    def _load_state(self) -> None:
        """Load state from file."""
        # Could load from JSON file
        pass

    def _save_state(self) -> None:
        """Save state to file."""
        # Could save to JSON file
        pass
