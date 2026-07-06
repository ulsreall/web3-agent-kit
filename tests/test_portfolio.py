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
from src.chains.chain import Chain


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

    @pytest.fixture
    def wallet(self):
        w = MagicMock()
        w.address = "0xabc"
        return w

    @pytest.fixture
    def chain_manager(self):
        cm = MagicMock()
        w3 = MagicMock()
        w3.to_checksum_address.side_effect = lambda addr: addr
        cm.get_web3.return_value = w3
        return cm

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

    def test_pnl_zero_initial_value(self):
        """Test P&L when initial value is zero (avoid division by zero)."""
        wallet = MagicMock()
        chain_manager = MagicMock()

        tracker = PortfolioTracker(chain_manager, wallet)
        tracker._history = [
            PortfolioSummary("0x123", 1000.0, [], 0.0, {}),
            PortfolioSummary("0x123", 2000.0, [], 100.0, {}),
        ]

        pnl = tracker.get_pnl()
        assert pnl["pnl_absolute"] == 100.0
        assert pnl["pnl_percent"] == 0.0  # Division by zero avoided

    def test_repr(self):
        """Test string representation."""
        wallet = MagicMock()
        wallet.address = "0x1234567890abcdef1234567890abcdef12345678"
        chain_manager = MagicMock()

        tracker = PortfolioTracker(chain_manager, wallet)
        assert "PortfolioTracker" in repr(tracker)
        assert "0x12345678" in repr(tracker)

    def test_get_summary_no_chains(self):
        """Test get_summary with no chains configured."""
        wallet = MagicMock()
        wallet.address = "0xabc"
        chain_manager = MagicMock()
        chain_manager.list_chains.return_value = []

        tracker = PortfolioTracker(chain_manager, wallet)
        summary = tracker.get_summary()

        assert summary.address == "0xabc"
        assert summary.total_value_usd == 0.0
        assert summary.chains == []
        assert len(tracker._history) == 1

    def test_get_summary_with_chains(self, wallet, chain_manager):
        """Test get_summary with configured chains."""
        wallet.get_balance.return_value = 1.5
        chain_manager.list_chains.return_value = [Chain.ETHEREUM, Chain.BASE]

        tracker = PortfolioTracker(chain_manager, wallet, eth_price=3000.0)
        summary = tracker.get_summary()

        assert summary.address == "0xabc"
        assert summary.total_value_usd > 0
        assert len(summary.chains) == 2

    def test_get_summary_handles_chain_error(self):
        """Test get_summary handles errors gracefully."""
        wallet = MagicMock()
        wallet.address = "0xabc"
        wallet.get_balance.side_effect = Exception("RPC error")

        chain_manager = MagicMock()
        chain_manager.list_chains.return_value = [Chain.ETHEREUM]

        tracker = PortfolioTracker(chain_manager, wallet)
        summary = tracker.get_summary()

        assert summary.total_value_usd == 0.0
        assert summary.chains == []
        assert "ethereum" not in summary.total_native_balances

    def test_get_history(self):
        """Test getting portfolio history."""
        wallet = MagicMock()
        chain_manager = MagicMock()
        tracker = PortfolioTracker(chain_manager, wallet)

        # Simulate multiple get_summary calls
        chain_manager.list_chains.return_value = []
        tracker.get_summary()
        tracker.get_summary()

        history = tracker.get_history()
        assert len(history) == 2
        assert isinstance(history[0], PortfolioSummary)

    def test_get_token_balance_success(self, wallet, chain_manager):
        """Test _get_token_balance returns a TokenBalance."""
        w3 = chain_manager.get_web3.return_value
        token_contract = MagicMock()

        # Set up mock chain: balanceOf(addr) -> callable -> .call() -> 1000000000
        balance_of_mock = MagicMock()
        balance_of_mock.call.return_value = 1000000000  # 10 USDC (6 decimals)
        token_contract.functions.balanceOf.return_value = balance_of_mock

        decimals_mock = MagicMock()
        decimals_mock.call.return_value = 6
        token_contract.functions.decimals.return_value = decimals_mock

        symbol_mock = MagicMock()
        symbol_mock.call.return_value = "USDC"
        token_contract.functions.symbol.return_value = symbol_mock

        w3.eth.contract.return_value = token_contract

        tracker = PortfolioTracker(chain_manager, wallet)
        result = tracker._get_token_balance("0xusdc", Chain.ETHEREUM)

        assert result is not None
        assert result.symbol == "USDC"
        assert result.balance == 1000.0  # Corrected
        assert result.decimals == 6

    def test_get_token_balance_failure(self):
        """Test _get_token_balance returns None on error."""
        wallet = MagicMock()
        chain_manager = MagicMock()
        chain_manager.get_web3.side_effect = Exception("RPC error")

        tracker = PortfolioTracker(chain_manager, wallet)
        result = tracker._get_token_balance("0xusdc", Chain.ETHEREUM)
        assert result is None

    def test_get_chain_portfolio(self, wallet, chain_manager):
        """Test _get_chain_portfolio calculates values correctly."""
        wallet.get_balance.return_value = 2.0
        w3 = chain_manager.get_web3.return_value

        token_contract = MagicMock()

        balance_mock = MagicMock()
        balance_mock.call.return_value = 500000000000000000  # 0.5 WETH
        token_contract.functions.balanceOf.return_value = balance_mock

        decimals_mock = MagicMock()
        decimals_mock.call.return_value = 18
        token_contract.functions.decimals.return_value = decimals_mock

        symbol_mock = MagicMock()
        symbol_mock.call.return_value = "WETH"
        token_contract.functions.symbol.return_value = symbol_mock

        w3.eth.contract.return_value = token_contract

        tracker = PortfolioTracker(chain_manager, wallet, eth_price=3500.0)
        portfolio = tracker._get_chain_portfolio(Chain.ETHEREUM)

        assert portfolio.chain == Chain.ETHEREUM
        assert portfolio.native_balance == 2.0
        assert portfolio.native_value_usd == 7000.0  # 2 * 3500

        weth_tokens = [t for t in portfolio.tokens if t.symbol == "WETH"]
        assert len(weth_tokens) == 1
        assert weth_tokens[0].balance == 0.5
        assert weth_tokens[0].price_usd == 3500.0
        assert weth_tokens[0].value_usd == 1750.0

    def test_get_chain_portfolio_stablecoins(self, wallet, chain_manager):
        """Test stablecoin pricing in chain portfolio."""
        wallet.get_balance.return_value = 0.5
        w3 = chain_manager.get_web3.return_value

        token_contract = MagicMock()
        bal_mock = MagicMock()
        bal_mock.call.return_value = 100000000  # 100 USDC
        dec_mock = MagicMock()
        dec_mock.call.return_value = 6
        sym_mock = MagicMock()
        sym_mock.call.return_value = "USDC"
        token_contract.functions.balanceOf.return_value = bal_mock
        token_contract.functions.decimals.return_value = dec_mock
        token_contract.functions.symbol.return_value = sym_mock

        w3.eth.contract.return_value = token_contract

        tracker = PortfolioTracker(chain_manager, wallet, eth_price=3500.0)
        portfolio = tracker._get_chain_portfolio(Chain.ETHEREUM)

        usdc_tokens = [t for t in portfolio.tokens if t.symbol == "USDC"]
        assert len(usdc_tokens) == 1
        assert usdc_tokens[0].price_usd == 1.0
        assert usdc_tokens[0].value_usd == 100.0

    def test_get_chain_portfolio_wbtc(self, wallet, chain_manager):
        """Test WBTC pricing in chain portfolio."""
        wallet.get_balance.return_value = 0.0
        w3 = chain_manager.get_web3.return_value

        token_contract = MagicMock()
        bal_mock = MagicMock()
        bal_mock.call.return_value = 100000000  # 1 WBTC (8 decimals)
        dec_mock = MagicMock()
        dec_mock.call.return_value = 8
        sym_mock = MagicMock()
        sym_mock.call.return_value = "WBTC"
        token_contract.functions.balanceOf.return_value = bal_mock
        token_contract.functions.decimals.return_value = dec_mock
        token_contract.functions.symbol.return_value = sym_mock
        w3.eth.contract.return_value = token_contract

        tracker = PortfolioTracker(chain_manager, wallet, eth_price=3500.0)
        portfolio = tracker._get_chain_portfolio(Chain.ETHEREUM)

        wbtc_tokens = [t for t in portfolio.tokens if t.symbol == "WBTC"]
        assert len(wbtc_tokens) == 1
        assert wbtc_tokens[0].price_usd == 60000.0
        assert wbtc_tokens[0].value_usd == 60000.0

    def test_get_chain_portfolio_unknown_token(self, wallet, chain_manager):
        """Test unknown token gets zero price."""
        wallet.get_balance.return_value = 0.0
        w3 = chain_manager.get_web3.return_value

        token_contract = MagicMock()
        bal_mock = MagicMock()
        bal_mock.call.return_value = 1000000000000000000  # 1 token
        dec_mock = MagicMock()
        dec_mock.call.return_value = 18
        sym_mock = MagicMock()
        sym_mock.call.return_value = "UNI"
        token_contract.functions.balanceOf.return_value = bal_mock
        token_contract.functions.decimals.return_value = dec_mock
        token_contract.functions.symbol.return_value = sym_mock
        w3.eth.contract.return_value = token_contract

        tracker = PortfolioTracker(chain_manager, wallet, eth_price=3500.0)
        portfolio = tracker._get_chain_portfolio(Chain.ETHEREUM)

        uni_tokens = [t for t in portfolio.tokens if t.symbol == "UNI"]
        assert len(uni_tokens) == 1
        assert uni_tokens[0].price_usd == 0.0
        assert uni_tokens[0].value_usd == 0.0

    def test_get_chain_portfolio_zero_balance_skipped(self, wallet, chain_manager):
        """Test zero balance tokens are excluded."""
        wallet.get_balance.return_value = 0.0
        w3 = chain_manager.get_web3.return_value

        token_contract = MagicMock()
        bal_mock = MagicMock()
        bal_mock.call.return_value = 0  # Zero balance
        dec_mock = MagicMock()
        dec_mock.call.return_value = 18
        sym_mock = MagicMock()
        sym_mock.call.return_value = "USDC"
        token_contract.functions.balanceOf.return_value = bal_mock
        token_contract.functions.decimals.return_value = dec_mock
        token_contract.functions.symbol.return_value = sym_mock
        w3.eth.contract.return_value = token_contract

        tracker = PortfolioTracker(chain_manager, wallet, eth_price=3500.0)
        portfolio = tracker._get_chain_portfolio(Chain.ETHEREUM)

        usdc_tokens = [t for t in portfolio.tokens if t.symbol == "USDC"]
        assert len(usdc_tokens) == 0  # Zero balance tokens are excluded

    def test_get_chain_portfolio_token_error(self, wallet, chain_manager):
        """Test token fetch errors don't crash chain portfolio."""
        wallet.get_balance.return_value = 1.0
        w3 = chain_manager.get_web3.return_value
        w3.eth.contract.side_effect = Exception("Contract not found")

        tracker = PortfolioTracker(chain_manager, wallet, eth_price=3500.0)
        portfolio = tracker._get_chain_portfolio(Chain.ETHEREUM)

        # Should still succeed with just native balance
        assert portfolio.native_balance == 1.0
        assert portfolio.total_value_usd == 3500.0
        assert len(portfolio.tokens) == 0

    def test_get_summary_with_custom_chains(self, wallet, chain_manager):
        """Test get_summary with specific chains list."""
        wallet.get_balance.return_value = 1.0

        tracker = PortfolioTracker(chain_manager, wallet, eth_price=3500.0)
        summary = tracker.get_summary(chains=[Chain.ETHEREUM])

        assert len(summary.chains) == 1
        assert summary.chains[0].chain == Chain.ETHEREUM


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
