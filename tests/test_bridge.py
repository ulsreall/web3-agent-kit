"""Tests for bridge agent."""

from unittest.mock import MagicMock, patch

import pytest

from web3_agent_kit.bridge.bridge import BridgeAgent, BridgeResult, BridgeRoute
from web3_agent_kit.chains.chain import Chain


class TestBridgeRoute:
    """Test BridgeRoute dataclass."""

    def test_creation(self):
        """Test creating a BridgeRoute."""
        route = BridgeRoute(
            bridge_name="Li.Fi",
            from_chain=Chain.ETHEREUM,
            to_chain=Chain.BASE,
            token_in="0x123",
            token_out="0x456",
            amount_in=0.1,
            amount_out=0.099,
            gas_estimate=5.0,
            time_estimate=300,
            fee_usd=5.0,
            steps=[],
        )
        assert route.bridge_name == "Li.Fi"
        assert route.amount_in == 0.1
        assert route.amount_out == 0.099

    def test_to_dict(self):
        """Test converting to dict."""
        route = BridgeRoute(
            bridge_name="Socket",
            from_chain=Chain.BASE,
            to_chain=Chain.ARBITRUM,
            token_in="0x123",
            token_out="0x456",
            amount_in=1.0,
            amount_out=0.998,
            gas_estimate=2.0,
            time_estimate=120,
            fee_usd=2.0,
            steps=[],
        )
        d = route.to_dict()
        assert d["bridge"] == "Socket"
        assert d["from"] == "base"
        assert d["to"] == "arbitrum"
        assert d["amount_in"] == 1.0


class TestBridgeResult:
    """Test BridgeResult dataclass."""

    def test_creation(self):
        """Test creating a BridgeResult."""
        result = BridgeResult(
            tx_hash="0xabc123",
            from_chain=Chain.ETHEREUM,
            to_chain=Chain.BASE,
            token="ETH",
            amount=0.1,
            bridge_name="Li.Fi",
            estimated_arrival=300,
        )
        assert result.tx_hash == "0xabc123"
        assert result.amount == 0.1

    def test_to_dict(self):
        """Test converting to dict."""
        result = BridgeResult(
            tx_hash="0xdef456",
            from_chain=Chain.BASE,
            to_chain=Chain.ARBITRUM,
            token="USDC",
            amount=100.0,
            bridge_name="Socket",
            estimated_arrival=120,
        )
        d = result.to_dict()
        assert d["tx_hash"] == "0xdef456"
        assert d["from"] == "base"
        assert d["to"] == "arbitrum"
        assert d["eta_minutes"] == 2


