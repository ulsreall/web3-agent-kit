"""Tests for Solana LP management module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from web3_agent_kit.solana.lp import SolanaLPManager, LPConfig, DEXProtocol, LPError
from web3_agent_kit.solana.wallet import SolanaWallet


@pytest.fixture
def lp_manager():
    return SolanaLPManager(config=LPConfig(timeout=5, max_retries=1))


@pytest.fixture
def lp_manager_with_wallet():
    wallet = SolanaWallet()
    return SolanaLPManager(wallet=wallet, config=LPConfig(timeout=5, max_retries=1))


class TestDEXProtocol:
    def test_enum_values(self):
        assert DEXProtocol.RAYDIUM.value == "raydium"
        assert DEXProtocol.ORCA.value == "orca"
        assert DEXProtocol.METEORA.value == "meteora"
        assert DEXProtocol.LIFINITY.value == "lifinity"

    def test_enum_members(self):
        names = {m.name for m in DEXProtocol}
        assert "RAYDIUM" in names
        assert "ORCA" in names
        assert "METEORA" in names


class TestLPConfig:
    def test_default_config(self):
        config = LPConfig()
        assert config.slippage_bps == 50
        assert config.timeout == 30
        assert config.max_retries == 3
        assert "jup.ag" in config.jupiter_api_url

    def test_custom_config(self):
        config = LPConfig(slippage_bps=100, timeout=15)
        assert config.slippage_bps == 100
        assert config.timeout == 15

    def test_custom_price_api(self):
        config = LPConfig(jupiter_price_api="https://custom.price.api")
        assert config.jupiter_price_api == "https://custom.price.api"


class TestSolanaLPManager:
    def test_init(self, lp_manager):
        assert lp_manager.config.slippage_bps == 50
        assert lp_manager._client is None
        assert lp_manager.wallet is None

    def test_init_with_wallet(self, lp_manager_with_wallet):
        assert lp_manager_with_wallet.wallet is not None
        assert lp_manager_with_wallet.wallet.address is not None

    def test_get_program_id(self, lp_manager):
        assert lp_manager._get_program_id("raydium") == "675kPX9MHTjS2zt1LKfr5y3U1wF5L9KL3QqyWQ6v1K"
        assert lp_manager._get_program_id("orca") == "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGf3W3P3"
        assert lp_manager._get_program_id("unknown") == ""

    @pytest.mark.asyncio
    async def test_get_jupiter_pools(self, lp_manager):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "pools": [
                {"pool_id": "pool1", "tvl": 1000000},
                {"pool_id": "pool2", "tvl": 500000},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            pools = await lp_manager.get_jupiter_pools()
            assert len(pools) == 2
            assert pools[0]["pool_id"] == "pool1"

    @pytest.mark.asyncio
    async def test_get_jupiter_pools_empty(self, lp_manager):
        with patch("httpx.AsyncClient.get", AsyncMock(side_effect=Exception("API error"))):
            pools = await lp_manager.get_jupiter_pools()
            assert pools == []

    @pytest.mark.asyncio
    async def test_get_pools_by_pair(self, lp_manager):
        mock_quote_resp = MagicMock()
        mock_quote_resp.json.return_value = {
            "routePlan": [
                {"swapInfo": {"label": "Raydium", "ammKey": "pool_raydium_1"}, "inAmount": "1000", "outAmount": "500"},
                {"swapInfo": {"label": "Orca", "ammKey": "pool_orca_1"}, "inAmount": "1000", "outAmount": "480"},
            ]
        }
        mock_quote_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_quote_resp)):
            pools = await lp_manager.get_pools_by_pair(
                "So11111111111111111111111111111111111111112",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            )
            assert len(pools) == 2
            assert pools[0]["label"] == "Raydium"
            assert pools[1]["protocol"] == "Orca"

    @pytest.mark.asyncio
    async def test_get_pools_by_pair_empty(self, lp_manager):
        mock_quote_resp = MagicMock()
        mock_quote_resp.json.return_value = {"routePlan": []}
        mock_quote_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_quote_resp)):
            pools = await lp_manager.get_pools_by_pair("SOL", "USDC")
            assert pools == []

    @pytest.mark.asyncio
    async def test_get_add_liquidity_quote(self, lp_manager):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "route": {"inAmount": "1000000", "outAmount": "500000"},
            "priceImpactPct": "0.05",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            quote = await lp_manager.get_add_liquidity_quote(
                "raydium",
                "pool_raydium_1",
                1000000,
                500000,
                "So11111111111111111111111111111111111111112",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            )
            assert "route" in quote

    @pytest.mark.asyncio
    async def test_get_add_liquidity_quote_api_error(self, lp_manager):
        with patch("httpx.AsyncClient.post", AsyncMock(side_effect=Exception("API error"))):
            result = await lp_manager.get_add_liquidity_quote(
                "raydium", "pool1", 1000, 500, "mint_a", "mint_b"
            )
            assert "error" in result

    @pytest.mark.asyncio
    async def test_get_remove_liquidity_quote(self, lp_manager):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "route": {"inAmount": "1000000", "outAmount": "500000"},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            quote = await lp_manager.get_remove_liquidity_quote(
                "orca", "pool_orca_1", 1000000, "lp_mint_address"
            )
            assert "route" in quote

    @pytest.mark.asyncio
    async def test_get_remove_liquidity_quote_api_error(self, lp_manager):
        with patch("httpx.AsyncClient.post", AsyncMock(side_effect=Exception("API error"))):
            result = await lp_manager.get_remove_liquidity_quote(
                "orca", "pool1", 1000, "lp_mint"
            )
            assert "error" in result

    @pytest.mark.asyncio
    async def test_get_add_liquidity_tx(self, lp_manager):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "swapTransaction": "base64_encoded_tx_data",
            "lastValidBlockHeight": 200000,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            tx = await lp_manager.get_add_liquidity_tx(
                "raydium", "pool1", 1000000, 500000, "mint_a", "mint_b"
            )
            assert tx["swapTransaction"] == "base64_encoded_tx_data"
            assert tx["lastValidBlockHeight"] == 200000

    @pytest.mark.asyncio
    async def test_get_add_liquidity_tx_error(self, lp_manager):
        with patch("httpx.AsyncClient.post", AsyncMock(side_effect=Exception("API error"))):
            result = await lp_manager.get_add_liquidity_tx(
                "raydium", "pool1", 1000, 500, "mint_a", "mint_b"
            )
            assert "error" in result

    @pytest.mark.asyncio
    async def test_get_remove_liquidity_tx(self, lp_manager):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "swapTransaction": "base64_tx_remove",
            "lastValidBlockHeight": 200001,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            tx = await lp_manager.get_remove_liquidity_tx(
                "orca", "pool_orca_1", 1000000, "lp_mint"
            )
            assert tx["swapTransaction"] == "base64_tx_remove"

    @pytest.mark.asyncio
    async def test_get_user_lp_positions_empty(self, lp_manager):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": {"value": []}}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            positions = await lp_manager.get_user_lp_positions("some_wallet")
            assert positions == []

    @pytest.mark.asyncio
    async def test_get_user_lp_positions_no_wallet(self, lp_manager):
        positions = await lp_manager.get_user_lp_positions()
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_user_lp_positions_with_data(self, lp_manager):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {
                "value": [
                    {
                        "pubkey": "ata_1",
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {
                                        "mint": "lp_mint_1",
                                        "tokenAmount": {
                                            "amount": "1000000000",
                                            "decimals": 9,
                                            "uiAmount": 1.0,
                                        },
                                    }
                                }
                            }
                        },
                    },
                    {
                        "pubkey": "ata_2",
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {
                                        "mint": "lp_mint_2",
                                        "tokenAmount": {
                                            "amount": "2000000000",
                                            "decimals": 9,
                                            "uiAmount": 2.0,
                                        },
                                    }
                                }
                            }
                        },
                    },
                    {
                        "pubkey": "ata_empty",
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {
                                        "mint": "empty_mint",
                                        "tokenAmount": {
                                            "amount": "0",
                                            "decimals": 0,
                                            "uiAmount": 0,
                                        },
                                    }
                                }
                            }
                        },
                    },
                ]
            }
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            positions = await lp_manager.get_user_lp_positions("wallet_address")
            assert len(positions) == 2  # Only non-zero balances
            assert positions[0]["mint"] == "lp_mint_1"
            assert positions[0]["amount"] == 1.0
            assert positions[1]["mint"] == "lp_mint_2"
            assert positions[1]["amount"] == 2.0

    @pytest.mark.asyncio
    async def test_get_pool_apr(self, lp_manager):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"apr": 12.5}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            apr = await lp_manager.get_pool_apr("pool_raydium_1", "raydium")
            assert apr == 12.5

    @pytest.mark.asyncio
    async def test_get_pool_apr_error(self, lp_manager):
        with patch("httpx.AsyncClient.get", AsyncMock(side_effect=Exception("API error"))):
            apr = await lp_manager.get_pool_apr("unknown_pool")
            assert apr == 0.0

    @pytest.mark.asyncio
    async def test_search_pools(self, lp_manager):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "pools": [
                {"pool_id": "p1", "mint_a": "So11111111111111111111111111111111111111112"},
                {"pool_id": "p2", "mint_a": "So11111111111111111111111111111111111111112"},
                {"pool_id": "p3", "mint_a": "other_mint"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            pools = await lp_manager.search_pools("So11111111111111111111111111111111111111112")
            assert len(pools) == 2

    @pytest.mark.asyncio
    async def test_close(self, lp_manager):
        mock_client = AsyncMock()
        lp_manager._client = mock_client
        await lp_manager.close()
        mock_client.aclose.assert_called_once()
        assert lp_manager._client is None

    @pytest.mark.asyncio
    async def test_get_pools_by_pair_cleans_up_jupiter(self, lp_manager):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"routePlan": []}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            pools = await lp_manager.get_pools_by_pair("SOL", "USDC")
            assert pools == []