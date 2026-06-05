"""Wallet module — wallet management, multi-wallet, watcher, approvals."""

from .wallet import Wallet, WalletConfig
from .multi_wallet import MultiWalletManager, WalletInfo, BatchTxResult, ConsolidatedBalance
from .watcher import WalletWatcher, WatchedWallet, WalletAlert, AlertType, AlertSeverity
from .approval import ApprovalManager, TokenApproval, RevokeResult, ApprovalRisk

__all__ = [
    # Wallet
    "Wallet",
    "WalletConfig",
    # Multi-wallet
    "MultiWalletManager",
    "WalletInfo",
    "BatchTxResult",
    "ConsolidatedBalance",
    # Watcher
    "WalletWatcher",
    "WatchedWallet",
    "WalletAlert",
    "AlertType",
    "AlertSeverity",
    # Approvals
    "ApprovalManager",
    "TokenApproval",
    "RevokeResult",
    "ApprovalRisk",
]
