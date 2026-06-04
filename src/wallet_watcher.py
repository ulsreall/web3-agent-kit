"""Wallet Watcher — Monitor whale wallets and get alerts on large movements."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

from .chain import Chain, ChainManager


class AlertType(Enum):
    """Types of wallet alerts."""
    LARGE_TRANSFER = "large_transfer"
    LARGE_SWAP = "large_swap"
    NEW_TOKEN = "new_token"
    APPROVAL = "approval"
    CONTRACT_INTERACTION = "contract_interaction"
    BALANCE_CHANGE = "balance_change"


class AlertSeverity(Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class WatchedWallet:
    """A wallet being monitored."""
    address: str
    label: str                            # e.g. "vitalik.eth", "whale-01"
    chain: Chain
    tags: list[str] = field(default_factory=list)
    alert_threshold_usd: float = 10000    # Alert on transfers > $10K
    watch_balance: bool = True
    watch_transfers: bool = True
    watch_approvals: bool = False
    is_active: bool = True
    last_checked: float = 0


@dataclass
class WalletAlert:
    """An alert triggered by wallet activity."""
    wallet_address: str
    wallet_label: str
    chain: Chain
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    details: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False


@dataclass
class BalanceSnapshot:
    """Point-in-time balance snapshot."""
    address: str
    chain: Chain
    native_balance: float
    token_balances: dict[str, float]
    total_value_usd: float
    timestamp: float


class WalletWatcher:
    """Monitor whale wallets and alert on significant activity.

    Example::

        watcher = WalletWatcher(chain_manager)

        # Add wallets to watch
        watcher.add_wallet("0xd8dA...6045", "vitalik.eth", Chain.ETHEREUM,
                          alert_threshold_usd=100000)
        watcher.add_wallet("0x28C6...1234", "whale-01", Chain.BASE,
                          tags=["dex-trader"])

        # Check for alerts
        alerts = watcher.check_all()

        # Get balance snapshots
        snapshots = watcher.snapshot_all()

        # Run monitoring loop
        watcher.start(interval=60)
    """

    STORAGE_PATH = os.path.expanduser("~/.web3-agent-kit/watched_wallets.json")

    def __init__(self, chain_manager: ChainManager, storage_path: Optional[str] = None):
        self.chain_manager = chain_manager
        self.wallets: dict[str, WatchedWallet] = {}
        self.alerts: list[WalletAlert] = []
        self.snapshots: dict[str, list[BalanceSnapshot]] = {}  # address -> snapshots
        self._callbacks: list[Callable[[WalletAlert], None]] = []
        self.STORAGE_PATH = storage_path or os.path.expanduser("~/.web3-agent-kit/watched_wallets.json")
        self._load_wallets()

    def add_wallet(
        self,
        address: str,
        label: str,
        chain: Chain,
        tags: Optional[list[str]] = None,
        alert_threshold_usd: float = 10000,
        watch_balance: bool = True,
        watch_transfers: bool = True,
        watch_approvals: bool = False,
    ) -> WatchedWallet:
        """Add a wallet to monitor.

        Args:
            address: Wallet address.
            label: Human-readable label.
            chain: Which chain to monitor.
            tags: Optional tags for categorization.
            alert_threshold_usd: Alert on transfers above this amount.
            watch_balance: Monitor balance changes.
            watch_transfers: Monitor transfers.
            watch_approvals: Monitor token approvals.

        Returns:
            WatchedWallet instance.
        """
        key = f"{address.lower()}:{chain.value}"
        wallet = WatchedWallet(
            address=address,
            label=label,
            chain=chain,
            tags=tags or [],
            alert_threshold_usd=alert_threshold_usd,
            watch_balance=watch_balance,
            watch_transfers=watch_transfers,
            watch_approvals=watch_approvals,
        )
        self.wallets[key] = wallet
        self._save_wallets()
        return wallet

    def remove_wallet(self, address: str, chain: Chain) -> bool:
        """Remove a wallet from monitoring."""
        key = f"{address.lower()}:{chain.value}"
        if key in self.wallets:
            del self.wallets[key]
            self._save_wallets()
            return True
        return False

    def list_wallets(
        self,
        chain: Optional[Chain] = None,
        tag: Optional[str] = None,
        active_only: bool = True,
    ) -> list[WatchedWallet]:
        """List watched wallets with optional filters."""
        result = list(self.wallets.values())
        if active_only:
            result = [w for w in result if w.is_active]
        if chain:
            result = [w for w in result if w.chain == chain]
        if tag:
            result = [w for w in result if tag in w.tags]
        return result

    def check_wallet(self, address: str, chain: Chain) -> list[WalletAlert]:
        """Check a specific wallet for new activity.

        Args:
            address: Wallet address.
            chain: Chain to check.

        Returns:
            List of new alerts.
        """
        key = f"{address.lower()}:{chain.value}"
        wallet = self.wallets.get(key)
        if not wallet or not wallet.is_active:
            return []

        new_alerts = []

        # Check balance
        if wallet.watch_balance:
            balance_alert = self._check_balance(wallet)
            if balance_alert:
                new_alerts.append(balance_alert)

        # Check recent transfers
        if wallet.watch_transfers:
            transfer_alerts = self._check_transfers(wallet)
            new_alerts.extend(transfer_alerts)

        # Update last checked
        wallet.last_checked = time.time()
        self._save_wallets()

        # Store alerts and fire callbacks
        for alert in new_alerts:
            self.alerts.append(alert)
            for cb in self._callbacks:
                try:
                    cb(alert)
                except Exception:
                    pass

        return new_alerts

    def check_all(self) -> list[WalletAlert]:
        """Check all watched wallets for new activity.

        Returns:
            List of all new alerts across all wallets.
        """
        all_alerts = []
        for wallet in self.wallets.values():
            if wallet.is_active:
                alerts = self.check_wallet(wallet.address, wallet.chain)
                all_alerts.extend(alerts)
        return all_alerts

    def snapshot(self, address: str, chain: Chain) -> Optional[BalanceSnapshot]:
        """Take a balance snapshot of a wallet.

        Args:
            address: Wallet address.
            chain: Chain to snapshot.

        Returns:
            BalanceSnapshot or None if error.
        """
        try:
            w3 = self.chain_manager.get_web3(chain)
            balance_wei = w3.eth.get_balance(address)
            native = float(w3.from_wei(balance_wei, "ether"))

            snapshot = BalanceSnapshot(
                address=address,
                chain=chain,
                native_balance=native,
                token_balances={},  # TODO: fetch token balances
                total_value_usd=native * 3500,  # TODO: fetch price
                timestamp=time.time(),
            )

            # Store snapshot
            self.snapshots.setdefault(address.lower(), []).append(snapshot)
            # Keep only last 100 snapshots per address
            self.snapshots[address.lower()] = self.snapshots[address.lower()][-100:]

            return snapshot
        except Exception:
            return None

    def snapshot_all(self) -> list[BalanceSnapshot]:
        """Take snapshots of all watched wallets."""
        snapshots = []
        for wallet in self.wallets.values():
            if wallet.is_active:
                snap = self.snapshot(wallet.address, wallet.chain)
                if snap:
                    snapshots.append(snap)
        return snapshots

    def get_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        wallet_label: Optional[str] = None,
        unacknowledged_only: bool = True,
        limit: int = 50,
    ) -> list[WalletAlert]:
        """Get alerts with optional filters."""
        result = self.alerts
        if unacknowledged_only:
            result = [a for a in result if not a.acknowledged]
        if severity:
            result = [a for a in result if a.severity == severity]
        if wallet_label:
            result = [a for a in result if a.wallet_label == wallet_label]
        return result[-limit:]

    def acknowledge_alert(self, alert_index: int) -> bool:
        """Acknowledge an alert."""
        if 0 <= alert_index < len(self.alerts):
            self.alerts[alert_index].acknowledged = True
            return True
        return False

    def acknowledge_all(self) -> int:
        """Acknowledge all alerts. Returns count."""
        count = 0
        for alert in self.alerts:
            if not alert.acknowledged:
                alert.acknowledged = True
                count += 1
        return count

    def on_alert(self, callback: Callable[[WalletAlert], None]):
        """Register an alert callback.

        Args:
            callback: Function called with WalletAlert when activity detected.
        """
        self._callbacks.append(callback)

    def get_balance_history(self, address: str) -> list[BalanceSnapshot]:
        """Get balance history for an address."""
        return self.snapshots.get(address.lower(), [])

    def get_summary(self) -> dict:
        """Get watcher summary."""
        active = [w for w in self.wallets.values() if w.is_active]
        unacked = [a for a in self.alerts if not a.acknowledged]

        return {
            "watched_wallets": len(active),
            "total_alerts": len(self.alerts),
            "unacknowledged_alerts": len(unacked),
            "chains": list(set(w.chain.value for w in active)),
            "wallets": [
                {
                    "label": w.label,
                    "address": f"{w.address[:8]}...{w.address[-6:]}",
                    "chain": w.chain.value,
                    "threshold_usd": w.alert_threshold_usd,
                    "tags": w.tags,
                }
                for w in active
            ],
        }

    def start(self, interval: int = 60):
        """Start monitoring loop (blocking).

        Args:
            interval: Seconds between checks.
        """
        print(f"👁️ Wallet Watcher started — {len(self.wallets)} wallets")
        print(f"   Checking every {interval}s...")

        while True:
            alerts = self.check_all()
            for alert in alerts:
                severity_emoji = {
                    AlertSeverity.LOW: "🟢",
                    AlertSeverity.MEDIUM: "🟡",
                    AlertSeverity.HIGH: "🟠",
                    AlertSeverity.CRITICAL: "🔴",
                }
                emoji = severity_emoji.get(alert.severity, "⚪")
                print(f"{emoji} [{alert.alert_type.value}] {alert.wallet_label}: {alert.message}")

            time.sleep(interval)

    # === Internal ===

    def _check_balance(self, wallet: WatchedWallet) -> Optional[WalletAlert]:
        """Check for significant balance changes."""
        try:
            w3 = self.chain_manager.get_web3(wallet.chain)
            balance_wei = w3.eth.get_balance(wallet.address)
            current = float(w3.from_wei(balance_wei, "ether"))

            history = self.snapshots.get(wallet.address.lower(), [])
            if not history:
                # First snapshot — just record, no alert
                self.snapshot(wallet.address, wallet.chain)
                return None

            previous = history[-1].native_balance
            diff = current - previous

            if abs(diff) > 0.01:  # > 0.01 ETH change
                severity = AlertSeverity.LOW
                if abs(diff) > 1:
                    severity = AlertSeverity.MEDIUM
                if abs(diff) > 10:
                    severity = AlertSeverity.HIGH
                if abs(diff) > 100:
                    severity = AlertSeverity.CRITICAL

                direction = "received" if diff > 0 else "sent"
                return WalletAlert(
                    wallet_address=wallet.address,
                    wallet_label=wallet.label,
                    chain=wallet.chain,
                    alert_type=AlertType.BALANCE_CHANGE,
                    severity=severity,
                    message=f"{direction} {abs(diff):.4f} ETH (balance: {current:.4f})",
                    details={
                        "previous": previous,
                        "current": current,
                        "change": diff,
                    },
                )
        except Exception:
            pass
        return None

    def _check_transfers(self, wallet: WatchedWallet) -> list[WalletAlert]:
        """Check for recent large transfers (simplified — uses balance diff)."""
        # Full implementation would index blockchain events
        # For now, rely on balance change detection
        return []

    def _save_wallets(self):
        """Save watched wallets to disk."""
        os.makedirs(os.path.dirname(self.STORAGE_PATH), exist_ok=True)
        data = {}
        for key, w in self.wallets.items():
            data[key] = {
                "address": w.address,
                "label": w.label,
                "chain": w.chain.value,
                "tags": w.tags,
                "alert_threshold_usd": w.alert_threshold_usd,
                "watch_balance": w.watch_balance,
                "watch_transfers": w.watch_transfers,
                "watch_approvals": w.watch_approvals,
                "is_active": w.is_active,
            }
        with open(self.STORAGE_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def _load_wallets(self):
        """Load watched wallets from disk."""
        if not os.path.exists(self.STORAGE_PATH):
            return
        try:
            with open(self.STORAGE_PATH) as f:
                data = json.load(f)
            for key, d in data.items():
                self.wallets[key] = WatchedWallet(
                    address=d["address"],
                    label=d["label"],
                    chain=Chain(d["chain"]),
                    tags=d.get("tags", []),
                    alert_threshold_usd=d.get("alert_threshold_usd", 10000),
                    watch_balance=d.get("watch_balance", True),
                    watch_transfers=d.get("watch_transfers", True),
                    watch_approvals=d.get("watch_approvals", False),
                    is_active=d.get("is_active", True),
                )
        except Exception:
            pass
