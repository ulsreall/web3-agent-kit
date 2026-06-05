"""MEV Protection — protect transactions from sandwich attacks.

Integrates with Flashbots and private transaction relays to
protect trades from MEV (Maximal Extractable Value) attacks.

Usage::

    from web3_agent_kit.mev import MEVProtector, MEVConfig

    protector = MEVProtector(MEVConfig(
        chain="ethereum",
        use_flashbots=True,
    ))
    protected_tx = protector.protect_tx(raw_tx)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


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


class MEVProtector:
    """Protect transactions from MEV attacks.

    Uses Flashbots and private transaction relays to prevent
    sandwich attacks and frontrunning.

    Example::

        protector = MEVProtector(MEVConfig(
            chain="ethereum",
            use_flashbots=True,
        ))

        # Protect a swap transaction
        protected = protector.protect_tx(raw_tx)
        tx_hash = protector.send_protected(protected)
    """

    # Flashbots endpoints
    FLASHBOTS_RPC = "https://rpc.flashbots.net"
    FLASHBOTS_PROTECT = "https://protect.flashbots.net"
    FLASHBOTS_BUNDLER = "https://relay.flashbots.net"
    FLASHBOTS_SHARE = "https://mev-share.flashbots.net"

    # Block time per chain (seconds)
    BLOCK_TIMES = {
        "ethereum": 12,
        "base": 2,
        "arbitrum": 0.25,
        "optimism": 2,
        "polygon": 2,
        "bnb": 3,
    }

    def __init__(self, config: Optional[MEVConfig] = None):
        """Initialize MEV protector.

        Args:
            config: MEV configuration.
        """
        self.config = config or MEVConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
        })
        if self.config.flashbots_auth_key:
            self.session.headers["X-Flashbots-Signature"] = self.config.flashbots_auth_key
        self._web3 = None
        self._bundles: list[BundleResult] = []
        logger.info("MEVProtector initialized")

    def protect_tx(self, raw_tx: dict) -> ProtectedTx:
        """Protect a transaction from MEV.

        Args:
            raw_tx: Raw transaction dict.

        Returns:
            ProtectedTx with protection applied.
        """
        strategy = self.config.strategy

        if strategy == MEVStrategy.FLASHBOTS:
            return self._protect_flashbots(raw_tx)
        elif strategy == MEVStrategy.PRIVATE_RPC:
            return self._protect_private_rpc(raw_tx)
        elif strategy == MEVStrategy.BUNDLE:
            return self._protect_bundle(raw_tx)
        else:
            return ProtectedTx(
                original_tx=raw_tx,
                protected_tx=raw_tx,
                strategy=MEVStrategy.NONE,
                status="unprotected",
            )

    def send_protected(self, protected: ProtectedTx) -> Optional[str]:
        """Send a protected transaction.

        Args:
            protected: ProtectedTx to send.

        Returns:
            Transaction hash, or None if failed.
        """
        try:
            if protected.strategy == MEVStrategy.FLASHBOTS:
                return self._send_flashbots(protected)
            elif protected.strategy == MEVStrategy.PRIVATE_RPC:
                return self._send_private_rpc(protected)
            elif protected.strategy == MEVStrategy.BUNDLE:
                return self._send_bundle(protected)
            else:
                return self._send_raw(protected)
        except Exception as e:
            protected.status = "failed"
            protected.error = str(e)
            logger.error(f"Failed to send protected tx: {e}")
            return None

    def create_bundle(self, txs: list[dict], target_block: int = 0) -> BundleResult:
        """Create a Flashbots bundle.

        Args:
            txs: List of raw transactions.
            target_block: Target block number (0 = next block).

        Returns:
            BundleResult with bundle details.
        """
        if not target_block:
            target_block = self._get_current_block() + 1

        bundle_hash = f"0x{hash(str(txs)) & 0xFFFFFFFFFFFFFFFF:016x}"
        result = BundleResult(
            bundle_hash=bundle_hash,
            block_number=target_block,
            tx_count=len(txs),
        )

        try:
            # Submit bundle to Flashbots
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_sendBundle",
                "params": [{
                    "txs": [self._encode_tx(tx) for tx in txs],
                    "blockNumber": hex(target_block),
                }],
            }

            resp = self.session.post(
                self.FLASHBOTS_BUNDLER,
                json=payload,
                timeout=self.config.timeout,
            )

            if resp.status_code == 200:
                data = resp.json()
                if "result" in data:
                    result.success = True
                    logger.info(f"Bundle submitted: {bundle_hash}")
                else:
                    result.error = data.get("error", {}).get("message", "Unknown error")
            else:
                result.error = f"HTTP {resp.status_code}"

        except Exception as e:
            result.error = str(e)

        self._bundles.append(result)
        return result

    def simulate_bundle(self, txs: list[dict], block_number: int = 0) -> dict:
        """Simulate a Flashbots bundle.

        Args:
            txs: List of raw transactions.
            block_number: Block number to simulate at.

        Returns:
            Simulation results.
        """
        if not block_number:
            block_number = self._get_current_block() + 1

        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_callBundle",
                "params": [{
                    "txs": [self._encode_tx(tx) for tx in txs],
                    "blockNumber": hex(block_number),
                }],
            }

            resp = self.session.post(
                self.FLASHBOTS_BUNDLER,
                json=payload,
                timeout=self.config.timeout,
            )

            if resp.status_code == 200:
                return resp.json()
            else:
                return {"error": f"HTTP {resp.status_code}"}

        except Exception as e:
            return {"error": str(e)}

    def get_pending_bundles(self) -> list[BundleResult]:
        """Get list of pending bundles.

        Returns:
            List of BundleResult objects.
        """
        return [b for b in self._bundles if not b.success]

    def get_bundle_history(self) -> list[BundleResult]:
        """Get bundle submission history.

        Returns:
            List of BundleResult objects.
        """
        return self._bundles.copy()

    def check_sandwich_risk(self, tx: dict) -> dict:
        """Check if a transaction is at risk of sandwich attack.

        Args:
            tx: Raw transaction dict.

        Returns:
            Risk assessment dict.
        """
        risk_factors = []
        risk_score = 0

        # Check if it's a swap (high MEV risk)
        data = tx.get("data", "0x")
        if data.startswith("0x38ed1739"):  # swapExactTokensForTokens
            risk_factors.append("Swap transaction (high MEV risk)")
            risk_score += 30
        elif data.startswith("0x7ff36ab5"):  # swapExactETHForTokens
            risk_factors.append("ETH swap (high MEV risk)")
            risk_score += 30

        # Check value
        value = int(tx.get("value", "0x0"), 16) if isinstance(tx.get("value"), str) else tx.get("value", 0)
        if value > 1e18:  # > 1 ETH
            risk_factors.append("High value transaction")
            risk_score += 20

        # Check gas price
        gas_price = int(tx.get("gasPrice", "0x0"), 16) if isinstance(tx.get("gasPrice"), str) else tx.get("gasPrice", 0)
        if gas_price > 50e9:  # > 50 Gwei
            risk_factors.append("High gas price (competitive)")
            risk_score += 10

        return {
            "risk_score": min(100, risk_score),
            "risk_factors": risk_factors,
            "recommendation": "Use Flashbots Protect" if risk_score > 30 else "Standard RPC is fine",
        }

    # ─── Private Methods ─────────────────────────────────────────

    def _protect_flashbots(self, raw_tx: dict) -> ProtectedTx:
        """Protect via Flashbots Protect RPC."""
        protected_tx = raw_tx.copy()
        # Flashbots Protect automatically handles protection
        # Just need to send to Flashbots RPC
        return ProtectedTx(
            original_tx=raw_tx,
            protected_tx=protected_tx,
            strategy=MEVStrategy.FLASHBOTS,
        )

    def _protect_private_rpc(self, raw_tx: dict) -> ProtectedTx:
        """Protect via private transaction relay."""
        protected_tx = raw_tx.copy()
        # Private RPCs don't expose tx to public mempool
        return ProtectedTx(
            original_tx=raw_tx,
            protected_tx=protected_tx,
            strategy=MEVStrategy.PRIVATE_RPC,
        )

    def _protect_bundle(self, raw_tx: dict) -> ProtectedTx:
        """Protect via Flashbots bundle."""
        target_block = self._get_current_block() + 1
        protected_tx = raw_tx.copy()
        return ProtectedTx(
            original_tx=raw_tx,
            protected_tx=protected_tx,
            strategy=MEVStrategy.BUNDLE,
            target_block=target_block,
        )

    def _send_flashbots(self, protected: ProtectedTx) -> Optional[str]:
        """Send via Flashbots Protect."""
        try:
            # Flashbots Protect is a JSON-RPC endpoint
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_sendRawTransaction",
                "params": [self._encode_tx(protected.protected_tx)],
            }

            resp = self.session.post(
                self.FLASHBOTS_PROTECT,
                json=payload,
                timeout=self.config.timeout,
            )

            if resp.status_code == 200:
                data = resp.json()
                if "result" in data:
                    protected.status = "submitted"
                    protected.bundle_hash = data["result"]
                    return data["result"]
                else:
                    protected.error = data.get("error", {}).get("message")
            else:
                protected.error = f"HTTP {resp.status_code}"

        except Exception as e:
            protected.error = str(e)

        return None

    def _send_private_rpc(self, protected: ProtectedTx) -> Optional[str]:
        """Send via private RPC."""
        for rpc in self.config.private_rpcs:
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_sendRawTransaction",
                    "params": [self._encode_tx(protected.protected_tx)],
                }

                resp = self.session.post(
                    rpc,
                    json=payload,
                    timeout=self.config.timeout,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if "result" in data:
                        protected.status = "submitted"
                        return data["result"]

            except Exception as e:
                logger.debug(f"Private RPC {rpc} failed: {e}")
                continue

        protected.error = "All private RPCs failed"
        return None

    def _send_bundle(self, protected: ProtectedTx) -> Optional[str]:
        """Send as part of a bundle."""
        result = self.create_bundle(
            [protected.protected_tx],
            protected.target_block,
        )
        if result.success:
            protected.status = "bundled"
            protected.bundle_hash = result.bundle_hash
            return result.bundle_hash
        else:
            protected.error = result.error
            return None

    def _send_raw(self, protected: ProtectedTx) -> Optional[str]:
        """Send raw transaction (no protection)."""
        # This would use web3 to send
        logger.warning("Sending raw transaction without MEV protection")
        return None

    def _get_current_block(self) -> int:
        """Get current block number."""
        try:
            resp = self.session.post(
                "https://eth.llamarpc.com",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_blockNumber",
                    "params": [],
                },
                timeout=10,
            )
            if resp.status_code == 200:
                return int(resp.json()["result"], 16)
        except Exception:
            pass
        return 0

    def _encode_tx(self, tx: dict) -> str:
        """Encode transaction to hex string."""
        # If already encoded
        if isinstance(tx, str):
            return tx
        # This would use rlp encoding in production
        return tx.get("raw", "0x")

__all__ = [
    "MEVStrategy",
    "MEVConfig",
    "ProtectedTx",
    "BundleResult",
    "MEVProtector",
]
