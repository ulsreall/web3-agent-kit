"""Table-driven tests for envelope field canonicalization.

The envelope is what the signature commits to. Two transactions that describe
the same call must hash identically, and any transaction that describes the
call *ambiguously* must be rejected rather than guessed at. These tests pin
each branch of the canonicalizers directly, because a regression there is
invisible: the gate still signs, it just signs something else than the
principal authorized.

Branches covered:

* integer fields accept ``int``, hex strings and decimal strings, and reject
  bools, negatives, garbage and unsupported types
* address fields are lower-cased and reject short, long, non-hex and
  non-string values
* calldata is normalized from bytes-likes and hex, and rejects non-0x strings
* creation (``to`` absent) is valid only with non-empty init code
* aliased fee fields (``gas``/``gasLimit``) must agree
* a v2 envelope needs gas, and exactly one of gasPrice or both EIP-1559 caps
"""

from __future__ import annotations

import pytest

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import CallEnvelopeV1, CallEnvelopeV2
from web3_agent_kit.execution.envelope import CallEnvelopeError

ROUTER = "0x94cc0aac535ccdb3c01d6787d6413c739ae12bc4"
SENDER = "0x9965507d1a55bcc2695c58ba16fb37d819b0a4dc"
CALLDATA = bytes.fromhex("deadbeef")


def _tx(**overrides) -> dict:
    tx = {
        "to": ROUTER,
        "from": SENDER,
        "data": CALLDATA,
        "value": 0,
        "nonce": 265,
        "chainId": 8453,
        "gas": 300_000,
        "gasPrice": 10**9,
    }
    tx.update(overrides)
    return tx


class TestIntegerCanonicalization:
    """`chainId`, `nonce` and `value` share one canonicalizer."""

    @pytest.mark.parametrize(
        ("field", "value", "expected"),
        [
            ("nonce", 7, 7),
            ("nonce", "7", 7),
            ("nonce", "0x7", 7),
            ("nonce", " 0x07 ", 7),
            ("value", "0X1f", 31),
            ("value", 0, 0),
        ],
    )
    def test_accepts_int_hex_and_decimal(self, field, value, expected):
        envelope = CallEnvelopeV1.from_transaction(
            transaction=_tx(**{field: value}), chain=Chain.BASE
        )
        attr = "native_value" if field == "value" else field
        assert getattr(envelope, attr) == expected

    @pytest.mark.parametrize("value", [True, False])
    def test_rejects_bool(self, value):
        # True is 1 in Python; reading it as a nonce would silently accept a
        # JSON `true` where an integer belongs.
        with pytest.raises(CallEnvelopeError, match="must be an integer, not a boolean"):
            CallEnvelopeV1.from_transaction(transaction=_tx(nonce=value), chain=Chain.BASE)

    def test_rejects_negative(self):
        with pytest.raises(CallEnvelopeError, match="cannot be negative"):
            CallEnvelopeV1.from_transaction(transaction=_tx(nonce=-1), chain=Chain.BASE)

    def test_rejects_invalid_hex(self):
        with pytest.raises(CallEnvelopeError, match="not valid hexadecimal"):
            CallEnvelopeV1.from_transaction(transaction=_tx(nonce="0xzz"), chain=Chain.BASE)

    def test_rejects_invalid_decimal(self):
        with pytest.raises(CallEnvelopeError, match="not a decimal integer"):
            CallEnvelopeV1.from_transaction(transaction=_tx(value="12abc"), chain=Chain.BASE)

    def test_rejects_unsupported_type(self):
        with pytest.raises(CallEnvelopeError, match="must be an int or a numeric string"):
            CallEnvelopeV1.from_transaction(transaction=_tx(value=1.5), chain=Chain.BASE)

    def test_chain_id_is_canonicalized_before_comparison(self):
        # Hex chain IDs are common in raw provider payloads; they must resolve
        # to the same chain rather than fail the mismatch check.
        envelope = CallEnvelopeV1.from_transaction(
            transaction=_tx(chainId="0x2105"), chain=Chain.BASE
        )
        assert envelope.chain_id == 8453


