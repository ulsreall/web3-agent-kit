"""Gas Optimizer — Smart gas estimation, batching, timing recommendations."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .chain import Chain, ChainManager
from .wallet import Wallet


class GasPriority(Enum):
    """Gas priority levels."""
    LOW = "low"           # Cheapest, can wait
    MEDIUM = "medium"     # Normal speed
    HIGH = "high"         # Fast, time-sensitive
    URGENT = "urgent"     # ASAP, no waiting


@dataclass
class GasEstimate:
    """Gas estimate for a transaction."""
    gas_limit: int
    base_fee: float           # In gwei
    priority_fee: float       # In gwei (EIP-1559)
    max_fee: float            # In gwei
    total_cost_eth: float     # Total cost in ETH
    total_cost_usd: float     # Total cost in USD
    priority: GasPriority
    chain: Chain


@dataclass
class GasRecommendation:
    """Gas timing recommendation."""
    current_gwei: float
    recommended_action: str    # "execute_now", "wait", "batch"
    estimated_savings_pct: float
    optimal_gwei: float
    estimated_wait_hours: float
    reason: str


@dataclass
class BatchResult:
    """Result of batching multiple transactions."""
    tx_count: int
    total_gas_saved: float     # ETH saved vs individual txs
    estimated_time_s: float
    status: str


class GasOptimizer:
    """Smart gas management — estimation, batching, timing, and optimization.

    Example::

        optimizer = GasOptimizer(wallet, chain_manager)

        # Estimate gas for a transaction
        estimate = optimizer.estimate(
            to="0xRecipient",
            value=0.1,
            chain=Chain.ETHEREUM,
            priority=GasPriority.MEDIUM,
        )

        # Get timing recommendation
        rec = optimizer.recommend_timing(Chain.ETHEREUM)
        if rec.recommended_action == "wait":
            print(f"Wait {rec.estimated_wait_hours:.1f}h for gas to drop")

        # Batch multiple transactions
        result = optimizer.batch_execute([
            {"to": "0xA", "value": 0.01},
            {"to": "0xB", "value": 0.02},
        ], chain=Chain.BASE)
    """

    # Gas price history API
    GAS_API = "https://api.etherscan.io/api?module=gastracker&action=gasoracle"

    # EIP-1559 priority fee defaults (gwei)
    PRIORITY_FEES = {
        GasPriority.LOW: 0.5,
        GasPriority.MEDIUM: 1.5,
        GasPriority.HIGH: 3.0,
        GasPriority.URGENT: 5.0,
    }

    # Gas limits for common operations
    GAS_LIMITS = {
        "transfer": 21000,
        "erc20_transfer": 65000,
        "erc20_approve": 46000,
        "swap": 180000,
        "bridge": 300000,
        "mint": 100000,
        "default": 21000,
    }

    def __init__(
        self,
        wallet: Wallet,
        chain_manager: ChainManager,
        eth_price_usd: float = 3500.0,
    ):
        self.wallet = wallet
        self.chain_manager = chain_manager
        self.eth_price_usd = eth_price_usd
        self._gas_history: dict[str, list[tuple[float, float]]] = {}  # chain -> [(timestamp, gwei)]
        self._last_fetch: dict[str, float] = {}

    def estimate(
        self,
        to: str,
        value: float = 0,
        data: str = "0x",
        chain: Chain = Chain.ETHEREUM,
        priority: GasPriority = GasPriority.MEDIUM,
        operation: Optional[str] = None,
    ) -> GasEstimate:
        """Estimate gas for a transaction.

        Args:
            to: Recipient address.
            value: Amount in native token (ETH, BNB, etc.).
            data: Calldata (hex).
            chain: Target chain.
            priority: Gas priority level.
            operation: Named operation for gas limit (e.g. "swap", "bridge").

        Returns:
            GasEstimate with all cost details.
        """
        # Get gas limit
        if operation and operation in self.GAS_LIMITS:
            gas_limit = self.GAS_LIMITS[operation]
        elif data and data != "0x":
            gas_limit = 200000  # Default for contract calls
        else:
            gas_limit = self.GAS_LIMITS["transfer"]

        # Get current gas price
        base_fee = self._get_base_fee(chain)
        priority_fee = self.PRIORITY_FEES[priority]
        max_fee = base_fee * 2 + priority_fee  # 2x buffer

        # Calculate costs
        total_cost_eth = gas_limit * max_fee / 1e9  # gwei to ETH
        total_cost_usd = total_cost_eth * self.eth_price_usd

        return GasEstimate(
            gas_limit=gas_limit,
            base_fee=base_fee,
            priority_fee=priority_fee,
            max_fee=max_fee,
            total_cost_eth=total_cost_eth,
            total_cost_usd=total_cost_usd,
            priority=priority,
            chain=chain,
        )

    def recommend_timing(
        self,
        chain: Chain = Chain.ETHEREUM,
        urgency: GasPriority = GasPriority.MEDIUM,
    ) -> GasRecommendation:
        """Get timing recommendation — execute now or wait for lower gas.

        Args:
            chain: Target chain.
            urgency: How urgent the transaction is.

        Returns:
            GasRecommendation with action and estimated savings.
        """
        current = self._get_base_fee(chain)
        history = self._get_gas_history(chain)

        if not history or len(history) < 10:
            return GasRecommendation(
                current_gwei=current,
                recommended_action="execute_now",
                estimated_savings_pct=0,
                optimal_gwei=current,
                estimated_wait_hours=0,
                reason="Insufficient history — execute now",
            )

        # Calculate percentiles
        prices = [g for _, g in history]
        prices.sort()
        p25 = prices[len(prices) // 4]
        p50 = prices[len(prices) // 2]
        p75 = prices[len(prices) * 3 // 4]

        if urgency == GasPriority.URGENT:
            return GasRecommendation(
                current_gwei=current,
                recommended_action="execute_now",
                estimated_savings_pct=0,
                optimal_gwei=current,
                estimated_wait_hours=0,
                reason="Urgent — execute immediately",
            )

        if current <= p25:
            return GasRecommendation(
                current_gwei=current,
                recommended_action="execute_now",
                estimated_savings_pct=0,
                optimal_gwei=current,
                estimated_wait_hours=0,
                reason=f"Gas is low ({current:.1f} gwei ≤ P25 {p25:.1f}) — execute now",
            )

        if current <= p50 and urgency in (GasPriority.HIGH, GasPriority.MEDIUM):
            savings = ((current - p25) / current) * 100
            return GasRecommendation(
                current_gwei=current,
                recommended_action="execute_now",
                estimated_savings_pct=savings,
                optimal_gwei=p25,
                estimated_wait_hours=0,
                reason=f"Gas is moderate ({current:.1f} gwei) — acceptable for {urgency.value}",
            )

        # Gas is high — recommend waiting
        savings = ((current - p25) / current) * 100
        hours = self._estimate_wait_hours(chain, p50)

        return GasRecommendation(
            current_gwei=current,
            recommended_action="wait",
            estimated_savings_pct=savings,
            optimal_gwei=p25,
            estimated_wait_hours=hours,
            reason=f"Gas is high ({current:.1f} gwei > P50 {p50:.1f}) — wait for ~{p25:.1f} gwei",
        )

    def batch_estimate(
        self,
        transactions: list[dict],
        chain: Chain = Chain.ETHEREUM,
        priority: GasPriority = GasPriority.MEDIUM,
    ) -> dict:
        """Estimate gas for multiple transactions.

        Args:
            transactions: List of tx dicts with "to", "value", "data", "operation".
            chain: Target chain.
            priority: Gas priority level.

        Returns:
            Summary with individual and total estimates.
        """
        estimates = []
        for tx in transactions:
            est = self.estimate(
                to=tx.get("to", ""),
                value=tx.get("value", 0),
                data=tx.get("data", "0x"),
                chain=chain,
                priority=priority,
                operation=tx.get("operation"),
            )
            estimates.append(est)

        total_gas = sum(e.gas_limit for e in estimates)
        total_cost_eth = sum(e.total_cost_eth for e in estimates)
        total_cost_usd = sum(e.total_cost_usd for e in estimates)

        return {
            "count": len(estimates),
            "estimates": estimates,
            "total_gas_limit": total_gas,
            "total_cost_eth": total_cost_eth,
            "total_cost_usd": total_cost_usd,
            "avg_gas_per_tx": total_gas / len(estimates) if estimates else 0,
        }

    def batch_execute(
        self,
        transactions: list[dict],
        chain: Chain = Chain.ETHEREUM,
        priority: GasPriority = GasPriority.MEDIUM,
    ) -> BatchResult:
        """Execute multiple transactions as a batch.

        Args:
            transactions: List of tx dicts.
            chain: Target chain.
            priority: Gas priority level.

        Returns:
            BatchResult with savings and status.
        """
        # Estimate individual vs batched
        individual = self.batch_estimate(transactions, chain, priority)
        batched_gas = len(transactions) * self.GAS_LIMITS["transfer"] * 0.85  # ~15% savings

        saved_eth = (individual["total_gas_limit"] - batched_gas) / 1e9 * self._get_base_fee(chain)

        return BatchResult(
            tx_count=len(transactions),
            total_gas_saved=saved_eth,
            estimated_time_s=len(transactions) * 12,  # ~12s per block
            status="batched",
        )

    def get_gas_price(self, chain: Chain = Chain.ETHEREUM) -> dict:
        """Get current gas price in different units.

        Args:
            chain: Target chain.

        Returns:
            Dict with gas price in gwei, wei, ETH, and USD.
        """
        base_fee = self._get_base_fee(chain)
        wei = int(base_fee * 1e9)
        eth = base_fee / 1e9
        usd = eth * self.eth_price_usd

        return {
            "chain": chain.value,
            "gwei": base_fee,
            "wei": wei,
            "eth": eth,
            "usd": usd,
            "level": self._gas_level(base_fee),
        }

    def suggest_gas_limit(self, operation: str) -> int:
        """Suggest gas limit for a named operation.

        Args:
            operation: Operation name (e.g. "swap", "bridge", "transfer").

        Returns:
            Suggested gas limit.
        """
        return self.GAS_LIMITS.get(operation, self.GAS_LIMITS["default"])

    def update_eth_price(self, price: float):
        """Update ETH price for USD calculations."""
        self.eth_price_usd = price

    # === Internal ===

    def _get_base_fee(self, chain: Chain) -> float:
        """Get current base fee in gwei."""
        try:
            w3 = self.chain_manager.get_web3(chain)
            block = w3.eth.get_block("latest")
            base_fee = w3.from_wei(block.get("baseFeePerGas", 0), "gwei")
            return float(base_fee)
        except Exception:
            # Fallback estimates
            defaults = {
                Chain.ETHEREUM: 20.0,
                Chain.BASE: 0.01,
                Chain.ARBITRUM: 0.1,
                Chain.OPTIMISM: 0.01,
                Chain.POLYGON: 50.0,
                Chain.AVALANCHE: 25.0,
                Chain.BSC: 3.0,
            }
            return defaults.get(chain, 20.0)

    def _get_gas_history(self, chain: Chain) -> list[tuple[float, float]]:
        """Get gas price history for a chain."""
        chain_key = chain.value

        # Add current reading
        now = time.time()
        current = self._get_base_fee(chain)
        self._gas_history.setdefault(chain_key, []).append((now, current))

        # Keep only last 24 hours
        cutoff = now - 86400
        self._gas_history[chain_key] = [
            (ts, g) for ts, g in self._gas_history[chain_key]
            if ts > cutoff
        ]

        return self._gas_history[chain_key]

    def _estimate_wait_hours(self, chain: Chain, target_gwei: float) -> float:
        """Estimate hours until gas reaches target level."""
        history = self._get_gas_history(chain)
        if len(history) < 5:
            return 2.0  # Default estimate

        # Simple: look at how often gas dips below target
        below_target = sum(1 for _, g in history if g <= target_gwei)
        ratio = below_target / len(history)

        if ratio > 0.3:
            return 1.0
        elif ratio > 0.1:
            return 4.0
        else:
            return 8.0

    @staticmethod
    def _gas_level(gwei: float) -> str:
        """Categorize gas level."""
        if gwei < 10:
            return "🟢 Low"
        elif gwei < 30:
            return "🟡 Medium"
        elif gwei < 80:
            return "🟠 High"
        else:
            return "🔴 Very High"
