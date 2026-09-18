"""Regression tests for the enforced pre-sign authorization gate.

These tests pin the security invariants of the interceptor:

1. A denied policy never produces a signature.
2. A missing policy is fail-closed, not fail-open.
3. Confirmation-required policy refuses to sign unattended.
4. An incomplete transaction is rejected before the signer is reached.
5. The audit log records every evaluation, authorized or denied.
6. The call fingerprint binds chain, target, calldata, value and nonce.
"""

from __future__ import annotations

import pytest

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import (
    ActionType,
    AuthorizationRequest,
    AuthorizationVerdict,
    EnforcementDenied,
    ExecutionPolicy,
    InvalidIntentError,
    PolicyReason,
    PreSignInterceptor,
)

ROUTER = "0x94cc0aac535ccdb3c01d6787d6413c739ae12bc4"
SENDER = "0x9965507d1a55bcc2695c58ba16fb37d819b0a4dc"
CALLDATA = bytes.fromhex(
    "7ff36ab5"
    "0000000000000000000000000000000000000000000000000000000000000f60"
    "0000000000000000000000000000000000000000000000000000000000000080"
    + "0" * 64
)


def _tx(**overrides) -> dict:
    tx = {
        "to": ROUTER,
        "from": SENDER,
        "data": CALLDATA,
        "value": 1_000_000_000_000,
        "nonce": 265,
        "chainId": 84532,
        "gas": 300_000,
    }
    tx.update(overrides)
    return tx


def _permissive_policy(**overrides) -> ExecutionPolicy:
    kwargs: dict = {
        "allowed_chains": frozenset({Chain.BASE}),
        "allowed_actions": frozenset({ActionType.SWAP}),
        "allowed_contracts": frozenset({ROUTER}),
        "max_native_value_wei": 10**18,
        "require_confirmation": False,
    }
    kwargs.update(overrides)
    return ExecutionPolicy(**kwargs)


class _RecordingSigner:
    """Stand-in for Account.sign_transaction that records whether it was reached."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, tx) -> bytes:
        self.calls.append(dict(tx))
        return b"\x01" * 64


def _request(**overrides) -> AuthorizationRequest:
    return AuthorizationRequest(
        chain=Chain.BASE,
        action=ActionType.SWAP,
        transaction=_tx(**overrides),
    )


def test_allowed_transaction_is_signed_and_audited():
    signer = _RecordingSigner()
    gate = PreSignInterceptor(policy=_permissive_policy(), signer=signer)

    result = gate.sign(_request())

    assert len(signer.calls) == 1
    assert result.raw_transaction == b"\x01" * 64
    assert result.audit_sequence == 1
    assert result.call_fingerprint.startswith("0x")

    log = gate.audit_log
    assert len(log) == 1
    assert log[0].verdict is AuthorizationVerdict.AUTHORIZED
    assert log[0].reasons == ()
    assert log[0].signature_hash is not None


def test_denied_policy_never_reaches_the_signer():
    signer = _RecordingSigner()
    policy = _permissive_policy(allowed_contracts=frozenset({"0x" + "11" * 20}))
    gate = PreSignInterceptor(policy=policy, signer=signer)

    with pytest.raises(EnforcementDenied) as excinfo:
        gate.sign(_request())

    assert len(signer.calls) == 0
    assert PolicyReason.CONTRACT_NOT_ALLOWED.value in str(excinfo.value)

    log = gate.audit_log
    assert len(log) == 1
    assert log[0].verdict is AuthorizationVerdict.DENIED
    assert PolicyReason.CONTRACT_NOT_ALLOWED.value in log[0].reasons
    assert log[0].signature_hash is None


def test_missing_policy_is_fail_closed():
    signer = _RecordingSigner()
    gate = PreSignInterceptor(policy=None, signer=signer)

    with pytest.raises(EnforcementDenied):
        gate.sign(_request())

    assert len(signer.calls) == 0
    assert gate.audit_log[0].verdict is AuthorizationVerdict.DENIED


def test_confirmation_required_without_handler_refuses_unattended():
    signer = _RecordingSigner()
    policy = _permissive_policy(require_confirmation=True)
    gate = PreSignInterceptor(policy=policy, signer=signer)

    with pytest.raises(EnforcementDenied):
        gate.sign(_request())

    assert len(signer.calls) == 0
    assert gate.audit_log[0].verdict is AuthorizationVerdict.DENIED


def test_confirmation_handler_approval_allows_signing():
    signer = _RecordingSigner()
    policy = _permissive_policy(require_confirmation=True)
    gate = PreSignInterceptor(
        policy=policy,
        signer=signer,
        confirmation_fn=lambda request, decision: True,
    )

    gate.sign(_request())
    assert len(signer.calls) == 1


def test_confirmation_handler_refusal_blocks_signing():
    signer = _RecordingSigner()
    policy = _permissive_policy(require_confirmation=True)
    gate = PreSignInterceptor(
        policy=policy,
        signer=signer,
        confirmation_fn=lambda request, decision: False,
    )

    with pytest.raises(EnforcementDenied):
        gate.sign(_request())

    assert len(signer.calls) == 0


def test_incomplete_transaction_rejected_before_signer():
    signer = _RecordingSigner()
    gate = PreSignInterceptor(policy=_permissive_policy(), signer=signer)

    with pytest.raises(InvalidIntentError):
        AuthorizationRequest(
            chain=Chain.BASE,
            action=ActionType.SWAP,
            transaction={"to": ROUTER, "data": CALLDATA},
        )

    assert len(signer.calls) == 0


def test_disallowed_chain_is_denied():
    signer = _RecordingSigner()
    policy = _permissive_policy(allowed_chains=frozenset({Chain.ETHEREUM}))
    gate = PreSignInterceptor(policy=policy, signer=signer)

    with pytest.raises(EnforcementDenied):
        gate.sign(_request())

    assert len(signer.calls) == 0


def test_call_fingerprint_binds_every_envelope_field():
    base = _request()
    variants = [
        _request(to="0x" + "22" * 20),
        _request(value=999),
        _request(nonce=266),
        _request(chainId=8453),
        _request(data=bytes.fromhex("deadbeef")),
    ]

    for variant in variants:
        assert variant.call_fingerprint != base.call_fingerprint, (
            "fingerprint must change when the call envelope changes"
        )

    assert _request().call_fingerprint == base.call_fingerprint


def test_audit_log_accumulates_in_order():
    signer = _RecordingSigner()
    policy = _permissive_policy(
        allowed_contracts=frozenset({ROUTER, "0x" + "33" * 20})
    )
    gate = PreSignInterceptor(policy=policy, signer=signer)

    gate.sign(_request())
    with pytest.raises(EnforcementDenied):
        gate.sign(_request(to="0x" + "44" * 20))
    gate.sign(_request())

    log = gate.audit_log
    assert [entry.sequence for entry in log] == [1, 2, 3]
    assert [entry.verdict for entry in log] == [
        AuthorizationVerdict.AUTHORIZED,
        AuthorizationVerdict.DENIED,
        AuthorizationVerdict.AUTHORIZED,
    ]


def test_audit_log_is_immutable_snapshot():
    signer = _RecordingSigner()
    gate = PreSignInterceptor(policy=_permissive_policy(), signer=signer)

    gate.sign(_request())
    snapshot = gate.audit_log

    gate.sign(_request())

    assert len(snapshot) == 1
    assert len(gate.audit_log) == 2
    assert isinstance(snapshot, tuple)
