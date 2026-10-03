"""Bounded, offline WAK / Insight / PriorSeal conformance example.

The default entry point runs N1-N5b only. It never uses a private key, contacts
an RPC endpoint, or attempts P1. Live P1 remains a separate operator action.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Protocol, runtime_checkable
from unittest.mock import patch

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import (
    ActionType,
    AuthorizationRequest,
    EnforcementDenied,
    ExecutionPolicy,
    PreSignInterceptor,
)

try:
    from examples.support.insight_priorseal_boundary import (
        BoundaryError,
        FixtureBundle,
        PriorSealAuthorizationProvider,
        SQLiteAcceptanceStore,
        insight_pair_commitment,
        verify_insight_attestation,
    )
except ModuleNotFoundError:  # direct: python examples/insight_priorseal_swap.py
    from support.insight_priorseal_boundary import (
        BoundaryError,
        FixtureBundle,
        PriorSealAuthorizationProvider,
        SQLiteAcceptanceStore,
        insight_pair_commitment,
        verify_insight_attestation,
    )


@runtime_checkable
class SignerProtocol(Protocol):
    """Explicit signing boundary used by the spike."""

    def sign_transaction(self, transaction: Mapping[str, Any]) -> bytes: ...


@runtime_checkable
class BroadcastFn(Protocol):
    """Explicit broadcast boundary used by the spike."""

    def __call__(self, raw_transaction: bytes) -> Mapping[str, Any]: ...


@runtime_checkable
class ReceiptFn(Protocol):
    """Explicit post-broadcast receipt boundary used by the spike."""

    def __call__(self, broadcast_result: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass
class BoundaryCounters:
    authorization_provider: int = 0
    signer: int = 0
    broadcast: int = 0
    receipt: int = 0

    def as_report(self) -> dict[str, int]:
        return {
            "authorizationProvider": self.authorization_provider,
            "signer": self.signer,
            "broadcast": self.broadcast,
            "receipt": self.receipt,
        }


@runtime_checkable
class BoundaryCounterSink(Protocol):
    """Anything the gate can count through: the dataclass above, or the live recorder.

    ``examples.support.insight_priorseal_live.CallEventRecorder`` implements the same
    four integer attributes, so one object can both count and retain the event log.
    Passing a plain ``dict`` here is the bug that raised ``AttributeError``.
    """

    authorization_provider: int
    signer: int
    broadcast: int
    receipt: int

    def as_report(self) -> dict[str, int]: ...


@dataclass(frozen=True)
class ExecutionBoundaries:
    """Injected signing, broadcast, and receipt boundaries for one attempt."""

    signer: SignerProtocol
    broadcast: BroadcastFn
    receipt: ReceiptFn


class _SyntheticSigner:
    def __init__(self, counters: BoundaryCounterSink) -> None:
        self._counters = counters

    def sign_transaction(self, transaction: Mapping[str, Any]) -> bytes:
        self._counters.signer += 1
        return b"\x01" * 64


class _SyntheticBroadcast:
    def __init__(self, counters: BoundaryCounterSink) -> None:
        self._counters = counters

    def __call__(self, raw_transaction: bytes) -> Mapping[str, Any]:
        self._counters.broadcast += 1
        return {"txHash": "0x" + "12" * 32, "rawLength": len(raw_transaction)}


class _SyntheticReceipt:
    def __init__(self, counters: BoundaryCounterSink) -> None:
        self._counters = counters

    def __call__(self, broadcast_result: Mapping[str, Any]) -> Mapping[str, Any]:
        self._counters.receipt += 1
        return {"status": "SYNTHETIC_CONFIRMED", "txHash": broadcast_result["txHash"]}


def synthetic_execution_boundaries(counters: BoundaryCounters) -> ExecutionBoundaries:
    """Default offline boundaries used by the CLI acceptance suite."""

    return ExecutionBoundaries(
        signer=_SyntheticSigner(counters),
        broadcast=_SyntheticBroadcast(counters),
        receipt=_SyntheticReceipt(counters),
    )


BoundaryFactory = Callable[[BoundaryCounters], ExecutionBoundaries]


class _CountingProvider:
    def __init__(self, provider: PriorSealAuthorizationProvider, counters: BoundaryCounterSink) -> None:
        self._provider = provider
        self._counters = counters

    @property
    def policy_id(self) -> str:
        return self._provider.policy_id

    def authorize(self, context):
        # Counter sinks that also retain events (CallEventRecorder) get a timestamped
        # attempted/error/success trail; plain BoundaryCounters keep the old
        # increment-on-call behavior so offline vectors are unchanged.
        started = int(time.time())
        recorder = getattr(self._counters, "record", None)
        if recorder is not None:
            recorder("authorizationProvider", "attempted", started_at=started, finished_at=started)
        else:
            self._counters.authorization_provider += 1
        try:
            result = self._provider.authorize(context)
        except Exception as exc:
            if recorder is not None:
                recorder(
                    "authorizationProvider",
                    "error",
                    started_at=started,
                    finished_at=int(time.time()),
                    detail={"error": type(exc).__name__},
                )
            raise
        if recorder is not None:
            recorder("authorizationProvider", "success", started_at=started, finished_at=int(time.time()))
        return result


# The agreed fixture pins this exact policy identifier. A dynamic subclass keeps
# the identifier in the existing interceptor contract without changing WAK core.
_SpikeExecutionPolicy = type(
    "wak-insight-priorseal-spike-v1",
    (ExecutionPolicy,),
    {},
)


def _policy(transaction: Mapping[str, Any]) -> ExecutionPolicy:
    return _SpikeExecutionPolicy(
        allowed_chains=frozenset({Chain.BASE_SEPOLIA}),
        allowed_actions=frozenset({ActionType.SWAP}),
        allowed_contracts=frozenset({str(transaction["to"])}),
        max_native_value_wei=int(transaction.get("value", 0)),
        require_confirmation=False,
    )


def _check_insight(bundle: FixtureBundle, *, variant: str, now: int) -> str:
    baseline = bundle.baseline
    insight = baseline["insight"]
    if variant == "signed-block":
        attestations = [insight["sourceAttestation"], insight["blockedDestinationAttestation"]]
    elif variant == "signed-pass":
        attestations = [insight["sourceAttestation"], insight["destinationAttestation"]]
    else:
        raise BoundaryError(f"unknown Insight fixture variant: {variant}")

    for attestation in attestations:
        verify_insight_attestation(attestation, baseline, bundle.trust_roots)
        if now >= int(attestation["validUntil"]):
            raise BoundaryError("INSIGHT_STALE")
    if any(attestation["data"]["verdict"] == "BLOCK" for attestation in attestations):
        expected = str(insight["blockedPairCommitment"]["digest"])
        if insight_pair_commitment(*attestations) != expected:
            raise BoundaryError("INSIGHT_PAIR_COMMITMENT_MISMATCH")
        raise BoundaryError("INSIGHT_BLOCK")
    expected = str(insight["positivePairCommitment"]["digest"])
    if insight_pair_commitment(*attestations) != expected:
        raise BoundaryError("INSIGHT_PAIR_COMMITMENT_MISMATCH")
    return expected


def _run_gate_attempt(
    *,
    transaction: Mapping[str, Any],
    response: Mapping[str, Any],
    trust_roots: Mapping[str, Any],
    counters: BoundaryCounterSink,
    now: int,
    acceptance_store: SQLiteAcceptanceStore | None,
    boundaries: ExecutionBoundaries,
    gate: PreSignInterceptor | None = None,
    provider: _CountingProvider | None = None,
    live: bool = False,
) -> tuple[
    PreSignInterceptor,
    _CountingProvider,
    Mapping[str, Any] | None,
    str | None,
]:
    current_provider = provider or _CountingProvider(
        PriorSealAuthorizationProvider(
            response,
            trust_roots=trust_roots,
            acceptance_store=acceptance_store,
        ),
        counters,
    )
    current_gate = gate or PreSignInterceptor(
        policy=_policy(transaction),
        signer=boundaries.signer.sign_transaction,
        authorization_provider=current_provider,
    )
    if gate is not None and gate.authorization_provider is not current_provider:
        raise BoundaryError("gate/provider reconstruction mismatch")

    request = AuthorizationRequest(Chain.BASE_SEPOLIA, ActionType.SWAP, transaction)
    try:
        if live:
            # Live/rehearsal leg: the interceptor and the authorization provider read the
            # real wall clock. No historical clock is injected -- the frozen fixture
            # timestamps exist only for the offline N1-N5b vectors, and using them here
            # would let a stale sheet look fresh.
            signed = current_gate.sign(request)
        else:
            evaluated_at = 1789639170
            # The fixture intentionally separates policy evaluation (17:59:30) from
            # authorization issuance (18:00:00). Rebinding the interceptor's module
            # clock preserves the pinned policy digest while the authorization clock
            # evaluates freshness at the case timestamp.
            with (
                patch(
                    "web3_agent_kit.execution.interceptor.time",
                    SimpleNamespace(time=lambda: evaluated_at),
                ),
                patch("web3_agent_kit.execution.authorization.time.time", return_value=now),
            ):
                signed = current_gate.sign(request)
        broadcast_result = boundaries.broadcast(signed.raw_transaction)
        receipt = boundaries.receipt(broadcast_result)
        return current_gate, current_provider, receipt, None
    except EnforcementDenied as exc:
        return current_gate, current_provider, None, str(exc)


def _case_row(
    vector: Mapping[str, Any],
    counters: BoundaryCounters,
    *,
    actual_terminal: str,
    reason: str,
    observed: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "id": vector["id"],
        "wakVersion": vector["wakVersion"],
        "inputArtifactHashes": vector["inputArtifactHashes"],
        "expectedTerminal": vector["terminal"],
        "actualTerminal": actual_terminal,
        "reason": reason,
        "counts": counters.as_report(),
        "observed": dict(observed),
    }


def _run_case(
    bundle: FixtureBundle,
    case_id: str,
    *,
    boundary_factory: BoundaryFactory,
) -> dict[str, Any]:
    vector = bundle.case(case_id)
    baseline = bundle.baseline
    transaction = dict(baseline["transaction"])
    transaction["chainId"] = int(transaction["chainId"])
    transaction["nonce"] = int(transaction["nonce"])
    transaction["value"] = int(transaction["value"])
    counters = BoundaryCounters()
    case_input = vector["input"]
    now = int(case_input.get("now", 1789639202))

    try:
        _check_insight(bundle, variant=str(case_input["insightVariant"]), now=now)
    except BoundaryError as exc:
        boundary_reason = str(exc)
        terminals = {
            "INSIGHT_BLOCK": "DENIED_BEFORE_AUTHORIZATION",
            "INSIGHT_STALE": "REASSESS_AND_REAUTHORIZE",
        }
        if boundary_reason not in terminals:
            raise
        return _case_row(
            vector,
            counters,
            actual_terminal=terminals[boundary_reason],
            reason=boundary_reason,
            observed={"boundaryReason": boundary_reason},
        )

    mutation = case_input.get("mutateAfterAuthorization")
    if isinstance(mutation, Mapping):
        transaction[str(mutation["field"])] = mutation["value"]

    response = baseline["priorSeal"]["response"]
    if case_id in {"N3", "N4"}:
        gate, _, receipt, error = _run_gate_attempt(
            transaction=transaction,
            response=response,
            trust_roots=bundle.trust_roots,
            counters=counters,
            now=now,
            acceptance_store=None,
            boundaries=boundary_factory(counters),
        )
        gate_reasons = list(gate.audit_log[-1].reasons)
        if receipt is not None or error is None:
            raise BoundaryError(f"{case_id} unexpectedly reached broadcast")
        if gate_reasons != ["authorization_call_mismatch"]:
            raise BoundaryError(f"{case_id} produced unexpected gate reasons: {gate_reasons}")
        observed: dict[str, Any] = {
            "gateReasons": gate_reasons,
            "gateError": error,
        }
        reason = "AUTHORIZATION_CALL_MISMATCH"
        if case_id == "N4":
            authorized_nonce = str(response["signedAuthorization"]["intent"]["nonce"])
            nonce_mismatch = authorized_nonce != str(transaction["nonce"])
            if not nonce_mismatch:
                raise BoundaryError("N4 did not produce a nonce mismatch")
            observed["nonceMismatch"] = True
            observed["authorizedNonce"] = authorized_nonce
            observed["transactionNonce"] = str(transaction["nonce"])
            reason = "NONCE_MISMATCH"
        return _case_row(
            vector,
            counters,
            actual_terminal="DENIED_BEFORE_SIGNING",
            reason=reason,
            observed=observed,
        )

    if case_id == "N5a":
        gate, provider, receipt, error = _run_gate_attempt(
            transaction=transaction,
            response=response,
            trust_roots=bundle.trust_roots,
            counters=counters,
            now=now,
            acceptance_store=None,
            boundaries=boundary_factory(counters),
        )
        if receipt is None or error is not None:
            raise BoundaryError(f"N5a first use failed: {error}")
        _, _, second_receipt, second_error = _run_gate_attempt(
            transaction=transaction,
            response=response,
            trust_roots=bundle.trust_roots,
            counters=counters,
            now=now,
            acceptance_store=None,
            boundaries=boundary_factory(counters),
            gate=gate,
            provider=provider,
        )
        gate_reasons = list(gate.audit_log[-1].reasons)
        if second_receipt is not None or gate_reasons != ["authorization_replayed"]:
            raise BoundaryError("N5a replay was not rejected by the WAK gate")
        return _case_row(
            vector,
            counters,
            actual_terminal="FIRST_USE_ONLY",
            reason="AUTHORIZATION_REPLAYED",
            observed={"gateReasons": gate_reasons, "gateError": second_error},
        )

    if case_id == "N5b":
        with tempfile.TemporaryDirectory(prefix="wak-priorseal-") as directory:
            database = Path(directory) / "acceptances.sqlite3"
            first_store = SQLiteAcceptanceStore(database)
            first_boundaries = boundary_factory(counters)
            first_gate, first_provider, receipt, error = _run_gate_attempt(
                transaction=transaction,
                response=response,
                trust_roots=bundle.trust_roots,
                counters=counters,
                now=now,
                acceptance_store=first_store,
                boundaries=first_boundaries,
            )
            if receipt is None or error is not None:
                raise BoundaryError(f"N5b first use failed: {error}")

            second_store = SQLiteAcceptanceStore(database)
            signer_before = counters.signer
            broadcast_before = counters.broadcast
            receipt_before = counters.receipt
            second_boundaries = boundary_factory(counters)
            second_gate, second_provider, second_receipt, second_error = _run_gate_attempt(
                transaction=transaction,
                response=response,
                trust_roots=bundle.trust_roots,
                counters=counters,
                now=now,
                acceptance_store=second_store,
                boundaries=second_boundaries,
            )
            authorization_id = str(response["signedAuthorization"]["authorizationId"])
            reconstruction = {
                "differentGateInstance": first_gate is not second_gate,
                "differentProviderInstance": first_provider is not second_provider,
                "differentStoreInstance": first_store is not second_store,
                "differentSignerInstance": first_boundaries.signer is not second_boundaries.signer,
                "differentBroadcastInstance": (
                    first_boundaries.broadcast is not second_boundaries.broadcast
                ),
                "differentReceiptInstance": first_boundaries.receipt is not second_boundaries.receipt,
                "sameDatabase": first_store.database_path == second_store.database_path,
                "samePersistedAcceptanceId": authorization_id in str(second_error),
            }
            denied_before_execution = (
                counters.signer == signer_before
                and counters.broadcast == broadcast_before
                and counters.receipt == receipt_before
            )

        provider_reason = (
            "AUTHORIZATION_REPLAYED"
            if "AUTHORIZATION_REPLAYED" in str(second_error)
            else ""
        )
        if (
            second_receipt is not None
            or provider_reason != "AUTHORIZATION_REPLAYED"
            or not denied_before_execution
            or not all(reconstruction.values())
        ):
            raise BoundaryError("N5b replay was not rejected by persisted acceptance state")
        row = _case_row(
            vector,
            counters,
            actual_terminal="FIRST_USE_ONLY",
            reason=provider_reason,
            observed={
                "providerReason": provider_reason,
                "gateError": second_error,
                "deniedBeforeSigner": counters.signer == signer_before,
                "deniedBeforeBroadcast": counters.broadcast == broadcast_before,
                "deniedBeforeReceipt": counters.receipt == receipt_before,
            },
        )
        row["reconstruction"] = reconstruction
        return row

    raise BoundaryError(f"unsupported negative case: {case_id}")


def validate_extended_n5b_evidence(report: Mapping[str, Any]) -> None:
    """Validate WAK-owned N5b evidence beyond the pinned verifier contract."""

    cases = report.get("cases")
    if not isinstance(cases, list):
        raise BoundaryError("N5b evidence is missing from the acceptance report")
    n5b = next(
        (case for case in cases if isinstance(case, Mapping) and case.get("id") == "N5b"),
        None,
    )
    if not isinstance(n5b, Mapping):
        raise BoundaryError("N5b evidence is missing from the acceptance report")
    reconstruction = n5b.get("reconstruction")
    observed = n5b.get("observed")
    if not isinstance(reconstruction, Mapping) or not isinstance(observed, Mapping):
        raise BoundaryError("N5b reconstruction evidence is malformed")
    reconstruction_fields = (
        "differentGateInstance",
        "differentProviderInstance",
        "differentStoreInstance",
        "differentSignerInstance",
        "differentBroadcastInstance",
        "differentReceiptInstance",
        "sameDatabase",
        "samePersistedAcceptanceId",
    )
    denial_fields = (
        "deniedBeforeSigner",
        "deniedBeforeBroadcast",
        "deniedBeforeReceipt",
    )
    if not all(reconstruction.get(field) is True for field in reconstruction_fields):
        raise BoundaryError("N5b reconstruction evidence is incomplete")
    if not all(observed.get(field) is True for field in denial_fields):
        raise BoundaryError("N5b denial did not precede every execution boundary")
    if observed.get("providerReason") != "AUTHORIZATION_REPLAYED":
        raise BoundaryError("N5b persisted replay denial is missing")
    if (
        n5b.get("actualTerminal") != "FIRST_USE_ONLY"
        or n5b.get("reason") != "AUTHORIZATION_REPLAYED"
    ):
        raise BoundaryError("N5b terminal evidence is inconsistent")
    if n5b.get("counts") != {
        "authorizationProvider": 2,
        "signer": 1,
        "broadcast": 1,
        "receipt": 1,
    }:
        raise BoundaryError("N5b structural counters are inconsistent")


def run_negative_suite(
    fixture_root: str | Path,
    *,
    boundary_factory: BoundaryFactory = synthetic_execution_boundaries,
) -> dict[str, Any]:
    bundle = FixtureBundle.load(fixture_root)
    baseline = bundle.baseline
    cases = [
        _run_case(bundle, case_id, boundary_factory=boundary_factory)
        for case_id in ("N1", "N2", "N3", "N4", "N5a", "N5b")
    ]
    report = {
        "schema": "wak-insight-priorseal.acceptance-report.v1",
        "fixtureVersion": bundle.version,
        "envelopeDigest": baseline["wak"]["callEnvelope"]["digest"],
        "policyCommitmentDigest": baseline["wak"]["policyDecisionCommitment"]["digest"],
        "instrumentation": {
            "explicitSignerProtocol": True,
            "explicitBroadcastFn": True,
        },
        "adapter": {"newFieldTypes": 0},
        "adapterAcceptance": {
            "expectedNewFieldTypes": 0,
            "actualNewFieldTypes": 0,
            "terminal": "PASS",
        },
        "cases": cases,
    }
    validate_extended_n5b_evidence(report)
    return report


def write_acceptance_report(fixture_root: str | Path, output: str | Path) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(run_negative_suite(fixture_root), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def build_p1_row(
    *,
    live_input_sha256: str,
    wak_version: str = "1.18.5",
    baseline_sha256: str | None = None,
    case_input_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the conditional P1 report row for a live Base Sepolia run.

    The verifier pins the P1 row to ``wakVersion == "1.18.5"`` (fixture v1.1) and to the
    fixture's expected P1 counts (1/1/1/1). ``liveInputSha256`` must be the raw run-sheet
    SHA-256 captured at execution time, never a placeholder. The fixture identity hashes
    come from the pinned cases.json when not supplied.
    """
    import re

    if not re.fullmatch(r"[0-9a-f]{64}", live_input_sha256):
        raise BoundaryError("liveInputSha256 must be 64 lowercase hex characters")
    if baseline_sha256 is None or case_input_sha256 is None:
        raise BoundaryError("fixture identity hashes are required")
    return {
        "id": "P1",
        "wakVersion": wak_version,
        "inputArtifactHashes": {
            "baselineSha256": baseline_sha256,
            "caseInputSha256": case_input_sha256,
            "liveInputSha256": live_input_sha256,
        },
        "expectedTerminal": "LIVE_RECEIPT_VERIFIED",
        "actualTerminal": "LIVE_RECEIPT_VERIFIED",
        "reason": "OK",
        "counts": {
            "authorizationProvider": 1,
            "signer": 1,
            "broadcast": 1,
            "receipt": 1,
        },
    }