class TestAddressCanonicalization:
    @pytest.mark.parametrize(
        ("field", "value", "expected_attr"),
        [
            ("to", ROUTER.upper().replace("0X", "0x"), "target"),
            ("from", SENDER.upper().replace("0X", "0x"), "executor"),
        ],
    )
    def test_lowercases(self, field, value, expected_attr):
        envelope = CallEnvelopeV1.from_transaction(
            transaction=_tx(**{field: value}), chain=Chain.BASE
        )
        assert getattr(envelope, expected_attr) == getattr(envelope, expected_attr).lower()
        assert getattr(envelope, expected_attr) is not None

    @pytest.mark.parametrize(
        "value",
        [
            "0x1234",  # short
            ROUTER + "00",  # long
            "0x" + "z" * 40,  # not hex
            ROUTER[2:],  # no 0x prefix
            b"\x00" * 20,  # bytes, not str
            12345,
        ],
    )
    def test_rejects_malformed_target(self, value):
        with pytest.raises(CallEnvelopeError, match="20-byte 0x-prefixed EVM address"):
            CallEnvelopeV1.from_transaction(transaction=_tx(to=value), chain=Chain.BASE)

    def test_rejects_malformed_sender(self):
        with pytest.raises(CallEnvelopeError, match="20-byte 0x-prefixed EVM address"):
            CallEnvelopeV1.from_transaction(transaction=_tx(**{"from": "0x00"}), chain=Chain.BASE)


class TestCalldata:
    def test_absent_and_empty_hex_hash_alike(self):
        absent = CallEnvelopeV1.from_transaction(
            transaction={k: v for k, v in _tx().items() if k != "data"}, chain=Chain.BASE
        )
        empty = CallEnvelopeV1.from_transaction(transaction=_tx(data="0x"), chain=Chain.BASE)
        assert absent.digest() == empty.digest()

    @pytest.mark.parametrize("value", [bytearray(b"\xde\xad"), memoryview(b"\xde\xad")])
    def test_accepts_bytes_likes(self, value):
        envelope = CallEnvelopeV1.from_transaction(transaction=_tx(data=value), chain=Chain.BASE)
        assert envelope.calldata == b"\xde\xad"

    def test_input_is_an_alias_of_data(self):
        aliased = CallEnvelopeV1.from_transaction(
            transaction={k: v for k, v in _tx().items() if k != "data"} | {"input": "0xdeadbeef"},
            chain=Chain.BASE,
        )
        assert (
            aliased.digest()
            == CallEnvelopeV1.from_transaction(transaction=_tx(), chain=Chain.BASE).digest()
        )

    def test_rejects_non_hex_string(self):
        with pytest.raises(CallEnvelopeError, match="must start with 0x"):
            CallEnvelopeV1.from_transaction(transaction=_tx(data="deadbeef"), chain=Chain.BASE)

    def test_rejects_odd_length_hex(self):
        with pytest.raises(CallEnvelopeError, match="not valid hexadecimal"):
            CallEnvelopeV1.from_transaction(transaction=_tx(data="0xabc"), chain=Chain.BASE)

    def test_rejects_unsupported_type(self):
        with pytest.raises(CallEnvelopeError, match="must be bytes or a 0x-prefixed hex string"):
            CallEnvelopeV1.from_transaction(transaction=_tx(data=42), chain=Chain.BASE)


class TestCreationProfile:
    def test_creation_requires_init_code(self):
        with pytest.raises(CallEnvelopeError, match="requires init code"):
            CallEnvelopeV1.from_transaction(transaction=_tx(to=None, data="0x"), chain=Chain.BASE)

    def test_creation_with_init_code_is_valid(self):
        envelope = CallEnvelopeV1.from_transaction(
            transaction=_tx(to=None, data="0x6080"), chain=Chain.BASE
        )
        assert envelope.target is None
        assert envelope.execution_profile == "create"

    def test_zero_address_target_is_a_call_not_a_creation(self):
        envelope = CallEnvelopeV1.from_transaction(
            transaction=_tx(to="0x" + "00" * 20), chain=Chain.BASE
        )
        assert envelope.target == "0x" + "00" * 20
        assert envelope.execution_profile == "call"

    def test_nonpositive_chain_id_rejected(self):
        with pytest.raises(CallEnvelopeError, match="positive EIP-155 chain ID"):
            CallEnvelopeV1(chain_id=0, executor=SENDER, nonce=0, calldata=CALLDATA, native_value=0)


