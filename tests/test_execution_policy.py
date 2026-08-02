"""Offline tests for deterministic transaction execution policy."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import ActionType, TransactionIntent
from web3_agent_kit.execution.policy import (
    UINT256_MAX,
    ExecutionPolicy,
    InvalidPolicyAllowlistError,
    InvalidPolicyError,
    InvalidPolicyLimitError,
    PolicyDecision,
    PolicyReason,
)

SENDER = "0x1111111111111111111111111111111111111111"
RECIPIENT = "0x2222222222222222222222222222222222222222"
CONTRACT = "0x3333333333333333333333333333333333333333"
TOKEN = "0x4444444444444444444444444444444444444444"
OTHER = "0x5555555555555555555555555555555555555555"


def policy(**overrides) -> ExecutionPolicy:
    values = {
        "allowed_chains": {Chain.BASE},
        "allowed_actions": set(ActionType),
        "allowed_contracts": {CONTRACT},
        "allowed_tokens": {TOKEN},
        "max_native_value_wei": 100,
        "max_token_amounts": {TOKEN: 1_000},
        "max_approval_amounts": {TOKEN: 500},
        "require_confirmation": True,
    }
    values.update(overrides)
    return ExecutionPolicy(**values)


def native_intent(**overrides) -> TransactionIntent:
    values = {
        "chain": Chain.BASE,
        "action": ActionType.TRANSFER_NATIVE,
        "sender": SENDER,
        "recipient": RECIPIENT,
        "native_value_wei": 100,
    }
    values.update(overrides)
    return TransactionIntent(**values)


def token_intent(action=ActionType.TRANSFER_TOKEN, **overrides) -> TransactionIntent:
    values = {
        "chain": Chain.BASE,
        "action": action,
        "sender": SENDER,
        "recipient": RECIPIENT,
        "token": TOKEN,
        "amount_base_units": 500,
        "calldata": b"encoded",
    }
    values.update(overrides)
    return TransactionIntent(**values)


class TestAllowedDecisions:
    def test_native_transfer_at_limit_is_allowed(self):
        intent = native_intent(native_value_wei=100)
        decision = policy().evaluate(intent)
        assert decision.allowed is True
        assert decision.reasons == ()
        assert decision.intent_id == intent.intent_id
        assert decision.requires_confirmation is True
        assert decision.primary_reason is None

    def test_token_transfer_at_limit_is_allowed(self):
        decision = policy().evaluate(token_intent(amount_base_units=1_000))
        assert decision.allowed

    def test_approval_at_limit_is_allowed(self):
        decision = policy().evaluate(
            token_intent(ActionType.APPROVE_TOKEN, amount_base_units=500)
        )
        assert decision.allowed

    def test_contract_call_with_allowlisted_contract_is_allowed(self):
        intent = TransactionIntent(
            chain=Chain.BASE,
            action=ActionType.CONTRACT_CALL,
            sender=SENDER,
            contract=CONTRACT,
            calldata=b"call",
        )
        assert policy().evaluate(intent).allowed

    def test_confirmation_is_separate_from_authorization(self):
        decision = policy(require_confirmation=False).evaluate(native_intent())
        assert decision.allowed
        assert decision.requires_confirmation is False


class TestDeniedDecisions:
    def test_deny_all_policy(self):
        decision = ExecutionPolicy.deny_all().evaluate(native_intent())
        assert not decision.allowed
        assert decision.reasons == (
            PolicyReason.CHAIN_NOT_ALLOWED,
            PolicyReason.ACTION_NOT_ALLOWED,
            PolicyReason.NATIVE_VALUE_EXCEEDED,
        )

    def test_chain_not_allowed(self):
        decision = policy(allowed_chains={Chain.ETHEREUM}).evaluate(native_intent())
        assert decision.reasons == (PolicyReason.CHAIN_NOT_ALLOWED,)

    def test_action_not_allowed(self):
        decision = policy(allowed_actions={ActionType.SWAP}).evaluate(native_intent())
        assert decision.reasons == (PolicyReason.ACTION_NOT_ALLOWED,)

    def test_contract_not_allowed(self):
        intent = TransactionIntent(
            chain=Chain.BASE,
            action=ActionType.CONTRACT_CALL,
            sender=SENDER,
            contract=OTHER,
        )
        decision = policy().evaluate(intent)
        assert decision.reasons == (PolicyReason.CONTRACT_NOT_ALLOWED,)

    def test_token_not_allowed(self):
        intent = token_intent(token=OTHER)
        decision = policy(max_token_amounts={OTHER: 1_000}).evaluate(intent)
        assert decision.reasons == (PolicyReason.TOKEN_NOT_ALLOWED,)

    def test_native_value_above_limit(self):
        decision = policy().evaluate(native_intent(native_value_wei=101))
        assert decision.reasons == (PolicyReason.NATIVE_VALUE_EXCEEDED,)

    def test_missing_token_limit_fails_closed(self):
        decision = policy(max_token_amounts={}).evaluate(token_intent())
        assert decision.reasons == (PolicyReason.TOKEN_LIMIT_NOT_CONFIGURED,)

    def test_token_amount_above_limit(self):
        decision = policy().evaluate(token_intent(amount_base_units=1_001))
        assert decision.reasons == (PolicyReason.TOKEN_AMOUNT_EXCEEDED,)

    def test_missing_approval_limit_fails_closed(self):
        decision = policy(max_approval_amounts={}).evaluate(
            token_intent(ActionType.APPROVE_TOKEN)
        )
        assert decision.reasons == (PolicyReason.APPROVAL_LIMIT_NOT_CONFIGURED,)

    def test_approval_amount_above_limit(self):
        decision = policy().evaluate(
            token_intent(ActionType.APPROVE_TOKEN, amount_base_units=501)
        )
        assert decision.reasons == (PolicyReason.APPROVAL_AMOUNT_EXCEEDED,)

    def test_unlimited_approval_is_denied_by_default(self):
        decision = policy(max_approval_amounts={TOKEN: UINT256_MAX}).evaluate(
            token_intent(ActionType.APPROVE_TOKEN, amount_base_units=UINT256_MAX)
        )
        assert decision.reasons == (PolicyReason.UNLIMITED_APPROVAL_DENIED,)

    def test_unlimited_approval_may_be_explicitly_enabled(self):
        decision = policy(
            max_approval_amounts={TOKEN: UINT256_MAX},
            deny_unlimited_approval=False,
        ).evaluate(
            token_intent(ActionType.APPROVE_TOKEN, amount_base_units=UINT256_MAX)
        )
        assert decision.allowed

    def test_collects_all_reasons_in_stable_order(self):
        intent = TransactionIntent(
            chain=Chain.ARBITRUM,
            action=ActionType.APPROVE_TOKEN,
            sender=SENDER,
            recipient=RECIPIENT,
            token=OTHER,
            amount_base_units=UINT256_MAX,
            native_value_wei=101,
        )
        decision = policy(allowed_actions={ActionType.TRANSFER_NATIVE}).evaluate(intent)
        assert decision.reasons == (
            PolicyReason.CHAIN_NOT_ALLOWED,
            PolicyReason.ACTION_NOT_ALLOWED,
            PolicyReason.TOKEN_NOT_ALLOWED,
            PolicyReason.NATIVE_VALUE_EXCEEDED,
            PolicyReason.APPROVAL_LIMIT_NOT_CONFIGURED,
            PolicyReason.UNLIMITED_APPROVAL_DENIED,
        )
        assert decision.primary_reason == PolicyReason.CHAIN_NOT_ALLOWED
        assert decision.has_reason(PolicyReason.UNLIMITED_APPROVAL_DENIED)


class TestPolicyConfiguration:
    def test_source_collections_are_copied(self):
        chains = {Chain.BASE}
        actions = {ActionType.TRANSFER_NATIVE}
        contracts = {CONTRACT}
        tokens = {TOKEN}
        token_limits = {TOKEN: 10}
        configured = policy(
            allowed_chains=chains,
            allowed_actions=actions,
            allowed_contracts=contracts,
            allowed_tokens=tokens,
            max_token_amounts=token_limits,
        )

        chains.add(Chain.ETHEREUM)
        actions.add(ActionType.SWAP)
        contracts.add(OTHER)
        tokens.add(OTHER)
        token_limits[TOKEN] = 999

        assert configured.allowed_chains == frozenset({Chain.BASE})
        assert configured.allowed_actions == frozenset({ActionType.TRANSFER_NATIVE})
        assert configured.allowed_contracts == frozenset({CONTRACT})
        assert configured.allowed_tokens == frozenset({TOKEN})
        assert configured.max_token_amounts[TOKEN] == 10

    def test_addresses_are_normalized(self):
        mixed = "0xAbCdEfabcdefABCDefABcdefAbcDEfAbCdEfABcD"
        configured = policy(
            allowed_contracts={mixed},
            allowed_tokens={mixed},
            max_token_amounts={mixed: 1},
            max_approval_amounts={mixed: 1},
        )
        normalized = mixed.lower()
        assert configured.allowed_contracts == frozenset({normalized})
        assert configured.allowed_tokens == frozenset({normalized})
        assert configured.max_token_amounts[normalized] == 1

    @pytest.mark.parametrize("field", ["allowed_chains", "allowed_actions"])
    def test_typed_allowlists_reject_strings(self, field):
        with pytest.raises(InvalidPolicyAllowlistError):
            policy(**{field: {"base"}})

    @pytest.mark.parametrize("field", ["allowed_contracts", "allowed_tokens"])
    @pytest.mark.parametrize("value", [{"bad"}, "bad", {123}])
    def test_address_allowlists_reject_invalid_values(self, field, value):
        with pytest.raises(InvalidPolicyAllowlistError):
            policy(**{field: value})

    @pytest.mark.parametrize(
        "field", ["max_native_value_wei", "max_token_amounts", "max_approval_amounts"]
    )
    @pytest.mark.parametrize("value", [-1, 1.5, "1", True, False, None])
    def test_limits_reject_non_base_unit_values(self, field, value):
        configured_value = value if field == "max_native_value_wei" else {TOKEN: value}
        with pytest.raises(InvalidPolicyLimitError):
            policy(**{field: configured_value})

    @pytest.mark.parametrize("field", ["max_token_amounts", "max_approval_amounts"])
    def test_limit_maps_reject_invalid_addresses(self, field):
        with pytest.raises(InvalidPolicyAllowlistError):
            policy(**{field: {"bad": 1}})

    def test_duplicate_normalized_limit_addresses_are_rejected(self):
        mixed = "0xAbCdEfabcdefABCDefABcdefAbcDEfAbCdEfABcD"
        with pytest.raises(InvalidPolicyLimitError, match="duplicate normalized"):
            policy(max_token_amounts={mixed: 1, mixed.lower(): 2})

    @pytest.mark.parametrize(
        "field", ["deny_unlimited_approval", "require_confirmation"]
    )
    def test_boolean_configuration_is_strict(self, field):
        with pytest.raises(InvalidPolicyError):
            policy(**{field: 1})

    def test_policy_is_frozen(self):
        configured = policy()
        with pytest.raises(FrozenInstanceError):
            configured.max_native_value_wei = 1  # type: ignore[misc]
        with pytest.raises(TypeError):
            configured.max_token_amounts[TOKEN] = 1  # type: ignore[index]

    def test_evaluate_requires_intent(self):
        with pytest.raises(InvalidPolicyError, match="TransactionIntent"):
            policy().evaluate(object())


class TestPolicyDecisionValidation:
    def test_denied_decision_requires_reason(self):
        with pytest.raises(InvalidPolicyError, match="requires at least one"):
            PolicyDecision(False, (), "intent")

    def test_allowed_decision_rejects_reasons(self):
        with pytest.raises(InvalidPolicyError, match="cannot contain"):
            PolicyDecision(True, (PolicyReason.CHAIN_NOT_ALLOWED,), "intent")

    def test_duplicate_reasons_are_rejected(self):
        with pytest.raises(InvalidPolicyError, match="duplicates"):
            PolicyDecision(
                False,
                (PolicyReason.CHAIN_NOT_ALLOWED, PolicyReason.CHAIN_NOT_ALLOWED),
                "intent",
            )

    @pytest.mark.parametrize("intent_id", ["", None, 123])
    def test_intent_id_is_required(self, intent_id):
        with pytest.raises(InvalidPolicyError):
            PolicyDecision(True, (), intent_id)
