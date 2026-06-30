"""Safety & Governor — spend caps, kill-switch, operator confirmation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

# Re-export notifications (merged from notifications/ module)
from .notif_notifier import Notifier
from .notif_utils import AlertLevel, Notification, NotifierConfig


@dataclass
class SpendLimits:
    """Spend limits for the governor."""

    max_per_tx: float = 1.0        # Max ETH per transaction
    daily_limit: float = 10.0      # Max ETH per day
    session_limit: float = 50.0    # Max ETH per session


@dataclass
class GovernorDecision:
    """Result of a governor authorization check."""

    allowed: bool
    reason: str = ""
    remaining_daily: float = 0.0
    remaining_session: float = 0.0


class SpendGovernor:
    """
    Spend governor — enforces transaction limits and safety caps.

    Features:
    - Per-transaction limits
    - Daily spending limits
    - Session spending limits
    - Kill switch (emergency stop)
    - Operator confirmation gate

    Example:
        governor = SpendGovernor(
            limits=SpendLimits(max_per_tx=0.1, daily_limit=1.0),
            require_confirm=True,
        )
        decision = governor.authorize(tx_value=0.05)
        if decision.allowed:
            # proceed with transaction
    """

    def __init__(
        self,
        limits: Optional[SpendLimits] = None,
        require_confirm: bool = True,
        confirm_fn: Optional[callable] = None,
    ):
        self.limits = limits or SpendLimits()
        self.require_confirm = require_confirm
        self.confirm_fn = confirm_fn

        # Tracking
        self._daily_spent: float = 0.0
        self._session_spent: float = 0.0
        self._daily_reset: float = time.time()
        self._kill_switch: bool = False

    def authorize(self, tx_value: float, action: str = "") -> GovernorDecision:
        """
        Check if a transaction should be authorized.

        Args:
            tx_value: Transaction value in ETH
            action: Description of the action

        Returns:
            GovernorDecision with allowed status and reason
        """
        # Kill switch check
        if self._kill_switch:
            return GovernorDecision(allowed=False, reason="Kill switch activated")

        # Reset daily counter if needed
        if time.time() - self._daily_reset > 86400:
            self._daily_spent = 0.0
            self._daily_reset = time.time()

        # Per-transaction limit
        if tx_value > self.limits.max_per_tx:
            return GovernorDecision(
                allowed=False,
                reason=f"Transaction value {tx_value} exceeds per-tx limit {self.limits.max_per_tx}",
            )

        # Daily limit
        if self._daily_spent + tx_value > self.limits.daily_limit:
            return GovernorDecision(
                allowed=False,
                reason=f"Daily limit reached ({self._daily_spent}/{self.limits.daily_limit})",
                remaining_daily=self.limits.daily_limit - self._daily_spent,
            )

        # Session limit
        if self._session_spent + tx_value > self.limits.session_limit:
            return GovernorDecision(
                allowed=False,
                reason=f"Session limit reached ({self._session_spent}/{self.limits.session_limit})",
                remaining_session=self.limits.session_limit - self._session_spent,
            )

        # Operator confirmation
        if self.require_confirm and self.confirm_fn:
            if not self.confirm_fn({"action": action, "value": tx_value}):
                return GovernorDecision(allowed=False, reason="Operator rejected")

        # Update tracking
        self._daily_spent += tx_value
        self._session_spent += tx_value

        return GovernorDecision(
            allowed=True,
            remaining_daily=self.limits.daily_limit - self._daily_spent,
            remaining_session=self.limits.session_limit - self._session_spent,
        )

    def kill(self):
        """Activate kill switch — blocks all transactions."""
        self._kill_switch = True

    def unkill(self):
        """Deactivate kill switch."""
        self._kill_switch = False

    def get_stats(self) -> dict:
        """Get current spending stats."""
        return {
            "daily_spent": self._daily_spent,
            "daily_limit": self.limits.daily_limit,
            "session_spent": self._session_spent,
            "session_limit": self.limits.session_limit,
            "kill_switch": self._kill_switch,
        }

__all__ = [
    "SpendLimits",
    "GovernorDecision",
    "SpendGovernor",
    "Notifier",
    "NotifierConfig",
    "AlertLevel",
    "Notification",
]
