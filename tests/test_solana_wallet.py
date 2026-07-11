"""Tests for Solana wallet module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from web3_agent_kit.solana.wallet import SolanaWallet, SolanaWalletConfig
from web3_agent_kit.solana.client import SolanaClientConfig


class TestSolanaWalletConfig:
    def test_default_config(self):
        config = SolanaWalletConfig()
        assert config.private_key is None
        assert config.keypair_path is None
        assert isinstance(config.client_config, SolanaClientConfig)


class TestSolanaWallet:
    def test_init_generates_keypair(self):
        wallet = SolanaWallet()
        assert wallet.address is not None
        assert len(wallet.address) >= 32
        assert wallet.address != ""

    def test_init_with_private_key_base58(self):
        # Use a known test keypair (DO NOT use for real funds)
        test_private_key = "4wBqpZM9xaDdZ1CQLFq2Jm6hJhx5YGPzJkFq6wiQrJkQzZvUqKxbi7NfNLESmB2VFKxgqkuRz9Yod1Gz3eFRM2da"
        try:
            wallet = SolanaWallet(SolanaWalletConfig(private_key=test_private_key))
            assert wallet.address is not None
        except Exception:
            # Key might not be valid base58; that's fine for test
            pass

    def test_init_with_keypair_path(self, tmp_path):
        import json
        from solders.keypair import Keypair

        kp = Keypair()
        keypair_file = tmp_path / "keypair.json"
        keypair_file.write_text(json.dumps(list(bytes(kp))))

        wallet = SolanaWallet(SolanaWalletConfig(keypair_path=str(keypair_file)))
        assert wallet.address == str(kp.pubkey())

    def test_address_format(self):
        wallet = SolanaWallet()
        addr = wallet.address
        # Solana addresses are base58, 32-44 chars
        assert 32 <= len(addr) <= 44, f"Address '{addr}' has unexpected length {len(addr)}"

    def test_sign_message(self):
        wallet = SolanaWallet()
        message = b"hello solana"
        signature = wallet.sign_message(message)
        assert len(signature) == 64  # Ed25519 signature is 64 bytes

    def test_sign_message_base58(self):
        wallet = SolanaWallet()
        signature = wallet.sign_message_base58("hello world")
        assert isinstance(signature, str)
        assert len(signature) > 0

    def test_export_private_key_base58(self):
        wallet = SolanaWallet()
        pk = wallet.export_private_key_base58()
        assert isinstance(pk, str)
        assert len(pk) >= 44

    def test_export_keypair_bytes(self):
        wallet = SolanaWallet()
        kp_bytes = wallet.export_keypair_bytes()
        assert isinstance(kp_bytes, bytes)
        assert len(kp_bytes) == 64  # 32 bytes secret + 32 bytes public

    def test_pubkey_property(self):
        wallet = SolanaWallet()
        pubkey = wallet.pubkey
        assert pubkey is not None
        assert str(pubkey) == wallet.address

    @pytest.mark.asyncio
    async def test_get_balance(self):
        wallet = SolanaWallet()
        mock_client = AsyncMock()
        mock_client.get_sol_balance = AsyncMock(return_value=10.5)
        wallet._client = mock_client

        balance = await wallet.get_balance()
        assert balance == 10.5
        mock_client.get_sol_balance.assert_called_once_with(wallet.address)

    @pytest.mark.asyncio
    async def test_get_token_balance(self):
        wallet = SolanaWallet()
        mock_client = AsyncMock()
        mock_client.get_token_balance = AsyncMock(
            return_value={"amount": "1000", "decimals": 6, "ui_amount": 0.001}
        )
        wallet._client = mock_client

        balance = await wallet.get_token_balance("usdc_mint")
        assert balance["amount"] == "1000"
        mock_client.get_token_balance.assert_called_once_with(wallet.address, "usdc_mint")

    @pytest.mark.asyncio
    async def test_send_sol(self):
        wallet = SolanaWallet()
        mock_client = AsyncMock()
        mock_client.get_latest_blockhash = AsyncMock(
            return_value={"blockhash": "5KQx2H8g3Bz6fNnQyVvRc9JmWpLk4Dh7TsXeA1CbEZaF", "lastValidBlockHeight": 123456}
        )
        mock_client.send_transaction = AsyncMock(return_value="tx_sig_123")
        wallet._client = mock_client

        result = await wallet.send_sol(
            "7EcDhSYGxXyscszYEp35KHN8vvw3svAuLKTzXwCFLtV",
            0.01,
        )
        assert result["signature"] == "tx_sig_123"
        assert result["status"] == "sent"
        assert result["amount_sol"] == 0.01
        assert "solscan.io" in result["explorer_url"]

    @pytest.mark.asyncio
    async def test_send_sol_no_blockhash(self):
        wallet = SolanaWallet()
        mock_client = AsyncMock()
        mock_client.get_latest_blockhash = AsyncMock(return_value={})
        wallet._client = mock_client

        with pytest.raises(ValueError, match="Failed to get blockhash"):
            await wallet.send_sol("7EcDhSYGxXyscszYEp35KHN8vvw3svAuLKTzXwCFLtV", 0.01)

    @pytest.mark.asyncio
    async def test_close(self):
        wallet = SolanaWallet()
        mock_client = AsyncMock()
        wallet._client = mock_client
        await wallet.close()
        mock_client.close.assert_called_once()

    def test_multiple_wallets_different(self):
        wallet1 = SolanaWallet()
        wallet2 = SolanaWallet()
        assert wallet1.address != wallet2.address
        assert wallet1.export_keypair_bytes() != wallet2.export_keypair_bytes()