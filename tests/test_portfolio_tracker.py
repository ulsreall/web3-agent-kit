"""Tests for the portfolio tracker — fully offline, all RPC calls mocked."""

from unittest.mock import MagicMock

import pytest

from web3_agent_kit.chains.chain import Chain
from web3_agent_kit.portfolio.tracker import (
    ChainPortfolio,
    PortfolioSummary,
    PortfolioTracker,
    TokenBalance,
)


def _make_tracker(native_balance=1.0, chains=None):
    chain_manager = MagicMock()
    chain_manager.list_chains.return_value = chains or [Chain.ETHEREUM]
    wallet = MagicMock()
    wallet.address = "0x00000000000000000000000000000000000000ab"
    wallet.get_balance.return_value = native_balance
    return PortfolioTracker(chain_manager, wallet, eth_price=3500.0), chain_manager, wallet


class TestDataclasses:
    def test_token_balance_to_dict(self):
        tb = TokenBalance(
            symbol="USDC",
            address="0xusdc",
            balance=100.0,
            decimals=6,
            chain=Chain.ETHEREUM,
            price_usd=1.0,
            value_usd=100.0,
        )
        d = tb.to_dict()
        assert d["symbol"] == "USDC"
        assert d["chain"] == "ethereum"
        assert d["value_usd"] == 100.0

    def test_chain_portfolio_to_dict(self):
        cp = ChainPortfolio(
            chain=Chain.BASE,
            native_balance=2.0,
            native_value_usd=7000.0,
            tokens=[],
            total_value_usd=7000.0,
        )
        d = cp.to_dict()
        assert d["chain"] == "base"
        assert d["tokens"] == []

    def test_portfolio_summary_to_dict_and_str(self):
        tb = TokenBalance(
            symbol="USDC", address="0xusdc", balance=50.0, decimals=6,
            chain=Chain.ETHEREUM, price_usd=1.0, value_usd=50.0,
        )
        cp = ChainPortfolio(
            chain=Chain.ETHEREUM, native_balance=1.0, native_value_usd=3500.0,
            tokens=[tb], total_value_usd=3550.0,
        )
        summary = PortfolioSummary(
            address="0x00000000000000000000000000000000000000ab",
            timestamp=123.0,
            chains=[cp],
            total_value_usd=3550.0,
            total_native_balances={"ethereum": 1.0},
        )
        d = summary.to_dict()
        assert d["total_value_usd"] == 3550.0
        assert len(d["chains"]) == 1
        text = str(summary)
        assert "Portfolio" in text
        assert "USDC" in text
        assert "ETHEREUM" in text


