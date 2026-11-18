"""Construction-time validation for the authorization request and the gate.

Both types are cheap to get wrong at a call site: a request built from a
half-constructed transaction, or a gate wired to a signer that is not callable,
must fail while the mistake is still local instead of producing a signature for
something the principal never described.
"""

from __future__ import annotations

import time

import pytest
from eth_account import Account

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import (
    ActionType,
    AuthorizationEvidence,
    AuthorizationRequest,
    CallableAuthorizationProvider,
    EnforcementDenied,
    ExecutionPolicy,
    InvalidIntentError,
    PreSignInterceptor,
)
from web3_agent_kit.execution.interceptor import ExecutionError
from web3_agent_kit.execution.replay import InMemoryReplayStore

SENDER_KEY = "0x" + "11" * 32
SENDER = Account.from_key(SENDER_KEY).address
TARGET = "0x" + "22" * 20


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        allowed_chains=frozenset({Chain.BASE}),
        allowed_actions=frozenset(ActionType),
        allowed_contracts=frozenset({TARGET}),
        max_native_value_wei=10**18,
        require_confirmation=False,
    )


def _provider():
    def verify(context):
        now = int(time.time())
        return AuthorizationEvidence(
            authorization_id="auth-1",
            envelope_digest=context.envelope_digest,
            executor=context.envelope.executor,
            authorizer=SENDER,
            valid_from=now - 5,
            valid_until=now + 300,
            nonce="1",
            policy_commitment_digest=context.policy_commitment.digest(),
        )

    return CallableAuthorizationProvider(verify)


def _signer(tx):
    return Account.sign_transaction(tx, SENDER_KEY).raw_transaction


def _gate(**overrides) -> PreSignInterceptor:
    kwargs = {
        "policy": _policy(),
        "signer": _signer,
        "authorization_provider": _provider(),
        "replay_store": InMemoryReplayStore(),
    }
    kwargs.update(overrides)
    return PreSignInterceptor(**kwargs)


def _tx(**overrides) -> dict:
    tx = {
        "from": SENDER,
        "to": TARGET,
        "nonce": 0,
        "chainId": 8453,
        "value": 0,
        "data": "0x" + "aa" * 4,
        "gas": 100000,
        "maxFeePerGas": 10**9,
        "maxPriorityFeePerGas": 10**9,
    }
    tx.update(overrides)
    return tx


class TestRequestValidation:
    def test_non_mapping_transaction_rejected(self):
        with pytest.raises(InvalidIntentError, match="transaction must be a mapping"):
            AuthorizationRequest(chain=Chain.BASE, action=ActionType.CONTRACT_CALL, transaction=[])  # type: ignore[arg-type]

    @pytest.mark.parametrize("field", ["from", "nonce", "chainId"])
    def test_missing_required_fields_rejected(self, field):
        transaction = {k: v for k, v in _tx().items() if k != field}
        with pytest.raises(InvalidIntentError, match=f"missing: {field}"):
            AuthorizationRequest(
                chain=Chain.BASE, action=ActionType.CONTRACT_CALL, transaction=transaction
            )

    def test_creation_does_not_require_to(self):
        request = AuthorizationRequest(
            chain=Chain.BASE,
            action=ActionType.CONTRACT_CALL,
            transaction={k: v for k, v in _tx().items() if k != "to"},
        )
        assert request.transaction.get("to") is None


class TestGateConstruction:
    def test_non_callable_signer_rejected(self):
        with pytest.raises(ExecutionError, match="signer must be callable"):
            _gate(signer="nope")  # type: ignore[arg-type]

    def test_non_policy_rejected(self):
        with pytest.raises(ExecutionError, match="policy must be an ExecutionPolicy"):
            _gate(policy={"allowed_chains": []})

    def test_provider_without_authorize_rejected(self):
        with pytest.raises(ExecutionError, match="must implement authorize"):
            _gate(authorization_provider=object())

    @pytest.mark.parametrize("version", [0, 3, "2", True])
    def test_bad_envelope_version_rejected(self, version):
        with pytest.raises(ExecutionError, match="envelope_version must be 1 or 2"):
            _gate(envelope_version=version)

    @pytest.mark.parametrize("version", [1, 2])
    def test_supported_versions_accepted(self, version):
        gate = _gate(envelope_version=version)
        assert gate.sign(
            AuthorizationRequest(
                chain=Chain.BASE, action=ActionType.CONTRACT_CALL, transaction=_tx()
            )
        ).raw_transaction


class TestSignValidation:
    def test_non_request_rejected(self):
        with pytest.raises(InvalidIntentError, match="request must be an AuthorizationRequest"):
            _gate().sign({"from": SENDER})  # type: ignore[arg-type]

    def test_malformed_target_is_denied_as_incomplete(self):
        # `to` present but malformed: the request builds, the envelope does not.
        request = AuthorizationRequest(
            chain=Chain.BASE,
            action=ActionType.CONTRACT_CALL,
            transaction=_tx(to="0xdead"),
        )
        gate = _gate()
        with pytest.raises(EnforcementDenied, match="20-byte"):
            gate.sign(request)
        assert "incomplete_transaction" in gate.audit_log[0].reasons

    def test_intent_construction_failure_is_denied_and_logged(self):
        # A token transfer with no token still builds an envelope but cannot be
        # described as an intent, so stage 2 is the one that refuses.
        request = AuthorizationRequest(
            chain=Chain.BASE,
            action=ActionType.TRANSFER_TOKEN,
            transaction=_tx(),
        )
        gate = _gate()
        with pytest.raises(EnforcementDenied, match="could not be described as an intent"):
            gate.sign(request)
        assert "intent_construction_failed" in gate.audit_log[0].reasons


class TestAuditSerialization:
    def test_denied_entry_serializes_with_its_reason(self):
        request = AuthorizationRequest(
            chain=Chain.BASE, action=ActionType.CONTRACT_CALL, transaction=_tx(to="0xdead")
        )
        gate = _gate()
        with pytest.raises(EnforcementDenied):
            gate.sign(request)
        entry = gate.audit_log[0].as_dict()
        assert entry["verdict"] == "denied"
        assert entry["chain"] == "base"
        assert entry["reasons"] == ["incomplete_transaction"]
        assert entry["signature_hash"] is None


class TestProviderOutput:
    def test_provider_returning_a_non_evidence_object_is_denied(self):
        # CallableAuthorizationProvider checks its own return type, but a
        # provider implementing `authorize` directly does not, so the gate has
        # to check again rather than trust the annotation.
        class RogueProvider:
            policy_id = "rogue"

            def authorize(self, context):
                return {"verdict": "allow"}

        with pytest.raises(EnforcementDenied, match="expected AuthorizationEvidence"):
            _gate(authorization_provider=RogueProvider()).sign(
                AuthorizationRequest(
                    chain=Chain.BASE, action=ActionType.CONTRACT_CALL, transaction=_tx()
                )
            )
