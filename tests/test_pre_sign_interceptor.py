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
    AuthorizationDenied,
    AuthorizationEvidence,
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
    "0000000000000000000000000000000000000000000000000000000000000080" + "0" * 64
)


def _tx(**overrides) -> dict:
    tx = {
        "to": ROUTER,
        "from": SENDER,
        "data": CALLDATA,
        "value": 1_000_000_000_000,
        "nonce": 265,
        "chainId": 8453,
        "gas": 300_000,
        "gasPrice": 1_000_000_000,
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


class _AllowingProvider:
    """Verifier that authorizes exactly the call it is handed.

    Stands in for a real principal authorization service. It is deliberately
    permissive: every gate test below is about what the *gate* does with
    evidence, not about what a verifier should refuse.
    """

    def __init__(self, *, valid_from: int = 0, valid_until: int = 2**31) -> None:
        self._valid_from = valid_from
        self._valid_until = valid_until

    @property
    def policy_id(self) -> str:
        return "test-allowing-provider"

    def authorize(self, context):
        return AuthorizationEvidence(
            authorization_id="test-auth",
            envelope_digest=context.envelope_digest,
            executor=context.envelope.executor,
            authorizer="0x" + "99" * 20,
            valid_from=self._valid_from,
            valid_until=self._valid_until,
            nonce="1",
            policy_commitment_digest=context.policy_commitment.digest(),
        )


class _RefusingProvider:
    """Verifier that denies every call."""

    @property
    def policy_id(self) -> str:
        return "test-refusing-provider"

    def authorize(self, context):
        raise AuthorizationDenied("no authorization on file")


def _request(**overrides) -> AuthorizationRequest:
    return AuthorizationRequest(
        chain=Chain.BASE,
        action=ActionType.SWAP,
        transaction=_tx(**overrides),
    )


def test_allowed_transaction_is_signed_and_audited():
    signer = _RecordingSigner()
    gate = PreSignInterceptor(
        policy=_permissive_policy(),
        signer=signer,
        authorization_provider=_AllowingProvider(),
    )

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
    assert log[0].envelope_schema == "agent-call-envelope.v2"


def test_denied_policy_never_reaches_the_signer():
    signer = _RecordingSigner()
    policy = _permissive_policy(allowed_contracts=frozenset({"0x" + "11" * 20}))
    gate = PreSignInterceptor(
        policy=policy, signer=signer, authorization_provider=_AllowingProvider()
    )

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
        authorization_provider=_AllowingProvider(),
    )

    gate.sign(_request())
    assert len(signer.calls) == 1


def test_legacy_envelope_requires_explicit_opt_in():
    signer = _RecordingSigner()
    gate = PreSignInterceptor(
        policy=_permissive_policy(),
        signer=signer,
        authorization_provider=_AllowingProvider(),
        envelope_version=1,
    )

    gate.sign(_request())

    assert len(signer.calls) == 1
    assert gate.audit_log[0].envelope_schema == "agent-call-envelope.v1"


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
    PreSignInterceptor(policy=_permissive_policy(), signer=signer)

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
    gate = PreSignInterceptor(
        policy=policy, signer=signer, authorization_provider=_AllowingProvider()
    )

    with pytest.raises(EnforcementDenied):
        gate.sign(_request())

    assert len(signer.calls) == 0


def test_call_fingerprint_binds_every_envelope_field():
    base = _request()
    variants = [
        _request(to="0x" + "22" * 20),
        _request(value=999),
        _request(nonce=266),
        _request(data=bytes.fromhex("deadbeef")),
        _request(gas=300_001),
        _request(gasPrice=2_000_000_000),
        _request(gasPrice=None, maxFeePerGas=2_000_000_000, maxPriorityFeePerGas=1_000_000_000),
        _request(gasPrice=None, maxFeePerGas=2_000_000_000, maxPriorityFeePerGas=1_000_000_001),
    ]

    for variant in variants:
        assert variant.call_fingerprint != base.call_fingerprint, (
            "fingerprint must change when the call envelope changes"
        )

    assert _request().call_fingerprint == base.call_fingerprint

    # The executor is part of the identity: the same call from another sender
    # must not share an envelope digest.
    other_sender = _tx()
    other_sender["from"] = "0x" + "55" * 20
    assert (
        AuthorizationRequest(
            chain=Chain.BASE, action=ActionType.SWAP, transaction=other_sender
        ).call_fingerprint
        != base.call_fingerprint
    ), "fingerprint must change when the executor changes"