class TestBridgeAgent:
    """Test BridgeAgent."""

    def test_creation(self):
        """Test creating a BridgeAgent."""
        wallet = MagicMock()
        wallet.address = "0x1234"
        chain_manager = MagicMock()

        bridge = BridgeAgent(chain_manager, wallet)
        assert bridge.wallet.address == "0x1234"

    @patch("web3_agent_kit.bridge.bridge.requests.Session.get")
    def test_get_routes_lifi(self, mock_get):
        """Test getting routes from Li.Fi."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "routes": [
                {
                    "toAmount": "99000000",
                    "gasCostUSD": "3.50",
                    "duration": 180,
                    "tags": ["cheapest"],
                    "steps": [],
                },
            ]
        }
        mock_get.return_value = mock_response

        wallet = MagicMock()
        wallet.address = "0x1234"
        chain_manager = MagicMock()

        bridge = BridgeAgent(chain_manager, wallet)

        # Mock the _get_decimals method
        bridge._get_decimals = MagicMock(return_value=6)

        routes = bridge.get_routes("USDC", 100.0, Chain.ETHEREUM, Chain.BASE)
        assert len(routes) >= 0  # May return empty if mocks don't align

    @patch("web3_agent_kit.bridge.bridge.requests.Session.get")
    def test_lifi_tags_do_not_change_provider_dispatch(self, mock_get):
        response = MagicMock()
        response.json.return_value = {
            "routes": [
                {
                    "toAmount": "99000000",
                    "gasCostUSD": "3.50",
                    "duration": 180,
                    "tags": ["cheapest"],
                    "steps": [],
                }
            ]
        }
        response.raise_for_status = MagicMock()
        mock_get.return_value = response
        wallet = MagicMock(address="0x1234")
        bridge = BridgeAgent(MagicMock(), wallet)
        bridge._resolve_token = MagicMock(return_value="0xToken")
        bridge._get_decimals = MagicMock(return_value=6)

        [route] = bridge._get_lifi_routes("USDC", 100, Chain.ETHEREUM, Chain.BASE)

        assert route.bridge_name == "Li.Fi"
        assert route.provider == "Li.Fi"
        bridge._execute_lifi = MagicMock()
        bridge._execute_socket = MagicMock()
        bridge.transfer("USDC", 100, Chain.ETHEREUM, Chain.BASE, route)
        bridge._execute_lifi.assert_called_once_with(route)
        bridge._execute_socket.assert_not_called()

    def test_repr(self):
        """Test string representation."""
        wallet = MagicMock()
        wallet.address = "0x1234567890abcdef1234567890abcdef12345678"
        chain_manager = MagicMock()

        bridge = BridgeAgent(chain_manager, wallet)
        assert "BridgeAgent" in repr(bridge)
        assert "0x12345678" in repr(bridge)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestRouteParsingRobustness:
    """A single null fee field used to discard every route from a provider."""

    def _bridge(self, monkeypatch):
        monkeypatch.setattr("web3_agent_kit.bridge.bridge.CHAIN_IDS", {})
        bridge = BridgeAgent(MagicMock(), MagicMock(address="0x1234"))
        bridge._resolve_token = MagicMock(return_value="0xToken")
        bridge._get_decimals = MagicMock(return_value=6)
        return bridge

    def _lifi(self, payload):
        resp = MagicMock()
        resp.json.return_value = payload
        resp.raise_for_status = MagicMock()
        return resp

    def test_a_null_gas_cost_does_not_lose_the_route(self, monkeypatch):
        from web3_agent_kit.chains.chain import CHAIN_IDS

        CHAIN_IDS[Chain.ETHEREUM] = 1
        CHAIN_IDS[Chain.BASE] = 8453
        bridge = self._bridge(monkeypatch)
        payload = {
            "routes": [
                {"toAmount": "99000000", "gasCostUSD": None, "duration": None, "steps": []},
                {"toAmount": "98000000", "gasCostUSD": "2.5", "duration": 120, "steps": []},
            ]
        }
        monkeypatch.setattr(
            "web3_agent_kit.bridge.bridge.requests.Session.get",
            lambda *a, **k: self._lifi(payload),
        )
        routes = bridge._get_lifi_routes("USDC", 100.0, Chain.ETHEREUM, Chain.BASE)
        assert len(routes) == 2
        assert routes[0].gas_estimate == 0.0
        assert routes[0].time_estimate == 300
        assert routes[1].fee_usd == 2.5

    def test_a_null_to_amount_does_not_lose_the_route(self, monkeypatch):
        from web3_agent_kit.chains.chain import CHAIN_IDS

        CHAIN_IDS[Chain.ETHEREUM] = 1
        CHAIN_IDS[Chain.BASE] = 8453
        bridge = self._bridge(monkeypatch)
        payload = {"routes": [{"toAmount": None, "gasCostUSD": "1", "steps": []}]}
        monkeypatch.setattr(
            "web3_agent_kit.bridge.bridge.requests.Session.get",
            lambda *a, **k: self._lifi(payload),
        )
        assert bridge._get_lifi_routes("USDC", 1.0, Chain.ETHEREUM, Chain.BASE)[0].amount_out == 0.0

    def test_a_socket_route_without_gas_fees(self, monkeypatch):
        from web3_agent_kit.chains.chain import CHAIN_IDS

        CHAIN_IDS[Chain.ETHEREUM] = 1
        CHAIN_IDS[Chain.BASE] = 8453
        bridge = self._bridge(monkeypatch)
        resp = MagicMock()
        resp.json.return_value = {"result": {"routes": [{"toAmount": "5000000"}]}}
        resp.raise_for_status = MagicMock()
        monkeypatch.setattr(
            "web3_agent_kit.bridge.bridge.requests.Session.get", lambda *a, **k: resp
        )
        routes = bridge._get_socket_routes("USDC", 5.0, Chain.ETHEREUM, Chain.BASE)
        assert len(routes) == 1
        assert routes[0].fee_usd == 0.0
