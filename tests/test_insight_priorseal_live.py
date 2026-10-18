"""Tests for the live P1 boundaries, call-event retention, GO arrival, and P1 report assembly."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from examples.insight_priorseal_swap import (
    BoundaryError,
    attach_p1_and_provenance,
    build_p1_block,
    build_p1_row,
    classify_run_outcome,
    run_live_p1,
    run_negative_suite,
    validate_p1_evidence,
    write_live_acceptance_report,
)
from examples.support.go_arrival import (
    GoArrivalError,
    authorize_go_message,
    authorize_go_sheet,
    floor_satisfied,
    query_go_messages,
    resolve_go_arrival,
)
from examples.support.insight_priorseal_live import (
    CallEventRecorder,
    CutoffError,
    EvmSigner,
    LiveRunConfig,
    check_cutoff,
    check_go_arrival,
    execution_flags,
    live_execution_boundaries,
    runtime_provenance,
    version_alignment,
)

FIXTURE = Path(__file__).parent / "fixtures" / "insight_priorseal_spike" / "v1"
P1_EVIDENCE = Path(__file__).parent / "fixtures" / "insight_priorseal_spike" / "attempt9-p1-evidence.json"


def test_recorder_retains_call_events():
    recorder = CallEventRecorder()
    recorder.record("signer", "attempted", started_at=1, finished_at=1)
    recorder.record("signer", "success", started_at=1, finished_at=2)
    recorder.record("broadcast", "attempted", started_at=2, finished_at=2)
    recorder.record("broadcast", "error", started_at=2, finished_at=3, detail={"error": "RPC error"})

    report = recorder.as_report()
    assert report["retained"] is True
    assert report["counts"]["signer"] == {"attempted": 1, "success": 1, "error": 0}
    assert report["counts"]["broadcast"] == {"attempted": 1, "success": 0, "error": 1}
    assert [e["outcome"] for e in report["events"]] == ["attempted", "success", "attempted", "error"]
    assert report["events"][-1]["detail"]["error"] == "RPC error"


def test_recorder_rejects_unknown_boundary():
    recorder = CallEventRecorder()
    with pytest.raises(ValueError):
        recorder.record("miner", "success", started_at=1, finished_at=1)


def test_evm_signer_recovers_sender_without_network():
    import eth_account

    account = eth_account.Account.create()
    signer = EvmSigner(account)
    tx = {
        "from": account.address,
        "to": "0x0000000000000000000000000000000000000000",
        "value": 0,
        "gas": 21000,
        "maxFeePerGas": 1000000000,
        "maxPriorityFeePerGas": 1000000000,
        "nonce": 0,
        "chainId": 84532,
        "data": b"",
    }
    raw = signer.sign_transaction(tx)
    recovered = eth_account.Account.recover_transaction(raw)
    assert recovered.lower() == account.address.lower()


def test_evm_signer_rejects_mismatched_from():
    import eth_account

    account = eth_account.Account.create()
    other = eth_account.Account.create()
    signer = EvmSigner(account)
    with pytest.raises(ValueError):
        signer.sign_transaction({"from": other.address, "to": "0x" + "00" * 20, "nonce": 0, "chainId": 84532})


def test_check_cutoff_and_go_arrival_floors():
    cutoff = 1_000_000
    check_cutoff(now_epoch=cutoff - 500, latest_broadcast_at=cutoff, minimum_seconds=120)
    with pytest.raises(CutoffError):
        check_cutoff(now_epoch=cutoff - 50, latest_broadcast_at=cutoff, minimum_seconds=120)

    config = LiveRunConfig(
        rpc_url="http://unused",
        chain_id=84532,
        latest_broadcast_at=cutoff,
        run_sheet_sha256="ab" * 32,
        go_arrival_epoch=cutoff - 500,
        receiver_floor_seconds=120,
    )
    assert check_go_arrival(config) == 500
    late = LiveRunConfig(
        rpc_url="http://unused",
        chain_id=84532,
        latest_broadcast_at=cutoff,
        run_sheet_sha256="ab" * 32,
        go_arrival_epoch=cutoff - 50,
        receiver_floor_seconds=120,
    )
    with pytest.raises(CutoffError):
        check_go_arrival(late)


def test_cutoff_guard_records_and_blocks_late():
    import eth_account

    recorder = CallEventRecorder()
    account = eth_account.Account.create()
    signer = EvmSigner(account)
    config = LiveRunConfig(
        rpc_url="http://unused",
        chain_id=84532,
        latest_broadcast_at=1_900_000_000 + 3600,
        run_sheet_sha256="ab" * 32,
        go_arrival_epoch=1_900_000_000,
    )
    boundaries = live_execution_boundaries(
        recorder=recorder,
        signer=signer,
        broadcast=lambda raw_transaction: {"txHash": "0x" + "12" * 32},
        receipt=lambda broadcast_result: {"status": "SYNTHETIC_CONFIRMED", "txHash": broadcast_result["txHash"]},
        config=config,
        cutoff_check_seconds=60,
    )
    tx = {"from": account.address, "to": "0x" + "00" * 20, "value": 0, "gas": 21000,
          "maxFeePerGas": 1, "maxPriorityFeePerGas": 1, "nonce": 0, "chainId": 84532, "data": b""}
    raw = boundaries.signer.sign_transaction(tx)
    assert len(raw) > 0
    assert recorder.counts()["signer"] == {"attempted": 1, "success": 1, "error": 0}

    import time

    past_cutoff = int(time.time()) - 60
    late_config = LiveRunConfig(
        rpc_url="http://unused",
        chain_id=84532,
        latest_broadcast_at=past_cutoff,
        run_sheet_sha256="ab" * 32,
        go_arrival_epoch=past_cutoff - 5000,
    )
    late_boundaries = live_execution_boundaries(
        recorder=recorder,
        signer=signer,
        broadcast=lambda raw_transaction: {"txHash": "0x" + "12" * 32},
        receipt=lambda broadcast_result: {"status": "SYNTHETIC_CONFIRMED", "txHash": broadcast_result["txHash"]},
        config=late_config,
        cutoff_check_seconds=60,
    )
    with pytest.raises(CutoffError):
        late_boundaries.signer.sign_transaction(tx)


def test_go_arrival_reads_session_store(tmp_path):
    db = tmp_path / "state.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, role TEXT, content TEXT, timestamp REAL)")
    con.execute(
        "INSERT INTO messages (id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (3826, "user", "GO — run-specific, latestBroadcastAt 1790440202", 1790439543),
    )
    con.execute(
        "INSERT INTO messages (id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (3827, "assistant", "acknowledged", 1790439600),
    )
    con.commit()
    con.close()

    rows = query_go_messages(db, message_id=3826, role="user")
    assert len(rows) == 1
    payload = resolve_go_arrival(rows, stated_arrival_deadline_epoch=1790440082)
    assert payload["schema"] == "wak-p1.go-arrival-metadata.v1"
    assert payload["deliveryTimestampEpoch"] == 1790439543
    assert payload["messageId"] == 3826
    assert payload["secondsBeforeStatedArrivalDeadline"] == 539
    assert floor_satisfied(payload, latest_broadcast_at=1790440202) is True
    assert floor_satisfied(payload, latest_broadcast_at=1790439600) is False

    with pytest.raises(GoArrivalError):
        resolve_go_arrival([])
    with pytest.raises(GoArrivalError):
        query_go_messages(db)


def test_go_arrival_requires_filters(tmp_path):
    db = tmp_path / "state.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, role TEXT, content TEXT, timestamp REAL)")
    con.commit()
    con.close()
    with pytest.raises(GoArrivalError):
        query_go_messages(db)  # no filters at all
    with pytest.raises(GoArrivalError):
        query_go_messages(tmp_path / "missing.db", message_id=1)  # store missing
    assert query_go_messages(db, message_id=1) == []  # valid filter, no match -> empty


def test_build_p1_row_and_validation():
    with pytest.raises(BoundaryError):
        build_p1_row(live_input_sha256="not-hex", baseline_sha256="ab" * 32, case_input_sha256="cd" * 32)

    p1_row = build_p1_row(
        live_input_sha256="ddc9068d14e6b6a50ecbb31c830bc8ef47d856d2f7da2773d61320da6e7cad17",
        baseline_sha256="799fc12b3ee0bcd8780e3b03361c80c179415f2cabaacb22dc42c077c471a64f",
        case_input_sha256="a115dc57d55a9c7bb795e58a06b6a74fc0ed9d2553144b1c4e3e9ed2f7e0fe61",
    )
    assert p1_row["id"] == "P1"
    assert p1_row["actualTerminal"] == "LIVE_RECEIPT_VERIFIED"
    assert p1_row["counts"] == {"authorizationProvider": 1, "signer": 1, "broadcast": 1, "receipt": 1}


def test_attach_p1_and_provenance_with_real_evidence():
    evidence = json.loads(P1_EVIDENCE.read_text(encoding="utf-8"))
    base = run_negative_suite(FIXTURE)
    p1_row = build_p1_row(
        live_input_sha256="ddc9068d14e6b6a50ecbb31c830bc8ef47d856d2f7da2773d61320da6e7cad17",
        baseline_sha256="799fc12b3ee0bcd8780e3b03361c80c179415f2cabaacb22dc42c077c471a64f",
        case_input_sha256="a115dc57d55a9c7bb795e58a06b6a74fc0ed9d2553144b1c4e3e9ed2f7e0fe61",
        wak_version="1.18.4",  # this test consumes the v1 fixture, which pins 1.18.4
    )
    p1_block = build_p1_block(
        receipt=evidence["receipt"],
        trusted_key=evidence["trustedKey"],
        envelope_digest=evidence["wak"]["envelopeDigest"],
        policy_commitment_digest=evidence["wak"]["policyCommitmentDigest"],
        insight_pair_commitment=evidence["insightPairCommitment"],
    )
    full = attach_p1_and_provenance(
        base,
        p1_row=p1_row,
        p1_block=p1_block,
        runtime_package_version="1.18.5",
        runtime_commit="abc123",
        runtime_tree_clean=True,
    )
    assert full["runtime"]["packageVersion"] == "1.18.5"
    assert full["versionAlignment"]["aligned"] is False  # deliberate: fixture pins 1.18.4
    assert full["cases"][-1]["id"] == "P1"
    validate_p1_evidence(full)


def test_rehearsal_full_runner_path(tmp_path):
    """Exercise the real entry point's live runner with inert boundaries.

    Regression guard for YuTao's flagged gaps: the runner must bind the GO to the exact
    fresh sheet and hash, read arrival from the session store, use the sheet's signed
    inputs and the live clock, retain timestamped boundary events including failures,
    and report 1/1/1/1 only on a successful inert leg.
    """
    v11 = Path(__file__).parent / "fixtures" / "insight_priorseal_spike" / "v1.1"
    out = tmp_path / "rehearsal"
    out.mkdir()
    evidence = run_live_p1(
        fixture_root=v11,
        report=out / "rehearsal-report.json",
        go_file=out / "go.json",
        run_sheet=out / "sheet.json",
        session_db=out / "go.db",
        go_message_id=90001,
        rpc_url=None,
        chain_id=84532,
        allow_broadcast=False,
        rehearsal=True,
        rehearsal_output_dir=out,
        cutoff_check_seconds=60,
        call_events=out / "call-events.json",
    )
    assert evidence["outcome"] == "REHEARSAL_LEG_COMPLETED"
    assert evidence["counts"] == {
        "authorizationProvider": 1,
        "signer": 1,
        "broadcast": 1,
        "receipt": 1,
    }
    assert evidence["signed"] is True and evidence["broadcast"] is True
    # GO arrival is read from the session store, not from the GO file.
    assert evidence["goArrival"]["source"].startswith("Hermes session store")
    assert evidence["goArrival"]["messageId"] == 90001
    # The Hermes GO MESSAGE itself authorizes the exact sheet hash (YuTao gap 1).
    auth = evidence["goArrival"]["goSheetAuthorization"]
    assert auth["authorized"] is True
    assert auth["authorizedRunSheetSha256"] == evidence["runSheetSha256"]
    assert auth["authorizationSource"] in ("label", "go-directive", "json")
    # The run sheet hash is bound in the GO and the report.
    assert evidence["runSheetSha256"] == json.loads((out / "go.json").read_text())["runSheetSha256"]
    # Every boundary retains a timestamped attempted + success pair (no failures).
    boundaries = {e["boundary"] for e in evidence["callEvents"]["events"]}
    assert boundaries == {"authorizationProvider", "signer", "broadcast", "receipt"}
    assert all(e["outcome"] != "error" for e in evidence["callEvents"]["events"])
    assert (out / "call-events.json").exists()


def test_write_live_acceptance_report(tmp_path):
    evidence = json.loads(P1_EVIDENCE.read_text(encoding="utf-8"))
    out = write_live_acceptance_report(
        FIXTURE,
        tmp_path / "report.json",
        receipt=evidence["receipt"],
        trusted_key=evidence["trustedKey"],
        live_input_sha256="ddc9068d14e6b6a50ecbb31c830bc8ef47d856d2f7da2773d61320da6e7cad17",
        envelope_digest=evidence["wak"]["envelopeDigest"],
        policy_commitment_digest=evidence["wak"]["policyCommitmentDigest"],
        insight_pair_commitment=evidence["insightPairCommitment"],
        runtime_package_version="1.18.5",
    )
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == "wak-insight-priorseal.acceptance-report.v1"
    assert data["runtime"]["packageVersion"] == "1.18.5"
    assert data["p1"]["trustedKey"]["status"] == "active"


def test_validate_p1_evidence_rejects_inactive_key():
    base = run_negative_suite(FIXTURE)
    evidence = json.loads(P1_EVIDENCE.read_text(encoding="utf-8"))
    bad_key = dict(evidence["trustedKey"], status="revoked")
    p1_block = build_p1_block(
        receipt=evidence["receipt"],
        trusted_key=bad_key,
        envelope_digest=evidence["wak"]["envelopeDigest"],
        policy_commitment_digest=evidence["wak"]["policyCommitmentDigest"],
        insight_pair_commitment=evidence["insightPairCommitment"],
    )
    with pytest.raises(BoundaryError, match="not active"):
        attach_p1_and_provenance(
            base,
            p1_row=build_p1_row(
                live_input_sha256="ddc9068d14e6b6a50ecbb31c830bc8ef47d856d2f7da2773d61320da6e7cad17",
                baseline_sha256="799fc12b3ee0bcd8780e3b03361c80c179415f2cabaacb22dc42c077c471a64f",
                case_input_sha256="a115dc57d55a9c7bb795e58a06b6a74fc0ed9d2553144b1c4e3e9ed2f7e0fe61",
            ),
            p1_block=p1_block,
            runtime_package_version="1.18.5",
        )


def test_runtime_provenance_and_alignment():
    prov = runtime_provenance(package_version="1.18.5", commit="abc123", tree_clean=True)
    assert prov["schema"] == "wak-p1.runtime-provenance.v1"
    align = version_alignment("1.18.4", "1.18.5")
    assert align["aligned"] is False
    assert version_alignment("1.18.5", "1.18.5")["aligned"] is True


def test_authorize_go_message_binds_exact_sheet_hash():
    """YuTao gap 1: the Hermes GO message itself must name the exact run-sheet hash."""
    sheet_hash = "ab" * 32
    ok = authorize_go_message(f"GO — latestBroadcastAt 1790440202, runSheetSha256 {sheet_hash}", sheet_hash)
    assert ok["authorized"] is True and ok["authorizationSource"] == "label"
    ok_json = authorize_go_message(json.dumps({"runSheetSha256": sheet_hash}), sheet_hash)
    assert ok_json["authorized"] is True and ok_json["authorizationSource"] == "json"
    ok_directive = authorize_go_message(f"GO {sheet_hash}", sheet_hash)
    assert ok_directive["authorizationSource"] == "go-directive"
    with pytest.raises(GoArrivalError, match="does not explicitly authorize"):
        authorize_go_message("GO — run is a go, no hash stated", sheet_hash)
    with pytest.raises(GoArrivalError, match="but the executing path bound"):
        authorize_go_message(f"GO — runSheetSha256 {'cd' * 32}", sheet_hash)


def test_authorize_go_sheet_reads_full_message_from_store(tmp_path):
    """YuTao gap 1 end-to-end: full GO message content fetched and verified."""
    db = tmp_path / "go.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, role TEXT, content TEXT, timestamp REAL)")
    sheet = "ef" * 32
    con.execute(
        'INSERT INTO messages (id, role, content, timestamp) VALUES (?, ?, ?, ?)',
        (511, "user", f"GO — latestBroadcastAt 1790442200, runSheetSha256 {sheet}", 1782399000),
    )
    con.commit()
    con.close()
    auth = authorize_go_sheet(db, 511, sheet)
    assert auth["authorized"] is True
    assert auth["messageId"] == 511
    with pytest.raises(GoArrivalError):
        authorize_go_sheet(db, 511, "ff" * 32)
    with pytest.raises(GoArrivalError):
        authorize_go_sheet(db, 999, sheet)


def test_execution_flags_from_events_on_receipt_failure():
    recorder = CallEventRecorder()
    for b in ("authorizationProvider", "signer", "broadcast", "receipt"):
        recorder.record(b, "attempted", started_at=1, finished_at=1)
    recorder.record("signer", "success", started_at=1, finished_at=2)
    recorder.record("broadcast", "success", started_at=2, finished_at=3)
    recorder.record("receipt", "error", started_at=3, finished_at=4, detail={"error": "TimeoutError"})
    flags = execution_flags(recorder)
    assert flags["signed"] is True and flags["broadcast"] is True
    assert recorder.boundary_counts()["signer"] == 1
    assert recorder.boundary_counts()["broadcast"] == 1
    assert recorder.boundary_counts()["receipt"] == 0
    denied = CallEventRecorder()
    denied.record("authorizationProvider", "attempted", started_at=1, finished_at=1)
    denied.record("authorizationProvider", "error", started_at=1, finished_at=2)
    assert execution_flags(denied) == {"signed": False, "broadcast": False}


def test_classify_outcome_reverted_and_no_receipt():
    ok = {"authorizationProvider": 1, "signer": 1, "broadcast": 1, "receipt": 1}
    assert classify_run_outcome(receipt={"status": "REVERTED"}, attempt_error=None,
                                counts=ok, rehearsal=False)[0] == "REVERTED"
    assert classify_run_outcome(receipt={"status": "CONFIRMED"}, attempt_error=None,
                                counts=ok, rehearsal=False)[0] == "LIVE_LEG_COMPLETED"
    assert classify_run_outcome(receipt=None, attempt_error="TimeoutError", counts=ok,
                                rehearsal=False)[0] == "BROADCAST_NO_CONFIRMED_RECEIPT"
    no_sign = {"authorizationProvider": 1, "signer": 0, "broadcast": 0, "receipt": 0}
    assert classify_run_outcome(receipt=None, attempt_error="EnforcementDenied", counts=no_sign,
                                rehearsal=False)[0] == "ENFORCEMENT_DENIED"
    assert classify_run_outcome(receipt=None, attempt_error="boom", counts=no_sign,
                                rehearsal=False)[0] == "ERROR"
    assert classify_run_outcome(receipt=None, attempt_error=None, counts=no_sign,
                                rehearsal=False)[0] == "NO_RECEIPT"


# --- frozen-sheet policy commitment: the two-clock trap (2026-10-17) ---------


def _decision_payload(evaluated_at, verdict="allow", reasons=()):
    """Build a policy decision payload the way the gate does, plus its digest."""
    from web3_agent_kit.execution.envelope import PolicyDecisionCommitment

    commitment = PolicyDecisionCommitment(
        call_identity="0x" + "ab" * 32,
        policy_id="priorseal-bounded-spike-v1",
        verdict=verdict,
        reason_codes=tuple(reasons),
        evaluated_at=evaluated_at,
    )
    return commitment.to_payload(), commitment.digest()


def _frozen_provider(payload, digest):
    from examples.support.insight_priorseal_boundary import PriorSealAuthorizationProvider

    return PriorSealAuthorizationProvider(
        {"schema": "priorseal.wak-authorization-response.v1"},
        trust_roots={},
        frozen_policy_decision=payload,
        frozen_policy_commitment_digest=digest,
    )


def _live_commitment(payload, evaluated_at, verdict=None, reasons=None):
    from web3_agent_kit.execution.envelope import PolicyDecisionCommitment

    return PolicyDecisionCommitment(
        call_identity=payload["callIdentity"],
        policy_id=payload["policyId"],
        verdict=verdict if verdict is not None else payload["verdict"],
        reason_codes=tuple(reasons if reasons is not None else payload["reasonCodes"]),
        evaluated_at=evaluated_at,
    )


def test_frozen_policy_commitment_survives_clock_skew():
    """A frozen digest must still verify when enforcement runs much later.

    Regression for the 2026-10-17 NO_RUN: the gate compared the authorization
    against a commitment recomputed at enforcement time, and because
    ``evaluatedAt`` is a per-second clock reading that comparison could never
    succeed. The pinned sheet's own decision must be the reference.
    """
    payload, digest = _decision_payload(evaluated_at=1000)
    provider = _frozen_provider(payload, digest)

    # Check 1 works no matter how old the sheet is.
    assert provider._verify_sheet_commitment() == digest

    # Live enforcement 300s later: the clock moved, the decision did not.
    live = _live_commitment(payload, evaluated_at=1300)
    provider._check_live_drift(live, digest)
    assert provider.drift_records == []


def test_doctored_sheet_digest_rejected_before_authorization():
    from examples.support.insight_priorseal_boundary import AuthorizationDenied

    payload, _ = _decision_payload(evaluated_at=1000)
    provider = _frozen_provider(payload, "0x" + "de" * 32)

    with pytest.raises(AuthorizationDenied) as excinfo:
        provider._verify_sheet_commitment()
    assert "self-inconsistent" in str(excinfo.value)


def test_policy_drift_aborts_and_records_both_payloads():
    from examples.support.insight_priorseal_boundary import AuthorizationDenied

    frozen_payload, frozen_digest = _decision_payload(evaluated_at=1000)
    provider = _frozen_provider(frozen_payload, frozen_digest)

    live = _live_commitment(
        frozen_payload, evaluated_at=1300, verdict="deny", reasons=("AMOUNT_CAP",)
    )
    with pytest.raises(AuthorizationDenied) as excinfo:
        provider._check_live_drift(live, frozen_digest)

    message = str(excinfo.value)
    assert "drifted" in message
    assert "verdict" in message and "reasonCodes" in message
    # Observability requirement: both digests travel with the denial.
    assert frozen_digest in message

    record = provider.drift_records[-1]
    assert record["fields"] == ["reasonCodes", "verdict"]
    assert record["frozenPayload"]["evaluatedAt"] == 1000
    assert record["livePayload"]["evaluatedAt"] == 1300
    assert record["frozenRecomputedDigest"] == frozen_digest
    assert record["liveDigest"] != frozen_digest


def _fake_context(policy_commitment):
    """Minimal stand-in for the interceptor context authorize() reads."""
    from types import SimpleNamespace

    return SimpleNamespace(
        envelope=None,
        envelope_digest="0x" + "00" * 32,
        policy_commitment=policy_commitment,
    )


def test_gate_checks_record_check1_failure():
    """The report must show check 1 failing, not just a bare denial."""
    from examples.support.insight_priorseal_boundary import AuthorizationDenied

    payload, _ = _decision_payload(evaluated_at=1000)
    provider = _frozen_provider(payload, "0x" + "de" * 32)
    live = _live_commitment(payload, evaluated_at=1300)

    with pytest.raises(AuthorizationDenied):
        provider.authorize(_fake_context(live))

    check1 = provider.gate_checks["check1SheetSelfConsistency"]
    assert check1["passed"] is False
    assert "self-inconsistent" in check1["detail"]
    assert check1["declaredDigest"] == "0x" + "de" * 32
    assert provider.gate_checks["frozenSheetSupplied"] is True


def test_gate_checks_record_drift_with_both_digests():
    """A drift abort must leave both digests and the compared field list behind."""
    from examples.support.insight_priorseal_boundary import AuthorizationDenied

    payload, digest = _decision_payload(evaluated_at=1000)
    provider = _frozen_provider(payload, digest)
    live = _live_commitment(payload, evaluated_at=1300, verdict="deny")

    with pytest.raises(AuthorizationDenied):
        provider.authorize(_fake_context(live))

    assert provider.gate_checks["check1SheetSelfConsistency"]["passed"] is True
    drift = provider.gate_checks["driftCheck"]
    assert drift["passed"] is False
    assert drift["frozenDigest"] == digest
    assert drift["liveDigest"] != digest
    assert "evaluatedAt" not in drift["comparedFields"]
    assert "verdict" in drift["record"]["fields"]


# --- Insight verdict gate: spec v0.1 §2/§4/§5 ---------------------------------


def _verdicts(source, destination):
    return {
        "source": {"verdict": source},
        "destination": {"verdict": destination},
    }


def _sheet_insight(source=None, destination=None, **extra):
    payload = {"sourceVerdict": source, "destinationVerdict": destination}
    payload.update(extra)
    return payload


def _gate(source, destination, sheet=None, extra_sheet=None):
    from examples.support.insight_verdict_gate import evaluate_insight_verdict_gate

    sheet_insight = sheet if sheet is not None else _sheet_insight(source, destination)
    if extra_sheet:
        sheet_insight = dict(sheet_insight)
        sheet_insight.update(extra_sheet)
    return evaluate_insight_verdict_gate(
        verdicts=_verdicts(source, destination),
        sheet_insight=sheet_insight,
        trust={"provenance": {"source": "test"}},
        pair_commitment="0x" + "11" * 32,
    )


def test_verdict_gate_allows_signed_pass():
    record = _gate("PASS", "PASS")
    assert record["decision"] == "ALLOW"
    assert record["reason"] == "ALLOW"
    assert record["signedVerdicts"] == {"source": "PASS", "destination": "PASS"}


def test_verdict_gate_refuses_caution_without_optin():
    from examples.support.insight_verdict_gate import InsightVerdictDenied

    with pytest.raises(InsightVerdictDenied) as excinfo:
        _gate("PASS", "CAUTION")
    assert excinfo.value.reason == "VERDICT_CAUTION_NO_OPTIN"
    assert excinfo.value.record["decision"] == "DENY"
    assert excinfo.value.record["refusedOn"] == "destination"
    assert excinfo.value.record["refusedValue"] == "CAUTION"


def test_verdict_gate_has_no_optin_path_under_policy_v1():
    """v1 carries no opt-in field, so a sheet-declared opt-in cannot unlock CAUTION."""
    from examples.support.insight_verdict_gate import InsightVerdictDenied

    with pytest.raises(InsightVerdictDenied) as excinfo:
        _gate("CAUTION", "CAUTION", extra_sheet={"cautionOptIn": True})
    assert excinfo.value.reason == "VERDICT_CAUTION_NO_OPTIN"
    assert "v1" in str(excinfo.value.record["policy"]["cautionOptIn"])


def test_verdict_gate_refuses_block():
    from examples.support.insight_verdict_gate import InsightVerdictDenied

    with pytest.raises(InsightVerdictDenied) as excinfo:
        _gate("PASS", "BLOCK")
    assert excinfo.value.reason == "VERDICT_BLOCK"


def test_verdict_gate_fails_closed_on_unknown_or_missing():
    from examples.support.insight_verdict_gate import InsightVerdictDenied

    for value in ("WARN", "", None, "   ", "not-block"):
        with pytest.raises(InsightVerdictDenied) as excinfo:
            _gate("PASS", value)
        assert excinfo.value.reason == "VERDICT_UNKNOWN", value


def test_verdict_gate_refuses_when_sheet_copy_differs_from_signed_verdict():
    from examples.support.insight_verdict_gate import InsightVerdictDenied

    with pytest.raises(InsightVerdictDenied) as excinfo:
        _gate("CAUTION", "CAUTION", sheet=_sheet_insight("PASS", "PASS"))
    assert excinfo.value.reason == "VERDICT_COPY_MISMATCH"
    assert excinfo.value.record["mismatched"] == ["source", "destination"]


def test_verdict_gate_ignores_optin_when_verdicts_pass():
    record = _gate("PASS", "PASS", extra_sheet={"cautionOptIn": True})
    assert record["decision"] == "ALLOW"


def test_collect_attestation_verdict_verifies_fixture_signatures():
    """The drop loader verifies real signatures, not just reads a field."""
    import json
    from pathlib import Path

    from examples.support.insight_verdict_gate import collect_attestation_verdict

    root = Path(__file__).resolve().parent / "fixtures/insight_priorseal_spike/v1.1/fixture"
    baseline = json.loads((root / "baseline.json").read_text())
    insight = baseline["insight"]
    registry = insight["keyRegistry"]
    attester = str(insight["sourceAttestation"]["attester"])
    entry = [e for e in registry["public_keys"] if str(e["public_key"]).lower() == attester.lower()][0]
    trust = {
        "baseline": {"insight": {"keyRegistry": registry}},
        "trust_roots": {"insight": {"attester": attester, "historicalKeyId": entry["key_id"]}},
        "provenance": {"source": "fixture"},
    }
    now = int(insight["sourceAttestation"]["data"]["checkedAt"]) + 1
    from examples.support.insight_priorseal_boundary import insight_pair_commitment

    expected = insight_pair_commitment(
        insight["sourceAttestation"], insight["destinationAttestation"]
    )
    verdicts = collect_attestation_verdict(
        insight["sourceAttestation"],
        insight["destinationAttestation"],
        trust,
        now=now,
        expected_pair_commitment=expected,
    )
    assert verdicts["pairCommitmentComputed"] == expected
    assert verdicts["source"]["verdict"] == "PASS"
    assert verdicts["destination"]["verdict"] == "PASS"

    blocked = collect_attestation_verdict(
        insight["sourceAttestation"],
        insight["blockedDestinationAttestation"],
        trust,
        now=now,
        expected_pair_commitment=insight_pair_commitment(
            insight["sourceAttestation"], insight["blockedDestinationAttestation"]
        ),
    )
    assert blocked["destination"]["verdict"] == "BLOCK"


def test_collect_attestation_verdict_refuses_when_pair_is_not_the_bound_one():
    """Two individually valid attestations that do not hash to the bound pair refuse."""
    import json
    from pathlib import Path

    import pytest

    from examples.support.insight_verdict_gate import InsightGateError, collect_attestation_verdict

    root = Path(__file__).resolve().parent / "fixtures/insight_priorseal_spike/v1.1/fixture"
    insight = json.loads((root / "baseline.json").read_text())["insight"]
    registry = insight["keyRegistry"]
    attester = str(insight["sourceAttestation"]["attester"])
    entry = [e for e in registry["public_keys"] if str(e["public_key"]).lower() == attester.lower()][0]
    trust = {
        "baseline": {"insight": {"keyRegistry": registry}},
        "trust_roots": {"insight": {"attester": attester, "historicalKeyId": entry["key_id"]}},
        "provenance": {"source": "fixture"},
    }
    now = int(insight["sourceAttestation"]["data"]["checkedAt"]) + 1
    with pytest.raises(InsightGateError) as excinfo:
        collect_attestation_verdict(
            insight["sourceAttestation"],
            insight["destinationAttestation"],
            trust,
            now=now,
            expected_pair_commitment="0x" + "ab" * 32,
        )
    assert excinfo.value.reason == "VERDICT_PAIR_MISMATCH"

    with pytest.raises(InsightGateError) as excinfo:
        collect_attestation_verdict(
            insight["sourceAttestation"], insight["destinationAttestation"], trust, now=now
        )
    assert excinfo.value.reason == "VERDICT_PAIR_MISMATCH"
    assert "declared" in excinfo.value.detail


def test_v1_policy_decision_carrying_optin_field_is_refused():
    """v1's field set is part of the namespace, not a convention (spec v1.0 §3).

    Reconstruction reads a fixed set of keys, so an extra key would be dropped and
    the digest would still match. The gate must reject the payload instead.
    """
    import pytest

    from examples.support.insight_priorseal_boundary import AuthorizationDenied

    payload, digest = _decision_payload(evaluated_at=1000)
    doctored = dict(payload)
    doctored["cautionOptIn"] = True
    provider = _frozen_provider(doctored, digest)

    with pytest.raises(AuthorizationDenied) as excinfo:
        provider._verify_sheet_commitment()
    assert "POLICY_FIELDSET_VIOLATION" in str(excinfo.value)
    assert "cautionOptIn" in str(excinfo.value)


def test_v1_policy_decision_missing_a_namespace_key_is_refused():
    import pytest

    from examples.support.insight_priorseal_boundary import AuthorizationDenied

    payload, digest = _decision_payload(evaluated_at=1000)
    trimmed = {k: v for k, v in payload.items() if k != "reasonCodes"}
    provider = _frozen_provider(trimmed, digest)

    with pytest.raises(AuthorizationDenied) as excinfo:
        provider._verify_sheet_commitment()
    assert "POLICY_FIELDSET_VIOLATION" in str(excinfo.value)
    assert "reasonCodes" in str(excinfo.value)
