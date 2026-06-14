"""MEV shared types, enums, and dataclasses."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class MEVStrategy(Enum):
    """MEV protection strategies."""
    FLASHBOTS = "flashbots"  # Flashbots Protect
    PRIVATE_RPC = "private_rpc"  # Private transaction relay
    BUNDLE = "bundle"  # Flashbots bundle
    NONE = "none"  # No protection


@dataclass
class MEVConfig:
    """Configuration for MEV protection."""
    chain: str = "ethereum"
    strategy: MEVStrategy = MEVStrategy.FLASHBOTS
    # Flashbots
    flashbots_rpc: str = "https://rpc.flashbots.net"
    flashbots_auth_key: str = ""  # Optional: Flashbots auth key
    # Private RPCs
    private_rpcs: list[str] = field(default_factory=lambda: [
        "https://rpc.flashbots.net",
        "https://protect.flashbots.net",
        "https://mev-share.flashbots.net",
    ])
    # Settings
    max_block_range: int = 25  # Max blocks for bundle
    retry_count: int = 3
    timeout: int = 30
    # Refund
    refund_address: str = ""  # Address for MEV refunds
    min_profit_wei: int = 0  # Minimum profit to include in bundle


@dataclass
class ProtectedTx:
    """A protected transaction."""
    original_tx: dict
    protected_tx: dict
    strategy: MEVStrategy
    target_block: int = 0
    bundle_hash: str = ""
    status: str = "pending"
    submitted_at: float = field(default_factory=time.time)
    confirmed_at: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy.value,
            "target_block": self.target_block,
            "bundle_hash": self.bundle_hash,
            "status": self.status,
            "error": self.error,
        }


@dataclass
class BundleResult:
    """Result of submitting a Flashbots bundle."""
    bundle_hash: str
    block_number: int
    success: bool = False
    tx_count: int = 0
    gas_used: int = 0
    mev_profit: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "bundle_hash": self.bundle_hash,
            "block_number": self.block_number,
            "success": self.success,
            "tx_count": self.tx_count,
            "gas_used": self.gas_used,
        }