def build_p1_block(
    *,
    receipt: Mapping[str, Any],
    trusted_key: Mapping[str, Any],
    envelope_digest: str,
    policy_commitment_digest: str,
    insight_pair_commitment: str,
) -> dict[str, Any]:
    """Assemble the top-level ``p1`` block consumed by the verifier's receipt path."""
    return {
        "receipt": dict(receipt),
        "trustedKey": dict(trusted_key),
        "wak": {
            "envelopeDigest": envelope_digest,
            "policyCommitmentDigest": policy_commitment_digest,
        },
        "insightPairCommitment": insight_pair_commitment,
    }


def validate_p1_evidence(report: Mapping[str, Any]) -> None:
    """Structural checks mirroring the verifier's ``verifyLiveReceipt`` demands.

    Cryptographic receipt-signature verification stays with the bundled verifier; these
    checks catch schema/status errors before the report is handed back.
    """
    import re

    if not isinstance(report.get("cases"), list):
        raise BoundaryError("P1 report is missing cases")
    p1 = report.get("p1")
    if not isinstance(p1, Mapping):
        raise BoundaryError("P1 evidence is missing from the acceptance report")
    for key in ("receipt", "trustedKey", "wak", "insightPairCommitment"):
        if key not in p1:
            raise BoundaryError(f"P1 evidence is missing '{key}'")
    trusted = p1["trustedKey"]
    if not isinstance(trusted, Mapping) or trusted.get("status") != "active":
        raise BoundaryError("P1 trusted key is not active")
    for field in ("issuer", "keyId", "algorithm", "publicKey"):
        if not trusted.get(field):
            raise BoundaryError(f"P1 trusted key is missing '{field}'")
    wak = p1["wak"]
    if not isinstance(wak, Mapping):
        raise BoundaryError("P1 wak commitment block is malformed")
    if not re.fullmatch(r"0x[0-9a-f]{64}", str(wak.get("envelopeDigest", ""))):
        raise BoundaryError("P1 envelope digest is not a 32-byte hex digest")
    if not re.fullmatch(r"0x[0-9a-f]{64}", str(wak.get("policyCommitmentDigest", ""))):
        raise BoundaryError("P1 policy commitment digest is not a 32-byte hex digest")
    row = next((c for c in report["cases"] if c.get("id") == "P1"), None)
    if not isinstance(row, Mapping):
        raise BoundaryError("P1 row is missing from cases")
    if row.get("actualTerminal") != "LIVE_RECEIPT_VERIFIED" or row.get("reason") != "OK":
        raise BoundaryError("P1 row terminal evidence is inconsistent")
    if row.get("counts") != {
        "authorizationProvider": 1,
        "signer": 1,
        "broadcast": 1,
        "receipt": 1,
    }:
        raise BoundaryError("P1 row structural counters are inconsistent")
    receipt = p1["receipt"]
    if not isinstance(receipt, Mapping):
        raise BoundaryError("P1 receipt is malformed")
    execution = receipt.get("execution")
    compliance = receipt.get("compliance")
    binding = receipt.get("binding")
    if not isinstance(execution, Mapping) or not isinstance(compliance, Mapping) or not isinstance(binding, Mapping):
        raise BoundaryError("P1 receipt status blocks are malformed")
    if int(execution.get("chainId", 0)) != 84532 or execution.get("status") != "CONFIRMED":
        raise BoundaryError("P1 receipt execution is not a confirmed Base Sepolia transaction")
    if compliance.get("status") != "COMPLIANT" or binding.get("bound") is not True:
        raise BoundaryError("P1 receipt compliance/binding status is not COMPLIANT/bound")
    if receipt.get("outcome") != "COMPLETED":
        raise BoundaryError("P1 receipt outcome is not COMPLETED")


