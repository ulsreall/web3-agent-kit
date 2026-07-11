"""Tests for Solana client module."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.solana.client import SolanaClient, SolanaClientConfig, SolanaRPCError


@pytest.fixture
def client_config():
    return SolanaClientConfig(
        rpc_url="https://api.mainnet-beta.solana.com",
        timeout=10,
        max_retries=2,
    )


@pytest.fixture
def solana_client(client_config):
    return SolanaClient(client_config)


class TestSolanaClientConfig:
    def test_default_config(self):
        config = SolanaClientConfig()
        assert config.rpc_url == "https://api.mainnet-beta.solana.com"
        assert config.timeout == 30
        assert config.max_retries == 3

    def test_custom_config(self):
        config = SolanaClientConfig(
            rpc_url="https://rpc.helius.xyz",
            timeout=10,
            max_retries=5,
        )
        assert config.rpc_url == "https://rpc.helius.xyz"
        assert config.timeout == 10
        assert config.max_retries == 5


class TestSolanaClient:
    def test_init(self, solana_client, client_config):
        assert solana_client.config == client_config
        assert solana_client._client is None

    @pytest.mark.asyncio
    async def test_get_balance(self, solana_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": {"value": 1000000000}}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            balance = await solana_client.get_balance("11111111111111111111111111111111")
            assert balance == 1000000000

    @pytest.mark.asyncio
    async def test_get_sol_balance(self, solana_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": {"value": 2500000000}}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            sol_balance = await solana_client.get_sol_balance("11111111111111111111111111111111")
            assert sol_balance == 2.5

    @pytest.mark.asyncio
    async def test_get_sol_balance_zero(self, solana_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": {"value": 0}}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            sol_balance = await solana_client.get_sol_balance("11111111111111111111111111111111")
            assert sol_balance == 0.0

    @pytest.mark.asyncio
    async def test_get_latest_blockhash(self, solana_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {
                "value": {
                    "blockhash": "abc123",
                    "lastValidBlockHeight": 123456,
                }
            }
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            blockhash = await solana_client.get_latest_blockhash()
            assert blockhash["blockhash"] == "abc123"
            assert blockhash["lastValidBlockHeight"] == 123456

    @pytest.mark.asyncio
    async def test_get_token_accounts_by_owner(self, solana_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {
                "value": [
                    {
                        "pubkey": "token_account_1",
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {
                                        "mint": "mint_address_1",
                                        "tokenAmount": {"amount": "1000", "decimals": 6, "uiAmount": 0.001},
                                    }
                                }
                            }
                        },
                    }
                ]
            }
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            accounts = await solana_client.get_token_accounts_by_owner("owner_address")
            assert len(accounts) == 1
            assert accounts[0]["pubkey"] == "token_account_1"

    @pytest.mark.asyncio
    async def test_rpc_error(self, solana_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": {"message": "Invalid param"}}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            with pytest.raises(SolanaRPCError, match="Invalid param"):
                await solana_client.get_balance("invalid")

    @pytest.mark.asyncio
    async def test_rpc_retry_on_timeout(self, solana_client):
        with patch("httpx.AsyncClient.post", AsyncMock(side_effect=Exception("timeout"))):
            with pytest.raises(Exception):
                await solana_client.get_balance("11111111111111111111111111111111")

    @pytest.mark.asyncio
    async def test_close(self, solana_client):
        mock_client = AsyncMock()
        solana_client._client = mock_client
        await solana_client.close()
        mock_client.aclose.assert_called_once()
        assert solana_client._client is None

    @pytest.mark.asyncio
    async def test_get_transaction(self, solana_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": {"slot": 123, "blockTime": 1700000000}}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            tx = await solana_client.get_transaction("tx_signature")
            assert tx["slot"] == 123

    @pytest.mark.asyncio
    async def test_get_token_balance(self, solana_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {
                "value": [
                    {
                        "pubkey": "ata1",
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {
                                        "mint": "USDC_MINT",
                                        "tokenAmount": {"amount": "5000000", "decimals": 6, "uiAmount": 5.0},
                                    }
                                }
                            }
                        },
                    },
                    {
                        "pubkey": "ata2",
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {
                                        "mint": "OTHER_MINT",
                                        "tokenAmount": {"amount": "100", "decimals": 0, "uiAmount": 100},
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
            balance = await solana_client.get_token_balance("owner", "USDC_MINT")
            assert balance["amount"] == "5000000"
            assert balance["ui_amount"] == 5.0

    @pytest.mark.asyncio
    async def test_get_token_balance_not_found(self, solana_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": {"value": []}}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            balance = await solana_client.get_token_balance("owner", "NONEXISTENT")
            assert balance["amount"] == "0"
            assert balance["ui_amount"] == 0

    @pytest.mark.asyncio
    async def test_get_account_info(self, solana_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": {"value": {"lamports": 5000000, "executable": False}}}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            info = await solana_client.get_account_info("address")
            assert info["lamports"] == 5000000

    @pytest.mark.asyncio
    async def test_get_token_supply(self, solana_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": {"value": {"amount": "1000000000000", "decimals": 6, "uiAmount": 1000000.0}}}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            supply = await solana_client.get_token_supply("mint")
            assert supply["amount"] == "1000000000000"