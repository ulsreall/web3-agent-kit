"""Tests for the API pydantic request/response models."""

from __future__ import annotations

import pytest

try:
    import web3_agent_kit.api.models as m

    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not MODELS_AVAILABLE, reason="pydantic/models not installed"
)


class TestWalletModels:
    def test_create_wallet_defaults(self):
        req = m.CreateWalletRequest()
        assert req.chain == "ethereum"

    def test_import_wallet_requires_private_key(self):
        with pytest.raises(Exception):
            m.ImportWalletRequest()
        req = m.ImportWalletRequest(private_key="0xabc")
        assert req.private_key == "0xabc"
        assert req.chain == "ethereum"

    def test_wallet_response_optional_balance(self):
        resp = m.WalletResponse(address="0x1", chain="ethereum")
        assert resp.balance is None
        resp2 = m.WalletResponse(address="0x1", chain="ethereum", balance="1.0")
        assert resp2.balance == "1.0"


class TestSwapModels:
    def test_swap_request_defaults(self):
        req = m.SwapRequest(token_in="ETH", token_out="USDC", amount_in="1.0")
        assert req.chain == "ethereum"
        assert req.slippage == 0.5
        assert req.private_key is None

    def test_swap_request_missing_required(self):
        with pytest.raises(Exception):
            m.SwapRequest(token_in="ETH")

    def test_swap_quote_response(self):
        resp = m.SwapQuoteResponse(
            token_in="ETH",
            token_out="USDC",
            amount_in="1.0",
            estimated_out="3500",
            price_impact=0.01,
            route=["ETH", "USDC"],
        )
        assert resp.route == ["ETH", "USDC"]


class TestPortfolioModels:
    def test_portfolio_request_defaults(self):
        req = m.PortfolioRequest()
        assert req.chain == "ethereum"
        assert req.address is None

    def test_portfolio_response(self):
        resp = m.PortfolioResponse(
            address="0x1",
            chain="ethereum",
            native_balance="1.0",
            native_symbol="ETH",
            tokens=[{"symbol": "USDC"}],
            total_value_usd=100.0,
        )
        assert resp.tokens[0]["symbol"] == "USDC"


class TestGasModels:
    def test_gas_request_default(self):
        assert m.GasRequest().chain == "ethereum"

    def test_gas_response(self):
        resp = m.GasResponse(
            chain="ethereum",
            base_fee=1,
            low={"max_fee": 1},
            medium={"max_fee": 2},
            high={"max_fee": 3},
            recommendation="now",
        )
        assert resp.recommendation == "now"


class TestWatcherModels:
    def test_watch_request(self):
        req = m.WatchRequest(address="0x1")
        assert req.tags == []
        assert req.label == ""

    def test_watch_request_missing_address(self):
        with pytest.raises(Exception):
            m.WatchRequest()

    def test_alert_request(self):
        req = m.AlertRequest(message="hi")
        assert req.severity == "medium"


class TestApprovalModels:
    def test_scan_request_defaults(self):
        req = m.ApprovalScanRequest()
        assert req.chain == "ethereum"
        assert req.address is None

    def test_revoke_request(self):
        req = m.RevokeRequest(token="0xtok", spender="0xsp")
        assert req.token == "0xtok"
        with pytest.raises(Exception):
            m.RevokeRequest(token="0xtok")


class TestDCAModels:
    def test_dca_order_request(self):
        req = m.DCAOrderRequest(
            token_in="USDC", token_out="ETH", amount_per_buy="100"
        )
        assert req.frequency == "daily"
        assert req.total_buys is None

    def test_dca_status_response(self):
        resp = m.DCAStatusResponse(
            order_id="d1",
            status="active",
            buys_executed=1,
            total_buys=5,
            avg_price=3500.0,
            total_spent="100",
        )
        assert resp.buys_executed == 1


class TestYieldModels:
    def test_yield_scan_request_defaults(self):
        req = m.YieldScanRequest()
        assert req.min_apy == 0.0
        assert req.min_tvl == 0.0
        assert req.category is None

    def test_yield_response(self):
        resp = m.YieldResponse(
            protocol="Aave",
            chain="ethereum",
            apy=4.5,
            tvl=1e9,
            category="lending",
            token="USDC",
        )
        assert resp.protocol == "Aave"


class TestBridgeModels:
    def test_bridge_request(self):
        req = m.BridgeRequest(
            from_chain="ethereum", to_chain="arbitrum", token="USDC", amount="100"
        )
        assert req.from_address is None

    def test_bridge_request_missing_required(self):
        with pytest.raises(Exception):
            m.BridgeRequest(from_chain="ethereum")

    def test_bridge_quote_response(self):
        resp = m.BridgeQuoteResponse(
            from_chain="ethereum",
            to_chain="arbitrum",
            token="USDC",
            amount="100",
            estimated_receive="99",
            bridge_fee="1",
            estimated_time="5m",
            route="lifi",
        )
        assert resp.route == "lifi"