def test_approval_is_checked_against_token_and_allowance_policy():
    token = "0x" + "44" * 20
    spender = "0x" + "55" * 20
    calldata = bytes.fromhex("095ea7b3" + "00" * 12 + spender[2:] + f"{500:064x}")
    transaction = _tx(to=token, data=calldata)
    signer = _RecordingSigner()
    gate = PreSignInterceptor(
        policy=_permissive_policy(
            allowed_actions=frozenset({ActionType.APPROVE_TOKEN}),
            allowed_tokens=frozenset({token}),
            max_approval_amounts={token: 500},
        ),
        signer=signer,
        authorization_provider=_AllowingProvider(),
    )

    result = gate.sign(AuthorizationRequest(Chain.BASE, ActionType.APPROVE_TOKEN, transaction))

    assert signer.calls == [transaction]
    assert result.decision.allowed


def test_approval_above_allowance_policy_limit_is_denied():
    token = "0x" + "44" * 20
    spender = "0x" + "55" * 20
    calldata = bytes.fromhex("095ea7b3" + "00" * 12 + spender[2:] + f"{501:064x}")
    signer = _RecordingSigner()
    gate = PreSignInterceptor(
        policy=_permissive_policy(
            allowed_actions=frozenset({ActionType.APPROVE_TOKEN}),
            allowed_tokens=frozenset({token}),
            max_approval_amounts={token: 500},
        ),
        signer=signer,
        authorization_provider=_AllowingProvider(),
    )

    with pytest.raises(EnforcementDenied, match="approval_amount_exceeded"):
        gate.sign(
            AuthorizationRequest(
                Chain.BASE,
                ActionType.APPROVE_TOKEN,
                _tx(to=token, data=calldata),
            )
        )

    assert signer.calls == []


def test_audit_log_accumulates_in_order():
    signer = _RecordingSigner()
    policy = _permissive_policy(allowed_contracts=frozenset({ROUTER, "0x" + "33" * 20}))

    class _PerCallProvider(_AllowingProvider):
        """Authorizes whatever it is handed, with a fresh authorization each time."""

        def __init__(self) -> None:
            super().__init__()
            self._n = 0

        def authorize(self, context):
            self._n += 1
            return AuthorizationEvidence(
                authorization_id=f"test-auth-{self._n}",
                envelope_digest=context.envelope_digest,
                executor=context.envelope.executor,
                authorizer="0x" + "99" * 20,
                valid_from=0,
                valid_until=2**31,
                nonce=str(self._n),
                policy_commitment_digest=context.policy_commitment.digest(),
            )

    gate = PreSignInterceptor(
        policy=policy, signer=signer, authorization_provider=_PerCallProvider()
    )

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

    class _PerCallProvider(_AllowingProvider):
        def __init__(self) -> None:
            super().__init__()
            self._n = 0

        def authorize(self, context):
            self._n += 1
            return AuthorizationEvidence(
                authorization_id=f"snap-{self._n}",
                envelope_digest=context.envelope_digest,
                executor=context.envelope.executor,
                authorizer="0x" + "99" * 20,
                valid_from=0,
                valid_until=2**31,
                nonce=str(self._n),
                policy_commitment_digest=context.policy_commitment.digest(),
            )

    gate = PreSignInterceptor(
        policy=_permissive_policy(),
        signer=signer,
        authorization_provider=_PerCallProvider(),
    )

    gate.sign(_request())
    snapshot = gate.audit_log

    gate.sign(_request())

    assert len(snapshot) == 1
    assert len(gate.audit_log) == 2
    assert isinstance(snapshot, tuple)