class TestPortfolioTracker:
    def test_repr(self):
        tracker, _, _ = _make_tracker()
        assert "PortfolioTracker" in repr(tracker)

    def test_get_token_balance_success(self):
        tracker, cm, _ = _make_tracker()
        w3 = MagicMock()
        w3.to_checksum_address.side_effect = lambda a: a
        contract = MagicMock()
        contract.functions.balanceOf.return_value.call.return_value = 100 * 10 ** 6
        contract.functions.decimals.return_value.call.return_value = 6
        contract.functions.symbol.return_value.call.return_value = "USDC"
        w3.eth.contract.return_value = contract
        cm.get_web3.return_value = w3

        tb = tracker._get_token_balance("0xusdc", Chain.ETHEREUM)
        assert tb is not None
        assert tb.symbol == "USDC"
        assert tb.balance == 100.0

    def test_get_token_balance_error_returns_none(self):
        tracker, cm, _ = _make_tracker()
        cm.get_web3.side_effect = RuntimeError("rpc down")
        assert tracker._get_token_balance("0xusdc", Chain.ETHEREUM) is None

    def test_get_chain_portfolio_with_tokens(self):
        tracker, cm, _ = _make_tracker(native_balance=1.0)

        # Patch _get_token_balance to return a USDC balance only
        def token_balance(addr, chain):
            if addr == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48":
                return TokenBalance(
                    symbol="USDC", address=addr, balance=200.0, decimals=6, chain=chain
                )
            return None

        tracker._get_token_balance = token_balance
        cp = tracker._get_chain_portfolio(Chain.ETHEREUM)
        assert cp.native_balance == 1.0
        assert cp.native_value_usd == 3500.0
        # USDC valued at $1 => 200 USD plus native
        assert cp.total_value_usd == pytest.approx(3700.0)
        assert any(t.symbol == "USDC" for t in cp.tokens)

    def test_get_chain_portfolio_weth_and_wbtc_and_unknown(self):
        tracker, cm, _ = _make_tracker(native_balance=0.0)

        def token_balance(addr, chain):
            mapping = {
                "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": ("WETH", 2.0),
                "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599": ("WBTC", 0.5),
                "0x514910771AF9Ca656af840dff83E8264EcF986CA": ("LINK", 100.0),
            }
            if addr in mapping:
                sym, bal = mapping[addr]
                return TokenBalance(symbol=sym, address=addr, balance=bal, decimals=18, chain=chain)
            return None

        tracker._get_token_balance = token_balance
        cp = tracker._get_chain_portfolio(Chain.ETHEREUM)
        syms = {t.symbol: t for t in cp.tokens}
        assert syms["WETH"].value_usd == pytest.approx(2.0 * 3500.0)
        assert syms["WBTC"].value_usd == pytest.approx(0.5 * 60000.0)
        # LINK has unknown price -> 0
        assert syms["LINK"].value_usd == 0.0

    def test_get_chain_portfolio_token_exception_skipped(self):
        tracker, cm, _ = _make_tracker(native_balance=1.0)

        def token_balance(addr, chain):
            raise RuntimeError("token call failed")

        tracker._get_token_balance = token_balance
        cp = tracker._get_chain_portfolio(Chain.ETHEREUM)
        # Only native counts; tokens all errored
        assert cp.tokens == []
        assert cp.total_value_usd == 3500.0

    def test_get_summary_default_chains(self):
        tracker, cm, _ = _make_tracker(native_balance=1.0, chains=[Chain.ETHEREUM])
        tracker._get_token_balance = lambda addr, chain: None
        summary = tracker.get_summary()
        assert summary.total_value_usd == 3500.0
        assert "ethereum" in summary.total_native_balances
        assert len(tracker.get_history()) == 1

    def test_get_summary_explicit_chains(self):
        tracker, cm, _ = _make_tracker(native_balance=1.0)
        tracker._get_token_balance = lambda addr, chain: None
        summary = tracker.get_summary(chains=[Chain.ETHEREUM, Chain.BASE])
        assert len(summary.chains) == 2

    def test_get_summary_chain_error_logged(self):
        tracker, cm, wallet = _make_tracker()
        wallet.get_balance.side_effect = RuntimeError("chain broke")
        summary = tracker.get_summary(chains=[Chain.ETHEREUM])
        # Chain failed => no chain portfolios but summary still produced
        assert summary.chains == []
        assert summary.total_value_usd == 0.0

    def test_get_pnl_insufficient_history(self):
        tracker, _, _ = _make_tracker()
        pnl = tracker.get_pnl()
        assert pnl == {"pnl_absolute": 0.0, "pnl_percent": 0.0}

    def test_get_pnl_with_history(self):
        tracker, cm, wallet = _make_tracker()
        tracker._get_token_balance = lambda addr, chain: None
        # First snapshot at 1 ETH
        wallet.get_balance.return_value = 1.0
        tracker.get_summary(chains=[Chain.ETHEREUM])
        # Second snapshot at 2 ETH
        wallet.get_balance.return_value = 2.0
        tracker.get_summary(chains=[Chain.ETHEREUM])
        pnl = tracker.get_pnl()
        assert pnl["pnl_absolute"] == pytest.approx(3500.0)
        assert pnl["pnl_percent"] == pytest.approx(100.0)

    def test_get_pnl_zero_initial(self):
        tracker, cm, wallet = _make_tracker()
        tracker._get_token_balance = lambda addr, chain: None
        wallet.get_balance.return_value = 0.0
        tracker.get_summary(chains=[Chain.ETHEREUM])
        wallet.get_balance.return_value = 1.0
        tracker.get_summary(chains=[Chain.ETHEREUM])
        pnl = tracker.get_pnl()
        assert pnl["pnl_percent"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
