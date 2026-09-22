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

import pytest

from examples.insight_priorseal_swap import run_negative_suite, write_acceptance_report
from examples.support.insight_priorseal_boundary import (
    BoundaryError,
    FixtureBundle,
    PriorSealAuthorizationProvider,
    verify_insight_attestation,
)
from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import AuthorizationEvidence, AuthorizationRequest
from web3_agent_kit.execution.intent import ActionType

FIXTURE = Path(__file__).parent / "fixtures" / "insight_priorseal_spike" / "v1"


def test_adapter_maps_priorseal_response_without_new_evidence_fields() -> None:
    bundle = FixtureBundle.load(FIXTURE)
    baseline = bundle.baseline
    provider = PriorSealAuthorizationProvider(baseline["priorSeal"]["response"])
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
        "differentProviderInstance": True,
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
