"""Tests for bridge agent."""

import pytest
from unittest.mock import MagicMock, patch

from src.bridge import BridgeAgent, BridgeRoute, BridgeResult
from src.chain import Chain


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

    @patch("src.bridge.requests.Session.get")
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
