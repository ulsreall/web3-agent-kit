"""Tests for portfolio tracker."""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from src.portfolio import (
    PortfolioTracker,
    PortfolioSummary,
    ChainPortfolio,
    TokenBalance,
)
from src.chain import Chain


class TestTokenBalance:
    """Test TokenBalance dataclass."""

    def test_creation(self):
        """Test creating a TokenBalance."""
        token = TokenBalance(
            symbol="USDC",
            address="0x1234",
            balance=100.0,
            decimals=6,
            chain=Chain.BASE,
            price_usd=1.0,
            value_usd=100.0,
        )
        assert token.symbol == "USDC"
        assert token.balance == 100.0
        assert token.value_usd == 100.0

    def test_to_dict(self):
        """Test converting to dict."""
        token = TokenBalance(
            symbol="ETH",
            address="0x456",
            balance=1.5,
            decimals=18,
            chain=Chain.ETHEREUM,
            price_usd=3500.0,
            value_usd=5250.0,
        )
        d = token.to_dict()
        assert d["symbol"] == "ETH"
        assert d["balance"] == 1.5
        assert d["value_usd"] == 5250.0


class TestChainPortfolio:
    """Test ChainPortfolio dataclass."""

    def test_creation(self):
        """Test creating a ChainPortfolio."""
        tokens = [
            TokenBalance("USDC", "0x123", 100.0, 6, Chain.BASE, 1.0, 100.0),
        ]
        portfolio = ChainPortfolio(
            chain=Chain.BASE,
            native_balance=1.0,
            native_value_usd=3500.0,
            tokens=tokens,
            total_value_usd=3600.0,
        )
        assert portfolio.chain == Chain.BASE
        assert portfolio.native_balance == 1.0
        assert len(portfolio.tokens) == 1

    def test_to_dict(self):
        """Test converting to dict."""
        portfolio = ChainPortfolio(
            chain=Chain.ETHEREUM,
            native_balance=2.0,
            native_value_usd=7000.0,
            tokens=[],
            total_value_usd=7000.0,
        )
        d = portfolio.to_dict()
        assert d["chain"] == "ethereum"
        assert d["native_balance"] == 2.0


class TestPortfolioSummary:
    """Test PortfolioSummary dataclass."""

    def test_str_output(self):
        """Test string representation."""
        chains = [
            ChainPortfolio(
                chain=Chain.BASE,
                native_balance=1.0,
                native_value_usd=3500.0,
                tokens=[TokenBalance("USDC", "0x123", 100.0, 6, Chain.BASE, 1.0, 100.0)],
                total_value_usd=3600.0,
            ),
        ]
        summary = PortfolioSummary(
            address="0x1234567890abcdef",
            timestamp=1234567890.0,
            chains=chains,
            total_value_usd=3600.0,
            total_native_balances={"base": 1.0},
        )
        output = str(summary)
        assert "Portfolio" in output
        assert "$3,600" in output
        assert "BASE" in output


class TestPortfolioTracker:
    """Test PortfolioTracker."""

    def test_creation(self):
        """Test creating a tracker."""
        wallet = MagicMock()
        wallet.address = "0x1234"
        chain_manager = MagicMock()

        tracker = PortfolioTracker(chain_manager, wallet, eth_price=3500.0)
        assert tracker.eth_price == 3500.0
        assert tracker.wallet.address == "0x1234"

    def test_pnl_no_history(self):
        """Test P&L with no history."""
        wallet = MagicMock()
        chain_manager = MagicMock()

        tracker = PortfolioTracker(chain_manager, wallet)
        pnl = tracker.get_pnl()
        assert pnl["pnl_absolute"] == 0.0
        assert pnl["pnl_percent"] == 0.0

    def test_pnl_with_history(self):
        """Test P&L calculation."""
        wallet = MagicMock()
        chain_manager = MagicMock()

        tracker = PortfolioTracker(chain_manager, wallet)

        # Add mock history
        tracker._history = [
            PortfolioSummary(
                address="0x123",
                timestamp=1000.0,
                chains=[],
                total_value_usd=1000.0,
                total_native_balances={},
            ),
            PortfolioSummary(
                address="0x123",
                timestamp=2000.0,
                chains=[],
                total_value_usd=1200.0,
                total_native_balances={},
            ),
        ]

        pnl = tracker.get_pnl()
        assert pnl["pnl_absolute"] == 200.0
        assert pnl["pnl_percent"] == 20.0

    def test_repr(self):
        """Test string representation."""
        wallet = MagicMock()
        wallet.address = "0x1234567890abcdef1234567890abcdef12345678"
        chain_manager = MagicMock()

        tracker = PortfolioTracker(chain_manager, wallet)
        assert "PortfolioTracker" in repr(tracker)
        assert "0x12345678" in repr(tracker)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
