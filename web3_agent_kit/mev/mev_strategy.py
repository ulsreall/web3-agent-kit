"""MEV protection strategy — protect transactions from sandwich attacks.

Integrates with Flashbots and private transaction relays to
protect trades from MEV (Maximal Extractable Value) attacks.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from .frontrun_detection import detect_frontrun
from .sandwich_protection import check_sandwich_risk
from .utils import BundleResult, MEVConfig, MEVStrategy, ProtectedTx

logger = logging.getLogger(__name__)


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
    FLASHBOTS_RPC: str = "https://rpc.flashbots.net"
    FLASHBOTS_PROTECT: str = "https://protect.flashbots.net"
    FLASHBOTS_BUNDLER: str = "https://relay.flashbots.net"
    FLASHBOTS_SHARE: str = "https://mev-share.flashbots.net"

    # Block time per chain (seconds)
    BLOCK_TIMES: dict[str, int | float] = {
        "ethereum": 12,
        "base": 2,
        "arbitrum": 0.25,
        "optimism": 2,
        "polygon": 2,
        "bnb": 3,
    }

    def __init__(self, config: Optional[MEVConfig] = None) -> None:
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
        self._web3: Any = None
        self._bundles: list[BundleResult] = []
        logger.info("MEVProtector initialized")

    def protect_tx(self, raw_tx: dict[str, Any]) -> ProtectedTx:
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
        except (requests.RequestException, ConnectionError, TimeoutError) as exc:
            protected.status = "failed"
            protected.error = str(exc)
            logger.error("Failed to send protected tx: %s", exc)
            return None

    def create_bundle(self, txs: list[dict[str, Any]], target_block: int = 0) -> BundleResult:
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
                    logger.info("Bundle submitted: %s", bundle_hash)
                else:
                    result.error = data.get("error", {}).get("message", "Unknown error")
            else:
                result.error = f"HTTP {resp.status_code}"

        except (requests.RequestException, ConnectionError, TimeoutError) as exc:
            result.error = str(exc)
            logger.error("Bundle submission failed: %s", exc)

        self._bundles.append(result)
        return result

    def simulate_bundle(self, txs: list[dict[str, Any]], block_number: int = 0) -> dict[str, Any]:
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

        except (requests.RequestException, ConnectionError, TimeoutError) as exc:
            return {"error": str(exc)}

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

    def check_sandwich_risk(self, tx: dict[str, Any]) -> dict[str, Any]:
        """Check if a transaction is at risk of sandwich attack.

        Delegates to :func:`sandwich_protection.check_sandwich_risk`.

        Args:
            tx: Raw transaction dict.

        Returns:
            Risk assessment dict.
        """
        return check_sandwich_risk(tx)

    def check_frontrun_risk(
        self,
        tx: dict[str, Any],
        pending_txs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Check if a transaction is at risk of frontrunning.

        Delegates to :func:`frontrun_detection.detect_frontrun`.

        Args:
            tx: Raw transaction dict.
            pending_txs: Optional list of pending mempool transactions.

        Returns:
            Frontrun risk assessment dict.
        """
        return detect_frontrun(tx, pending_txs)

    # ─── Private Methods ─────────────────────────────────────────

    def _protect_flashbots(self, raw_tx: dict[str, Any]) -> ProtectedTx:
        """Protect via Flashbots Protect RPC."""
        protected_tx = raw_tx.copy()
        return ProtectedTx(
            original_tx=raw_tx,
            protected_tx=protected_tx,
            strategy=MEVStrategy.FLASHBOTS,
        )

    def _protect_private_rpc(self, raw_tx: dict[str, Any]) -> ProtectedTx:
        """Protect via private transaction relay."""
        protected_tx = raw_tx.copy()
        return ProtectedTx(
            original_tx=raw_tx,
            protected_tx=protected_tx,
            strategy=MEVStrategy.PRIVATE_RPC,
        )

    def _protect_bundle(self, raw_tx: dict[str, Any]) -> ProtectedTx:
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

        except (requests.RequestException, ConnectionError, TimeoutError) as exc:
            protected.error = str(exc)
            logger.error("Flashbots send failed: %s", exc)

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

            except (requests.RequestException, ConnectionError, TimeoutError) as exc:
                logger.debug("Private RPC %s failed: %s", rpc, exc)
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
        except (requests.RequestException, ConnectionError, TimeoutError, KeyError, ValueError):
            logger.debug("Failed to fetch current block number")
        return 0

    def _encode_tx(self, tx: dict[str, Any] | str) -> str:
        """Encode transaction to hex string."""
        if isinstance(tx, str):
            return tx
        return tx.get("raw", "0x")
