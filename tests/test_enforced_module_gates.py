"""Regression tests for the enforced gate inside messaging, airdrop and bridge.

These are the three modules that previously signed outside the Wallet wrapper.
The point of these tests is not line coverage for its own sake: it is to prove
that the bypass that existed before is actually closed on each of them.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import (
    ActionType,
    EnforcementDenied,
    ExecutionPolicy,
    PreSignInterceptor,
)
from web3_agent_kit.messaging import CrossChainMessenger

# Address derived from TEST_KEY, so the "from" field matches the signer.
SENDER = "0x5CbDd86a2FA8Dc4bDdd8a8f69dBa48572EeC07FB"
ENDPOINT = "0x7564105E977516C53bE337314c7E53838967bDaC"
TEST_KEY = "0x" + "33" * 32


def _tx(to: str = ENDPOINT, value: int = 0) -> dict:
    return {
        "to": to,
        "from": SENDER,
        "data": "0xdeadbeef",
        "value": value,
        "nonce": 5,
        "chainId": 42161,
        "gas": 300_000,
        "gasPrice": 1_000_000_000,
    }


# ---------------------------------------------------------------------------
# messaging
# ---------------------------------------------------------------------------


def _messenger(policy=None) -> CrossChainMessenger:
    m = CrossChainMessenger(
        rpc_url="http://localhost:8545",
        src_chain="arbitrum",
        private_key=TEST_KEY,
        policy=policy,
    )
    return m


def test_messaging_gate_is_built_lazily_and_reused():
    m = _messenger()
    first = m._gate()
    second = m._gate()
    assert isinstance(first, PreSignInterceptor)
    assert first is second


def test_messaging_gate_requires_web3():
    m = CrossChainMessenger(rpc_url="", private_key=TEST_KEY)
    with pytest.raises(ValueError, match="Web3 not configured"):
        m._gate()


def test_messaging_gate_without_policy_is_fail_closed():
    """The pre-migration code signed unconditionally; it must not any more."""
    m = _messenger()
    gate = m._gate()

    with pytest.raises(EnforcementDenied, match="no ExecutionPolicy"):
        gate.sign(
            _authorization_request(),
        )

    assert gate.audit_log[-1].signature_hash is None


def _authorization_request():
    from web3_agent_kit.execution import AuthorizationRequest

    return AuthorizationRequest(
        chain=Chain.ARBITRUM if hasattr(Chain, "ARBITRUM") else Chain.ETHEREUM,
        action=ActionType.BRIDGE,
        transaction=_tx(),
    )


def test_messaging_gate_signs_when_policy_allows():
    policy = ExecutionPolicy(
        allowed_chains=frozenset({Chain.ETHEREUM, Chain.ARBITRUM}),
        allowed_actions=frozenset({ActionType.BRIDGE}),
        allowed_contracts=frozenset({ENDPOINT.lower()}),
        require_confirmation=False,
    )
    m = _messenger(policy=policy)
    gate = m._gate()

    raw = gate.sign(_authorization_request()).raw_transaction

    assert isinstance(raw, bytes)
    assert len(raw) > 0
    assert gate.audit_log[-1].verdict.value == "authorized"


def test_messaging_gate_denies_disallowed_contract():
    policy = ExecutionPolicy(
        allowed_chains=frozenset({Chain.ETHEREUM, Chain.ARBITRUM}),
        allowed_actions=frozenset({ActionType.BRIDGE}),
        allowed_contracts=frozenset({"0xe1fAE9b4fAB2F5726677ECfA912d96b0B683e6a9"}),
        require_confirmation=False,
    )
    m = _messenger(policy=policy)
    gate = m._gate()

    with pytest.raises(EnforcementDenied, match="contract_not_allowed"):
        gate.sign(_authorization_request())


def test_messaging_raw_signer_handles_both_attribute_names():
    """eth_account exposes raw_transaction; older builds used rawTransaction."""
    m = _messenger()

    for attr in ("raw_transaction", "rawTransaction"):
        signed = MagicMock(spec=[attr])
        setattr(signed, attr, b"raw-bytes")
        other = "rawTransaction" if attr == "raw_transaction" else "raw_transaction"
        try:
            delattr(signed, other)
        except AttributeError:
            pass

        m.w3 = MagicMock()
        m.w3.eth.account.sign_transaction.return_value = signed
        assert m._raw_signer(_tx()) == b"raw-bytes"


def test_messaging_resolves_known_and_unknown_chains():
    from web3_agent_kit.messaging import _resolve_chain

    assert _resolve_chain("ethereum") is Chain.ETHEREUM
    assert _resolve_chain(Chain.BASE) is Chain.BASE
    with pytest.raises(ValueError, match="unsupported chain"):
        _resolve_chain("not-a-chain")


# ---------------------------------------------------------------------------
# airdrop
# ---------------------------------------------------------------------------


def _farmer(policy=None):
    from web3_agent_kit.airdrop.onchain import OnChainAirdropFarmer, OnChainConfig

    farmer = OnChainAirdropFarmer(OnChainConfig(chain="ethereum", dry_run=True))
    farmer._policy = policy
    farmer._web3 = MagicMock()
    farmer._account = MagicMock()
    farmer._account.address = "0x" + "ac" * 20
    return farmer


def test_airdrop_gate_is_built_lazily_and_reused():
    f = _farmer()
    assert isinstance(f._gate(), PreSignInterceptor)
    assert f._gate() is f._gate()


def test_airdrop_gate_without_policy_is_fail_closed():
    """airdrop used to sign through its own account with no policy at all."""
    f = _farmer()
    signed = MagicMock()
    signed.raw_transaction = b"raw"
    f._account.sign_transaction.return_value = signed

    result = f._send_transaction(_tx(to="0x" + "dd" * 20))

    assert result is None
    assert f._gate().audit_log[-1].verdict.value == "denied"
    f._web3.eth.send_raw_transaction.assert_not_called()


def test_airdrop_gate_signs_when_policy_allows():
    policy = ExecutionPolicy(
        allowed_chains=frozenset({Chain.ETHEREUM}),
        allowed_actions=frozenset({ActionType.CONTRACT_CALL}),
        allowed_contracts=frozenset({"0x" + "dd" * 20}),
        require_confirmation=False,
    )
    f = _farmer(policy=policy)

    signed = MagicMock()
    signed.raw_transaction = b"raw-bytes"
    f._account.sign_transaction.return_value = signed
    receipt = MagicMock()
    receipt.transactionHash.hex.return_value = "0xairdrop"
    f._web3.eth.wait_for_transaction_receipt.return_value = receipt

    result = f._send_transaction(_tx(to="0x" + "dd" * 20))

    assert result == "0xairdrop"
    f._web3.eth.send_raw_transaction.assert_called_once_with(b"raw-bytes")


def test_airdrop_send_returns_none_without_web3():
    from web3_agent_kit.airdrop.onchain import OnChainAirdropFarmer, OnChainConfig

    f = OnChainAirdropFarmer(OnChainConfig(chain="ethereum", dry_run=True))
    f._web3 = None
    f._account = None
    assert f._send_transaction(_tx()) is None


def test_airdrop_resolves_chain_name():
    f = _farmer()
    assert f._resolve_chain() is Chain.ETHEREUM

    f.config = MagicMock(chain="base")
    assert f._resolve_chain() is Chain.BASE

    f.config = MagicMock(chain="definitely-not-a-chain")
    assert f._resolve_chain() is Chain.ETHEREUM
