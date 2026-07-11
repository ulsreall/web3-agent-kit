"""Tests for DEX Aggregator module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.defi.aggregator import DEXAggregator, AggregatorConfig, Chain, AggregatorError


@pytest.fixture
def aggregator():
    return DEXAggregator(AggregatorConfig(slippage=0.5, timeout=10, max_retries=2))


class TestAggregatorConfig:
    def test_default_config(self):
        config = AggregatorConfig()
        assert config.slippage == 0.5
        assert config.timeout == 30
        assert config.max_retries == 3

    def test_custom_config(self):
        config = AggregatorConfig(slippage=1.0, oneinch_api_key="test_key")
        assert config.slippage == 1.0
        assert config.oneinch_api_key == "test_key"


class TestChain:
    def test_chain_enum(self):
        assert Chain.ETHEREUM.value == "ethereum"
        assert Chain.SOLANA.value == "solana"
        assert Chain.BASE.value == "base"

    def test_chain_ids(self):
        from src.defi.aggregator import CHAIN_IDS
        assert CHAIN_IDS[Chain.ETHEREUM] == 1
        assert CHAIN_IDS[Chain.BSC] == 56
        assert CHAIN_IDS[Chain.POLYGON] == 137


class TestDEXAggregator:
    def test_init(self, aggregator):
        assert aggregator.config.slippage == 0.5
        assert aggregator._client is None

    @pytest.mark.asyncio
    async def test_oneinch_quote(self, aggregator):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "toAmount": "500000000000000000",
            "fromToken": {"symbol": "ETH"},
            "toToken": {"symbol": "USDC"},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            quote = await aggregator.oneinch_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "1000000000000000000",
            )
            assert "toAmount" in quote

    @pytest.mark.asyncio
    async def test_oneinch_swap(self, aggregator):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tx": {"data": "0x...", "to": "0x...", "value": "0"},
            "toAmount": "500000000",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            swap = await aggregator.oneinch_swap(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "1000000000000000000",
                "0x1234567890123456789012345678901234567890",
            )
            assert "tx" in swap

    @pytest.mark.asyncio
    async def test_paraswap_quote(self, aggregator):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "priceRoute": {
                "destAmount": "500000000",
                "bestRoute": [],
            }
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            quote = await aggregator.paraswap_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "1000000000000000000",
                "0x1234567890123456789012345678901234567890",
            )
            assert "priceRoute" in quote

    @pytest.mark.asyncio
    async def test_zeroex_quote(self, aggregator):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "buyAmount": "500000000",
            "sellAmount": "1000000000000000000",
            "price": "0.0005",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            quote = await aggregator.zeroex_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "1000000000000000000",
                "0x1234567890123456789012345678901234567890",
            )
            assert quote["buyAmount"] == "500000000"

    @pytest.mark.asyncio
    async def test_get_best_quote_evm(self, aggregator):
        """Test best quote aggregation across all EVM providers."""
        mock_1inch = MagicMock()
        mock_1inch.json.return_value = {"toAmount": "500000000"}
        mock_1inch.raise_for_status = MagicMock()

        mock_paraswap = MagicMock()
        mock_paraswap.json.return_value = {
            "priceRoute": {"destAmount": "550000000"}
        }
        mock_paraswap.raise_for_status = MagicMock()

        mock_0x = MagicMock()
        mock_0x.json.return_value = {"buyAmount": "480000000"}
        mock_0x.raise_for_status = MagicMock()

        # Paraswap should win with 550000000
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = [mock_1inch, mock_paraswap, mock_0x]

            result = await aggregator.get_best_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                1000000000000000000,
            )
            assert result["best_provider"] == "paraswap"
            assert result["amount_out"] == "550000000"

    @pytest.mark.asyncio
    async def test_get_best_quote_solana(self, aggregator):
        """Test that Solana routes to Jupiter."""
        mock_jupiter = MagicMock()
        mock_jupiter.json.return_value = {
            "inAmount": "1000000000",
            "outAmount": "23000",
            "priceImpactPct": "0.01",
            "routePlan": [],
        }
        mock_jupiter.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_jupiter)):
            result = await aggregator.get_best_quote(
                Chain.SOLANA,
                "So11111111111111111111111111111111111111112",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                1000000000,
            )
            assert result["best_provider"] == "jupiter"

    @pytest.mark.asyncio
    async def test_extract_output_amount(self, aggregator):
        assert aggregator._extract_output_amount("1inch", {"toAmount": "1000"}) == 1000
        assert aggregator._extract_output_amount("paraswap", {"priceRoute": {"destAmount": "2000"}}) == 2000
        assert aggregator._extract_output_amount("0x", {"buyAmount": "3000"}) == 3000
        assert aggregator._extract_output_amount("unknown", {}) == 0

    @pytest.mark.asyncio
    async def test_close(self, aggregator):
        mock_client = AsyncMock()
        aggregator._client = mock_client
        await aggregator.close()
        mock_client.aclose.assert_called_once()
        assert aggregator._client is None

    @pytest.mark.asyncio
    async def test_oneinch_quote_with_api_key(self):
        agg = DEXAggregator(AggregatorConfig(oneinch_api_key="test-key-123"))
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"toAmount": "1000000"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            quote = await agg.oneinch_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "1000000000000000000",
            )
            assert quote["toAmount"] == "1000000"