class TestFeeFields:
    def test_conflicting_gas_aliases_rejected(self):
        with pytest.raises(CallEnvelopeError, match="conflicting values for gasLimit"):
            CallEnvelopeV2.from_transaction(transaction=_tx(gasLimit=1), chain=Chain.BASE)

    def test_agreeing_gas_aliases_are_accepted(self):
        envelope = CallEnvelopeV2.from_transaction(
            transaction=_tx(gasLimit=300_000), chain=Chain.BASE
        )
        assert envelope.gas_limit == 300_000

    def test_gas_limit_required(self):
        transaction = {k: v for k, v in _tx().items() if k != "gas"}
        with pytest.raises(CallEnvelopeError, match="missing gas or gasLimit"):
            CallEnvelopeV2.from_transaction(transaction=transaction, chain=Chain.BASE)

    def test_mixing_gas_price_with_eip1559_rejected(self):
        with pytest.raises(CallEnvelopeError, match="cannot mix gasPrice"):
            CallEnvelopeV2.from_transaction(
                transaction=_tx(maxFeePerGas=2, maxPriorityFeePerGas=1), chain=Chain.BASE
            )

    def test_half_of_the_eip1559_pair_rejected(self):
        transaction = {k: v for k, v in _tx().items() if k != "gasPrice"}
        with pytest.raises(CallEnvelopeError, match="requires gasPrice or both"):
            CallEnvelopeV2.from_transaction(
                transaction=transaction | {"maxFeePerGas": 2}, chain=Chain.BASE
            )

    def test_full_eip1559_pair_accepted(self):
        transaction = {k: v for k, v in _tx().items() if k != "gasPrice"}
        envelope = CallEnvelopeV2.from_transaction(
            transaction=transaction | {"maxFeePerGas": 2, "maxPriorityFeePerGas": 1},
            chain=Chain.BASE,
        )
        assert envelope.max_fee_per_gas == 2
        assert envelope.gas_price is None

    @pytest.mark.parametrize(
        "field", ["gas_limit", "gas_price", "max_fee_per_gas", "max_priority_fee_per_gas"]
    )
    def test_non_negative_integer_fields(self, field):
        # bools pass `isinstance(int)` and would read as 0 or 1, so each field is
        # checked explicitly. Every field is populated so the fee-consistency
        # check cannot mask the per-field one.
        kwargs = {
            "gas_limit": 1,
            "gas_price": 1,
            "max_fee_per_gas": None,
            "max_priority_fee_per_gas": None,
        }
        kwargs[field] = True
        if field in ("max_fee_per_gas", "max_priority_fee_per_gas"):
            kwargs["gas_price"] = None
            kwargs["max_fee_per_gas"] = kwargs["max_fee_per_gas"] or 1
            kwargs["max_priority_fee_per_gas"] = kwargs["max_priority_fee_per_gas"] or 1
            kwargs[field] = True
        with pytest.raises(CallEnvelopeError, match="non-negative integer"):
            CallEnvelopeV2(
                chain_id=8453,
                executor=SENDER,
                nonce=0,
                calldata=CALLDATA,
                native_value=0,
                target=ROUTER,
                **kwargs,
            )

    def test_negative_fee_rejected(self):
        with pytest.raises(CallEnvelopeError, match="non-negative integer"):
            CallEnvelopeV2(
                chain_id=8453,
                executor=SENDER,
                nonce=0,
                calldata=CALLDATA,
                native_value=0,
                target=ROUTER,
                gas_limit=-1,
            )


class TestMappingValidation:
    def test_non_mapping_rejected(self):
        with pytest.raises(CallEnvelopeError, match="must be a mapping"):
            CallEnvelopeV1.from_transaction(transaction=["not", "a", "mapping"], chain=Chain.BASE)

    def test_missing_chain_id_rejected(self):
        transaction = {k: v for k, v in _tx().items() if k != "chainId"}
        with pytest.raises(CallEnvelopeError, match="missing chainId"):
            CallEnvelopeV1.from_transaction(transaction=transaction, chain=Chain.BASE)

    def test_missing_sender_rejected(self):
        transaction = {k: v for k, v in _tx().items() if k != "from"}
        with pytest.raises(CallEnvelopeError, match="missing from"):
            CallEnvelopeV1.from_transaction(transaction=transaction, chain=Chain.BASE)


class TestCalldataAliasConflict:
    def test_conflicting_data_and_input_rejected(self):
        # A custom signer may read `input` while the envelope committed to
        # `data`; disagreement must not be resolved by picking one.
        with pytest.raises(CallEnvelopeError, match="conflicting data and input"):
            CallEnvelopeV1.from_transaction(transaction=_tx(input="0xfeedface"), chain=Chain.BASE)

    def test_agreeing_data_and_input_accepted(self):
        envelope = CallEnvelopeV1.from_transaction(
            transaction=_tx(input="0xdeadbeef"), chain=Chain.BASE
        )
        assert envelope.calldata == CALLDATA

    def test_normalize_calldata_key_moves_input_to_data(self):
        from web3_agent_kit.execution.envelope import normalize_calldata_key

        normalized = normalize_calldata_key({"to": ROUTER, "input": "0xdeadbeef"})
        assert "input" not in normalized
        assert normalized["data"] == CALLDATA

    def test_normalize_calldata_key_leaves_data_alone(self):
        from web3_agent_kit.execution.envelope import normalize_calldata_key

        transaction = {"to": ROUTER, "data": CALLDATA}
        assert normalize_calldata_key(transaction)["data"] == CALLDATA


