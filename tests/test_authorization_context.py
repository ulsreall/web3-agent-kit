"""Validation tests for authorization evidence and its providers.

Evidence is the gate's only statement of *which* call the principal authorized.
If malformed evidence is accepted, the gate verifies something weaker than the
call it is about to sign, so every field is validated eagerly here rather than
at the point of use.
"""

from __future__ import annotations

import time

import pytest

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import (
    AuthorizationContext,
    AuthorizationEvidence,
    CallableAuthorizationProvider,
    CallEnvelopeV1,
)
from web3_agent_kit.execution.authorization import AuthorizationContextError
from web3_agent_kit.execution.envelope import PolicyDecisionCommitment

ROUTER = "0x94cc0aac535ccdb3c01d6787d6413c739ae12bc4"
SENDER = "0x9965507d1a55bcc2695c58ba16fb37d819b0a4dc"
DIGEST = "0x" + "ab" * 32
OTHER_DIGEST = "0x" + "cd" * 32


def _evidence(**overrides) -> AuthorizationEvidence:
    fields = {
        "authorization_id": "auth-1",
        "envelope_digest": DIGEST,
        "executor": SENDER,
        "authorizer": "principal",
        "valid_from": 100,
        "valid_until": 200,
        "nonce": "7",
        "policy_commitment_digest": DIGEST,
    }
    fields.update(overrides)
    return AuthorizationEvidence(**fields)


def _context() -> AuthorizationContext:
    envelope = CallEnvelopeV1.from_transaction(
        transaction={
            "to": ROUTER,
            "from": SENDER,
            "data": b"\xde\xad",
            "nonce": 0,
            "chainId": 8453,
        },
        chain=Chain.BASE,
    )
    return AuthorizationContext(
        envelope=envelope,
        envelope_digest=envelope.digest(),
        policy_commitment=PolicyDecisionCommitment(
            call_identity=envelope.digest(),
            policy_id="policy-1",
            verdict="allow",
            reason_codes=("OK",),
            evaluated_at=1,
        ),
        action="call",
        chain="base",
    )


class TestEvidenceValidation:
    def test_valid_evidence_constructs(self):
        assert _evidence().authorization_id == "auth-1"

    def test_empty_authorization_id_rejected(self):
        with pytest.raises(AuthorizationContextError, match="authorization_id must be non-empty"):
            _evidence(authorization_id="")

    def test_unprefixed_digest_rejected(self):
        with pytest.raises(AuthorizationContextError, match="0x-prefixed digest"):
            _evidence(envelope_digest="ab" * 32)

    def test_empty_nonce_rejected(self):
        with pytest.raises(AuthorizationContextError, match="nonce must be non-empty"):
            _evidence(nonce="")

    @pytest.mark.parametrize(("start", "end"), [(200, 200), (200, 100)])
    def test_window_must_be_open(self, start, end):
        with pytest.raises(AuthorizationContextError, match="later than valid_from"):
            _evidence(valid_from=start, valid_until=end)


class TestCoverage:
    def test_covers_matching_call(self):
        assert _evidence().covers(envelope_digest=DIGEST, executor=SENDER) is True

    def test_rejects_other_digest(self):
        assert _evidence().covers(envelope_digest=OTHER_DIGEST, executor=SENDER) is False

    def test_rejects_other_executor(self):
        assert _evidence().covers(envelope_digest=DIGEST, executor="0x" + "11" * 20) is False

    def test_executor_comparison_ignores_case(self):
        # Checksummed and lower-case spellings are the same account; a case
        # difference must not void a valid authorization.
        assert _evidence().covers(envelope_digest=DIGEST, executor=SENDER.upper()) is True


class TestFreshness:
    def test_inside_window(self):
        assert _evidence().is_fresh(now=150) is True

    @pytest.mark.parametrize("moment", [99, 201])
    def test_outside_window(self, moment):
        assert _evidence().is_fresh(now=moment) is False

    def test_boundaries_are_inclusive(self):
        assert _evidence(valid_from=150, valid_until=160).is_fresh(now=150) is True
        assert _evidence(valid_from=150, valid_until=160).is_fresh(now=160) is True

    def test_defaults_to_wall_clock(self):
        now = int(time.time())
        assert _evidence(valid_from=now - 5, valid_until=now + 5).is_fresh() is True


class TestContext:
    def test_context_carries_the_envelope_it_describes(self):
        context = _context()
        assert context.envelope_digest == context.envelope.digest()
        assert context.envelope.executor == SENDER


class TestCallableProvider:
    def test_rejects_non_callable(self):
        with pytest.raises(AuthorizationContextError, match="verifier must be callable"):
            CallableAuthorizationProvider("not callable")  # type: ignore[arg-type]

    def test_wraps_a_verifier(self):
        evidence = _evidence()
        provider = CallableAuthorizationProvider(lambda context: evidence)
        assert provider.authorize(_context()) is evidence

    def test_policy_id_is_stable(self):
        provider = CallableAuthorizationProvider(lambda c: _evidence())
        assert provider.policy_id == "callable-authorization"

    def test_wrong_return_type_is_an_error_not_an_allow(self):
        provider = CallableAuthorizationProvider(lambda context: {"verdict": "allow"})  # type: ignore[arg-type,return-value]
        with pytest.raises(AuthorizationContextError, match="expected AuthorizationEvidence"):
            provider.authorize(_context())


class TestNullProvider:
    """The default provider must refuse, never silently allow."""

    def test_policy_id_is_named(self):
        from web3_agent_kit.execution import NullAuthorizationProvider

        assert NullAuthorizationProvider().policy_id == "null-authorization"

    def test_authorize_raises_and_says_why(self):
        from web3_agent_kit.execution import AuthorizationDenied, NullAuthorizationProvider

        with pytest.raises(AuthorizationDenied, match="no principal authorization provider"):
            NullAuthorizationProvider().authorize(_context())
