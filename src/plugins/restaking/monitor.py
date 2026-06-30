"""Restaking monitor — track positions, slashing risks, reward claims."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & data classes
# ---------------------------------------------------------------------------

class AlertType(Enum):
    """Types of monitoring alerts."""
    SLASHING = "slashing"
    REWARD_CLAIM = "reward_claim"
    POSITION_CHANGE = "position_change"
    RISK_INCREASE = "risk_increase"
    OPERATOR_OFFLINE = "operator_offline"
    UNLOCK_AVAILABLE = "unlock_available"
    APY_DROP = "apy_drop"
    HIGH_GAS = "high_gas"


@dataclass
class Alert:
    """A monitoring alert."""
    alert_type: AlertType
    severity: str                # "info", "warning", "critical"
    message: str
    protocol: str
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp

    @property
    def is_critical(self) -> bool:
        return self.severity == "critical"


@dataclass
class SlashingEvent:
    """Record of a slashing event."""
    protocol: str
    operator: str
    amount_slashed: float        # In native token
    amount_usd: float
    reason: str
    block_number: int
    timestamp: float
    tx_hash: str = ""
    affected_stakers: int = 0


@dataclass
class MonitoredPosition:
    """A position being tracked by the monitor."""
    position_id: str
    protocol: str
    chain: str
    asset: str
    amount: float
    value_usd: float
    apy: float
    operator: str
    risk_score: float
    lock_end: float               # Timestamp
    rewards_pending: float        # In native token
    rewards_usd: float
    last_updated: float = 0.0
    entry_price_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.last_updated == 0.0:
            self.last_updated = time.time()

    @property
    def pnl_usd(self) -> float:
        """Unrealized PnL in USD."""
        if self.entry_price_usd == 0:
            return 0
        cost_basis = self.amount * self.entry_price_usd
        return self.value_usd + self.rewards_usd - cost_basis

    @property
    def pnl_pct(self) -> float:
        """Unrealized PnL percentage."""
        if self.entry_price_usd == 0:
            return 0
        cost_basis = self.amount * self.entry_price_usd
        if cost_basis == 0:
            return 0
        return (self.pnl_usd / cost_basis) * 100

    @property
    def is_locked(self) -> bool:
        """Whether position is still locked."""
        return self.lock_end > time.time()

    @property
    def lock_remaining_days(self) -> float:
        """Days remaining in lock period."""
        remaining = self.lock_end - time.time()
        return max(remaining / 86400, 0)


@dataclass
class PortfolioSnapshot:
    """Snapshot of the entire restaking portfolio."""
    total_value_usd: float
    total_staked: float
    total_rewards_usd: float
    positions: list[MonitoredPosition]
    alerts: list[Alert]
    protocol_breakdown: dict[str, float]   # protocol -> value USD
    chain_breakdown: dict[str, float]      # chain -> value USD
    avg_apy: float
    total_risk_score: float
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def num_positions(self) -> int:
        return len(self.positions)

    @property
    def total_pnl_usd(self) -> float:
        return sum(p.pnl_usd for p in self.positions)


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class RestakingMonitor:
    """Track restaking positions, slashing risks, and reward claims.

    Maintains a registry of positions across all protocols and
    provides alerting for slashing events, reward claims, and
    risk changes.

    Example::

        monitor = RestakingMonitor()
        monitor.add_position(MonitoredPosition(...))
        snapshot = monitor.get_snapshot()
        alerts = monitor.check_alerts()
    """

    def __init__(
        self,
        slashing_alert_threshold: float = 100.0,  # USD
        apy_drop_threshold: float = 1.0,           # Percentage points
        reward_claim_threshold: float = 50.0,      # USD
    ):
        self.slashing_alert_threshold = slashing_alert_threshold
        self.apy_drop_threshold = apy_drop_threshold
        self.reward_claim_threshold = reward_claim_threshold
        self._positions: dict[str, MonitoredPosition] = {}
        self._alerts: list[Alert] = []
        self._slashing_events: list[SlashingEvent] = []
        self._last_apy: dict[str, float] = {}   # position_id -> last known APY
        self._callbacks: list = []

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def add_position(self, position: MonitoredPosition) -> None:
        """Add a position to monitor."""
        self._positions[position.position_id] = position
        self._last_apy[position.position_id] = position.apy
        logger.info(
            "Monitoring position %s: %s %.4f %s on %s",
            position.position_id, position.protocol, position.amount,
            position.asset, position.chain,
        )

    def remove_position(self, position_id: str) -> bool:
        """Stop monitoring a position."""
        if position_id in self._positions:
            del self._positions[position_id]
            self._last_apy.pop(position_id, None)
            logger.info("Removed position %s from monitoring", position_id)
            return True
        return False

    def update_position(self, position_id: str, **kwargs) -> bool:
        """Update attributes of a monitored position."""
        pos = self._positions.get(position_id)
        if not pos:
            return False

        old_apy = pos.apy
        for key, value in kwargs.items():
            if hasattr(pos, key):
                setattr(pos, key, value)
        pos.last_updated = time.time()

        # Check for APY drop
        if "apy" in kwargs and old_apy - kwargs["apy"] >= self.apy_drop_threshold:
            self._add_alert(Alert(
                alert_type=AlertType.APY_DROP,
                severity="warning",
                message=(
                    f"{pos.protocol} {pos.asset} APY dropped from "
                    f"{old_apy:.2f}% to {kwargs['apy']:.2f}%"
                ),
                protocol=pos.protocol,
            ))

        return True

    @property
    def positions(self) -> list[MonitoredPosition]:
        """All monitored positions."""
        return list(self._positions.values())

    def get_position(self, position_id: str) -> Optional[MonitoredPosition]:
        """Get a specific position."""
        return self._positions.get(position_id)

    # ------------------------------------------------------------------
    # Alerting
    # ------------------------------------------------------------------

    def check_alerts(self, clear: bool = True) -> list[Alert]:
        """Check for new alerts (slashing, unlocks, rewards).

        Args:
            clear: Whether to clear alerts after reading.

        Returns:
            List of alerts since last check.
        """
        self._check_unlocks()
        self._check_high_risk()

        alerts = list(self._alerts)
        if clear:
            self._alerts.clear()
        return alerts

    def _check_unlocks(self) -> None:
        """Check for positions that have unlocked."""
        now = time.time()
        for pos in self._positions.values():
            if 0 < pos.lock_end <= now:
                self._add_alert(Alert(
                    alert_type=AlertType.UNLOCK_AVAILABLE,
                    severity="info",
                    message=f"{pos.protocol} {pos.asset} position {pos.position_id} is now unlocked",
                    protocol=pos.protocol,
                    metadata={"position_id": pos.position_id},
                ))

    def _check_high_risk(self) -> None:
        """Check for positions with elevated risk."""
        for pos in self._positions.values():
            if pos.risk_score > 70:
                self._add_alert(Alert(
                    alert_type=AlertType.RISK_INCREASE,
                    severity="warning",
                    message=(
                        f"{pos.protocol} {pos.asset} risk score elevated to "
                        f"{pos.risk_score:.0f}/100"
                    ),
                    protocol=pos.protocol,
                ))

    def report_slashing(self, event: SlashingEvent) -> None:
        """Record a slashing event and generate alert.

        Args:
            event: The slashing event details.
        """
        self._slashing_events.append(event)
        severity = "critical" if event.amount_usd >= self.slashing_alert_threshold else "warning"

        self._add_alert(Alert(
            alert_type=AlertType.SLASHING,
            severity=severity,
            message=(
                f"🔴 Slashing on {event.protocol}: {event.amount_slashed:.4f} "
                f"(${event.amount_usd:.2f}) — {event.reason}"
            ),
            protocol=event.protocol,
            metadata={
                "operator": event.operator,
                "amount": event.amount_slashed,
                "tx_hash": event.tx_hash,
            },
        ))

        # Update affected positions
        for pos in self._positions.values():
            if pos.protocol == event.protocol:
                if pos.operator == event.operator:
                    pos.risk_score = min(pos.risk_score + 10, 100)

        logger.warning(
            "Slashing event: %s operator %s lost %.4f ($%.2f)",
            event.protocol, event.operator, event.amount_slashed, event.amount_usd,
        )

    def report_reward_claim(
        self,
        position_id: str,
        reward_token: str,
        amount: float,
        value_usd: float,
    ) -> None:
        """Record a reward claim event."""
        pos = self._positions.get(position_id)
        protocol = pos.protocol if pos else "unknown"

        if value_usd >= self.reward_claim_threshold:
            self._add_alert(Alert(
                alert_type=AlertType.REWARD_CLAIM,
                severity="info",
                message=(
                    f"💰 Claimed {amount:.6f} {reward_token} (${value_usd:.2f}) "
                    f"from {protocol}"
                ),
                protocol=protocol,
                metadata={
                    "position_id": position_id,
                    "reward_token": reward_token,
                    "amount": amount,
                    "value_usd": value_usd,
                },
            ))

        if pos:
            pos.rewards_pending = max(pos.rewards_pending - amount, 0)

    def _add_alert(self, alert: Alert) -> None:
        """Add an alert and notify callbacks."""
        self._alerts.append(alert)
        for cb in self._callbacks:
            try:
                cb(alert)
            except Exception as e:
                logger.warning("Alert callback failed: %s", e)

    def on_alert(self, callback) -> None:
        """Register an alert callback.

        Args:
            callback: Callable that receives an Alert object.
        """
        self._callbacks.append(callback)

    # ------------------------------------------------------------------
    # Portfolio snapshot
    # ------------------------------------------------------------------

    def get_snapshot(self) -> PortfolioSnapshot:
        """Generate a snapshot of the current restaking portfolio.

        Returns:
            PortfolioSnapshot with all positions and metrics.
        """
        positions = list(self._positions.values())

        total_value = sum(p.value_usd for p in positions)
        total_staked = sum(p.amount for p in positions)
        total_rewards = sum(p.rewards_usd for p in positions)

        # Protocol breakdown
        proto_breakdown: dict[str, float] = {}
        for p in positions:
            proto_breakdown[p.protocol] = proto_breakdown.get(p.protocol, 0) + p.value_usd

        # Chain breakdown
        chain_breakdown: dict[str, float] = {}
        for p in positions:
            chain_breakdown[p.chain] = chain_breakdown.get(p.chain, 0) + p.value_usd

        # Weighted average APY
        avg_apy = 0.0
        if total_value > 0:
            avg_apy = sum(p.apy * p.value_usd for p in positions) / total_value

        # Weighted risk score
        total_risk = 0.0
        if total_value > 0:
            total_risk = sum(p.risk_score * p.value_usd for p in positions) / total_value

        return PortfolioSnapshot(
            total_value_usd=total_value,
            total_staked=total_staked,
            total_rewards_usd=total_rewards,
            positions=positions,
            alerts=list(self._alerts),
            protocol_breakdown=proto_breakdown,
            chain_breakdown=chain_breakdown,
            avg_apy=avg_apy,
            total_risk_score=total_risk,
        )

    def get_protocol_summary(self) -> list[dict]:
        """Get summary by protocol.

        Returns:
            List of dicts with per-protocol stats.
        """
        by_protocol: dict[str, list[MonitoredPosition]] = {}
        for pos in self._positions.values():
            by_protocol.setdefault(pos.protocol, []).append(pos)

        summaries = []
        for protocol, positions in by_protocol.items():
            total_value = sum(p.value_usd for p in positions)
            total_rewards = sum(p.rewards_usd for p in positions)
            avg_apy = (
                sum(p.apy * p.value_usd for p in positions) / total_value
                if total_value > 0 else 0
            )
            summaries.append({
                "protocol": protocol,
                "positions": len(positions),
                "total_value_usd": total_value,
                "total_rewards_usd": total_rewards,
                "avg_apy": avg_apy,
                "avg_risk": sum(p.risk_score for p in positions) / len(positions),
            })

        summaries.sort(key=lambda x: x["total_value_usd"], reverse=True)
        return summaries

    def get_slashing_history(self) -> list[SlashingEvent]:
        """Get all recorded slashing events."""
        return list(self._slashing_events)

    def get_alerts_by_type(self, alert_type: AlertType) -> list[Alert]:
        """Filter alerts by type."""
        return [a for a in self._alerts if a.alert_type == alert_type]

    def clear_alerts(self) -> None:
        """Clear all alerts."""
        self._alerts.clear()
