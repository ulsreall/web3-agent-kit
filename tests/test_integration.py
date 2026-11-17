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
    from web3_agent_kit.wallet.wallet import Wallet

    key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    wallet = Wallet.from_key(key)
    assert wallet.address == "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


def test_wallet_from_seed():
    """Verify wallet from seed phrase."""
    from web3_agent_kit.wallet.wallet import Wallet

    seed = "test test test test test test test test test test test junk"
    wallet = Wallet.from_seed(seed)
    assert wallet.address.startswith("0x")
    assert len(wallet.address) == 42


def test_wallet_repr():
    """Verify wallet repr."""
    from web3_agent_kit.wallet.wallet import Wallet

    key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    wallet = Wallet.from_key(key)
    assert "Wallet(address=" in repr(wallet)


def test_wallet_no_key_error():
    """Verify wallet raises when no key configured."""
    import pytest

    from web3_agent_kit.wallet.wallet import Wallet, WalletConfig

    w = Wallet(WalletConfig())
    with pytest.raises(ValueError, match="No private key"):
        w._get_account()


def _bound_wallet(key: str):
    """Return a wallet with an enforced gate attached.

    Signing fails closed without one, so an integration test that signs through
    a bare wallet only passes while the gate is unbound.
    """
    import time

    from web3_agent_kit.chains.chain import Chain
    from web3_agent_kit.execution import (
        ActionType,
        AuthorizationEvidence,
        CallableAuthorizationProvider,
        ExecutionPolicy,
        PreSignInterceptor,
    )
    from web3_agent_kit.wallet.wallet import Wallet

    wallet = Wallet.from_key(key)

    def verify(context):
        now = int(time.time())
        return AuthorizationEvidence(
            authorization_id="integration",
            envelope_digest=context.envelope_digest,
            executor=context.envelope.executor,
            authorizer=wallet.address,
            valid_from=now - 5,
            valid_until=now + 300,
            nonce="1",
            policy_commitment_digest=context.policy_commitment.digest(),
        )

    gate = PreSignInterceptor(
        policy=ExecutionPolicy(
            allowed_chains=frozenset({Chain.ETHEREUM}),
            allowed_actions=frozenset(ActionType),
            allowed_contracts=frozenset({"0x" + "00" * 20}),
            max_native_value_wei=10**18,
            require_confirmation=False,
        ),
        signer=wallet.raw_signer,
        authorization_provider=CallableAuthorizationProvider(verify),
    )
    return wallet.bind_enforcement(gate)


def test_wallet_sign_transaction():
    """Verify a gate-bound wallet can sign a transaction."""
    from web3_agent_kit.chains.chain import Chain

    key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    wallet = _bound_wallet(key)
    tx = {
        "to": "0x0000000000000000000000000000000000000000",
        "value": 0,
        "gas": 21000,
        "gasPrice": 1,
        "nonce": 0,
        "chainId": 1,
    }
    signed = wallet.sign_transaction(tx, Chain.ETHEREUM)
    assert isinstance(signed, bytes)
    assert len(signed) > 0


def test_unbound_wallet_refuses_to_sign():
    """The fail-closed contract itself, exercised end to end."""
    from web3_agent_kit.chains.chain import Chain
    from web3_agent_kit.execution import EnforcementDenied
    from web3_agent_kit.wallet.wallet import Wallet

    key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    wallet = Wallet.from_key(key)
    tx = {
        "to": "0x0000000000000000000000000000000000000000",
        "value": 0,
        "gas": 21000,
        "gasPrice": 1,
        "nonce": 0,
        "chainId": 1,
    }
    with pytest.raises(EnforcementDenied):
        wallet.sign_transaction(tx, Chain.ETHEREUM)
