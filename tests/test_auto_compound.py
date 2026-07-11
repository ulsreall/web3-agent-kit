"""Tests for Yield Auto-Compound module."""

import pytest
from src.defi.auto_compound import (
    AutoCompound,
    CompoundConfig,
    Position,
    Protocol,
    CompoundResult,
)


@pytest.fixture
def compounder():
    return AutoCompound(CompoundConfig(
        protocol=Protocol.AAVE_V3,
        min_reward_threshold_usd=10.0,
        max_gas_cost_usd=5.0,
        gas_price_gwei=30,
        check_interval_minutes=60,
        dry_run=True,
    ))


@pytest.fixture
def usdc_position():
    return Position(
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


class TestCompoundConfig:
    def test_default_config(self):
        config = CompoundConfig()
        assert config.protocol == Protocol.AAVE_V3
        assert config.min_reward_threshold_usd == 10.0
        assert config.dry_run is True

    def test_custom_config(self):
        config = CompoundConfig(
            protocol=Protocol.COMPOUND_V3,
            min_reward_threshold_usd=50.0,
            dry_run=False,
        )
        assert config.protocol == Protocol.COMPOUND_V3
        assert config.min_reward_threshold_usd == 50.0
        assert config.dry_run is False


class TestPosition:
    def test_position_creation(self):
        pos = Position(
            chain="ethereum",
            protocol=Protocol.AAVE_V3,
            token="USDC",
            deposited_amount=5000.0,
            deposited_value_usd=5000.0,
            current_apy=4.0,
            reward_token="AAVE",
            pending_rewards=10.0,
            pending_rewards_usd=10.0,
        )
        assert pos.chain == "ethereum"
        assert pos.token == "USDC"
        assert pos.current_apy == 4.0


class TestAutoCompound:
    def test_init(self, compounder):
        assert compounder.config.min_reward_threshold_usd == 10.0
        assert len(compounder.positions) == 0

    def test_add_position(self, compounder, usdc_position):
        compounder.add_position(usdc_position)
        assert len(compounder.positions) == 1
        key = "ethereum:aave_v3:USDC"
        assert key in compounder.positions

    def test_remove_position(self, compounder, usdc_position):
        compounder.add_position(usdc_position)
        compounder.remove_position("ethereum", Protocol.AAVE_V3, "USDC")
        assert len(compounder.positions) == 0

    def test_evaluate_profitable(self, compounder, usdc_position):
        """Should compound: $25 rewards > $5 max gas (at 3 gwei)."""
        compounder.config.gas_price_gwei = 3
        result = compounder.evaluate(usdc_position)
        assert result.should_compound is True
        assert result.compound_amount == 25.0
        assert result.net_profit_usd > 0
        assert "Profitable" in result.reason

    def test_evaluate_no_rewards(self, compounder):
        pos = Position(
            chain="ethereum",
            protocol=Protocol.AAVE_V3,
            token="USDC",
            deposited_amount=10000.0,
            deposited_value_usd=10000.0,
            current_apy=5.0,
            reward_token="AAVE",
            pending_rewards=0,
            pending_rewards_usd=0,
        )
        result = compounder.evaluate(pos)
        assert result.should_compound is False
        assert "No pending rewards" in result.reason

    def test_evaluate_below_threshold(self, compounder):
        pos = Position(
            chain="ethereum",
            protocol=Protocol.AAVE_V3,
            token="USDC",
            deposited_amount=10000.0,
            deposited_value_usd=10000.0,
            current_apy=5.0,
            reward_token="AAVE",
            pending_rewards=5.0,
            pending_rewards_usd=5.0,
        )
        result = compounder.evaluate(pos)
        assert result.should_compound is False
        assert "Below threshold" in result.reason

    def test_evaluate_gas_too_high(self, compounder):
        """With gas price at 1000 gwei, gas cost exceeds max_gas_cost_usd."""
        compounder.config.gas_price_gwei = 1000
        pos = Position(
            chain="ethereum",
            protocol=Protocol.AAVE_V3,
            token="USDC",
            deposited_amount=10000.0,
            deposited_value_usd=10000.0,
            current_apy=5.0,
            reward_token="AAVE",
            pending_rewards=100.0,
            pending_rewards_usd=100.0,
        )
        result = compounder.evaluate(pos)
        assert result.should_compound is False
        assert "Gas too high" in result.reason

    def test_calculate_compound_apy(self, compounder):
        """APY should be higher than base APR with compounding."""
        base_apy = 5.0
        effective = compounder._calculate_compound_apy(base_apy, 60)
        assert effective > base_apy  # Compounding increases APY

    def test_calculate_compound_apy_zero(self, compounder):
        assert compounder._calculate_compound_apy(0, 60) == 0.0

    def test_calculate_compound_apy_daily(self, compounder):
        """Daily compound of 5% APR."""
        effective = compounder._calculate_compound_apy(5.0, 1440)
        assert effective > 5.0
        assert effective < 6.0  # Should be around 5.13%

    def test_calculate_optimal_interval(self, compounder, usdc_position):
        interval = compounder.calculate_optimal_interval(
            usdc_position, gas_cost_usd=2.0
        )
        assert interval > 0
        # Should be in our tested intervals
        assert interval in [60, 120, 240, 360, 720, 1440, 2880, 4320, 5760, 10080]

    def test_evaluate_all(self, compounder, usdc_position):
        compounder.add_position(usdc_position)
        results = compounder.evaluate_all()
        assert len(results) == 1
        assert len(compounder.history) == 1

    def test_portfolio_summary(self, compounder, usdc_position):
        compounder.add_position(usdc_position)
        summary = compounder.get_portfolio_summary()
        assert summary["total_positions"] == 1
        assert summary["total_deposited_usd"] == 10000.0
        assert summary["total_pending_rewards_usd"] == 25.0
        assert len(summary["positions"]) == 1

    def test_compound_result_net_profit(self, compounder, usdc_position):
        result = compounder.evaluate(usdc_position)
        assert result.net_profit_usd == result.compound_amount_usd - result.gas_cost_usd

    def test_compound_result_fields(self, compounder, usdc_position):
        result = compounder.evaluate(usdc_position)
        assert result.position == usdc_position
        assert result.compound_amount_usd == 25.0
        assert result.new_apy_effective > 0
        assert isinstance(result.should_compound, bool)

    def test_multiple_positions(self, compounder):
        pos1 = Position(
            chain="ethereum", protocol=Protocol.AAVE_V3, token="USDC",
            deposited_amount=10000, deposited_value_usd=10000,
            current_apy=5.0, reward_token="AAVE",
            pending_rewards=25, pending_rewards_usd=25,
        )
        pos2 = Position(
            chain="arbitrum", protocol=Protocol.COMPOUND_V3, token="ETH",
            deposited_amount=5, deposited_value_usd=15000,
            current_apy=3.0, reward_token="COMP",
            pending_rewards=2, pending_rewards_usd=2,
        )
        compounder.add_position(pos1)
        compounder.add_position(pos2)

        summary = compounder.get_portfolio_summary()
        assert summary["total_positions"] == 2
        assert summary["total_deposited_usd"] == 25000.0
        assert summary["total_pending_rewards_usd"] == 27.0