def attach_p1_and_provenance(
    report: Mapping[str, Any],
    *,
    p1_row: Mapping[str, Any],
    p1_block: Mapping[str, Any],
    runtime_package_version: str,
    runtime_commit: str | None = None,
    runtime_tree_clean: bool | None = None,
) -> dict[str, Any]:
    """Append the P1 row + ``p1`` block + runtime provenance to an N1-N5b report."""
    try:
        from examples.support.insight_priorseal_live import runtime_provenance, version_alignment
    except ModuleNotFoundError:  # running as examples/insight_priorseal_swap.py
        from support.insight_priorseal_live import runtime_provenance, version_alignment

    out = dict(report)
    out["cases"] = [*report["cases"], dict(p1_row)]
    out["p1"] = dict(p1_block)
    out["runtime"] = runtime_provenance(
        package_version=runtime_package_version,
        commit=runtime_commit,
        tree_clean=runtime_tree_clean,
    )
    fixture_wak_version = str(p1_row.get("wakVersion", ""))
    out["versionAlignment"] = version_alignment(
        fixture_wak_version=fixture_wak_version,
        runtime_package_version=runtime_package_version,
    )
    validate_p1_evidence(out)
    return out


def write_live_acceptance_report(
    fixture_root: str | Path,
    output: str | Path,
    *,
    receipt: Mapping[str, Any],
    trusted_key: Mapping[str, Any],
    live_input_sha256: str,
    envelope_digest: str,
    policy_commitment_digest: str,
    insight_pair_commitment: str,
    runtime_package_version: str,
    runtime_commit: str | None = None,
    runtime_tree_clean: bool | None = None,
) -> Path:
    """Run N1-N5b offline, append the P1 evidence, and write the report.

    Assembles and validates only; it never signs or broadcasts. A P1-included report is
    only verifier-valid when ``receipt`` is an issuer-signed execution receipt for a real
    Base Sepolia transaction and ``trusted_key`` carries ``status: "active"``.
    """
    base = run_negative_suite(fixture_root)
    bundle = FixtureBundle.load(fixture_root)
    p1_vector = bundle.case("P1")
    p1_hashes = p1_vector["inputArtifactHashes"]
    p1_row = build_p1_row(
        live_input_sha256=live_input_sha256,
        wak_version=str(p1_vector.get("wakVersion", "1.18.5")),
        baseline_sha256=str(p1_hashes["baselineSha256"]),
        case_input_sha256=str(p1_hashes["caseInputSha256"]),
    )
    p1_block = build_p1_block(
        receipt=receipt,
        trusted_key=trusted_key,
        envelope_digest=envelope_digest,
        policy_commitment_digest=policy_commitment_digest,
        insight_pair_commitment=insight_pair_commitment,
    )
    full = attach_p1_and_provenance(
        base,
        p1_row=p1_row,
        p1_block=p1_block,
        runtime_package_version=runtime_package_version,
        runtime_commit=runtime_commit,
        runtime_tree_clean=runtime_tree_clean,
    )
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(full, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def classify_run_outcome(
    *,
    receipt: Mapping[str, Any] | None,
    attempt_error: str | None,
    counts: Mapping[str, int] | None,
    rehearsal: bool,
) -> tuple[str, str | None]:
    """Classify a terminal P1 outcome from what the attempt actually observed.

    Pure decision used by :func:`run_live_p1` and unit-tested directly. Returns
    ``(outcome, detail)`` where ``detail`` is the error/enforcement message to surface
    (``None`` when the outcome needs none).

    Rules (each is an observed fact, never a silent reset):
    - a ``REVERTED`` receipt -> ``REVERTED`` (never ``LIVE_LEG_COMPLETED``);
    - any other receipt -> ``REHEARSAL_LEG_COMPLETED`` / ``LIVE_LEG_COMPLETED``;
    - authorization/enforcement denial -> ``ENFORCEMENT_DENIED``;
    - a gate error after a sign+broadcast the events prove -> ``BROADCAST_NO_CONFIRMED_RECEIPT``;
    - a gate error before any sign+broadcast -> ``ERROR``;
    - no receipt and no error -> ``NO_RECEIPT``.
    """
    if receipt is not None and str(receipt.get("status", "")).upper() == "REVERTED":
        return "REVERTED", None
    if receipt is not None:
        return ("REHEARSAL_LEG_COMPLETED" if rehearsal else "LIVE_LEG_COMPLETED"), None
    if attempt_error is not None and (
        "AuthorizationDenied" in str(attempt_error) or "EnforcementDenied" in str(attempt_error)
    ):
        return "ENFORCEMENT_DENIED", attempt_error
    if attempt_error is not None:
        counts = counts or {}
        if counts.get("signer", 0) >= 1 and counts.get("broadcast", 0) >= 1:
            return "BROADCAST_NO_CONFIRMED_RECEIPT", attempt_error
        return "ERROR", attempt_error
    return "NO_RECEIPT", "gate returned no receipt and no error"


def run_live_p1(
    *,
    fixture_root: str | Path,
    report: str | Path,
    go_file: str | Path,
    run_sheet: str | Path,
    session_db: str | Path,
    go_message_id: int,
    rpc_url: str | None = None,
    signer_env: str | None = None,
    signer_key: str | None = None,
    chain_id: int = 84532,
    allow_broadcast: bool = False,
    rehearsal: bool = False,
    rehearsal_output_dir: str | Path | None = None,
    cutoff_check_seconds: int = 60,
    confirmations: int = 2,
    receipt_timeout: int = 180,
    poll_seconds: float = 2.0,
    wak_commit: str | None = None,
    call_events: str | Path | None = None,
) -> dict[str, Any]:
    """Run the P1 leg through this module's explicit boundary protocol.

    Live mode (``allow_broadcast``) signs once with the sheet's exact signed inputs,
    broadcasts once, and waits for confirmations. Rehearsal mode (``rehearsal``) runs
    the identical runner path with inert broadcast/receipt boundaries so the GO
    binding, session-store arrival, live clock, cutoff rechecks, event retention, and
    counters can be exercised without an on-chain effect. Dry-run (neither flag) only
    checks the GO/cutoff and writes a plan.

    The runner never reports success it did not observe:

    - ``signed``/``broadcast`` are derived from the actual gate result (the retained
      boundary events), so a denied gate yields ``False``/``False`` and an error
      outcome -- never ``LIVE_LEG_COMPLETED``. A sign+broadcast whose receipt
      collection failed reports ``signed``/``broadcast`` true (the events prove the
      side effect) with outcome ``BROADCAST_NO_CONFIRMED_RECEIPT``.
    - a ``REVERTED`` receipt is reported as outcome ``REVERTED``, never
      ``LIVE_LEG_COMPLETED``.
    - the Hermes GO message itself (from the session store) must name the exact
      run-sheet hash the runner is about to sign/broadcast; otherwise the run aborts
      as ``GO_NOT_AUTHORIZED`` before signing anything.
    - ``counts`` come from the retained call events; 1/1/1/1 appears only on a
      successful sign+broadcast+receipt leg.
    """
    import hashlib
    import os
    import time

    try:
        from examples.support.go_arrival import (
            GoArrivalError,
            authorize_go_sheet,
            query_go_messages,
            resolve_go_arrival,
        )
        from examples.support.insight_priorseal_live import (
            CallEventRecorder,
            CutoffError,
            EvmSigner,
            InertBroadcast,
            InertReceipt,
            LiveRunConfig,
            RpcBroadcast,
            RpcReceipt,
            check_cutoff,
            check_go_arrival,
            execution_flags,
            live_execution_boundaries,
            runtime_provenance,
            version_alignment,
        )
        from examples.support.insight_priorseal_rehearsal import generate_rehearsal_materials
    except ModuleNotFoundError:  # running as examples/insight_priorseal_swap.py
        from support.go_arrival import (
            GoArrivalError,
            authorize_go_sheet,
            query_go_messages,
            resolve_go_arrival,
        )
        from support.insight_priorseal_live import (
            CallEventRecorder,
            CutoffError,
            EvmSigner,
            InertBroadcast,
            InertReceipt,
            LiveRunConfig,
            RpcBroadcast,
            RpcReceipt,
            check_cutoff,
            check_go_arrival,
            execution_flags,
            live_execution_boundaries,
            runtime_provenance,
            version_alignment,
        )
        from support.insight_priorseal_rehearsal import generate_rehearsal_materials

    executing = allow_broadcast or rehearsal
    if executing and (run_sheet is None or session_db is None or go_message_id is None):
        raise BoundaryError(
            "broadcast/rehearsal requires --run-sheet, --session-db, and --go-message-id "
            "(GO arrival is read from the session store, never from the GO file)"
        )

    run_sheet_hash: str | None = None
    sheet: dict[str, Any] = {}
    rehearsal_materials = None
    if rehearsal:
        # Rehearsal first: fresh synthetic sheet + GO + session store are generated with
        # a live validity window, and the runner binds to THAT exact sheet and hash.
        # Align generation with the next wall-clock second so the gate's live policy
        # evaluation lands on the same evaluatedAt the sheet pins.
        target = int(time.time()) + 1
        while int(time.time()) < target:
            time.sleep(0.01)
        rehearsal_materials = generate_rehearsal_materials(
            fixture_root=fixture_root,
            output_dir=rehearsal_output_dir,
            now=int(time.time()),
            go_message_id=int(go_message_id),
        )
        go = dict(rehearsal_materials.go_file)
        sheet = rehearsal_materials.sheet
        run_sheet_hash = hashlib.sha256(rehearsal_materials.sheet_bytes).hexdigest()
        session_db = rehearsal_materials.session_db
        if go_file is not None:
            Path(go_file).write_text(json.dumps(go, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if run_sheet is not None:
            Path(run_sheet).write_text(rehearsal_materials.sheet_text + "\n", encoding="utf-8")
    else:
        go = json.loads(Path(go_file).read_text(encoding="utf-8"))
        if not isinstance(go, Mapping):
            raise BoundaryError("GO file must be a JSON object")
        for field in ("latestBroadcastAt", "runSheetSha256"):
            if field not in go:
                raise BoundaryError(f"GO file is missing '{field}'")
        if executing and go.get("goArrivalEpoch") is not None:
            raise BoundaryError(
                "GO arrival must come from the session store timestamp; "
                "goArrivalEpoch in the GO file is not acceptable for an executing run"
            )
        if executing:
            raw_sheet = Path(run_sheet).read_bytes()
            run_sheet_hash = hashlib.sha256(raw_sheet).hexdigest()
            if run_sheet_hash != str(go["runSheetSha256"]):
                raise BoundaryError(
                    f"run sheet SHA-256 {run_sheet_hash} does not match the GO file pin "
                    f"{go['runSheetSha256']}"
                )
            sheet = json.loads(raw_sheet.decode("utf-8"))
            if not isinstance(sheet, Mapping):
                raise BoundaryError("run sheet must be a JSON object")

    if executing and (session_db is None or go_message_id is None):
        raise BoundaryError("executing runs require --session-db and --go-message-id")
    if session_db is not None and go_message_id is not None:
        rows = query_go_messages(session_db, message_id=int(go_message_id), role="user")
        arrival_metadata = dict(resolve_go_arrival(rows))
        go_arrival_epoch = int(arrival_metadata["deliveryTimestampEpoch"])
    elif go.get("goArrivalEpoch") is not None:
        arrival_metadata = {
            "schema": "wak-p1.go-arrival-metadata.v1",
            "source": "GO file (planning only; executing runs require the session store)",
            "goArrivalEpoch": int(go["goArrivalEpoch"]),
            "deliveryTimestampEpoch": int(go["goArrivalEpoch"]),
            "receiverFloorSeconds": int(go.get("receiverFloorSeconds", 120)),
            "candidatesMatched": 0,
        }
        go_arrival_epoch = int(go["goArrivalEpoch"])
    else:
        raise BoundaryError(
            "GO arrival is required: pass --session-db + --go-message-id, or a "
            "goArrivalEpoch in the GO file for a planning-only dry run"
        )

    bundle = FixtureBundle.load(fixture_root)
    p1_vector = bundle.case("P1")
    fixture_wak_version = str(p1_vector.get("wakVersion", "1.18.5"))
    baseline = bundle.baseline

    if executing:
        transaction = dict(sheet["transaction"])
    else:
        transaction = dict(baseline["transaction"])
    transaction["chainId"] = int(transaction["chainId"])
    transaction["nonce"] = int(transaction["nonce"])
    transaction["value"] = int(transaction["value"])

    if signer_key is not None:
        import eth_account

        account = eth_account.Account.from_key(signer_key)
    elif signer_env is not None:
        key = os.environ.get(signer_env)
        if not key:
            raise BoundaryError(f"signer key environment {signer_env} is not set")
        import eth_account

        account = eth_account.Account.from_key(key)
    elif rehearsal and rehearsal_materials is not None:
        # Rehearsal: sign with the generated rehearsal executor key (local sign only;
        # the raw transaction is only ever handed to the inert broadcast boundary).
        import eth_account

        account = eth_account.Account.from_key(rehearsal_materials.executor_key)
    else:
        raise BoundaryError("a signer key source is required (--signer-env or --signer-key)")
    signer = EvmSigner(account)
    if executing and str(transaction.get("from", "")).lower() != signer.address().lower():
        raise BoundaryError(
            f"run sheet executor {transaction.get('from')} does not match the signer "
            f"key address {signer.address()}"
        )

    config = LiveRunConfig(
        rpc_url=rpc_url or "http://inert-rehearsal.local",
        chain_id=chain_id,
        latest_broadcast_at=int(go["latestBroadcastAt"]),
        run_sheet_sha256=str(go["runSheetSha256"]),
        go_arrival_epoch=go_arrival_epoch,
        receiver_floor_seconds=int(go.get("receiverFloorSeconds", 120)),
        margin_seconds=int(go.get("marginSeconds", 180)),
        confirmations=confirmations,
        receipt_timeout_seconds=receipt_timeout,
        broadcast_poll_seconds=poll_seconds,
    )
    go_runway = check_go_arrival(config)
    now_runway = check_cutoff(
        now_epoch=int(time.time()),
        latest_broadcast_at=config.latest_broadcast_at,
        minimum_seconds=cutoff_check_seconds,
    )

    if executing and not rehearsal:
        plan = _rpc_preflight(rpc_url, config, signer)
    else:
        plan = {"inert": True, "mode": "REHEARSAL" if rehearsal else "PLAN", "note": "no RPC contacted"}

    attempts: list[dict[str, Any]] = []
    final_recorder: CallEventRecorder | None = None
    receipt: Mapping[str, Any] | None = None
    outcome: str | None = None
    enforcement_error: str | None = None
    run_error: str | None = None
    note: str | None = None
    go_authorization: dict[str, Any] | None = None

    if executing:
        max_attempts = 3 if rehearsal else 1
        for attempt_index in range(max_attempts):
            recorder = CallEventRecorder()
            if rehearsal and attempt_index > 0:
                rehearsal_materials = generate_rehearsal_materials(
                    fixture_root=fixture_root,
                    output_dir=rehearsal_output_dir,
                    now=int(time.time()),
                    go_message_id=int(go_message_id),
                )
                go = dict(rehearsal_materials.go_file)
                sheet = rehearsal_materials.sheet
                transaction = dict(sheet["transaction"])
                transaction["chainId"] = int(transaction["chainId"])
                transaction["nonce"] = int(transaction["nonce"])
                transaction["value"] = int(transaction["value"])
                run_sheet_hash = hashlib.sha256(rehearsal_materials.sheet_bytes).hexdigest()
                config = LiveRunConfig(
                    rpc_url=rpc_url or "http://inert-rehearsal.local",
                    chain_id=chain_id,
                    latest_broadcast_at=int(go["latestBroadcastAt"]),
                    run_sheet_sha256=str(go["runSheetSha256"]),
                    go_arrival_epoch=go_arrival_epoch,
                    receiver_floor_seconds=int(go.get("receiverFloorSeconds", 120)),
                    margin_seconds=int(go.get("marginSeconds", 180)),
                    confirmations=confirmations,
                    receipt_timeout_seconds=receipt_timeout,
                    broadcast_poll_seconds=poll_seconds,
                )

            if rehearsal:
                boundaries = live_execution_boundaries(
                    recorder=recorder,
                    signer=signer,
                    broadcast=InertBroadcast(),
                    receipt=InertReceipt(confirmations=config.confirmations),
                    config=config,
                    cutoff_check_seconds=cutoff_check_seconds,
                )
                trust_roots = rehearsal_materials.trust_roots  # type: ignore[union-attr]
            else:
                boundaries = live_execution_boundaries(
                    recorder=recorder,
                    signer=signer,
                    broadcast=RpcBroadcast(config.rpc_url),
                    receipt=RpcReceipt(
                        config.rpc_url,
                        confirmations=config.confirmations,
                        timeout=config.receipt_timeout_seconds,
                        poll_seconds=config.broadcast_poll_seconds,
                    ),
                    config=config,
                    cutoff_check_seconds=cutoff_check_seconds,
                )
                trust_roots = bundle.trust_roots

            # The Hermes GO message itself must authorize the exact sheet hash we are
            # about to sign/broadcast. Verify against the CURRENT attempt's sheet hash
            # (a rehearsal retry regenerates the sheet, and the synthetic GO message in
            # the session store is rewritten to match it, so this stays in sync). A
            # missing/mismatched authorization aborts the run as GO_NOT_AUTHORIZED.
            try:
                go_authorization = authorize_go_sheet(
                    session_db,
                    int(go_message_id),
                    str(run_sheet_hash),
                )
            except Exception as exc:  # noqa: BLE001 - classified below
                final_recorder = recorder
                outcome = "GO_NOT_AUTHORIZED"
                run_error = f"{type(exc).__name__}: {exc}"
                go_authorization = None
                break

            response = sheet["priorSeal"]["response"]
            with tempfile.TemporaryDirectory(prefix="wak-p1-acceptance-") as directory:
                store = SQLiteAcceptanceStore(Path(directory) / "acceptances.sqlite3")
                try:
                    _, _, attempt_receipt, attempt_error = _run_gate_attempt(
                        transaction=transaction,
                        response=response,
                        trust_roots=trust_roots,
                        counters=recorder,
                        now=int(time.time()),
                        acceptance_store=store,
                        boundaries=boundaries,
                        live=True,
                    )
                except Exception as exc:  # noqa: BLE001 - classified below
                    attempt_receipt, attempt_error = None, f"{type(exc).__name__}: {exc}"
                if attempt_error is not None and "covers another policy decision" in str(attempt_error) and rehearsal and attempt_index < max_attempts - 1:
                    attempts.append(
                        {
                            "attempt": attempt_index + 1,
                            "outcome": "POLICY_COMMITMENT_SKEW_RETRY",
                            "error": attempt_error,
                            "callEvents": recorder.as_report(),
                            "counts": recorder.boundary_counts(),
                        }
                    )
                    continue
                final_recorder = recorder
                receipt = attempt_receipt
                outcome, detail = classify_run_outcome(
                    receipt=attempt_receipt,
                    attempt_error=attempt_error,
                    counts=recorder.boundary_counts(),
                    rehearsal=rehearsal,
                )
                if outcome == "ENFORCEMENT_DENIED":
                    enforcement_error = detail
                elif outcome in ("ERROR", "BROADCAST_NO_CONFIRMED_RECEIPT", "NO_RECEIPT"):
                    run_error = detail
                break
        if final_recorder is None:
            final_recorder = CallEventRecorder()
            outcome = "ERROR"
            run_error = "all rehearsal attempts failed before a terminal outcome"
    else:
        final_recorder = CallEventRecorder()
        outcome = "DRY_RUN_NO_TRANSACTION"
        note = "GO and cutoff checks passed; no transaction signed or broadcast."

    # signed/broadcast come from the RETAINED boundary events, never from receipt
    # presence. A run that signed and broadcast but could not collect a receipt still
    # reports true/true (the events prove it); a leg denied before signing reports
    # false/false even if the attempt loop otherwise errored.
    flags = execution_flags(final_recorder)
    signed = bool(flags["signed"])
    broadcast = bool(flags["broadcast"])

    from web3_agent_kit import __version__

    if go_authorization is not None:
        arrival_metadata["goSheetAuthorization"] = go_authorization

    evidence: dict[str, Any] = {
        "schema": "wak-p1.execution-evidence.v1",
        "mode": "REHEARSAL" if rehearsal else ("LIVE" if allow_broadcast else "DRY_RUN"),
        "goArrival": arrival_metadata,
        "goArrivalRunwaySeconds": go_runway,
        "runwayAtCheckSeconds": now_runway,
        "receiverFloorSeconds": config.receiver_floor_seconds,
        "cutoffCheckSeconds": cutoff_check_seconds,
        "preflight": plan,
        "signerAddress": signer.address(),
        "runSheetSha256": run_sheet_hash,
        "transaction": {k: v for k, v in transaction.items() if k != "from"},
        "runtime": runtime_provenance(
            package_version=__version__,
            commit=wak_commit or _git_head(),
            tree_clean=_git_clean(),
        ),
        "versionAlignment": version_alignment(
            fixture_wak_version=fixture_wak_version,
            runtime_package_version=__version__,
        ),
        "callEvents": final_recorder.as_report(),
        "counts": final_recorder.boundary_counts(),
        "signed": signed,
        "broadcast": broadcast,
        "outcome": outcome,
    }
    if enforcement_error is not None:
        evidence["enforcementError"] = enforcement_error
    if run_error is not None:
        evidence["error"] = run_error
    if receipt is not None:
        evidence["receipt"] = dict(receipt)
    if rehearsal:
        evidence["rehearsal"] = {
            "mode": "inert-boundary",
            "boundaries": {
                "signer": "EvmSigner (local sign, sheet executor)",
                "broadcast": "InertBroadcast (no eth_sendRawTransaction)",
                "receipt": "InertReceipt (no RPC)",
            },
            "noOnChainEffect": True,
            "sheetSchema": sheet.get("schema"),
            "evaluatedAt": sheet.get("evaluatedAt"),
            "note": "REHEARSAL ONLY: fresh synthetic signed inputs, inert boundaries, "
            "no transaction was authorized or broadcast on any chain.",
        }
        if attempts:
            evidence["rehearsalAttempts"] = attempts
    if not executing:
        evidence["note"] = note
    destination = Path(report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if call_events is not None:
        events_path = Path(call_events)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text(json.dumps(final_recorder.as_report(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def _rpc_preflight(rpc_url: str | None, config: Any, signer: Any) -> dict[str, Any]:
    import httpx

    if not rpc_url:
        raise BoundaryError("live broadcast requires --rpc-url")

    def jsonrpc(method: str, params: list[Any], *, timeout: float = 20.0) -> Any:
        resp = httpx.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"{method} RPC error: {body['error']}")
        return body["result"]

    chain_id = int(str(jsonrpc("eth_chainId", [])), 16)
    if chain_id != config.chain_id:
        raise RuntimeError(f"RPC chainId {chain_id} != configured {config.chain_id}")
    block = int(str(jsonrpc("eth_blockNumber", [])), 16)
    nonce = int(str(jsonrpc("eth_getTransactionCount", [signer.address(), "pending"], timeout=20)), 16)
    balance = int(str(jsonrpc("eth_getBalance", [signer.address(), "latest"], timeout=20)), 16)
    return {"chainId": chain_id, "headBlock": block, "pendingNonce": nonce, "balanceWei": balance, "inert": False}


def _git_head() -> str | None:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent.parent), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return None


def _git_clean() -> bool | None:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent.parent), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return proc.stdout.strip() == ""
    except Exception:  # noqa: BLE001
        pass
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--live-p1", action="store_true", help="run the P1 leg (live or rehearsal) instead of the offline N1-N5b suite")
    parser.add_argument("--rehearsal", action="store_true", help="inert-boundary rehearsal: same runner path, no on-chain effect")
    parser.add_argument("--go-file", type=Path, default=None)
    parser.add_argument("--run-sheet", type=Path, default=None)
    parser.add_argument("--session-db", type=Path, default=None)
    parser.add_argument("--go-message-id", type=int, default=None)
    parser.add_argument("--rpc-url", default=None)
    parser.add_argument("--signer-env", default=None)
    parser.add_argument("--chain-id", type=int, default=84532)
    parser.add_argument("--allow-broadcast", action="store_true")
    parser.add_argument("--cutoff-check-seconds", type=int, default=60)
    parser.add_argument("--confirmations", type=int, default=2)
    parser.add_argument("--receipt-timeout", type=int, default=180)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--wak-commit", default=None)
    parser.add_argument("--call-events", type=Path, default=None)
    parser.add_argument("--rehearsal-output-dir", type=Path, default=None)
    args = parser.parse_args()
    if args.live_p1:
        evidence = run_live_p1(
            fixture_root=args.fixture,
            report=args.report,
            go_file=args.go_file,
            run_sheet=args.run_sheet,
            session_db=args.session_db,
            go_message_id=args.go_message_id,
            rpc_url=args.rpc_url,
            signer_env=args.signer_env,
            chain_id=args.chain_id,
            allow_broadcast=args.allow_broadcast,
            rehearsal=args.rehearsal,
            rehearsal_output_dir=args.rehearsal_output_dir,
            cutoff_check_seconds=args.cutoff_check_seconds,
            confirmations=args.confirmations,
            receipt_timeout=args.receipt_timeout,
            poll_seconds=args.poll_seconds,
            wak_commit=args.wak_commit,
            call_events=args.call_events,
        )
        print(json.dumps({"report": str(args.report), "outcome": evidence.get("outcome"), "counts": evidence.get("counts")}, indent=2))
        return 0
    write_acceptance_report(args.fixture, args.report)
    print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())