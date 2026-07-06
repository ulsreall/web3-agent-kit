"""Tests for Wallet module."""

import pytest
from unittest.mock import MagicMock, patch

from src.wallet.wallet import Wallet, WalletConfig
from src.chains.chain import Chain


class TestWalletConfig:
    """Test WalletConfig dataclass."""

    def test_default_config(self):
        config = WalletConfig()
        assert config.private_key is None
        assert config.seed_phrase is None
        assert config.keystore_path is None
        assert config.password is None

    def test_with_private_key(self):
        config = WalletConfig(private_key="0xabc123")
        assert config.private_key == "0xabc123"

    def test_with_seed_phrase(self):
        config = WalletConfig(seed_phrase="word1 word2 word3")
        assert config.seed_phrase == "word1 word2 word3"


class TestWalletCreation:
    """Test wallet creation methods."""

    def test_from_key(self):
        key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        wallet = Wallet.from_key(key)
        assert wallet._account is None  # Lazy init - not loaded yet
        assert wallet.address.startswith("0x")
        assert len(wallet.address) == 42

    def test_from_key_lazy_account(self):
        key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        wallet = Wallet.from_key(key)
        # Access address triggers _get_account
        _ = wallet.address
        assert wallet._account is not None

    def test_from_env_missing(self, monkeypatch):
        monkeypatch.delenv("TEST_KEY", raising=False)
        with pytest.raises(ValueError, match="not set"):
            Wallet.from_env("TEST_KEY")

    def test_from_env(self, monkeypatch):
        key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        monkeypatch.setenv("TEST_KEY", key)
        wallet = Wallet.from_env("TEST_KEY")
        assert wallet.address.startswith("0x")

    def test_from_env_default_var(self, monkeypatch):
        key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        monkeypatch.setenv("PRIVATE_KEY", key)
        wallet = Wallet.from_env()
        assert wallet.address.startswith("0x")

    def test_from_seed(self):
        # Test with a known seed phrase
        seed = "test test test test test test test test test test test junk"
        wallet = Wallet.from_seed(seed, index=0)
        assert wallet.address.startswith("0x")
        assert len(wallet.address) == 42

    def test_from_seed_with_index(self):
        seed = "test test test test test test test test test test test junk"
        wallet_0 = Wallet.from_seed(seed, index=0)
        wallet_1 = Wallet.from_seed(seed, index=1)
        assert wallet_0.address != wallet_1.address

    def test_init_with_chain_manager(self):
        key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        chain_manager = MagicMock()
        wallet = Wallet.from_key(key, chain_manager=chain_manager)
        assert wallet.chain_manager is not None


class TestWalletProperties:
    """Test wallet properties."""

    @pytest.fixture
    def wallet(self):
        key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        return Wallet.from_key(key)

    def test_address(self, wallet):
        assert wallet.address.startswith("0x")
        assert len(wallet.address) == 42

    def test_private_key(self, wallet):
        pk = wallet.private_key
        assert pk.startswith("0x")
        assert len(pk) > 40

    def test_repr(self, wallet):
        rep = repr(wallet)
        assert "Wallet" in rep
        assert wallet.address[:10] in rep

    def test_private_key_none(self):
        wallet = Wallet(WalletConfig())
        assert wallet.private_key == ""


class TestWalletOperations:
    """Test wallet operations requiring chain interaction."""

    @pytest.fixture
    def wallet(self):
        key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        return Wallet.from_key(key)

    def test_get_balance_no_chain_manager(self, wallet):
        with pytest.raises(ValueError, match="ChainManager not configured"):
            wallet.get_balance(Chain.ETHEREUM)

    def test_get_balance_ethereum(self, wallet):
        chain_manager = MagicMock()
        w3 = MagicMock()
        w3.eth.get_balance.return_value = 1000000000000000000  # 1 ETH
        w3.from_wei.return_value = 1.0
        chain_manager.get_web3.return_value = w3
        wallet.chain_manager = chain_manager

        balance = wallet.get_balance(Chain.ETHEREUM)
        assert balance == 1.0
        chain_manager.get_web3.assert_called_once_with(Chain.ETHEREUM)

    def test_get_balance_solana(self, wallet):
        chain_manager = MagicMock()
        sol_client = MagicMock()
        resp = MagicMock()
        resp.value = 1000000000  # 1 SOL in lamports
        sol_client.get_balance.return_value = resp
        chain_manager.get_solana.return_value = sol_client
        wallet.chain_manager = chain_manager

        balance = wallet.get_balance(Chain.SOLANA)
        assert balance == 1.0

    def test_get_account_no_key(self):
        wallet = Wallet(WalletConfig())
        with pytest.raises(ValueError, match="No private key configured"):
            wallet._get_account()

    def test_get_account_uses_cache(self, wallet):
        acct1 = wallet._get_account()
        acct2 = wallet._get_account()
        assert acct1 is acct2

    def test_sign_transaction(self, wallet):
        tx = {"to": "0xabc", "value": 1000, "gas": 21000, "nonce": 0, "gasPrice": 20000000000}
        signed = wallet.sign_transaction(tx, Chain.ETHEREUM)
        assert isinstance(signed, bytes)
        assert len(signed) > 0

    def test_sign_transaction_no_key(self):
        wallet = Wallet(WalletConfig())
        with pytest.raises(ValueError, match="No private key configured"):
            wallet.sign_transaction({}, Chain.ETHEREUM)

    def test_send_transaction_no_chain_manager(self, wallet):
        with pytest.raises(ValueError, match="ChainManager not configured"):
            wallet.send_transaction({"to": "0xabc"}, Chain.ETHEREUM)

    def test_send_transaction_success(self, wallet):
        chain_manager = MagicMock()
        w3 = MagicMock()
        w3.eth.send_raw_transaction.return_value = b"\x00" * 32
        chain_manager.get_web3.return_value = w3
        wallet.chain_manager = chain_manager

        tx_hash = wallet.send_transaction(
            {"to": "0xabc", "value": 1000, "gas": 21000, "nonce": 0, "gasPrice": 20000000000},
            Chain.ETHEREUM,
        )
        assert isinstance(tx_hash, str)
        assert len(tx_hash) == 64  # Hex-encoded 32 bytes

    def test_derive_account_no_seed(self):
        wallet = Wallet(WalletConfig())
        with pytest.raises(ValueError, match="No seed phrase configured"):
            wallet._derive_account(0)

    def test_derive_account_with_seed(self):
        config = WalletConfig(seed_phrase="test test test test test test test test test test test junk")
        wallet = Wallet(config)
        wallet._derive_account(0)
        assert wallet._account is not None
        assert wallet.address.startswith("0x")


class TestInitialization:
    """Test Wallet __init__ directly."""

    def test_init_with_none_chain_manager(self):
        wallet = Wallet(WalletConfig(), chain_manager=None)
        assert wallet.chain_manager is None
        assert wallet._account is None

    def test_init_with_empty_config(self):
        wallet = Wallet(WalletConfig())
        assert wallet.config.private_key is None
        assert wallet._account is None