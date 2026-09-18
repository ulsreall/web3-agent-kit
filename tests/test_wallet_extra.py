"""Extra tests for Wallet — key/seed/keystore handling and tx signing."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account

from web3_agent_kit.chains.chain import Chain
from web3_agent_kit.execution import (
    ActionType,
    AuthorizationEvidence,
    EnforcementDenied,
    ExecutionPolicy,
    PreSignInterceptor,
)
from web3_agent_kit.wallet.wallet import Wallet, WalletConfig


@pytest.fixture
def test_key():
    """A deterministic test private key."""
    acct = Account.create()
    return acct.key.hex(), acct.address


class _AllowingProvider:
    """Verifier that authorizes the call it is handed."""

    @property
    def policy_id(self) -> str:
        return "wallet-test-provider"

    def authorize(self, context):
        return AuthorizationEvidence(
            authorization_id="wallet-test-auth",
            envelope_digest=context.envelope_digest,
            executor=context.envelope.executor,
            authorizer="0x" + "99" * 20,
            valid_from=0,
            valid_until=2**31,
            nonce="1",
            policy_commitment_digest=context.policy_commitment.digest(),
        )


def _authorizing_gate(signer) -> PreSignInterceptor:
    """A gate that allows ETHEREUM contract calls through, using ``signer``."""
    return PreSignInterceptor(
        policy=ExecutionPolicy(
            allowed_chains=frozenset({Chain.ETHEREUM}),
            allowed_actions=frozenset({ActionType.CONTRACT_CALL}),
            allowed_contracts=frozenset({"0x" + "11" * 20}),
            max_native_value_wei=10**18,
            require_confirmation=False,
        ),
        signer=signer,
        authorization_provider=_AllowingProvider(),
    )


def _signed_tx(sender: str) -> dict:
    return {
        "to": "0x" + "11" * 20,
        "from": sender,
        "data": "0xdeadbeef",
        "value": 0,
        "nonce": 0,
        "chainId": 1,
        "gas": 300_000,
        "gasPrice": 10**9,
    }


class TestWalletConfig:
    def test_defaults(self):
        config = WalletConfig()
        assert config.private_key is None
        assert config.seed_phrase is None
        assert config.keystore_path is None
        assert config.password is None


class TestWalletFromKey:
    def test_from_key(self, test_key):
        key, addr = test_key
        wallet = Wallet.from_key(key)
        assert wallet.address == addr
        assert wallet.private_key == key

    def test_from_env(self, test_key, monkeypatch):
        key, addr = test_key
        monkeypatch.setenv("MY_TEST_KEY", key)
        wallet = Wallet.from_env("MY_TEST_KEY")
        assert wallet.address == addr

    def test_from_env_missing(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        with pytest.raises(ValueError, match="not set"):
            Wallet.from_env("MISSING_KEY")

    def test_get_account_no_key(self):
        wallet = Wallet(WalletConfig())
        with pytest.raises(ValueError, match="No private key"):
            _ = wallet.address

    def test_private_key_empty(self):
        wallet = Wallet(WalletConfig())
        assert wallet.private_key == ""

    def test_repr(self, test_key):
        key, _ = test_key
        wallet = Wallet.from_key(key)
        assert "Wallet(address=" in repr(wallet)


class TestWalletFromSeed:
    def test_from_seed(self):
        Account.enable_unaudited_hdwallet_features()
        acct, mnemonic = Account.create_with_mnemonic()
        wallet = Wallet.from_seed(mnemonic)
        assert wallet.address.startswith("0x")
        assert len(wallet.address) == 42

    def test_derive_account_no_seed(self):
        wallet = Wallet(WalletConfig())
        with pytest.raises(ValueError, match="No seed phrase"):
            wallet._derive_account(0)


class TestWalletFromKeystore:
    def test_from_keystore_roundtrip(self, test_key):
        key, addr = test_key
        password = "hunter2"
        keystore = Account.encrypt(key, password)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(keystore, f)
            path = f.name
        try:
            wallet = Wallet.from_keystore(path, password)
            assert wallet.address == addr
            assert wallet.config.keystore_path == path
        finally:
            os.unlink(path)

    def test_from_keystore_wrong_password(self, test_key):
        key, _ = test_key
        keystore = Account.encrypt(key, "correct")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(keystore, f)
            path = f.name
        try:
            with pytest.raises(ValueError):
                Wallet.from_keystore(path, "wrong")
        finally:
            os.unlink(path)

    def test_from_keystore_missing_file(self):
        with pytest.raises(FileNotFoundError):
            Wallet.from_keystore("/nonexistent/keystore.json", "pw")


class TestWalletBalance:
    def test_get_balance_no_chain_manager(self, test_key):
        key, _ = test_key
        wallet = Wallet.from_key(key)
        with pytest.raises(ValueError, match="ChainManager not configured"):
            wallet.get_balance(Chain.ETHEREUM)

    def test_get_balance_evm(self, test_key):
        key, _ = test_key
        cm = MagicMock()
        w3 = MagicMock()
        w3.eth.get_balance.return_value = 2 * 10**18
        w3.from_wei.return_value = 2.0
        cm.get_web3.return_value = w3
        wallet = Wallet.from_key(key, chain_manager=cm)
        assert wallet.get_balance(Chain.ETHEREUM) == 2.0
        cm.get_web3.assert_called_once_with(Chain.ETHEREUM)

    def test_get_balance_solana(self, test_key):
        key, _ = test_key
        cm = MagicMock()
        sol = MagicMock()
        resp = MagicMock()
        resp.value = 5_000_000_000
        sol.get_balance.return_value = resp
        cm.get_solana.return_value = sol
        wallet = Wallet.from_key(key, chain_manager=cm)
        assert wallet.get_balance(Chain.SOLANA) == 5.0


class TestWalletTransactions:
    def test_sign_transaction_requires_a_gate(self, test_key):
        """Every write-capable transaction needs a bound gate.

        This test previously asserted the opposite for a payload with no
        destination: it reached the raw signer because the refusal was keyed on
        a non-null ``to``. Contract creation spends the nonce and runs arbitrary
        init code, so that path is now closed as well.
        """
        key, _ = test_key
        wallet = Wallet.from_key(key)
        with pytest.raises(EnforcementDenied, match="no bound pre-sign gate"):
            wallet.sign_transaction({"nonce": 0}, Chain.ETHEREUM)

    def test_sign_transaction_reaches_signer_when_gate_authorizes(self, test_key):
        key, _ = test_key
        wallet = Wallet.from_key(key)
        with patch.object(Account, "sign_transaction") as mock_sign:
            signed = MagicMock()
            signed.rawTransaction = b"\x01\x02"
            signed.raw_transaction = b"\x01\x02"
            mock_sign.return_value = signed
            wallet.bind_enforcement(_authorizing_gate(wallet._raw_signer))
            raw = wallet.sign_transaction(
                _signed_tx(wallet.address), Chain.ETHEREUM
            )
            assert raw == b"\x01\x02"

    def test_sign_transaction_unbound_refuses_contract_creation(self, test_key):
        """to=None is write-capable and must be refused too."""
        key, _ = test_key
        wallet = Wallet.from_key(key)
        with pytest.raises(EnforcementDenied, match="to=None"):
            wallet.sign_transaction(
                {"nonce": 0, "data": "0x60806040", "chainId": 1}, Chain.ETHEREUM
            )

    def test_sign_transaction_with_destination_requires_a_gate(self, test_key):
        """A write-capable call must never be signed by an unbound wallet."""
        key, _ = test_key
        wallet = Wallet.from_key(key)
        with pytest.raises(EnforcementDenied, match="no bound pre-sign gate"):
            wallet.sign_transaction(
                {"nonce": 0, "to": "0x" + "11" * 20, "data": "0x"}, Chain.ETHEREUM
            )

    def test_send_transaction_no_chain_manager(self, test_key):
        key, _ = test_key
        wallet = Wallet.from_key(key)
        with pytest.raises(ValueError, match="ChainManager not configured"):
            wallet.send_transaction({}, Chain.ETHEREUM)

    def test_send_transaction(self, test_key):
        key, _ = test_key
        cm = MagicMock()
        w3 = MagicMock()
        tx_hash = MagicMock()
        tx_hash.hex.return_value = "0xdeadbeef"
        w3.eth.send_raw_transaction.return_value = tx_hash
        cm.get_web3.return_value = w3
        wallet = Wallet.from_key(key, chain_manager=cm)
        with patch.object(wallet, "sign_transaction", return_value=b"\xaa"):
            result = wallet.send_transaction({"nonce": 0}, Chain.ETHEREUM)
        assert result == "0xdeadbeef"
        w3.eth.send_raw_transaction.assert_called_once_with(b"\xaa")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
