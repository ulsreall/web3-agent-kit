"""Regression tests for the enforced Wallet signing boundary.

These pin the invariants that make the Wallet a real gate rather than a
pass-through:

1. A wallet with no bound gate refuses write-capable transactions.
2. A bound gate evaluates policy before any signature exists.
3. A denial produces no signature and no sent transaction.
4. A native-value transfer without a destination still signs (nothing to gate).
5. The action passed by the caller reaches the intent, so allowlists apply.
"""

from __future__ import annotations

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import (
    ActionType,
    EnforcementDenied,
    ExecutionPolicy,
    PolicyReason,
    PreSignInterceptor,
)
from web3_agent_kit.wallet.wallet import Wallet, WalletConfig

ROUTER = "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4"

# A deterministic test key. Never fund this address.
TEST_KEY = "0x" + "11" * 32

# The signer address derived from TEST_KEY, so "from" matches the key.
SIGNER = "0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A"


def _tx(**overrides) -> dict:
    tx = {
        "to": ROUTER,
        "from": SIGNER,
        "data": "0xdeadbeef",
        "value": 0,
        "nonce": 1,
        "chainId": 84532,
        "gas": 300_000,
        "gasPrice": 1_000_000_000,
    }
    tx.update(overrides)
    return tx


def _wallet() -> Wallet:
    return Wallet(WalletConfig(private_key=TEST_KEY))


def _gate(wallet: Wallet, **policy_overrides) -> PreSignInterceptor:
    kwargs: dict = {
        "allowed_chains": frozenset({Chain.BASE}),
        "allowed_actions": frozenset({ActionType.SWAP}),
        "allowed_contracts": frozenset({ROUTER}),
        "max_native_value_wei": 10**18,
        "require_confirmation": False,
    }
    kwargs.update(policy_overrides)
    return PreSignInterceptor(
        policy=ExecutionPolicy(**kwargs), signer=wallet._raw_signer
    )


def _enforced(**policy_overrides) -> Wallet:
    """Return a wallet with a bound gate, chained in one step."""
    wallet = _wallet()
    return wallet.bind_enforcement(_gate(wallet, **policy_overrides))


def test_unbound_wallet_refuses_write_capable_signing():
    wallet = _wallet()

    assert wallet.is_enforced is False
    try:
        wallet.sign_transaction(_tx(), Chain.BASE)
    except EnforcementDenied as exc:
        assert "no bound pre-sign gate" in str(exc)
    else:  # pragma: no cover - the assertion below reports the failure
        raise AssertionError("unbound wallet produced a signature")


def test_bound_wallet_authorizes_allowed_call():
    wallet = _enforced()

    raw = wallet.sign_transaction(_tx(), Chain.BASE, action=ActionType.SWAP)

    assert isinstance(raw, bytes)
    assert len(raw) > 0
    assert wallet.is_enforced is True
    assert len(wallet.enforcement.audit_log) == 1


def test_bound_wallet_denies_disallowed_contract():
    wallet = _enforced()
    tx = _tx(to="0x" + "99" * 20)

    try:
        wallet.sign_transaction(tx, Chain.BASE, action=ActionType.SWAP)
    except EnforcementDenied as exc:
        assert PolicyReason.CONTRACT_NOT_ALLOWED.value in str(exc)
    else:  # pragma: no cover
        raise AssertionError("disallowed contract was signed")

    entry = wallet.enforcement.audit_log[-1]
    assert entry.signature_hash is None


def test_action_allowlist_is_enforced_through_the_wallet():
    wallet = _enforced()

    try:
        wallet.sign_transaction(_tx(), Chain.BASE, action=ActionType.BRIDGE)
    except EnforcementDenied as exc:
        assert PolicyReason.ACTION_NOT_ALLOWED.value in str(exc)
    else:  # pragma: no cover
        raise AssertionError("action outside the allowlist was signed")


def test_default_action_is_contract_call_not_a_blanket_allow():
    """Without an explicit action the intent is CONTRACT_CALL, not SWAP."""
    wallet = _enforced(allowed_actions=frozenset({ActionType.CONTRACT_CALL}))

    raw = wallet.sign_transaction(_tx(), Chain.BASE)

    assert len(raw) > 0
    assert wallet.enforcement.audit_log[-1].action == ActionType.CONTRACT_CALL.value


def test_native_value_limit_applies_through_the_wallet():
    wallet = _enforced(max_native_value_wei=1000)

    try:
        wallet.sign_transaction(
            _tx(value=5000), Chain.BASE, action=ActionType.SWAP
        )
    except EnforcementDenied as exc:
        assert PolicyReason.NATIVE_VALUE_EXCEEDED.value in str(exc)
    else:  # pragma: no cover
        raise AssertionError("value above the policy ceiling was signed")


def test_bind_enforcement_rejects_a_non_gate():
    wallet = _wallet()

    try:
        wallet.bind_enforcement(object())
    except ValueError as exc:
        assert "PreSignInterceptor" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a non-gate was accepted as enforcement")


def test_bind_enforcement_returns_self_for_chaining():
    wallet = _wallet()
    assert wallet.bind_enforcement(_gate(wallet)) is wallet


def test_enforced_property_exposes_the_bound_gate():
    wallet = _enforced()
    assert wallet.enforcement is not None
    assert wallet.enforcement.policy is not None
    assert wallet.enforcement.audit_log == ()
