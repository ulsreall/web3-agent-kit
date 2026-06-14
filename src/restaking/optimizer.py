"""Restaking yield optimizer — find best risk-adjusted yields across protocols."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes & enums
# ---------------------------------------------------------------------------

class OptimizationStrategy(Enum):
    """Yield optimization strategy types."""
    MAX_YIELD = "max_yield"                        # Highest raw APY
    RISK_ADJUSTED = "risk_adjusted"                 # Best Sharpe-like ratio
    BALANCED = "balanced"                           # Balance yield, risk, and diversification
    CONSERVATIVE = "conservative"                   # Minimize risk above all
    DIVERSIFIED = "diversified"                     # Spread across multiple protocols


@dataclass
class RestakingOpportunity:
    """A restaking yield opportunity from any protocol."""
    protocol: str                # e.g. "eigenlayer", "babylon", "solayer"
    chain: str                   # e.g. "ethereum", "solana"
    asset: str                   # e.g. "ETH", "BTC", "SOL"
    apy: float                   # Annual percentage yield (e.g. 5.2 = 5.2%)
    tvl_usd: float               # Total value locked in USD
    risk_score: float            # 0-100 (0 = no risk, 100 = max risk)
    min_deposit: float = 0.0     # Minimum deposit
    lock_period_days: int = 0    # 0 = flexible
    slashing_coverage: bool = False  # Whether slashing losses are covered
    audit_count: int = 0         # Number of audits
    is_native_staking: bool = False
    reward_tokens: list[str] = field(default_factory=list)
    pool_address: str = ""
    protocol_version: str = ""

    @property
    def risk_adjusted_yield(self) -> float:
        """Compute a Sharpe-like risk-adjusted yield score.

        Higher is better. Penalizes risk quadratically.
        """
        if self.risk_score <= 0:
            return self.apy * 100  # Infinite-ish risk-free
        return self.apy / (1 + (self.risk_score / 20) ** 2)

    @property
    def liquidity_score(self) -> float:
        """Score reflecting TVL and lock period (higher = more liquid)."""
        tvl_score = math.log10(max(self.tvl_usd, 1)) / 10  # 0-8ish
        lock_penalty = self.lock_period_days / 365           # 0-1
        return max(tvl_score - lock_penalty, 0)

    @property
    def display_apy(self) -> str:
        return f"{self.apy:.2f}%"


@dataclass
class RiskAdjustedYield:
    """Risk-adjusted yield analysis for an opportunity."""
    opportunity: RestakingOpportunity
    raw_apy: float
    risk_adjusted_apy: float
    max_drawdown_est: float          # Estimated max drawdown %
    sharpe_ratio: float              # Simplified Sharpe-like ratio
    confidence_score: float          # 0-100
    recommended_allocation_pct: float  # 0-100


@dataclass
class OptimizationResult:
    """Result of a yield optimization run."""
    strategy: OptimizationStrategy
    opportunities: list[RiskAdjustedYield]
    total_expected_apy: float
    portfolio_risk_score: float
    allocations: dict[str, float]    # protocol -> allocation %
    timestamp: float = 0.0
    recommendations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def num_positions(self) -> int:
        return len([a for a in self.allocations.values() if a > 0])


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

class RestakingOptimizer:
    """Yield optimizer for restaking protocols.

    Analyzes opportunities across EigenLayer, Babylon, Solana restaking,
    and others. Computes risk-adjusted yields and generates allocation
    recommendations.

    Example::

        optimizer = RestakingOptimizer()
        optimizer.add_opportunity(RestakingOpportunity(...))
        result = optimizer.optimize(strategy=OptimizationStrategy.RISK_ADJUSTED)
        print(result.allocations)
        print(result.recommendations)
    """

    # Risk-free rate for Sharpe calculation (annual %)
    RISK_FREE_RATE = 4.5  # US Treasury approximate

    def __init__(
        self,
        max_risk_score: float = 60.0,
        min_apy: float = 2.0,
        max_single_allocation_pct: float = 50.0,
        diversification_bonus: float = 0.5,  # APY bonus for diversification
    ):
        self.max_risk_score = max_risk_score
        self.min_apy = min_apy
        self.max_single_allocation_pct = max_single_allocation_pct
        self.diversification_bonus = diversification_bonus
        self._opportunities: list[RestakingOpportunity] = []
        self._last_result: Optional[OptimizationResult] = None

    # ------------------------------------------------------------------
    # Opportunity management
    # ------------------------------------------------------------------

    def add_opportunity(self, opportunity: RestakingOpportunity) -> None:
        """Add a restaking opportunity for analysis."""
        self._opportunities.append(opportunity)
        logger.debug("Added opportunity: %s %s @ %.2f%%", opportunity.protocol, opportunity.asset, opportunity.apy)

    def add_opportunities(self, opportunities: list[RestakingOpportunity]) -> None:
        """Add multiple opportunities."""
        for opp in opportunities:
            self.add_opportunity(opp)

    def clear_opportunities(self) -> None:
        """Clear all stored opportunities."""
        self._opportunities.clear()

    @property
    def opportunities(self) -> list[RestakingOpportunity]:
        """All stored opportunities."""
        return list(self._opportunities)

    def set_benchmark_opportunities(self) -> None:
        """Populate with current real-world benchmark data (Jan 2026 estimates)."""
        benchmarks = [
            RestakingOpportunity(
                protocol="eigenlayer",
                chain="ethereum",
                asset="stETH",
                apy=4.2,
                tvl_usd=15_000_000_000,
                risk_score=25,
                lock_period_days=7,
                slashing_coverage=True,
                audit_count=5,
                is_native_staking=True,
                reward_tokens=["EIGEN", "ETH"],
                pool_address="0x93c4b944D05dfe6df7645A86cd2206016c51564D",
            ),
            RestakingOpportunity(
                protocol="eigenlayer",
                chain="ethereum",
                asset="rETH",
                apy=3.8,
                tvl_usd=4_000_000_000,
                risk_score=28,
                lock_period_days=7,
                slashing_coverage=True,
                audit_count=4,
                reward_tokens=["EIGEN", "ETH"],
                pool_address="0x1BeE69b7dFFfA4E8d5cd3F4b5e49c0F8C5C6b8e6",
            ),
            RestakingOpportunity(
                protocol="eigenlayer",
                chain="ethereum",
                asset="cbETH",
                apy=4.0,
                tvl_usd=3_000_000_000,
                risk_score=22,
                lock_period_days=7,
                slashing_coverage=True,
                audit_count=5,
                reward_tokens=["EIGEN", "ETH"],
                pool_address="0x54945180dB7943c0ed0FEE7EdaB2Bd24620256bc",
            ),
            RestakingOpportunity(
                protocol="babylon",
                chain="bitcoin",
                asset="BTC",
                apy=3.5,
                tvl_usd=6_000_000_000,
                risk_score=35,
                lock_period_days=7,
                slashing_coverage=False,
                audit_count=3,
                is_native_staking=True,
                reward_tokens=["BABY"],
            ),
            RestakingOpportunity(
                protocol="solayer",
                chain="solana",
                asset="SOL",
                apy=8.5,
                tvl_usd=800_000_000,
                risk_score=45,
                lock_period_days=2,
                slashing_coverage=False,
                audit_count=2,
                reward_tokens=["SOL"],
            ),
            RestakingOpportunity(
                protocol="jito",
                chain="solana",
                asset="SOL",
                apy=7.8,
                tvl_usd=2_000_000_000,
                risk_score=40,
                lock_period_days=2,
                slashing_coverage=False,
                audit_count=3,
                reward_tokens=["JTO", "SOL"],
            ),
            RestakingOpportunity(
                protocol="symbiotic",
                chain="ethereum",
                asset="WETH",
                apy=5.5,
                tvl_usd=2_500_000_000,
                risk_score=50,
                lock_period_days=14,
                slashing_coverage=False,
                audit_count=2,
                reward_tokens=["WETH"],
                pool_address="0xB9d5F78b95dA4b7A0E2B8C6D5E4F3A2B1C0D9E8F",
            ),
            RestakingOpportunity(
                protocol="karak",
                chain="ethereum",
                asset="WETH",
                apy=5.1,
                tvl_usd=1_200_000_000,
                risk_score=48,
                lock_period_days=10,
                slashing_coverage=False,
                audit_count=2,
                reward_tokens=["WETH"],
                pool_address="0xA8c4E67b9d44C3cCB4F1B5D6E7F8A9B0C1D2E3F4",
            ),
            RestakingOpportunity(
                protocol="renzo",
                chain="ethereum",
                asset="ezETH",
                apy=4.8,
                tvl_usd=3_500_000_000,
                risk_score=32,
                lock_period_days=7,
                slashing_coverage=True,
                audit_count=3,
                reward_tokens=["EIGEN", "ETH", "REZ"],
            ),
            RestakingOpportunity(
                protocol="puffer",
                chain="ethereum",
                asset="pufETH",
                apy=4.5,
                tvl_usd=2_000_000_000,
                risk_score=36,
                lock_period_days=7,
                slashing_coverage=True,
                audit_count=3,
                reward_tokens=["EIGEN", "PUFFER"],
            ),
        ]
        self.add_opportunities(benchmarks)
        logger.info("Loaded %d benchmark restaking opportunities", len(benchmarks))

    # ------------------------------------------------------------------
    # Core optimization
    # ------------------------------------------------------------------

    def optimize(
        self,
        strategy: OptimizationStrategy = OptimizationStrategy.RISK_ADJUSTED,
        asset_filter: Optional[str] = None,
        max_positions: int = 5,
    ) -> OptimizationResult:
        """Run yield optimization across all stored opportunities.

        Args:
            strategy: Optimization strategy to use.
            asset_filter: Optional filter by asset (e.g. "ETH").
            max_positions: Maximum number of positions to recommend.

        Returns:
            OptimizationResult with allocations and recommendations.
        """
        # Filter opportunities
        candidates = list(self._opportunities)
        if asset_filter:
            candidates = [o for o in candidates if o.asset.upper() == asset_filter.upper()]

        # Remove below-minimum APY and over-risk-limit
        candidates = [
            o for o in candidates
            if o.apy >= self.min_apy and o.risk_score <= self.max_risk_score
        ]

        if not candidates:
            return OptimizationResult(
                strategy=strategy,
                opportunities=[],
                total_expected_apy=0,
                portfolio_risk_score=0,
                allocations={},
                recommendations=["No opportunities meet the current criteria."],
            )

        # Compute risk-adjusted yields
        analyzed = [self._analyze(o) for o in candidates]

        # Apply strategy
        if strategy == OptimizationStrategy.MAX_YIELD:
            analyzed.sort(key=lambda x: x.raw_apy, reverse=True)
        elif strategy == OptimizationStrategy.RISK_ADJUSTED:
            analyzed.sort(key=lambda x: x.risk_adjusted_apy, reverse=True)
        elif strategy == OptimizationStrategy.CONSERVATIVE:
            analyzed.sort(key=lambda x: x.opportunity.risk_score)
        elif strategy == OptimizationStrategy.DIVERSIFIED:
            analyzed = self._diversified_sort(analyzed)
        else:  # BALANCED
            analyzed.sort(
                key=lambda x: x.risk_adjusted_apy * 0.6 + x.confidence_score * 0.04,
                reverse=True,
            )

        # Take top N
        selected = analyzed[:max_positions]

        # Allocate capital
        allocations = self._allocate(selected, strategy)

        # Apply allocations back
        for ray in selected:
            key = f"{ray.opportunity.protocol}:{ray.opportunity.asset}"
            ray.recommended_allocation_pct = allocations.get(key, 0)

        # Compute portfolio metrics
        total_apy = sum(
            ray.risk_adjusted_apy * (ray.recommended_allocation_pct / 100)
            for ray in selected
        )
        portfolio_risk = sum(
            ray.opportunity.risk_score * (ray.recommended_allocation_pct / 100)
            for ray in selected
        )

        # Generate recommendations
        recs = self._generate_recommendations(selected, strategy)

        result = OptimizationResult(
            strategy=strategy,
            opportunities=selected,
            total_expected_apy=total_apy,
            portfolio_risk_score=portfolio_risk,
            allocations=allocations,
            recommendations=recs,
        )
        self._last_result = result
        return result

    def compare_strategies(self, asset_filter: Optional[str] = None) -> dict[str, OptimizationResult]:
        """Compare all optimization strategies.

        Returns:
            Dict mapping strategy name to OptimizationResult.
        """
        results = {}
        for strategy in OptimizationStrategy:
            results[strategy.value] = self.optimize(strategy=strategy, asset_filter=asset_filter)
        return results

    def get_top_opportunities(self, n: int = 5, sort_by: str = "risk_adjusted") -> list[RestakingOpportunity]:
        """Get top N opportunities sorted by a metric.

        Args:
            n: Number of opportunities to return.
            sort_by: Sort metric ("apy", "risk_adjusted", "tvl").

        Returns:
            List of top opportunities.
        """
        candidates = [o for o in self._opportunities if o.apy >= self.min_apy]

        if sort_by == "apy":
            candidates.sort(key=lambda o: o.apy, reverse=True)
        elif sort_by == "tvl":
            candidates.sort(key=lambda o: o.tvl_usd, reverse=True)
        else:
            candidates.sort(key=lambda o: o.risk_adjusted_yield, reverse=True)

        return candidates[:n]

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _analyze(self, opp: RestakingOpportunity) -> RiskAdjustedYield:
        """Compute risk-adjusted yield metrics for an opportunity."""
        ra_yield = opp.risk_adjusted_yield

        # Simplified Sharpe: (yield - risk_free) / volatility proxy
        vol_proxy = opp.risk_score / 10  # 0-10
        sharpe = (opp.apy - self.RISK_FREE_RATE) / max(vol_proxy, 0.1) if opp.apy > self.RISK_FREE_RATE else -1

        # Confidence based on audit count, TVL, and track record
        audit_score = min(opp.audit_count / 5, 1.0) * 30
        tvl_score = min(math.log10(max(opp.tvl_usd, 1)) / 9, 1.0) * 40
        coverage_score = 15 if opp.slashing_coverage else 0
        native_score = 15 if opp.is_native_staking else 5
        confidence = audit_score + tvl_score + coverage_score + native_score

        # Max drawdown estimate
        max_dd = opp.risk_score * 0.5  # Simple linear estimate

        return RiskAdjustedYield(
            opportunity=opp,
            raw_apy=opp.apy,
            risk_adjusted_apy=ra_yield,
            max_drawdown_est=max_dd,
            sharpe_ratio=sharpe,
            confidence_score=confidence,
            recommended_allocation_pct=0,  # filled later
        )

    def _allocate(
        self,
        analyzed: list[RiskAdjustedYield],
        strategy: OptimizationStrategy,
    ) -> dict[str, float]:
        """Compute capital allocation percentages."""
        if not analyzed:
            return {}

        allocs: dict[str, float] = {}

        if strategy == OptimizationStrategy.MAX_YIELD:
            # Concentrate in top yield
            key = f"{analyzed[0].opportunity.protocol}:{analyzed[0].opportunity.asset}"
            allocs[key] = min(100.0, self.max_single_allocation_pct)
            remaining = 100 - allocs[key]
            for ray in analyzed[1:]:
                if remaining <= 0:
                    break
                k = f"{ray.opportunity.protocol}:{ray.opportunity.asset}"
                alloc = min(remaining, self.max_single_allocation_pct)
                allocs[k] = alloc
                remaining -= alloc

        elif strategy == OptimizationStrategy.DIVERSIFIED:
            # Equal weight across protocols
            per_protocol: dict[str, list[RiskAdjustedYield]] = {}
            for ray in analyzed:
                per_protocol.setdefault(ray.opportunity.protocol, []).append(ray)
            per_proto_alloc = 100.0 / max(len(per_protocol), 1)
            for proto, rays in per_protocol.items():
                per_ray = per_proto_alloc / max(len(rays), 1)
                for ray in rays:
                    k = f"{ray.opportunity.protocol}:{ray.opportunity.asset}"
                    allocs[k] = round(per_ray, 2)

        elif strategy == OptimizationStrategy.CONSERVATIVE:
            # Weight by inverse risk
            inv_risks = [1 / max(ray.opportunity.risk_score, 1) for ray in analyzed]
            total = sum(inv_risks)
            for ray, inv in zip(analyzed, inv_risks):
                k = f"{ray.opportunity.protocol}:{ray.opportunity.asset}"
                allocs[k] = round((inv / total) * 100, 2)

        else:
            # Risk-adjusted / balanced: weight by risk-adjusted yield
            total_ra = sum(ray.risk_adjusted_apy for ray in analyzed)
            if total_ra > 0:
                for ray in analyzed:
                    k = f"{ray.opportunity.protocol}:{ray.opportunity.asset}"
                    raw_alloc = (ray.risk_adjusted_apy / total_ra) * 100
                    allocs[k] = round(min(raw_alloc, self.max_single_allocation_pct), 2)

        # Normalize to 100%
        total_alloc = sum(allocs.values())
        if total_alloc > 0 and abs(total_alloc - 100) > 0.1:
            scale = 100 / total_alloc
            allocs = {k: round(v * scale, 2) for k, v in allocs.items()}

        return allocs

    def _diversified_sort(self, analyzed: list[RiskAdjustedYield]) -> list[RiskAdjustedYield]:
        """Sort to maximize protocol and asset diversity."""
        seen_protocols: set[str] = set()
        seen_assets: set[str] = set()
        priority: list[RiskAdjustedYield] = []
        remaining: list[RiskAdjustedYield] = []

        analyzed_sorted = sorted(analyzed, key=lambda x: x.risk_adjusted_apy, reverse=True)

        for ray in analyzed_sorted:
            proto = ray.opportunity.protocol
            asset = ray.opportunity.asset
            if proto not in seen_protocols and asset not in seen_assets:
                priority.append(ray)
                seen_protocols.add(proto)
                seen_assets.add(asset)
            else:
                remaining.append(ray)

        return priority + remaining

    def _generate_recommendations(
        self,
        selected: list[RiskAdjustedYield],
        strategy: OptimizationStrategy,
    ) -> list[str]:
        """Generate human-readable recommendations."""
        recs: list[str] = []

        if not selected:
            return ["No viable opportunities found."]

        best = selected[0]
        recs.append(
            f"Top pick: {best.opportunity.protocol} {best.opportunity.asset} "
            f"at {best.raw_apy:.2f}% APY (risk-adjusted: {best.risk_adjusted_apy:.2f}%)"
        )

        # Diversification
        protocols = set(ray.opportunity.protocol for ray in selected)
        if len(protocols) == 1:
            recs.append("⚠️ All allocations in single protocol — consider diversifying.")
        elif len(protocols) >= 3:
            recs.append(f"✅ Good diversification across {len(protocols)} protocols.")

        # Risk check
        high_risk = [ray for ray in selected if ray.opportunity.risk_score > 50]
        if high_risk:
            names = ", ".join(f"{r.opportunity.protocol}" for r in high_risk)
            recs.append(f"⚠️ High-risk allocations: {names} — monitor closely.")

        # Lock periods
        locked = [ray for ray in selected if ray.opportunity.lock_period_days > 7]
        if locked:
            names = ", ".join(
                f"{r.opportunity.protocol} ({r.opportunity.lock_period_days}d)"
                for r in locked
            )
            recs.append(f"⏱️ Lock periods: {names}")

        if strategy == OptimizationStrategy.CONSERVATIVE:
            recs.append("🛡️ Conservative strategy prioritizes capital preservation.")

        return recs