class TestCommitmentContext:
    def _commitment(self):
        from web3_agent_kit.execution.envelope import PolicyDecisionCommitment

        return PolicyDecisionCommitment(
            call_identity="abc",
            policy_id="policy-1",
            verdict="allow",
            reason_codes=("OK",),
            evaluated_at=1758000000,
        )

    def test_context_commitment_names_the_algorithm(self):
        context = self._commitment().as_context_commitment()
        assert context["algorithm"] == "sha256"
        assert context["namespace"] == self._commitment().schema
        assert context["digest"] == self._commitment().digest()

    def test_commitment_digest_is_domain_separated_from_envelope(self):
        envelope = CallEnvelopeV1.from_transaction(transaction=_tx(), chain=Chain.BASE)
        assert self._commitment().digest() != envelope.digest()

    def test_reason_order_changes_the_digest(self):
        from web3_agent_kit.execution.envelope import PolicyDecisionCommitment

        base = dict(
            call_identity="abc",
            policy_id="policy-1",
            verdict="deny",
            evaluated_at=1758000000,
        )
        first = PolicyDecisionCommitment(reason_codes=("A", "B"), **base)
        second = PolicyDecisionCommitment(reason_codes=("B", "A"), **base)
        assert first.digest() != second.digest()


class TestChainResolution:
    def test_non_chain_rejected(self):
        with pytest.raises(CallEnvelopeError, match="must be a Chain enum member"):
            CallEnvelopeV1.from_transaction(transaction=_tx(), chain="base")

    def test_non_evm_chain_rejected(self):
        with pytest.raises(CallEnvelopeError, match="has no EIP-155 chain ID"):
            CallEnvelopeV1.from_transaction(transaction=_tx(), chain=Chain.SOLANA)


class TestChainMismatch:
    def test_mismatch_names_both_chains(self):
        with pytest.raises(CallEnvelopeError, match="chain mismatch"):
            CallEnvelopeV1.from_transaction(transaction=_tx(chainId=84532), chain=Chain.BASE)


class TestSchemaAndDigest:
    def test_v1_schema_and_domain(self):
        envelope = CallEnvelopeV1.from_transaction(transaction=_tx(), chain=Chain.BASE)
        assert envelope.schema.endswith(".v1")
        assert envelope.digest() == envelope.digest()

    def test_v2_schema_differs_from_v1(self):
        v1 = CallEnvelopeV1.from_transaction(transaction=_tx(), chain=Chain.BASE)
        v2 = CallEnvelopeV2.from_transaction(transaction=_tx(), chain=Chain.BASE)
        assert v2.schema != v1.schema

    def test_v2_digest_is_domain_separated_from_v1(self):
        # Same call, same fields: only the domain prefix differs, so a v1 digest
        # can never be replayed as a v2 commitment.
        v1 = CallEnvelopeV1.from_transaction(transaction=_tx(), chain=Chain.BASE)
        v2 = CallEnvelopeV2.from_transaction(transaction=_tx(), chain=Chain.BASE)
        assert v2.digest() != v1.digest()

    def test_v2_payload_states_the_fees_it_commits_to(self):
        transaction = {k: v for k, v in _tx().items() if k != "gasPrice"}
        envelope = CallEnvelopeV2.from_transaction(
            transaction=transaction | {"maxFeePerGas": 2, "maxPriorityFeePerGas": 1},
            chain=Chain.BASE,
        )
        payload = envelope.to_payload()
        assert payload["gasPrice"] is None
        assert payload["maxFeePerGas"] == "2"
        assert payload["maxPriorityFeePerGas"] == "1"
        assert payload["executionProfile"] == "call"

    def test_creation_payload_omits_target(self):
        envelope = CallEnvelopeV2.from_transaction(
            transaction=_tx(to=None, data="0x6080"), chain=Chain.BASE
        )
        assert "target" not in envelope.to_payload()
        assert envelope.to_payload()["executionProfile"] == "create"
