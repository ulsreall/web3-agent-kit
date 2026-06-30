"""Integration tests — run against testnet to verify real onchain operations.

Usage:
    PRIVATE_KEY=0x... pytest tests/test_integration.py -v -s

Requirements:
    PRIVATE_KEY env var with a funded testnet wallet.
"""

import os
import pytest


pytestmark = pytest.mark.skipif(
    not os.environ.get("PRIVATE_KEY"),
    reason="PRIVATE_KEY not set. Run: PRIVATE_KEY=0x... pytest tests/test_integration.py -v",
)


def test_wallet_address_derivation():
    """Verify wallet address is correctly derived from private key."""
    from src.wallet.wallet import Wallet

    key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    wallet = Wallet.from_key(key)
    assert wallet.address == "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


def test_wallet_from_seed():
    """Verify wallet from seed phrase."""
    from src.wallet.wallet import Wallet

    seed = "test test test test test test test test test test test junk"
    wallet = Wallet.from_seed(seed)
    assert wallet.address.startswith("0x")
    assert len(wallet.address) == 42


def test_wallet_repr():
    """Verify wallet repr."""
    from src.wallet.wallet import Wallet

    key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    wallet = Wallet.from_key(key)
    assert "Wallet(address=" in repr(wallet)


def test_wallet_no_key_error():
    """Verify wallet raises when no key configured."""
    from src.wallet.wallet import Wallet, WalletConfig
    import pytest

    w = Wallet(WalletConfig())
    with pytest.raises(ValueError, match="No private key"):
        w._get_account()


def test_wallet_sign_transaction():
    """Verify wallet can sign a transaction."""
    from src.wallet.wallet import Wallet
    from src.chains.chain import Chain

    key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    wallet = Wallet.from_key(key)
    tx = {"to": "0x0000000000000000000000000000000000000000", "value": 0, "gas": 21000, "gasPrice": 1, "nonce": 0, "chainId": 1}
    signed = wallet.sign_transaction(tx, Chain.ETHEREUM)
    assert isinstance(signed, bytes)
    assert len(signed) > 0