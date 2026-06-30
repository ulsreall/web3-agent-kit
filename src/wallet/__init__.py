"""Wallet module — wallet management, multi-wallet, watcher, approvals."""

from .approval import ApprovalManager, ApprovalRisk, RevokeResult, TokenApproval
from .multi_wallet import BatchTxResult, ConsolidatedBalance, MultiWalletManager, WalletInfo
from .wallet import Wallet, WalletConfig
from .watcher import AlertSeverity, AlertType, WalletAlert, WalletWatcher, WatchedWallet

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
