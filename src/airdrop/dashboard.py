"""Points Dashboard — track airdrop points across all platforms.

Aggregates points from Galxe, Zealy, Layer3, and other platforms
into a unified dashboard with historical tracking.

Usage::

    from web3_agent_kit.airdrop.dashboard import PointsDashboard

    dashboard = PointsDashboard()
    dashboard.sync_all(wallet="0x...")
    dashboard.print_summary()
    dashboard.export_json("points_report.json")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class PlatformPoints:
    """Points balance on a single platform."""
    platform: str
    points: int = 0
    rank: int = 0
    level: int = 0
    tier: str = ""
    campaigns_completed: int = 0
    campaigns_active: int = 0
    last_activity: Optional[datetime] = None
    streak_days: int = 0
    referrals: int = 0
    referral_points: int = 0
    badges: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def total_with_referrals(self) -> int:
        """Total points including referrals."""
        return self.points + self.referral_points

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "points": self.points,
            "rank": self.rank,
            "level": self.level,
            "tier": self.tier,
            "campaigns_completed": self.campaigns_completed,
            "campaigns_active": self.campaigns_active,
            "streak_days": self.streak_days,
            "referrals": self.referrals,
            "referral_points": self.referral_points,
            "badges": self.badges,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
        }


@dataclass
class PointsSnapshot:
    """A point-in-time snapshot of all platform points."""
    timestamp: datetime
    platforms: dict[str, PlatformPoints] = field(default_factory=dict)

    @property
    def total_points(self) -> int:
        """Total points across all platforms."""
        return sum(p.points for p in self.platforms.values())

    @property
    def total_campaigns(self) -> int:
        """Total campaigns completed across all platforms."""
        return sum(p.campaigns_completed for p in self.platforms.values())

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_points": self.total_points,
            "total_campaigns": self.total_campaigns,
            "platforms": {k: v.to_dict() for k, v in self.platforms.items()},
        }


@dataclass
class DashboardConfig:
    """Configuration for the points dashboard."""
    # Wallet address
    wallet_address: str = ""
    # Platforms to track
    platforms: list[str] = field(default_factory=lambda: [
        "galxe", "zealy", "layer3", "questn", "taskon", "intract", "port3"
    ])
    # API keys (optional, for authenticated endpoints)
    galxe_api_key: str = ""
    # History file
    history_path: Optional[str] = None
    # Proxy
    proxy: Optional[str] = None


class PointsDashboard:
    """Track airdrop points across all platforms.

    Aggregates points from multiple platforms, tracks history,
    and provides reporting/export capabilities.

    Example::

        dashboard = PointsDashboard(config)
        dashboard.sync_all(wallet="0x721e885...A522")
        dashboard.print_summary()
    """

    def __init__(self, config: Optional[DashboardConfig] = None):
        """Initialize the dashboard.

        Args:
            config: Dashboard configuration.
        """
        self.config = config or DashboardConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        if self.config.proxy:
            self.session.proxies = {
                "http": self.config.proxy,
                "https": self.config.proxy,
            }
        self._current: Optional[PointsSnapshot] = None
        self._history: list[PointsSnapshot] = []
        self._load_history()
        logger.info("PointsDashboard initialized")

    def sync_all(self, wallet: Optional[str] = None) -> PointsSnapshot:
        """Sync points from all configured platforms.

        Args:
            wallet: Wallet address (overrides config).

        Returns:
            Current points snapshot.
        """
        address = wallet or self.config.wallet_address
        if not address:
            raise ValueError("Wallet address required")

        platforms: dict[str, PlatformPoints] = {}

        syncers = {
            "galxe": self._sync_galxe,
            "zealy": self._sync_zealy,
            "layer3": self._sync_layer3,
            "questn": self._sync_questn,
            "taskon": self._sync_taskon,
            "intract": self._sync_intract,
            "port3": self._sync_port3,
        }

        for platform in self.config.platforms:
            syncer = syncers.get(platform)
            if not syncer:
                continue
            try:
                points = syncer(address)
                if points:
                    platforms[platform] = points
                    logger.info(f"{platform}: {points.points} points")
            except Exception as e:
                logger.error(f"Failed to sync {platform}: {e}")

        self._current = PointsSnapshot(
            timestamp=datetime.now(timezone.utc),
            platforms=platforms,
        )
        self._history.append(self._current)
        self._save_history()

        logger.info(f"Sync complete: {self._current.total_points} total points")
        return self._current

    def get_current(self) -> Optional[PointsSnapshot]:
        """Get the current points snapshot.

        Returns:
            Current snapshot, or None if not synced.
        """
        return self._current

    def get_history(self, limit: int = 30) -> list[PointsSnapshot]:
        """Get historical snapshots.

        Args:
            limit: Max snapshots to return.

        Returns:
            List of historical snapshots.
        """
        return self._history[-limit:]

    def get_growth(self, days: int = 7) -> dict:
        """Calculate points growth over time.

        Args:
            days: Number of days to look back.

        Returns:
            Growth dict with per-platform and total deltas.
        """
        if len(self._history) < 2:
            return {"total_delta": 0, "platforms": {}}

        now = self._history[-1]
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)

        # Find snapshot closest to cutoff
        old = self._history[0]
        for snap in self._history:
            if snap.timestamp.timestamp() >= cutoff:
                old = snap
                break

        growth: dict[str, Any] = {
            "days": days,
            "total_delta": now.total_points - old.total_points,
            "total_delta_pct": 0.0,
            "platforms": {},
        }

        if old.total_points > 0:
            growth["total_delta_pct"] = round(
                (growth["total_delta"] / old.total_points) * 100, 1
            )

        for platform in set(
            list(now.platforms.keys()) + list(old.platforms.keys())
        ):
            new_pts = now.platforms.get(platform, PlatformPoints(platform)).points
            old_pts = old.platforms.get(platform, PlatformPoints(platform)).points
            delta = new_pts - old_pts
            growth["platforms"][platform] = {
                "current": new_pts,
                "previous": old_pts,
                "delta": delta,
            }

        return growth

    def get_leaderboard_position(self) -> list[dict]:
        """Get estimated leaderboard positions.

        Returns:
            List of platform rankings.
        """
        if not self._current:
            return []

        positions = []
        for platform, points in self._current.platforms.items():
            positions.append({
                "platform": platform,
                "points": points.points,
                "rank": points.rank,
                "tier": points.tier,
            })

        positions.sort(key=lambda x: x["points"], reverse=True)
        return positions

    def print_summary(self) -> str:
        """Print a formatted summary.

        Returns:
            Formatted summary string.
        """
        if not self._current:
            return "Not synced yet. Call sync_all() first."

        lines = [
            "╔══════════════════════════════════════════════════════════╗",
            "║              🏆 AIRDROP POINTS DASHBOARD                ║",
            "╠══════════════════════════════════════════════════════════╣",
            f"║  Wallet: {self.config.wallet_address[:20]}...{' ' * 20}║",
            f"║  Synced: {self._current.timestamp.strftime('%Y-%m-%d %H:%M UTC')}{' ' * 25}║",
            "╠══════════════════════════════════════════════════════════╣",
        ]

        for platform, points in sorted(
            self._current.platforms.items(),
            key=lambda x: x[1].points,
            reverse=True,
        ):
            bar_len = min(30, points.points // 100)
            bar = "█" * bar_len + "░" * (30 - bar_len)
            lines.append(
                f"║  {platform:12} │ {points.points:>8,} pts │ {bar} ║"
            )

        lines.extend([
            "╠══════════════════════════════════════════════════════════╣",
            f"║  TOTAL: {self._current.total_points:>10,} points"
            f"  │  {self._current.total_campaigns} campaigns completed"
            f"  ║",
            "╚══════════════════════════════════════════════════════════╝",
        ])

        summary = "\n".join(lines)
        print(summary)
        return summary

    def export_json(self, path: Optional[str] = None) -> str:
        """Export dashboard data to JSON.

        Args:
            path: Optional file path to save.

        Returns:
            JSON string.
        """
        data = {
            "wallet": self.config.wallet_address,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "current": self._current.to_dict() if self._current else None,
            "history_count": len(self._history),
            "growth_7d": self.get_growth(7),
            "growth_30d": self.get_growth(30),
        }
        json_str = json.dumps(data, indent=2, default=str)

        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json_str)
            logger.info(f"Exported dashboard to {path}")

        return json_str

    def export_markdown(self, path: Optional[str] = None) -> str:
        """Export dashboard as markdown report.

        Args:
            path: Optional file path to save.

        Returns:
            Markdown string.
        """
        if not self._current:
            return "# No data synced yet"

        lines = [
            "# 🏆 Airdrop Points Report",
            "",
            f"**Wallet:** `{self.config.wallet_address}`",
            f"**Synced:** {self._current.timestamp.strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "## Summary",
            "",
            f"- **Total Points:** {self._current.total_points:,}",
            f"- **Campaigns Completed:** {self._current.total_campaigns}",
            "",
            "## Platform Breakdown",
            "",
            "| Platform | Points | Rank | Campaigns | Streak |",
            "|----------|--------|------|-----------|--------|",
        ]

        for platform, points in sorted(
            self._current.platforms.items(),
            key=lambda x: x[1].points,
            reverse=True,
        ):
            lines.append(
                f"| {platform} | {points.points:,} | "
                f"#{points.rank or '-'} | {points.campaigns_completed} | "
                f"{points.streak_days}d |"
            )

        # Growth section
        growth = self.get_growth(7)
        if growth["total_delta"] != 0:
            lines.extend([
                "",
                "## 7-Day Growth",
                "",
                f"- **Total Delta:** +{growth['total_delta']:,} points",
            ])
            for platform, data in growth["platforms"].items():
                if data["delta"] != 0:
                    lines.append(
                        f"- **{platform}:** +{data['delta']:,} "
                        f"({data['current']:,} total)"
                    )

        md = "\n".join(lines)

        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(md)
            logger.info(f"Exported markdown to {path}")

        return md

    # ─── Platform Syncers ─────────────────────────────────────────

    def _sync_galxe(self, wallet: str) -> Optional[PlatformPoints]:
        """Sync Galxe points."""
        try:
            # Galxe GraphQL query for user points
            query = """
            query UserPoints($address: String!) {
              user(address: $address) {
                galxeScore {
                  score
                  rank
                }
                participatedCampaignCount
              }
            }
            """
            resp = self.session.post(
                "https://graphigo.prd.galaxy.eco/query",
                json={"query": query, "variables": {"address": wallet}},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                user = data.get("data", {}).get("user", {})
                score = user.get("galxeScore", {})
                return PlatformPoints(
                    platform="galxe",
                    points=score.get("score", 0),
                    rank=score.get("rank", 0),
                    campaigns_completed=user.get("participatedCampaignCount", 0),
                )
        except Exception as e:
            logger.error(f"Galxe sync error: {e}")
        return None

    def _sync_zealy(self, wallet: str) -> Optional[PlatformPoints]:
        """Sync Zealy points."""
        # Zealy doesn't have a public API for user points
        # Would need to scrape or use hidden API
        return PlatformPoints(platform="zealy")

    def _sync_layer3(self, wallet: str) -> Optional[PlatformPoints]:
        """Sync Layer3 points."""
        try:
            resp = self.session.get(
                f"https://layer3.xyz/api/users/{wallet}/stats",
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                return PlatformPoints(
                    platform="layer3",
                    points=data.get("xp", 0),
                    campaigns_completed=data.get("questsCompleted", 0),
                )
        except Exception as e:
            logger.error(f"Layer3 sync error: {e}")
        return None

    def _sync_questn(self, wallet: str) -> Optional[PlatformPoints]:
        """Sync QuestN points."""
        return PlatformPoints(platform="questn")

    def _sync_taskon(self, wallet: str) -> Optional[PlatformPoints]:
        """Sync TaskOn points."""
        return PlatformPoints(platform="taskon")

    def _sync_intract(self, wallet: str) -> Optional[PlatformPoints]:
        """Sync Intract points."""
        return PlatformPoints(platform="intract")

    def _sync_port3(self, wallet: str) -> Optional[PlatformPoints]:
        """Sync Port3 points."""
        return PlatformPoints(platform="port3")

    # ─── Persistence ──────────────────────────────────────────────

    def _load_history(self) -> None:
        """Load history from file."""
        if not self.config.history_path:
            return
        path = Path(self.config.history_path)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            for snap_data in data.get("snapshots", []):
                platforms = {}
                for k, v in snap_data.get("platforms", {}).items():
                    platforms[k] = PlatformPoints(
                        platform=k,
                        points=v.get("points", 0),
                        rank=v.get("rank", 0),
                        campaigns_completed=v.get("campaigns_completed", 0),
                    )
                self._history.append(PointsSnapshot(
                    timestamp=datetime.fromisoformat(snap_data["timestamp"]),
                    platforms=platforms,
                ))
            logger.info(f"Loaded {len(self._history)} historical snapshots")
        except Exception as e:
            logger.warning(f"Failed to load history: {e}")

    def _save_history(self) -> None:
        """Save history to file."""
        if not self.config.history_path:
            return
        path = Path(self.config.history_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "wallet": self.config.wallet_address,
                "snapshots": [s.to_dict() for s in self._history[-100:]],
            }
            path.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.warning(f"Failed to save history: {e}")
