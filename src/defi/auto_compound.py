"""Yield Auto-Compound — automated compounding of DeFi yield positions.

Supports Aave, Compound, and generic ERC-4626 vaults. Calculates optimal
compound frequency based on gas costs vs rewards.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Protocol(Enum):
    AAVE_V3 = "aave_v3"
    COMPOUND_V3 = "compound_v3"
    ERC4626 = "erc4626"


@dataclass
class CompoundConfig:
    """Configuration for auto-compound strategy."""

    protocol: Protocol = Protocol.AAVE_V3
    min_reward_threshold_usd: float = 10.0  # Minimum rewards to trigger compound
    max_gas_cost_usd: float = 5.0  # Max gas willing to pay per compound
    gas_price_gwei: int = 30
    check_interval_minutes: int = 60  # How often to check rewards
    dry_run: bool = True  # Don't actually execute transactions


@dataclass
class Position:
    """A yield position being tracked."""

    chain: str
    protocol: Protocol
    token: str  # Token symbol
    deposited_amount: float
    deposited_value_usd: float
    current_apy: float  # Annual percentage yield (e.g., 5.0 = 5%)
    reward_token: str
    pending_rewards: float
    pending_rewards_usd: float
    token_address: str = ""
    reward_token_address: str = ""


@dataclass
class CompoundResult:
    """Result of a compound attempt."""

    position: Position
    should_compound: bool
    compound_amount: float
    compound_amount_usd: float
    gas_cost_usd: float
    net_profit_usd: float
    reason: str  # Why we did/didn't compound
    new_apy_effective: float  # APY with compounding effect


class AutoCompound:
    """Automated yield compounding strategy.

    Usage:
        compounder = AutoCompound(CompoundConfig(
            protocol=Protocol.AAVE_V3,
            min_reward_threshold_usd=10.0,
            max_gas_cost_usd=5.0,
            dry_run=True,
        ))

        pos = Position(
            chain="ethereum",
            protocol=Protocol.AAVE_V3,
            token="USDC",
            deposited_amount=10000.0,
            deposited_value_usd=10000.0,
            current_apy=5.0,
            reward_token="AAVE",
            pending_rewards=25.0,
            pending_rewards_usd=25.0,
        )

        result = compounder.evaluate(pos)
        print(f"Compound: {result.should_compound} — {result.reason}")
    """

    def __init__(self, config: Optional[CompoundConfig] = None):
        self.config = config or CompoundConfig()
        self.positions: dict[str, Position] = {}
        self.history: list[CompoundResult] = []

    # ── Evaluation ──────────────────────────────────

    def evaluate(self, position: Position) -> CompoundResult:
        """Evaluate whether a position should be compounded.

        Decision logic:
        1. Is pending rewards > gas cost?
        2. Is pending rewards > minimum threshold?
        3. Is compound frequency optimal?
        """
        # Estimate gas cost for claiming + redepositing
        gas_cost_eth = self._estimate_gas_cost(position.chain)
        gas_cost_usd = gas_cost_eth * self._eth_price()

        compound_amount = position.pending_rewards
        compound_amount_usd = position.pending_rewards_usd

        # Net profit after gas
        net_profit_usd = compound_amount_usd - gas_cost_usd

        # Calculate effective APY with compounding
        new_apy = self._calculate_compound_apy(
            position.current_apy,
            self.config.check_interval_minutes,
        )

        # Decision checks
        if compound_amount_usd <= 0:
            return CompoundResult(
                position=position,
                should_compound=False,
                compound_amount=0,
                compound_amount_usd=0,
                gas_cost_usd=gas_cost_usd,
                net_profit_usd=0,
                reason="No pending rewards",
                new_apy_effective=new_apy,
            )

        if compound_amount_usd < self.config.min_reward_threshold_usd:
            return CompoundResult(
                position=position,
                should_compound=False,
                compound_amount=compound_amount,
                compound_amount_usd=compound_amount_usd,
                gas_cost_usd=gas_cost_usd,
                net_profit_usd=net_profit_usd,
                reason=f"Below threshold: ${compound_amount_usd:.2f} < ${self.config.min_reward_threshold_usd:.2f}",
                new_apy_effective=new_apy,
            )

        if gas_cost_usd > self.config.max_gas_cost_usd:
            return CompoundResult(
                position=position,
                should_compound=False,
                compound_amount=compound_amount,
                compound_amount_usd=compound_amount_usd,
                gas_cost_usd=gas_cost_usd,
                net_profit_usd=net_profit_usd,
                reason=f"Gas too high: ${gas_cost_usd:.2f} > ${self.config.max_gas_cost_usd:.2f}",
                new_apy_effective=new_apy,
            )

        if net_profit_usd <= 0:
            return CompoundResult(
                position=position,
                should_compound=False,
                compound_amount=compound_amount,
                compound_amount_usd=compound_amount_usd,
                gas_cost_usd=gas_cost_usd,
                net_profit_usd=net_profit_usd,
                reason=f"Not profitable: gas ${gas_cost_usd:.2f} > rewards ${compound_amount_usd:.2f}",
                new_apy_effective=new_apy,
            )

        return CompoundResult(
            position=position,
            should_compound=True,
            compound_amount=compound_amount,
            compound_amount_usd=compound_amount_usd,
            gas_cost_usd=gas_cost_usd,
            net_profit_usd=net_profit_usd,
            reason=f"Profitable: ${net_profit_usd:.2f} net after gas",
            new_apy_effective=new_apy,
        )

    # ── Gas Estimation ──────────────────────────────

    def _estimate_gas_cost(self, chain: str) -> float:
        """Estimate gas cost in ETH for one compound operation.

        Aave V3 claimRewards + deposit: ~300K gas
        Compound V3 claim + supply: ~250K gas
        ERC-4626 redeem + deposit: ~200K gas
        """
        gas_estimates = {
            Protocol.AAVE_V3: 300_000,
            Protocol.COMPOUND_V3: 250_000,
            Protocol.ERC4626: 200_000,
        }

        # Find the protocol from our positions
        gas_units = 300_000  # default
        for pos in self.positions.values():
            if pos.chain == chain:
                gas_units = gas_estimates.get(pos.protocol, 300_000)
                break

        gas_price_eth = self.config.gas_price_gwei * 1e-9
        return gas_units * gas_price_eth

    def _eth_price(self) -> float:
        """Get current ETH price in USD."""
        # In production, fetch from oracle
        return 3000.0  # placeholder

    # ── APY Calculations ────────────────────────────

    def _calculate_compound_apy(
        self,
        base_apy: float,
        compound_interval_minutes: int,
    ) -> float:
        """Calculate effective APY with compounding.

        Formula: APY = (1 + r/n)^n - 1
        where r = base APR, n = compounds per year
        """
        if base_apy <= 0:
            return 0.0

        compounds_per_year = (365 * 24 * 60) / compound_interval_minutes
        apr = base_apy / 100.0

        if compounds_per_year <= 0:
            return base_apy

        apy = (1 + apr / compounds_per_year) ** compounds_per_year - 1
        return apy * 100.0

    def calculate_optimal_interval(
        self,
        position: Position,
        gas_cost_usd: float,
    ) -> int:
        """Calculate optimal compound interval in minutes.

        Balances compound frequency vs gas costs to maximize net returns.
        """
        best_interval = 1440  # Default: daily
        best_net_return = 0

        # Test intervals from 1 hour to 7 days
        intervals = [60, 120, 240, 360, 720, 1440, 2880, 4320, 5760, 10080]

        for interval in intervals:
            effective_apy = self._calculate_compound_apy(
                position.current_apy, interval
            )
            annual_return = position.deposited_value_usd * (effective_apy / 100)
            compounds_per_year = (365 * 24 * 60) / interval
            annual_gas_cost = compounds_per_year * gas_cost_usd
            net_return = annual_return - position.deposited_value_usd * (position.current_apy / 100) - annual_gas_cost

            if net_return > best_net_return:
                best_net_return = net_return
                best_interval = interval

        return best_interval

    # ── Position Management ─────────────────────────

    def add_position(self, position: Position):
        """Track a new yield position."""
        key = f"{position.chain}:{position.protocol.value}:{position.token}"
        self.positions[key] = position

    def remove_position(self, chain: str, protocol: Protocol, token: str):
        """Stop tracking a position."""
        key = f"{chain}:{protocol.value}:{token}"
        self.positions.pop(key, None)

    def evaluate_all(self) -> dict[str, CompoundResult]:
        """Evaluate all tracked positions."""
        results = {}
        for key, pos in self.positions.items():
            results[key] = self.evaluate(pos)
            self.history.append(results[key])
        return results

    # ── Portfolio Summary ───────────────────────────

    def get_portfolio_summary(self) -> dict:
        """Get summary of all positions and compound status."""
        results = self.evaluate_all()
        total_deposited = sum(p.deposited_value_usd for p in self.positions.values())
        total_pending = sum(p.pending_rewards_usd for p in self.positions.values())
        total_to_compound = sum(
            r.compound_amount_usd for r in results.values() if r.should_compound
        )

        return {
            "total_positions": len(self.positions),
            "total_deposited_usd": total_deposited,
            "total_pending_rewards_usd": total_pending,
            "total_to_compound_usd": total_to_compound,
            "positions": [
                {
                    "chain": p.chain,
                    "token": p.token,
                    "apy": p.current_apy,
                    "deposited": p.deposited_value_usd,
                    "pending": p.pending_rewards_usd,
                    "should_compound": results[k].should_compound,
                    "net_profit": results[k].net_profit_usd,
                }
                for k, p in self.positions.items()
            ],
        }