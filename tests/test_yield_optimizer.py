"""Tests for Yield Optimizer."""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.defi.yield_optimizer import (
    YieldOptimizer,
    YieldConfig,
    YieldOpportunity,
    YieldPosition,
    Protocol,
    RiskLevel,
)
from src.chains.chain import Chain


@pytest.fixture
def mock_wallet():
    """Create a mock wallet."""
    wallet = MagicMock()
    wallet.address = "0x1234567890123456789012345678901234567890"
    return wallet


@pytest.fixture
def config():
    """Create a default yield config."""
    return YieldConfig(
        min_apy=1.0,
        max_risk=RiskLevel.MEDIUM,
        min_tvl=1_000_000,
        auto_compound_threshold=50,
        compound_interval=3600,
    )


@pytest.fixture
def optimizer(mock_wallet, config):
    """Create a yield optimizer instance."""
    return YieldOptimizer(mock_wallet, Chain.ETHEREUM, config)


@pytest.fixture
def sample_opportunity():
    """Create a sample yield opportunity."""
    return YieldOpportunity(
        protocol=Protocol.AAVE_V3,
        chain=Chain.ETHEREUM,
        asset="USDC",
        apy=4.5,
        tvl=500_000_000,
        risk=RiskLevel.LOW,
        pool_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
        pool_name="Aave V3 USDC",
        deposit_token="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        is_compoundable=True,
        last_updated=time.time(),
    )


class TestYieldOpportunity:
    def test_apy_display(self, sample_opportunity):
        assert sample_opportunity.apy_display == "4.50%"

    def test_tvl_display_millions(self, sample_opportunity):
        assert sample_opportunity.tvl_display == "$500.0M"

    def test_tvl_display_thousands(self):
        opp = YieldOpportunity(
            protocol=Protocol.AAVE_V3,
            chain=Chain.ETHEREUM,
            asset="USDC",
            apy=4.5,
            tvl=50_000,
            risk=RiskLevel.LOW,
            pool_address="0x123",
            pool_name="Test",
            deposit_token="0x456",
        )
        assert opp.tvl_display == "$50.0K"

    def test_tvl_display_raw(self):
        opp = YieldOpportunity(
            protocol=Protocol.AAVE_V3,
            chain=Chain.ETHEREUM,
            asset="USDC",
            apy=4.5,
            tvl=500,
            risk=RiskLevel.LOW,
            pool_address="0x123",
            pool_name="Test",
            deposit_token="0x456",
        )
        assert opp.tvl_display == "$500"


class TestYieldPosition:
    def test_pnl_positive(self, sample_opportunity):
        position = YieldPosition(
            opportunity=sample_opportunity,
            deposited_amount=10000,
            deposited_value_usd=10000,
            current_value_usd=10450,
            rewards_earned=50,
            entry_timestamp=time.time(),
            last_compound=time.time(),
        )
        assert position.pnl == 500
        assert position.pnl_pct == 5.0

    def test_pnl_negative(self, sample_opportunity):
        position = YieldPosition(
            opportunity=sample_opportunity,
            deposited_amount=10000,
            deposited_value_usd=10000,
            current_value_usd=9500,
            rewards_earned=0,
            entry_timestamp=time.time(),
            last_compound=time.time(),
        )
        assert position.pnl == -500
        assert position.pnl_pct == -5.0

    def test_pnl_zero_deposit(self, sample_opportunity):
        position = YieldPosition(
            opportunity=sample_opportunity,
            deposited_amount=0,
            deposited_value_usd=0,
            current_value_usd=0,
            rewards_earned=0,
            entry_timestamp=time.time(),
            last_compound=time.time(),
        )
        assert position.pnl_pct == 0


class TestYieldConfig:
    def test_defaults(self):
        config = YieldConfig()
        assert config.min_apy == 1.0
        assert config.max_risk == RiskLevel.MEDIUM
        assert config.min_tvl == 1_000_000
        assert config.auto_compound_threshold == 50
        assert config.slippage_tolerance == 0.5


