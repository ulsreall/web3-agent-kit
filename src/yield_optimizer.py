"""Yield Optimizer — Auto-compound, APY comparison, cross-protocol yield farming."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from web3 import Web3

from .wallet import Wallet
from .chain import Chain


class Protocol(Enum):
    """Supported DeFi protocols."""
    AAVE_V3 = "aave_v3"
    COMPOUND_V3 = "compound_v3"
    MORPHO = "morpho"
    LIDO = "lido"
    ROCKET_POOL = "rocket_pool"
    FLUID = "fluid"


class RiskLevel(Enum):
    """Risk level for yield strategies."""
    LOW = "low"           # Blue chips, battle-tested
    MEDIUM = "medium"     # Newer protocols, minor risks
    HIGH = "high"         # Exotic strategies, higher APY


@dataclass
class YieldOpportunity:
    """A yield opportunity from a protocol."""
    protocol: Protocol
    chain: Chain
    asset: str                    # e.g. "USDC", "WETH"
    apy: float                    # Annual percentage yield (e.g. 5.2 = 5.2%)
    tvl: float                    # Total value locked in USD
    risk: RiskLevel
    pool_address: str             # Contract address
    pool_name: str                # Human-readable name
    deposit_token: str            # Token address to deposit
    reward_tokens: list[str] = field(default_factory=list)  # Reward token addresses
    is_compoundable: bool = True  # Whether auto-compound is supported
    min_deposit: float = 0        # Minimum deposit in USD
    last_updated: float = 0       # Timestamp of last APY update

    @property
    def apy_display(self) -> str:
        return f"{self.apy:.2f}%"

    @property
    def tvl_display(self) -> str:
        if self.tvl >= 1_000_000:
            return f"${self.tvl / 1_000_000:.1f}M"
        elif self.tvl >= 1_000:
            return f"${self.tvl / 1_000:.1f}K"
        return f"${self.tvl:.0f}"


@dataclass
class YieldPosition:
    """An active yield position."""
    opportunity: YieldOpportunity
    deposited_amount: float       # Amount of deposit token
    deposited_value_usd: float    # Value at deposit time
    current_value_usd: float      # Current value including yield
    rewards_earned: float         # Unclaimed rewards in USD
    entry_timestamp: float        # When position was opened
    last_compound: float          # Last auto-compound timestamp

    @property
    def pnl(self) -> float:
        """Profit/loss in USD."""
        return self.current_value_usd - self.deposited_value_usd + self.rewards_earned

    @property
    def pnl_pct(self) -> float:
        """Profit/loss percentage."""
        if self.deposited_value_usd == 0:
            return 0
        return (self.pnl / self.deposited_value_usd) * 100


@dataclass
class YieldConfig:
    """Configuration for yield optimizer."""
    min_apy: float = 1.0              # Minimum APY to consider (%)
    max_risk: RiskLevel = RiskLevel.MEDIUM
    min_tvl: float = 1_000_000        # Minimum TVL in USD
    auto_compound_threshold: float = 50  # Compound when rewards > $50
    compound_interval: int = 86400    # Max compound every 24h
    slippage_tolerance: float = 0.5   # 0.5% slippage
    preferred_protocols: list[Protocol] = field(default_factory=lambda: list(Protocol))
    excluded_protocols: list[Protocol] = field(default_factory=list)


class YieldOptimizer:
    """Auto-compound and optimize yield across DeFi protocols.

    Example::

        optimizer = YieldOptimizer(wallet, chain)
        opportunities = optimizer.scan_opportunities("USDC")
        best = optimizer.find_best("USDC", amount=10000)
        tx = optimizer.deposit(best, amount=10000)
        optimizer.auto_compound_all()
    """

    # DeFi protocol endpoints for APY data
    DEFI_LLAMA_POOLS = "https://yields.llama.fi/pools"
    DEFI_LLAMA_CHART = "https://yields.llama.fi/chart/{pool_id}"

    # Protocol-specific contract ABIs (simplified)
    AAVE_V3_POOL = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"  # Ethereum
    COMPOUND_V3_USDC = "0xc3d688B66703497DAA19211EEdff47f25384cdc3"

    def __init__(
        self,
        wallet: Wallet,
        chain: Chain,
        config: Optional[YieldConfig] = None,
    ):
        self.wallet = wallet
        self.chain = chain
        self.config = config or YieldConfig()
        self.positions: list[YieldPosition] = []
        self._cached_opportunities: list[YieldOpportunity] = []
        self._last_scan: float = 0

    def scan_opportunities(
        self,
        asset: Optional[str] = None,
        force_refresh: bool = False,
    ) -> list[YieldOpportunity]:
        """Scan DeFi protocols for yield opportunities.

        Args:
            asset: Filter by asset (e.g. "USDC", "WETH"). None = all.
            force_refresh: Force fresh data fetch.

        Returns:
            List of yield opportunities sorted by APY (descending).
        """
        now = time.time()
        if (
            not force_refresh
            and self._cached_opportunities
            and now - self._last_scan < 300  # Cache for 5 min
        ):
            opportunities = self._cached_opportunities
        else:
            opportunities = self._fetch_yields_from_defillama()
            self._cached_opportunities = opportunities
            self._last_scan = now

        # Apply filters
        filtered = []
        for opp in opportunities:
            if asset and opp.asset.upper() != asset.upper():
                continue
            if opp.apy < self.config.min_apy:
                continue
            if opp.tvl < self.config.min_tvl:
                continue
            if self._risk_priority(opp.risk) > self._risk_priority(self.config.max_risk):
                continue
            if opp.protocol in self.config.excluded_protocols:
                continue
            filtered.append(opp)

        # Sort by APY descending
        filtered.sort(key=lambda x: x.apy, reverse=True)
        return filtered

    def find_best(
        self,
        asset: str,
        amount: float,
        risk: Optional[RiskLevel] = None,
    ) -> Optional[YieldOpportunity]:
        """Find the best yield opportunity for a given asset and amount.

        Args:
            asset: Token symbol (e.g. "USDC")
            amount: Amount in token units
            risk: Maximum risk level override

        Returns:
            Best opportunity or None if nothing qualifies.
        """
        max_risk = risk or self.config.max_risk
        opportunities = self.scan_opportunities(asset)

        for opp in opportunities:
            if self._risk_priority(opp.risk) <= self._risk_priority(max_risk):
                if opp.min_deposit <= amount:
                    return opp
        return None

    def deposit(
        self,
        opportunity: YieldOpportunity,
        amount: float,
    ) -> dict:
        """Deposit into a yield opportunity.

        Args:
            opportunity: The yield opportunity to deposit into.
            amount: Amount of deposit token.

        Returns:
            Transaction result dict.
        """
        # Approve token spending
        approve_tx = self._build_approve_tx(
            token=opportunity.deposit_token,
            spender=opportunity.pool_address,
            amount=amount,
        )

        # Build deposit transaction
        deposit_tx = self._build_deposit_tx(
            opportunity=opportunity,
            amount=amount,
        )

        # Track position
        position = YieldPosition(
            opportunity=opportunity,
            deposited_amount=amount,
            deposited_value_usd=amount,  # TODO: fetch actual USD value
            current_value_usd=amount,
            rewards_earned=0,
            entry_timestamp=time.time(),
            last_compound=time.time(),
        )
        self.positions.append(position)

        return {
            "approve_tx": approve_tx,
            "deposit_tx": deposit_tx,
            "position": position,
            "status": "submitted",
        }

    def withdraw(
        self,
        position: YieldPosition,
        percentage: float = 100,
    ) -> dict:
        """Withdraw from a yield position.

        Args:
            position: The position to withdraw from.
            percentage: Percentage to withdraw (1-100).

        Returns:
            Transaction result dict.
        """
        withdraw_amount = position.deposited_amount * (percentage / 100)

        withdraw_tx = self._build_withdraw_tx(
            opportunity=position.opportunity,
            amount=withdraw_amount,
        )

        if percentage >= 100:
            self.positions.remove(position)
        else:
            position.deposited_amount -= withdraw_amount

        return {
            "withdraw_tx": withdraw_tx,
            "amount": withdraw_amount,
            "status": "submitted",
        }

    def auto_compound_all(self) -> list[dict]:
        """Auto-compound all positions where rewards exceed threshold.

        Returns:
            List of compound results.
        """
        results = []
        now = time.time()

        for position in self.positions:
            # Check if enough time has passed since last compound
            if now - position.last_compound < self.config.compound_interval:
                continue

            # Check if rewards exceed threshold
            if position.rewards_earned < self.config.auto_compound_threshold:
                continue

            result = self._compound_position(position)
            results.append(result)
            position.last_compound = now

        return results

    def get_portfolio_summary(self) -> dict:
        """Get summary of all yield positions.

        Returns:
            Portfolio summary dict.
        """
        total_deposited = sum(p.deposited_value_usd for p in self.positions)
        total_current = sum(p.current_value_usd for p in self.positions)
        total_rewards = sum(p.rewards_earned for p in self.positions)
        total_pnl = sum(p.pnl for p in self.positions)

        avg_apy = 0
        if self.positions:
            weighted_apy = sum(
                p.opportunity.apy * p.deposited_value_usd
                for p in self.positions
            )
            avg_apy = weighted_apy / total_deposited if total_deposited > 0 else 0

        return {
            "total_positions": len(self.positions),
            "total_deposited_usd": total_deposited,
            "total_current_usd": total_current,
            "total_rewards_usd": total_rewards,
            "total_pnl_usd": total_pnl,
            "total_pnl_pct": (total_pnl / total_deposited * 100) if total_deposited > 0 else 0,
            "average_apy": avg_apy,
            "positions": [
                {
                    "protocol": p.opportunity.protocol.value,
                    "asset": p.opportunity.asset,
                    "apy": p.opportunity.apy,
                    "deposited": p.deposited_value_usd,
                    "current": p.current_value_usd,
                    "pnl": p.pnl,
                }
                for p in self.positions
            ],
        }

    def compare_protocols(self, asset: str) -> list[dict]:
        """Compare yield across protocols for a specific asset.

        Args:
            asset: Token symbol to compare.

        Returns:
            List of protocol comparisons sorted by APY.
        """
        opportunities = self.scan_opportunities(asset)
        return [
            {
                "protocol": opp.protocol.value,
                "pool": opp.pool_name,
                "apy": opp.apy,
                "tvl": opp.tvl,
                "risk": opp.risk.value,
                "compoundable": opp.is_compoundable,
            }
            for opp in opportunities
        ]

    # === Internal methods ===

    def _fetch_yields_from_defillama(self) -> list[YieldOpportunity]:
        """Fetch yield data from DeFiLlama API."""
        import httpx

        try:
            resp = httpx.get(self.DEFI_LLAMA_POOLS, timeout=15)
            resp.raise_for_status()
            data = resp.json().get("data", [])
        except Exception:
            return self._get_fallback_yields()

        opportunities = []
        chain_name = self._chain_to_defillama()

        for pool in data:
            if pool.get("chain", "").lower() != chain_name:
                continue
            if not pool.get("apy") or pool.get("apy", 0) < self.config.min_apy:
                continue
            tvl = pool.get("tvlUsd", 0)
            if tvl < self.config.min_tvl:
                continue

            protocol = self._map_protocol(pool.get("project", ""))
            if protocol is None:
                continue

            opp = YieldOpportunity(
                protocol=protocol,
                chain=self.chain,
                asset=pool.get("symbol", "UNKNOWN"),
                apy=pool.get("apy", 0),
                tvl=tvl,
                risk=self._assess_risk(pool),
                pool_address=pool.get("pool", ""),
                pool_name=pool.get("poolMeta", pool.get("symbol", "")),
                deposit_token=pool.get("tokenAddress", ""),
                reward_tokens=pool.get("rewardTokens", []),
                is_compoundable=pool.get("exposure", "single") == "single",
                last_updated=time.time(),
            )
            opportunities.append(opp)

        return opportunities

    def _get_fallback_yields(self) -> list[YieldOpportunity]:
        """Fallback hardcoded yields when API is unavailable."""
        return [
            YieldOpportunity(
                protocol=Protocol.AAVE_V3,
                chain=self.chain,
                asset="USDC",
                apy=4.5,
                tvl=500_000_000,
                risk=RiskLevel.LOW,
                pool_address=self.AAVE_V3_POOL,
                pool_name="Aave V3 USDC",
                deposit_token="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                is_compoundable=True,
                last_updated=time.time(),
            ),
            YieldOpportunity(
                protocol=Protocol.COMPOUND_V3,
                chain=self.chain,
                asset="USDC",
                apy=3.8,
                tvl=300_000_000,
                risk=RiskLevel.LOW,
                pool_address=self.COMPOUND_V3_USDC,
                pool_name="Compound V3 USDC",
                deposit_token="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                is_compoundable=True,
                last_updated=time.time(),
            ),
            YieldOpportunity(
                protocol=Protocol.LIDO,
                chain=self.chain,
                asset="ETH",
                apy=3.2,
                tvl=15_000_000_000,
                risk=RiskLevel.LOW,
                pool_address="0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",
                pool_name="Lido stETH",
                deposit_token="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                is_compoundable=True,
                last_updated=time.time(),
            ),
        ]

    def _compound_position(self, position: YieldPosition) -> dict:
        """Compound rewards back into a position."""
        claim_tx = self._build_claim_tx(position)
        deposit_tx = self._build_deposit_tx(
            opportunity=position.opportunity,
            amount=position.rewards_earned,
        )

        compounded = position.rewards_earned
        position.deposited_amount += compounded
        position.current_value_usd += compounded
        position.rewards_earned = 0

        return {
            "claim_tx": claim_tx,
            "deposit_tx": deposit_tx,
            "compounded_amount": compounded,
            "status": "compounded",
        }

    def _build_approve_tx(self, token: str, spender: str, amount: float) -> dict:
        """Build ERC20 approve transaction."""
        return {
            "to": token,
            "function": "approve",
            "args": {"spender": spender, "amount": amount},
            "status": "built",
        }

    def _build_deposit_tx(self, opportunity: YieldOpportunity, amount: float) -> dict:
        """Build deposit transaction for a protocol."""
        return {
            "to": opportunity.pool_address,
            "function": "deposit",
            "args": {"amount": amount, "asset": opportunity.deposit_token},
            "protocol": opportunity.protocol.value,
            "status": "built",
        }

    def _build_withdraw_tx(self, opportunity: YieldOpportunity, amount: float) -> dict:
        """Build withdraw transaction."""
        return {
            "to": opportunity.pool_address,
            "function": "withdraw",
            "args": {"amount": amount},
            "protocol": opportunity.protocol.value,
            "status": "built",
        }

    def _build_claim_tx(self, position: YieldPosition) -> dict:
        """Build claim rewards transaction."""
        return {
            "to": position.opportunity.pool_address,
            "function": "claimRewards",
            "args": {},
            "status": "built",
        }

    def _chain_to_defillama(self) -> str:
        """Map Chain enum to DeFiLlama chain name."""
        mapping = {
            Chain.ETHEREUM: "ethereum",
            Chain.BASE: "base",
            Chain.ARBITRUM: "arbitrum",
            Chain.POLYGON: "polygon",
            Chain.OPTIMISM: "optimism",
            Chain.BSC: "bsc",
            Chain.AVALANCHE: "avax",
            Chain.SOLANA: "solana",
        }
        return mapping.get(self.chain, "ethereum")

    def _map_protocol(self, project: str) -> Protocol | None:
        """Map DeFiLlama project name to Protocol enum."""
        mapping = {
            "aave-v3": Protocol.AAVE_V3,
            "compound-v3": Protocol.COMPOUND_V3,
            "morpho": Protocol.MORPHO,
            "lido": Protocol.LIDO,
            "rocket-pool": Protocol.ROCKET_POOL,
            "fluid": Protocol.FLUID,
        }
        return mapping.get(project.lower())

    def _assess_risk(self, pool: dict) -> RiskLevel:
        """Assess risk level of a pool."""
        tvl = pool.get("tvlUsd", 0)
        apy = pool.get("apy", 0)
        stablecoin = pool.get("stablecoin", False)

        if stablecoin and tvl > 100_000_000:
            return RiskLevel.LOW
        if tvl > 50_000_000 and apy < 20:
            return RiskLevel.LOW
        if tvl > 10_000_000 and apy < 50:
            return RiskLevel.MEDIUM
        return RiskLevel.HIGH

    @staticmethod
    def _risk_priority(risk: RiskLevel) -> int:
        """Risk priority for comparison (lower = safer)."""
        return {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}[risk]
