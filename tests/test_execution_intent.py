"""Offline tests for immutable transaction intents."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import (
    ActionType,
    InvalidAddressError,
    InvalidAmountError,
    InvalidCalldataError,
    InvalidIntentError,
    InvalidMetadataError,
    TransactionIntent,
    UnsupportedActionError,
    UnsupportedChainError,
)

SENDER = "0x1111111111111111111111111111111111111111"
RECIPIENT = "0x2222222222222222222222222222222222222222"
CONTRACT = "0x3333333333333333333333333333333333333333"
TOKEN = "0x4444444444444444444444444444444444444444"


def native_intent(**overrides) -> TransactionIntent:
    values = {
        "chain": Chain.BASE,
        "action": ActionType.TRANSFER_NATIVE,
        "sender": SENDER,
        "recipient": RECIPIENT,
        "native_value_wei": 10**18,
    }
    values.update(overrides)
    return TransactionIntent(**values)


class TestValidIntents:
    def test_native_transfer(self):
        intent = native_intent()
        assert intent.chain == Chain.BASE
        assert intent.native_value_wei == 10**18
        assert intent.recipient == RECIPIENT

    def test_token_transfer(self):
        intent = TransactionIntent(
            chain=Chain.ETHEREUM,
            action=ActionType.TRANSFER_TOKEN,
            sender=SENDER,
            recipient=RECIPIENT,
            token=TOKEN,
            amount_base_units=1_000_000,
            calldata=b"transfer",
        )
        assert intent.amount_base_units == 1_000_000

    def test_token_approval(self):
        intent = TransactionIntent(
            chain=Chain.ETHEREUM,
            action=ActionType.APPROVE_TOKEN,
            sender=SENDER,
            recipient=RECIPIENT,
            token=TOKEN,
            amount_base_units=500,
            calldata=b"approve",
        )
        assert intent.recipient == RECIPIENT
        assert intent.token == TOKEN

    @pytest.mark.parametrize(
        "action",
        [
            ActionType.CONTRACT_CALL,
            ActionType.SWAP,
            ActionType.BRIDGE,
            ActionType.STAKE,
            ActionType.UNSTAKE,
            ActionType.GOVERNANCE,
        ],
    )
    def test_contract_actions(self, action):
        intent = TransactionIntent(
            chain=Chain.ARBITRUM,
            action=action,
            sender=SENDER,
            contract=CONTRACT,
            calldata=b"\x12\x34",
        )
        assert intent.contract == CONTRACT

    def test_addresses_are_normalized_for_stable_comparison(self):
        mixed = "0xAbCdEfabcdefABCDefABcdefAbcDEfAbCdEfABcD"
        intent = native_intent(sender=mixed)
        assert intent.sender == mixed.lower()


class TestValidation:
    @pytest.mark.parametrize("sender", [None, "", "0x1234", "not-an-address", 123])
    def test_invalid_sender(self, sender):
        with pytest.raises(InvalidAddressError):
            native_intent(sender=sender)

    def test_native_transfer_requires_recipient(self):
        with pytest.raises(InvalidAddressError, match="recipient is required"):
            native_intent(recipient=None)

    @pytest.mark.parametrize("field", ["recipient", "token"])
    def test_token_transfer_requires_recipient_and_token(self, field):
        values = {
            "chain": Chain.ETHEREUM,
            "action": ActionType.TRANSFER_TOKEN,
            "sender": SENDER,
            "recipient": RECIPIENT,
            "token": TOKEN,
        }
        values[field] = None
        with pytest.raises(InvalidAddressError):
            TransactionIntent(**values)

    @pytest.mark.parametrize("field", ["recipient", "token"])
    def test_approval_requires_spender_and_token(self, field):
        values = {
            "chain": Chain.ETHEREUM,
            "action": ActionType.APPROVE_TOKEN,
            "sender": SENDER,
            "recipient": RECIPIENT,
            "token": TOKEN,
        }
        values[field] = None
        with pytest.raises(InvalidAddressError):
            TransactionIntent(**values)

    def test_contract_action_requires_contract(self):
        with pytest.raises(InvalidAddressError, match="contract is required"):
            TransactionIntent(
                chain=Chain.BASE,
                action=ActionType.CONTRACT_CALL,
                sender=SENDER,
            )

    @pytest.mark.parametrize("value", [-1, -10**30, 1.5, "1", True, False, None])
    @pytest.mark.parametrize("field", ["amount_base_units", "native_value_wei"])
    def test_amounts_must_be_non_negative_base_unit_integers(self, field, value):
        with pytest.raises(InvalidAmountError):
            native_intent(**{field: value})

    @pytest.mark.parametrize("calldata", ["0x1234", bytearray(b"x"), 123, None])
    def test_calldata_must_be_bytes(self, calldata):
        with pytest.raises(InvalidCalldataError):
            native_intent(calldata=calldata)

    def test_action_must_be_enum(self):
        with pytest.raises(UnsupportedActionError):
            native_intent(action="transfer_native")

    def test_chain_must_be_enum(self):
        with pytest.raises(UnsupportedChainError):
            native_intent(chain="base")

    def test_solana_requires_a_future_chain_specific_intent(self):
        with pytest.raises(UnsupportedChainError, match="EVM chains only"):
            native_intent(chain=Chain.SOLANA)


class TestImmutability:
    def test_intent_fields_are_frozen(self):
        intent = native_intent()
        with pytest.raises(FrozenInstanceError):
            intent.native_value_wei = 2  # type: ignore[misc]

    def test_metadata_is_copied_and_recursively_frozen(self):
        source = {"labels": ["safe"], "nested": {"attempt": 1}}
        intent = native_intent(metadata=source)
        source["labels"].append("mutated")
        source["nested"]["attempt"] = 2

        assert intent.metadata["labels"] == ("safe",)
        assert intent.metadata["nested"]["attempt"] == 1
        with pytest.raises(TypeError):
            intent.metadata["new"] = "value"  # type: ignore[index]
        with pytest.raises(TypeError):
            intent.metadata["nested"]["attempt"] = 3  # type: ignore[index]

    def test_metadata_keys_must_be_strings(self):
        with pytest.raises(InvalidMetadataError, match="keys must be strings"):
            native_intent(metadata={1: "value"})

    def test_metadata_rejects_arbitrary_objects(self):
        with pytest.raises(InvalidMetadataError, match="unsupported metadata"):
            native_intent(metadata={"object": object()})


class TestIntentId:
    def test_id_is_stable_sha256_hex(self):
        first = native_intent()
        second = native_intent()
        assert first.intent_id == second.intent_id
        assert len(first.intent_id) == 64
        int(first.intent_id, 16)

    def test_metadata_does_not_change_id(self):
        assert native_intent(metadata={"label": "a"}).intent_id == native_intent(
            metadata={"label": "b"}
        ).intent_id

    @pytest.mark.parametrize(
        "override",
        [
            {"chain": Chain.ARBITRUM},
            {"recipient": CONTRACT},
            {"native_value_wei": 2},
            {"calldata": b"different"},
        ],
    )
    def test_security_fields_change_id(self, override):
        assert native_intent().intent_id != native_intent(**override).intent_id


class TestEvmConversion:
    def test_from_native_transaction(self):
        intent = TransactionIntent.from_evm_transaction(
            chain=Chain.BASE,
            action=ActionType.TRANSFER_NATIVE,
            transaction={
                "from": SENDER,
                "to": RECIPIENT,
                "value": 123,
                "data": "0x1234",
            },
        )
        assert intent.native_value_wei == 123
        assert intent.calldata == b"\x12\x34"

    def test_contract_call_round_trip(self):
        tx = {"from": SENDER, "to": CONTRACT, "value": 7, "data": b"\xab\xcd"}
        intent = TransactionIntent.from_evm_transaction(
            chain=Chain.ETHEREUM,
            action=ActionType.CONTRACT_CALL,
            transaction=tx,
        )
        assert intent.to_evm_transaction() == tx

    @pytest.mark.parametrize("data", ["1234", "0xzz", 123])
    def test_invalid_transaction_calldata(self, data):
        with pytest.raises(InvalidCalldataError):
            TransactionIntent.from_evm_transaction(
                chain=Chain.BASE,
                action=ActionType.CONTRACT_CALL,
                transaction={"from": SENDER, "to": CONTRACT, "data": data},
            )

    @pytest.mark.parametrize(
        "action", [ActionType.TRANSFER_TOKEN, ActionType.APPROVE_TOKEN]
    )
    def test_encoded_token_actions_require_semantic_decoding(self, action):
        with pytest.raises(InvalidIntentError, match="decoded semantic fields"):
            TransactionIntent.from_evm_transaction(
                chain=Chain.BASE,
                action=action,
                transaction={"from": SENDER, "to": TOKEN, "data": b"encoded"},
            )

    def test_transaction_must_be_mapping(self):
        with pytest.raises(InvalidIntentError, match="must be a mapping"):
            TransactionIntent.from_evm_transaction(
                chain=Chain.BASE,
                action=ActionType.CONTRACT_CALL,
                transaction=[],
            )