class TestYieldOptimizer:
    def test_fallback_yields(self, optimizer):
        """Test that fallback yields are returned when API fails."""
        opportunities = optimizer._get_fallback_yields()
        assert len(opportunities) >= 2
        assert any(o.protocol == Protocol.AAVE_V3 for o in opportunities)
        assert any(o.protocol == Protocol.COMPOUND_V3 for o in opportunities)

    def test_scan_filters_by_asset(self, optimizer):
        """Test that scan filters by asset."""
        fallback = optimizer._get_fallback_yields()
        optimizer._cached_opportunities = fallback
        optimizer._last_scan = time.time()

        usdc_opps = optimizer.scan_opportunities("USDC")
        for opp in usdc_opps:
            assert opp.asset.upper() == "USDC"

    def test_scan_filters_by_min_apy(self, optimizer, config):
        """Test that scan filters by minimum APY."""
        config.min_apy = 4.0
        fallback = optimizer._get_fallback_yields()
        optimizer._cached_opportunities = fallback
        optimizer._last_scan = time.time()

        filtered = optimizer.scan_opportunities()
        for opp in filtered:
            assert opp.apy >= 4.0

    def test_find_best(self, optimizer):
        """Test finding best opportunity."""
        fallback = optimizer._get_fallback_yields()
        optimizer._cached_opportunities = fallback
        optimizer._last_scan = time.time()

        best = optimizer.find_best("USDC", amount=10000)
        assert best is not None
        assert best.asset.upper() == "USDC"

    def test_deposit_tracks_position(self, optimizer, sample_opportunity):
        """Test that deposit creates a position."""
        result = optimizer.deposit(sample_opportunity, amount=10000)
        assert result["status"] == "submitted"
        assert len(optimizer.positions) == 1
        assert optimizer.positions[0].deposited_amount == 10000

    def test_withdraw_removes_position(self, optimizer, sample_opportunity):
        """Test that full withdraw removes position."""
        optimizer.deposit(sample_opportunity, amount=10000)
        position = optimizer.positions[0]

        result = optimizer.withdraw(position, percentage=100)
        assert result["status"] == "submitted"
        assert len(optimizer.positions) == 0

    def test_withdraw_partial(self, optimizer, sample_opportunity):
        """Test partial withdrawal."""
        optimizer.deposit(sample_opportunity, amount=10000)
        position = optimizer.positions[0]

        result = optimizer.withdraw(position, percentage=50)
        assert optimizer.positions[0].deposited_amount == 5000

    def test_auto_compound_respects_threshold(self, optimizer, sample_opportunity):
        """Test that auto-compound only compounds when above threshold."""
        optimizer.deposit(sample_opportunity, amount=10000)
        position = optimizer.positions[0]
        position.rewards_earned = 10  # Below threshold of 50
        position.last_compound = 0  # Force past interval

        results = optimizer.auto_compound_all()
        assert len(results) == 0  # Below threshold

    def test_auto_compound_respects_interval(self, optimizer, sample_opportunity):
        """Test that auto-compound respects time interval."""
        optimizer.deposit(sample_opportunity, amount=10000)
        position = optimizer.positions[0]
        position.rewards_earned = 100  # Above threshold
        position.last_compound = time.time()  # Just compounded

        results = optimizer.auto_compound_all()
        assert len(results) == 0  # Too soon

    def test_portfolio_summary_empty(self, optimizer):
        """Test portfolio summary with no positions."""
        summary = optimizer.get_portfolio_summary()
        assert summary["total_positions"] == 0
        assert summary["total_deposited_usd"] == 0

    def test_portfolio_summary_with_positions(self, optimizer, sample_opportunity):
        """Test portfolio summary with positions."""
        optimizer.deposit(sample_opportunity, amount=10000)
        summary = optimizer.get_portfolio_summary()

        assert summary["total_positions"] == 1
        assert summary["total_deposited_usd"] == 10000

    def test_compare_protocols(self, optimizer):
        """Test protocol comparison."""
        fallback = optimizer._get_fallback_yields()
        optimizer._cached_opportunities = fallback
        optimizer._last_scan = time.time()

        comparison = optimizer.compare_protocols("USDC")
        assert isinstance(comparison, list)

    def test_chain_to_defillama(self, optimizer):
        """Test chain name mapping."""
        assert optimizer._chain_to_defillama() == "ethereum"

    def test_risk_priority(self):
        """Test risk priority ordering."""
        assert YieldOptimizer._risk_priority(RiskLevel.LOW) < YieldOptimizer._risk_priority(RiskLevel.MEDIUM)
        assert YieldOptimizer._risk_priority(RiskLevel.MEDIUM) < YieldOptimizer._risk_priority(RiskLevel.HIGH)
