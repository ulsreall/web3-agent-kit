"""Tests for Solana DEX (Jupiter) module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from web3_agent_kit.solana.dex import JupiterDEX, JupiterDEXConfig, JupiterAPIError


@pytest.fixture
def jupiter():
    return JupiterDEX(JupiterDEXConfig(api_url="https://quote-api.jup.ag/v6", slippage_bps=50))


class TestJupiterDEXConfig:
    def test_default_config(self):
        config = JupiterDEXConfig()
        assert config.api_url == "https://quote-api.jup.ag/v6"
        assert config.slippage_bps == 50
        assert config.timeout == 30

    def test_custom_config(self):
        config = JupiterDEXConfig(slippage_bps=100, timeout=15)
        assert config.slippage_bps == 100
        assert config.timeout == 15


class TestJupiterDEX:
    def test_init(self):
        jup = JupiterDEX()
        assert jup.config.slippage_bps == 50
        assert jup._client is None

    @pytest.mark.asyncio
    async def test_get_quote(self, jupiter):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "inAmount": "1000000000",
            "outAmount": "100000",
            "priceImpactPct": "0.01",
            "routePlan": [],
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            quote = await jupiter.get_quote(
                "So11111111111111111111111111111111111111112",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                1000000000,
            )
            assert quote["inAmount"] == "1000000000"
            assert quote["outAmount"] == "100000"

    @pytest.mark.asyncio
    async def test_get_quote_with_custom_slippage(self, jupiter):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"outAmount": "50000"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            quote = await jupiter.get_quote("SOL", "USDC", 1000000, slippage_bps=100)
            assert quote["outAmount"] == "50000"

    @pytest.mark.asyncio
    async def test_get_swap_route(self, jupiter):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "swapTransaction": "base64_tx_data",
            "lastValidBlockHeight": 123456,
            "prioritizationFeeLamports": 5000,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            route = await jupiter.get_swap_route(
                "wallet_address",
                {"inAmount": "1000000", "outAmount": "50000"},
            )
            assert route["swapTransaction"] == "base64_tx_data"
            assert route["lastValidBlockHeight"] == 123456

    @pytest.mark.asyncio
    async def test_swap_full_flow(self, jupiter):
        mock_quote_resp = MagicMock()
        mock_quote_resp.json.return_value = {
            "inAmount": "1000000000",
            "outAmount": "100000",
            "priceImpactPct": "0.01",
            "routePlan": [{"swapInfo": {"label": "Orca"}}],
        }
        mock_quote_resp.raise_for_status = MagicMock()

        mock_swap_resp = MagicMock()
        mock_swap_resp.json.return_value = {
            "swapTransaction": "base64_encoded_tx",
            "lastValidBlockHeight": 200000,
        }
        mock_swap_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_quote_resp)), \
             patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_swap_resp)):
            result = await jupiter.swap(
                "wallet_address",
                "So11111111111111111111111111111111111111112",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                1000000000,
            )
            assert result["quote"]["in_amount"] == 1000000000
            assert result["swap_transaction"] == "base64_encoded_tx"

    @pytest.mark.asyncio
    async def test_get_tokens(self, jupiter):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"address": "So11111111111111111111111111111111111111112", "symbol": "SOL", "decimals": 9},
            {"address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "symbol": "USDC", "decimals": 6},
        ]
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            tokens = await jupiter.get_tokens()
            assert len(tokens) == 2
            assert tokens[0]["symbol"] == "SOL"

    @pytest.mark.asyncio
    async def test_get_token_by_symbol(self, jupiter):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "symbol": "USDC", "decimals": 6},
        ]
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            token = await jupiter.get_token_by_symbol("usdc")
            assert token is not None
            assert token["symbol"] == "USDC"

    @pytest.mark.asyncio
    async def test_get_token_by_symbol_not_found(self, jupiter):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            token = await jupiter.get_token_by_symbol("NONEXISTENT")
            assert token is None

    @pytest.mark.asyncio
    async def test_get_token_by_mint(self, jupiter):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"address": "MINT123", "symbol": "TKN", "decimals": 9},
        ]
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            token = await jupiter.get_token_by_mint("MINT123")
            assert token is not None
            assert token["symbol"] == "TKN"

    @pytest.mark.asyncio
    async def test_api_error(self, jupiter):
        import httpx
        with patch("httpx.AsyncClient.get", AsyncMock(side_effect=httpx.HTTPStatusError("error", request=MagicMock(), response=MagicMock(status_code=500)))):
            with pytest.raises(JupiterAPIError):
                await jupiter.get_quote("SOL", "USDC", 1000000)

    @pytest.mark.asyncio
    async def test_close(self, jupiter):
        mock_client = AsyncMock()
        jupiter._client = mock_client
        await jupiter.close()
        mock_client.aclose.assert_called_once()
        assert jupiter._client is None