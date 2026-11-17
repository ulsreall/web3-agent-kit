"""Regression tests for the gate gaps found in review.

Covers contract creation, the ``input`` alias, and policy-commitment binding.
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
    PreSignInterceptor,
)
from web3_agent_kit.execution.replay import InMemoryReplayStore

SENDER_KEY = "0x" + "11" * 32
SENDER = Account.from_key(SENDER_KEY).address
TARGET = "0x" + "22" * 20


def _policy(**overrides) -> ExecutionPolicy:
    kwargs = {
        "allowed_chains": frozenset({Chain.BASE}),
        "allowed_actions": frozenset(ActionType),
        "allowed_contracts": frozenset({TARGET}),
        "max_native_value_wei": 10**18,
        "require_confirmation": False,
    }
    kwargs.update(overrides)
    return ExecutionPolicy(**kwargs)


def _provider(commitment: str | None = None):
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
            policy_commitment_digest=commitment or context.policy_commitment.digest(),
        )

    return CallableAuthorizationProvider(verify)


def _gate(policy=None, commitment=None) -> PreSignInterceptor:
    return PreSignInterceptor(
        policy=policy or _policy(),
        signer=lambda tx: Account.sign_transaction(tx, SENDER_KEY).raw_transaction,
        authorization_provider=_provider(commitment),
        replay_store=InMemoryReplayStore(),
    )


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


def _request(transaction, action=ActionType.CONTRACT_CALL) -> AuthorizationRequest:
    return AuthorizationRequest(chain=Chain.BASE, action=action, transaction=transaction)


# -- contract creation ------------------------------------------------


def test_creation_request_accepts_missing_to():
    request = _request(_tx(to=None, data="0x6080604052"))
    assert request.envelope_v2().execution_profile == "create"


def test_creation_signs_through_the_gate():
    result = _gate().sign(_request(_tx(to=None, data="0x6080604052")))
    assert result.raw_transaction


def test_creation_without_init_code_is_denied():
    with pytest.raises(EnforcementDenied):
        _gate().sign(_request(_tx(to=None, data="0x")))


def test_creation_is_not_a_call_to_the_zero_address():
    zero = "0x" + "00" * 20
    policy = _policy(allowed_contracts=frozenset({TARGET, zero}))
    creation = _gate(policy).sign(_request(_tx(to=None, data="0x6080")))
    call = _gate(policy).sign(_request(_tx(to=zero, data="0x6080")))
    assert creation.call_fingerprint != call.call_fingerprint


# -- calldata aliases -------------------------------------------------


def test_input_only_is_signed():
    tx = _tx()
    tx.pop("data")
    tx["input"] = "0x" + "bb" * 4
    result = _gate().sign(_request(tx))
    assert result.raw_transaction


def test_input_only_commits_to_the_real_calldata():
    tx = _tx()
    tx.pop("data")
    tx["input"] = "0x" + "bb" * 4
    request = _request(tx)
    empty = _request(_tx(data="0x"))
    assert request.call_fingerprint != empty.call_fingerprint


def test_conflicting_data_and_input_is_denied():
    with pytest.raises(EnforcementDenied):
        _gate().sign(_request(_tx(data="0x" + "aa" * 4, input="0x" + "bb" * 4)))


def test_matching_data_and_input_is_accepted():
    payload = "0x" + "cc" * 4
    result = _gate().sign(_request(_tx(data=payload, input=payload)))
    assert result.raw_transaction


# -- policy commitment binding ----------------------------------------


def test_bogus_policy_commitment_is_denied():
    with pytest.raises(EnforcementDenied) as excinfo:
        _gate(commitment="0xdeadbeef").sign(_request(_tx()))
    assert "different policy verdict" in str(excinfo.value)


def test_matching_policy_commitment_is_accepted():
    result = _gate().sign(_request(_tx()))
    assert result.authorization.policy_commitment_digest == result.policy_commitment.digest()
