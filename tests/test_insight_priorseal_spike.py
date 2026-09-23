"""Acceptance tests for the bounded WAK / Insight / PriorSeal spike."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import fields
from pathlib import Path
from unittest.mock import patch

import pytest

from examples.insight_priorseal_swap import (
    BoundaryCounters,
    ExecutionBoundaries,
    _run_gate_attempt,
    run_negative_suite,
    synthetic_execution_boundaries,
    validate_extended_n5b_evidence,
    write_acceptance_report,
)
from examples.support.insight_priorseal_boundary import (
    BoundaryError,
    FixtureBundle,
    PriorSealAuthorizationProvider,
    SQLiteAcceptanceStore,
    _chain_id,
    _js_number,
    _js_string,
    _normalize_priorseal_intent,
    _positive_time,
    _protocol_id,
    _uint_string,
    _verify_priorseal_authorization,
    verify_insight_attestation,
)
from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import (
    AuthorizationDenied,
    AuthorizationEvidence,
    AuthorizationRequest,
)
from web3_agent_kit.execution.intent import ActionType

FIXTURE = Path(__file__).parent / "fixtures" / "insight_priorseal_spike" / "v1"


def test_priorseal_positive_time_enforces_javascript_safe_integer_boundary() -> None:
    assert _positive_time(9_007_199_254_740_991, "validUntil") == 9_007_199_254_740_991
    with pytest.raises(AuthorizationDenied, match="positive Unix timestamp"):
        _positive_time(9_007_199_254_740_992, "validUntil")


def test_priorseal_positive_time_normalizes_numeric_strings_like_javascript() -> None:
    assert _positive_time("1789639380", "validUntil") == 1_789_639_380
    assert _positive_time("1.78963938e9", "validUntil") == 1_789_639_380


def test_priorseal_uses_javascript_string_coercion_for_signed_values() -> None:
    assert _uint_string(1.0, "amount") == "1"
    assert _protocol_id(True, "principal.id") == "true"
    assert _protocol_id(1.0, "delegate.agentId") == "1"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.2345678901234567, "1.2345678901234567"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (1e-6, "0.000001"),
        (1e-7, "1e-7"),
        (1000000000000000100.0, "1000000000000000100"),
    ],
)
def test_javascript_string_number_formatting(value: float, expected: str) -> None:
    assert _js_string(value) == expected


@pytest.mark.parametrize("value", ["+0x10", "-0x10", "+0b10", "-0o10"])
def test_javascript_number_rejects_sign_prefixed_radix_strings(value: str) -> None:
    assert _js_number(value) is None


def test_priorseal_chain_ids_use_verifier_numeric_and_eip155_normalization() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    intent = copy.deepcopy(bundle.baseline["priorSeal"]["authorization"]["intent"])
    intent.pop("intentHash")
    intent["chainIds"] = ["84532", "eip155:8453"]

    normalized = _normalize_priorseal_intent(intent)

    assert normalized["chainIds"] == [84532, 8453]
    assert normalized["intentHash"] == (
        "8fb4bf97c2a3456ee099b0614f2761463e93df57568b9b271ef5f644710cd729"
    )


def test_priorseal_chain_id_enforces_javascript_safe_integer_boundary() -> None:
    assert _chain_id(9_007_199_254_740_991) == 9_007_199_254_740_991
    with pytest.raises(AuthorizationDenied, match="chainId"):
        _chain_id(9_007_199_254_740_992)


def test_priorseal_rejects_malformed_min_confirmations_before_hashing() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    intent = copy.deepcopy(bundle.baseline["priorSeal"]["authorization"]["intent"])
    intent.pop("intentHash")
    intent["constraints"] = {"minConfirmations": {"bad": True}}

    with pytest.raises(AuthorizationDenied, match="minConfirmations"):
        _normalize_priorseal_intent(intent)


def test_priorseal_does_not_default_an_explicit_empty_intent_schema() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    intent = copy.deepcopy(bundle.baseline["priorSeal"]["authorization"]["intent"])
    intent.pop("intentHash")
    intent["schema"] = ""

    with pytest.raises(AuthorizationDenied, match="intent schema"):
        _normalize_priorseal_intent(intent)


def test_context_namespace_distinguishes_missing_from_explicit_null() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    missing = copy.deepcopy(bundle.baseline["priorSeal"]["authorization"]["intent"])
    missing.pop("intentHash")
    missing["contextCommitments"][0].pop("namespace")
    explicit_null = copy.deepcopy(missing)
    explicit_null["contextCommitments"][0]["namespace"] = None

    normalized_missing = _normalize_priorseal_intent(missing)
    normalized_null = _normalize_priorseal_intent(explicit_null)

    missing_namespaces = {
        item["namespace"] for item in normalized_missing["contextCommitments"]
    }
    null_namespaces = {
        item["namespace"] for item in normalized_null["contextCommitments"]
    }
    assert "undefined" in missing_namespaces
    assert "null" in null_namespaces
    assert normalized_missing["intentHash"] != normalized_null["intentHash"]


@pytest.mark.parametrize("nested_hash", ["", "bogus", False, None])
def test_authorization_strips_nested_intent_hash_like_pinned_verifier(
    nested_hash: object,
) -> None:
    bundle = FixtureBundle.load(FIXTURE)
    signed = copy.deepcopy(bundle.baseline["priorSeal"]["authorization"])
    signed["intent"]["intentHash"] = nested_hash

    normalized = _verify_priorseal_authorization(signed)

    assert normalized["intent_hash"] == signed["intentHash"]
    assert normalized["authorization_id"] == signed["authorizationId"]


def test_priorseal_preserves_valid_min_confirmations_form_in_signed_hash() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    intent = copy.deepcopy(bundle.baseline["priorSeal"]["authorization"]["intent"])
    intent.pop("intentHash")
    intent["constraints"] = {"minConfirmations": "12", "maxGasUsed": 21_000}

    normalized = _normalize_priorseal_intent(intent)

    assert normalized["constraints"] == {
        "minConfirmations": "12",
        "maxGasUsed": "21000",
    }
    assert normalized["intentHash"] == (
        "a1d5a11a140d1238ff61c1bfceba813d2fa556ee4919c8b0ed1ca8693b7ed08b"
    )

    intent["constraints"]["minConfirmations"] = 12.0
    normalized_number = _normalize_priorseal_intent(intent)
    assert normalized_number["constraints"]["minConfirmations"] == 12

    intent["constraints"]["minConfirmations"] = "0x10"
    normalized_hex_string = _normalize_priorseal_intent(intent)
    assert normalized_hex_string["constraints"]["minConfirmations"] == "0x10"


def _transaction(bundle: FixtureBundle) -> dict:
    transaction = dict(bundle.baseline["transaction"])
    transaction["chainId"] = int(transaction["chainId"])
    transaction["nonce"] = int(transaction["nonce"])
    transaction["value"] = int(transaction["value"])
    return transaction


def test_adapter_maps_priorseal_response_without_new_evidence_fields() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    baseline = bundle.baseline
    provider = PriorSealAuthorizationProvider(
        baseline["priorSeal"]["response"],
        trust_roots=bundle.trust_roots,
    )
    request = AuthorizationRequest(
        chain=Chain.BASE_SEPOLIA,
        action=ActionType.SWAP,
        transaction=baseline["transaction"],
    )
    envelope = request.envelope()

    evidence = provider.evidence_for(
        envelope=envelope,
        envelope_digest=envelope.digest(),
        policy_commitment_digest=baseline["wak"]["policyDecisionCommitment"]["digest"],
    )

    expected = baseline["priorSeal"]["expectedWakEvidence"]
    assert {field.name for field in fields(evidence)} == {
        field.name for field in fields(AuthorizationEvidence)
    }
    assert evidence.authorization_id == expected["authorization_id"]
    assert evidence.envelope_digest == expected["envelope_digest"]
    assert evidence.nonce == expected["nonce"]
    assert evidence.policy_commitment_digest == expected["policy_commitment_digest"]
    assert dict(evidence.raw) == expected["raw"]
    assert provider.calls == 1


def test_priorseal_authorization_signature_is_verified_fail_closed() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    response = copy.deepcopy(bundle.baseline["priorSeal"]["response"])
    response["signedAuthorization"]["signature"] = "0x00"
    provider = PriorSealAuthorizationProvider(response, trust_roots=bundle.trust_roots)
    request = AuthorizationRequest(
        chain=Chain.BASE_SEPOLIA,
        action=ActionType.SWAP,
        transaction=_transaction(bundle),
    )

    with pytest.raises(AuthorizationDenied, match="signature"):
        provider.evidence_for(
            envelope=request.envelope(),
            envelope_digest=request.envelope().digest(),
            policy_commitment_digest=bundle.baseline["wak"][
                "policyDecisionCommitment"
            ]["digest"],
        )


def test_priorseal_does_not_trust_claimed_verification_result() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    response = copy.deepcopy(bundle.baseline["priorSeal"]["response"])
    response["verificationResult"] = {"valid": False, "code": "UNTRUSTED_CLAIM"}
    provider = PriorSealAuthorizationProvider(response, trust_roots=bundle.trust_roots)
    request = AuthorizationRequest(
        chain=Chain.BASE_SEPOLIA,
        action=ActionType.SWAP,
        transaction=_transaction(bundle),
    )

    evidence = provider.evidence_for(
        envelope=request.envelope(),
        envelope_digest=request.envelope().digest(),
        policy_commitment_digest=bundle.baseline["wak"]["policyDecisionCommitment"][
            "digest"
        ],
    )

    assert evidence.authorization_id == response["authorization_id"]


def test_priorseal_hashes_the_normalized_allowlisted_authorization() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    response = copy.deepcopy(bundle.baseline["priorSeal"]["response"])
    signed = response["signedAuthorization"]
    signed["principal"]["account"] = signed["principal"]["account"].upper().replace("0X", "0x")
    signed["authorizer"]["address"] = signed["authorizer"]["address"].upper().replace("0X", "0x")
    signed["delegate"]["executor"] = signed["delegate"]["executor"].upper().replace("0X", "0x")
    signed["intent"]["sender"] = signed["intent"]["sender"].upper().replace("0X", "0x")
    signed["intent"]["recipient"] = signed["intent"]["recipient"].upper().replace("0X", "0x")
    signed["intent"]["callTarget"] = signed["intent"]["callTarget"].upper().replace("0X", "0x")
    signed["intent"]["calldataHash"] = signed["intent"]["calldataHash"].upper().replace("0X", "0x")
    signed["intent"]["contextCommitments"].reverse()
    provider = PriorSealAuthorizationProvider(response, trust_roots=bundle.trust_roots)
    request = AuthorizationRequest(
        chain=Chain.BASE_SEPOLIA,
        action=ActionType.SWAP,
        transaction=_transaction(bundle),
    )

    evidence = provider.evidence_for(
        envelope=request.envelope(),
        envelope_digest=request.envelope().digest(),
        policy_commitment_digest=bundle.baseline["wak"]["policyDecisionCommitment"][
            "digest"
        ],
    )

    assert evidence.authorization_id == response["authorization_id"]


def test_priorseal_v2_normalizes_defaultable_fields_before_verification() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    response = copy.deepcopy(bundle.baseline["priorSeal"]["response"])
    signed = response["signedAuthorization"]
    for field in (
        "schema",
        "domain",
        "authorizationId",
        "intentHash",
        "notBefore",
        "expiresAt",
        "maxUses",
        "audience",
        "policyHash",
    ):
        signed.pop(field)
    signed["intent"].pop("schema")
    signed["intent"].pop("intentHash")
    provider = PriorSealAuthorizationProvider(response, trust_roots=bundle.trust_roots)
    request = AuthorizationRequest(
        chain=Chain.BASE_SEPOLIA,
        action=ActionType.SWAP,
        transaction=_transaction(bundle),
    )

    evidence = provider.evidence_for(
        envelope=request.envelope(),
        envelope_digest=request.envelope().digest(),
        policy_commitment_digest=bundle.baseline["wak"]["policyDecisionCommitment"][
            "digest"
        ],
    )

    assert evidence.authorization_id == response["authorization_id"]


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("unknown_authorization", "unsupported field"),
        ("unknown_intent", "unsupported field"),
        ("intent_schema", "intent schema"),
        ("execution_profile", "execution profile"),
        ("max_uses", "maxUses"),
        ("audience", "audience"),
        ("timing", "time window"),
        ("authorizer_type", "authorizer type"),
    ],
)
def test_priorseal_v2_semantic_mutations_fail_closed_without_burn(
    case: str, message: str, tmp_path: Path
) -> None:
    bundle = FixtureBundle.load(FIXTURE)
    valid_response = bundle.baseline["priorSeal"]["response"]
    response = copy.deepcopy(valid_response)
    signed = response["signedAuthorization"]
    if case == "unknown_authorization":
        signed["unexpected"] = True
    elif case == "unknown_intent":
        signed["intent"]["unexpected"] = True
    elif case == "intent_schema":
        signed["intent"]["schema"] = "priorseal.intent.v1"
    elif case == "execution_profile":
        signed["intent"]["executionProfile"] = "wrong-profile"
    elif case == "max_uses":
        signed["maxUses"] = "2"
    elif case == "audience":
        signed["audience"] = "other"
    elif case == "timing":
        signed["notBefore"] = signed["issuedAt"] - 1
    elif case == "authorizer_type":
        signed["authorizer"]["type"] = "eip1271"
    database = tmp_path / f"{case}.sqlite3"
    request = AuthorizationRequest(
        chain=Chain.BASE_SEPOLIA,
        action=ActionType.SWAP,
        transaction=_transaction(bundle),
    )
    envelope = request.envelope()

    denied = PriorSealAuthorizationProvider(
        response,
        trust_roots=bundle.trust_roots,
        acceptance_store=SQLiteAcceptanceStore(database),
    )
    with pytest.raises(AuthorizationDenied, match=message):
        denied.evidence_for(
            envelope=envelope,
            envelope_digest=envelope.digest(),
            policy_commitment_digest=bundle.baseline["wak"][
                "policyDecisionCommitment"
            ]["digest"],
        )

    valid = PriorSealAuthorizationProvider(
        valid_response,
        trust_roots=bundle.trust_roots,
        acceptance_store=SQLiteAcceptanceStore(database),
    )
    with patch("web3_agent_kit.execution.authorization.time.time", return_value=1789639202):
        evidence = valid.evidence_for(
            envelope=envelope,
            envelope_digest=envelope.digest(),
            policy_commitment_digest=bundle.baseline["wak"][
                "policyDecisionCommitment"
            ]["digest"],
        )
    assert evidence.authorization_id == valid_response["authorization_id"]


def test_priorseal_acceptance_rejects_noncanonical_base64url_without_burn(
    tmp_path: Path,
) -> None:
    bundle = FixtureBundle.load(FIXTURE)
    valid_response = bundle.baseline["priorSeal"]["response"]
    response = copy.deepcopy(valid_response)
    response["acceptance"]["signature"] += "="
    database = tmp_path / "noncanonical.sqlite3"
    request = AuthorizationRequest(
        chain=Chain.BASE_SEPOLIA,
        action=ActionType.SWAP,
        transaction=_transaction(bundle),
    )
    envelope = request.envelope()

    denied = PriorSealAuthorizationProvider(
        response,
        trust_roots=bundle.trust_roots,
        acceptance_store=SQLiteAcceptanceStore(database),
    )
    with pytest.raises(AuthorizationDenied, match="acceptance signature"):
        denied.evidence_for(
            envelope=envelope,
            envelope_digest=envelope.digest(),
            policy_commitment_digest=bundle.baseline["wak"][
                "policyDecisionCommitment"
            ]["digest"],
        )

    valid = PriorSealAuthorizationProvider(
        valid_response,
        trust_roots=bundle.trust_roots,
        acceptance_store=SQLiteAcceptanceStore(database),
    )
    with patch("web3_agent_kit.execution.authorization.time.time", return_value=1789639202):
        evidence = valid.evidence_for(
            envelope=envelope,
            envelope_digest=envelope.digest(),
            policy_commitment_digest=bundle.baseline["wak"][
                "policyDecisionCommitment"
            ]["digest"],
        )
    assert evidence.authorization_id == valid_response["authorization_id"]


@pytest.mark.parametrize(
    "accepted_at",
    [1789639199, 1789639381],
)
def test_priorseal_acceptance_timing_is_ordered_without_burn(
    accepted_at: int, tmp_path: Path
) -> None:
    bundle = FixtureBundle.load(FIXTURE)
    valid_response = bundle.baseline["priorSeal"]["response"]
    response = copy.deepcopy(valid_response)
    response["acceptance"]["acceptedAt"] = accepted_at
    database = tmp_path / f"acceptance-{accepted_at}.sqlite3"
    request = AuthorizationRequest(
        chain=Chain.BASE_SEPOLIA,
        action=ActionType.SWAP,
        transaction=_transaction(bundle),
    )
    envelope = request.envelope()

    denied = PriorSealAuthorizationProvider(
        response,
        trust_roots=bundle.trust_roots,
        acceptance_store=SQLiteAcceptanceStore(database),
    )
    with pytest.raises(AuthorizationDenied, match="acceptance timing"):
        denied.evidence_for(
            envelope=envelope,
            envelope_digest=envelope.digest(),
            policy_commitment_digest=bundle.baseline["wak"][
                "policyDecisionCommitment"
            ]["digest"],
        )

    valid = PriorSealAuthorizationProvider(
        valid_response,
        trust_roots=bundle.trust_roots,
        acceptance_store=SQLiteAcceptanceStore(database),
    )
    with patch("web3_agent_kit.execution.authorization.time.time", return_value=1789639202):
        evidence = valid.evidence_for(
            envelope=envelope,
            envelope_digest=envelope.digest(),
            policy_commitment_digest=bundle.baseline["wak"][
                "policyDecisionCommitment"
            ]["digest"],
        )
    assert evidence.authorization_id == valid_response["authorization_id"]


@pytest.mark.parametrize(
    ("mutation_path", "replacement", "message"),
    [
        (("signedAuthorization", "signature"), "0x00", "authorization signature"),
        (("signedAuthorization", "intent", "nonce"), "2049", "intent hash"),
        (("acceptance", "signature"), "A" * 86, "acceptance signature"),
        (("acceptance", "keyId"), "untrusted-key", "acceptance key"),
        (("authorizer",), "0x" + "ff" * 20, "top-level authorizer"),
    ],
)
def test_priorseal_tampering_is_denied_before_execution_boundaries(
    mutation_path: tuple[str, ...], replacement: str, message: str
) -> None:
    bundle = FixtureBundle.load(FIXTURE)
    response = copy.deepcopy(bundle.baseline["priorSeal"]["response"])
    target = response
    for component in mutation_path[:-1]:
        target = target[component]
    target[mutation_path[-1]] = replacement
    counters = BoundaryCounters()

    _, _, receipt, error = _run_gate_attempt(
        transaction=_transaction(bundle),
        response=response,
        trust_roots=bundle.trust_roots,
        counters=counters,
        now=1789639202,
        acceptance_store=None,
        boundaries=synthetic_execution_boundaries(counters),
    )

    assert receipt is None
    assert message.lower() in str(error).lower()
    assert counters.as_report() == {
        "authorizationProvider": 1,
        "signer": 0,
        "broadcast": 0,
        "receipt": 0,
    }


def test_sqlite_acceptance_state_survives_store_reconstruction(tmp_path: Path) -> None:
    database = tmp_path / "acceptances.sqlite3"
    first = SQLiteAcceptanceStore(database)
    second = SQLiteAcceptanceStore(database)

    assert first.consume("auth-example") is True
    assert second.consume("auth-example") is False
    assert first is not second
    assert first.database_path == second.database_path


def test_wrong_current_policy_does_not_burn_durable_acceptance(tmp_path: Path) -> None:
    bundle = FixtureBundle.load(FIXTURE)
    response = bundle.baseline["priorSeal"]["response"]
    database = tmp_path / "acceptances.sqlite3"
    request = AuthorizationRequest(
        chain=Chain.BASE_SEPOLIA,
        action=ActionType.SWAP,
        transaction=_transaction(bundle),
    )
    envelope = request.envelope()

    denied = PriorSealAuthorizationProvider(
        response,
        trust_roots=bundle.trust_roots,
        acceptance_store=SQLiteAcceptanceStore(database),
    )
    with pytest.raises(AuthorizationDenied, match="policy"):
        denied.evidence_for(
            envelope=envelope,
            envelope_digest=envelope.digest(),
            policy_commitment_digest="0x" + "ff" * 32,
        )

    valid = PriorSealAuthorizationProvider(
        response,
        trust_roots=bundle.trust_roots,
        acceptance_store=SQLiteAcceptanceStore(database),
    )
    with patch("web3_agent_kit.execution.authorization.time.time", return_value=1789639202):
        evidence = valid.evidence_for(
            envelope=envelope,
            envelope_digest=envelope.digest(),
            policy_commitment_digest=bundle.baseline["wak"][
                "policyDecisionCommitment"
            ]["digest"],
        )

    assert evidence.authorization_id == response["authorization_id"]


def test_mutated_call_does_not_burn_durable_acceptance(tmp_path: Path) -> None:
    bundle = FixtureBundle.load(FIXTURE)
    response = bundle.baseline["priorSeal"]["response"]
    database = tmp_path / "acceptances.sqlite3"
    mutated = _transaction(bundle)
    mutated["data"] = "0xdeadbeef"
    denied_counters = BoundaryCounters()

    _, _, denied_receipt, denied_error = _run_gate_attempt(
        transaction=mutated,
        response=response,
        trust_roots=bundle.trust_roots,
        counters=denied_counters,
        now=1789639202,
        acceptance_store=SQLiteAcceptanceStore(database),
        boundaries=synthetic_execution_boundaries(denied_counters),
    )

    assert denied_receipt is None
    assert "envelope" in str(denied_error).lower()
    assert denied_counters.as_report() == {
        "authorizationProvider": 1,
        "signer": 0,
        "broadcast": 0,
        "receipt": 0,
    }

    valid_counters = BoundaryCounters()
    _, _, valid_receipt, valid_error = _run_gate_attempt(
        transaction=_transaction(bundle),
        response=response,
        trust_roots=bundle.trust_roots,
        counters=valid_counters,
        now=1789639202,
        acceptance_store=SQLiteAcceptanceStore(database),
        boundaries=synthetic_execution_boundaries(valid_counters),
    )

    assert valid_error is None
    assert valid_receipt is not None
    assert valid_counters.as_report() == {
        "authorizationProvider": 1,
        "signer": 1,
        "broadcast": 1,
        "receipt": 1,
    }


def test_not_yet_valid_attempt_does_not_burn_durable_acceptance(tmp_path: Path) -> None:
    bundle = FixtureBundle.load(FIXTURE)
    response = bundle.baseline["priorSeal"]["response"]
    database = tmp_path / "acceptances.sqlite3"
    denied_counters = BoundaryCounters()

    _, _, denied_receipt, denied_error = _run_gate_attempt(
        transaction=_transaction(bundle),
        response=response,
        trust_roots=bundle.trust_roots,
        counters=denied_counters,
        now=1789639199,
        acceptance_store=SQLiteAcceptanceStore(database),
        boundaries=synthetic_execution_boundaries(denied_counters),
    )

    assert denied_receipt is None
    assert "validity window" in str(denied_error).lower()
    assert denied_counters.signer == 0

    valid_counters = BoundaryCounters()
    _, _, valid_receipt, valid_error = _run_gate_attempt(
        transaction=_transaction(bundle),
        response=response,
        trust_roots=bundle.trust_roots,
        counters=valid_counters,
        now=1789639202,
        acceptance_store=SQLiteAcceptanceStore(database),
        boundaries=synthetic_execution_boundaries(valid_counters),
    )

    assert valid_error is None
    assert valid_receipt is not None
    assert valid_counters.signer == 1


def test_gate_attempt_uses_injected_execution_boundaries() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    counters = BoundaryCounters()
    calls: list[str] = []

    class Signer:
        def sign_transaction(self, transaction):
            calls.append("signer")
            counters.signer += 1
            return b"injected"

    def broadcast(raw_transaction):
        assert raw_transaction == b"injected"
        calls.append("broadcast")
        counters.broadcast += 1
        return {"txHash": "injected"}

    def receipt(broadcast_result):
        assert broadcast_result == {"txHash": "injected"}
        calls.append("receipt")
        counters.receipt += 1
        return {"status": "INJECTED"}

    boundaries = ExecutionBoundaries(Signer(), broadcast, receipt)
    _, _, observed_receipt, error = _run_gate_attempt(
        transaction=_transaction(bundle),
        response=bundle.baseline["priorSeal"]["response"],
        trust_roots=bundle.trust_roots,
        counters=counters,
        now=1789639202,
        acceptance_store=None,
        boundaries=boundaries,
    )

    assert error is None
    assert observed_receipt == {"status": "INJECTED"}
    assert calls == ["signer", "broadcast", "receipt"]


def test_vendored_fixture_manifest_and_pin_are_exact() -> None:
    bundle = FixtureBundle.load(FIXTURE)

    assert bundle.version == "v1"
    assert bundle.case_ids == ("N1", "N2", "N3", "N4", "N5a", "N5b", "P1")
    pin = json.loads((FIXTURE / "fixture" / "manifest.json").read_text())["version"]
    assert pin == "v1"

    archive = FIXTURE.parent / "2026-09-21-wak-insight-priorseal-conformance-v1.zip"
    expected_hash = "6fea0cdc0b42642d9b716ff347d629db2c4b8dc2cf573e34df893b423e8efe5f"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected_hash
    assert (FIXTURE.parent / "UPSTREAM_BUNDLE.sha256").read_text().split()[0] == expected_hash


def test_insight_signature_and_uid_are_verified() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    attestation = bundle.baseline["insight"]["sourceAttestation"]

    verify_insight_attestation(attestation, bundle.baseline, bundle.trust_roots)

    tampered = copy.deepcopy(attestation)
    tampered["data"]["tradeAmountUsd"] += 1
    with pytest.raises(BoundaryError, match="INSIGHT_UID_MISMATCH"):
        verify_insight_attestation(tampered, bundle.baseline, bundle.trust_roots)


def test_fixture_rejects_self_consistent_extraction_that_differs_from_zip(
    tmp_path: Path,
) -> None:
    copied_parent = tmp_path / "insight_priorseal_spike"
    shutil.copytree(FIXTURE.parent, copied_parent)
    copied_fixture = copied_parent / "v1"
    baseline_path = copied_fixture / "fixture" / "baseline.json"
    manifest_path = copied_fixture / "fixture" / "manifest.json"

    baseline = json.loads(baseline_path.read_text())
    baseline["transaction"]["nonce"] = "9999"
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n")
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["fixture/baseline.json"] = hashlib.sha256(
        baseline_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    with pytest.raises(BoundaryError, match="pinned archive"):
        FixtureBundle.load(copied_fixture)


def test_negative_suite_hits_the_real_boundaries() -> None:
    report = run_negative_suite(FIXTURE)

    assert report["instrumentation"] == {
        "explicitSignerProtocol": True,
        "explicitBroadcastFn": True,
    }
    assert report["adapter"] == {"newFieldTypes": 0}
    assert report["adapterAcceptance"]["terminal"] == "PASS"
    assert [case["id"] for case in report["cases"]] == [
        "N1",
        "N2",
        "N3",
        "N4",
        "N5a",
        "N5b",
    ]

    expected = FixtureBundle.load(FIXTURE).cases["cases"][:6]
    for actual, vector in zip(report["cases"], expected, strict=True):
        assert actual["actualTerminal"] == vector["terminal"]
        assert actual["reason"] == vector["reason"]
        assert actual["counts"] == vector["counts"]
    assert report["cases"][-1]["reconstruction"] == {
        "differentGateInstance": True,
        "differentProviderInstance": True,
        "differentStoreInstance": True,
        "differentSignerInstance": True,
        "differentBroadcastInstance": True,
        "differentReceiptInstance": True,
        "sameDatabase": True,
        "samePersistedAcceptanceId": True,
    }
    observed = {case["id"]: case["observed"] for case in report["cases"]}
    assert observed["N1"]["boundaryReason"] == "INSIGHT_BLOCK"
    assert observed["N2"]["boundaryReason"] == "INSIGHT_STALE"
    assert observed["N3"]["gateReasons"] == ["authorization_call_mismatch"]
    assert observed["N4"]["gateReasons"] == ["authorization_call_mismatch"]
    assert observed["N4"]["nonceMismatch"] is True
    assert observed["N5a"]["gateReasons"] == ["authorization_replayed"]
    assert observed["N5b"]["providerReason"] == "AUTHORIZATION_REPLAYED"
    assert observed["N5b"]["deniedBeforeSigner"] is True
    assert observed["N5b"]["deniedBeforeBroadcast"] is True
    assert observed["N5b"]["deniedBeforeReceipt"] is True
    assert report["cases"][5]["reconstruction"]["differentSignerInstance"] is True
    assert report["cases"][5]["reconstruction"]["differentBroadcastInstance"] is True
    assert report["cases"][5]["reconstruction"]["differentReceiptInstance"] is True


def test_negative_acceptance_report_passes_portable_verifier(tmp_path: Path) -> None:
    report_path = tmp_path / "wak-acceptance-report.json"
    write_acceptance_report(FIXTURE, report_path)

    completed = subprocess.run(
        ["node", str(FIXTURE / "verify.mjs"), "--report", str(report_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["status"] == "PASS"
    assert result["wakAcceptance"] == "NEGATIVE_REPORT_FIELDS_VERIFIED_P1_PENDING"


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("reconstruction", "differentSignerInstance"),
        ("reconstruction", "differentBroadcastInstance"),
        ("reconstruction", "differentReceiptInstance"),
        ("reconstruction", "sameDatabase"),
        ("observed", "deniedBeforeSigner"),
        ("observed", "deniedBeforeBroadcast"),
        ("observed", "deniedBeforeReceipt"),
    ],
)
def test_local_n5b_evidence_validator_rejects_falsified_fields(
    section: str, field: str
) -> None:
    report = run_negative_suite(FIXTURE)
    n5b = next(case for case in report["cases"] if case["id"] == "N5b")
    n5b[section][field] = False

    with pytest.raises(BoundaryError, match="N5b"):
        validate_extended_n5b_evidence(report)


def test_example_runs_directly_from_repository_root(tmp_path: Path) -> None:
    report_path = tmp_path / "direct-report.json"
    completed = subprocess.run(
        [
            sys.executable,
            "examples/insight_priorseal_swap.py",
            str(FIXTURE),
            "--report",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert report_path.exists()
