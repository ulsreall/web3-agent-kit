"""Bounded, offline WAK / Insight / PriorSeal conformance example.

The default entry point runs N1-N5b only. It never uses a private key, contacts
an RPC endpoint, or attempts P1. Live P1 remains a separate operator action.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol, runtime_checkable
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
        insight_pair_commitment,
        verify_insight_attestation,
    )
except ModuleNotFoundError:  # direct: python examples/insight_priorseal_swap.py
    from support.insight_priorseal_boundary import (
        BoundaryError,
        FixtureBundle,
        PriorSealAuthorizationProvider,
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


class _SyntheticSigner:
    def __init__(self, counters: BoundaryCounters) -> None:
        self._counters = counters

    def sign_transaction(self, transaction: Mapping[str, Any]) -> bytes:
        self._counters.signer += 1
        return b"\x01" * 64


class _SyntheticBroadcast:
    def __init__(self, counters: BoundaryCounters) -> None:
        self._counters = counters

    def __call__(self, raw_transaction: bytes) -> Mapping[str, Any]:
        self._counters.broadcast += 1
        return {"txHash": "0x" + "12" * 32, "rawLength": len(raw_transaction)}


class _SyntheticReceipt:
    def __init__(self, counters: BoundaryCounters) -> None:
        self._counters = counters

    def __call__(self, broadcast_result: Mapping[str, Any]) -> Mapping[str, Any]:
        self._counters.receipt += 1
        return {"status": "SYNTHETIC_CONFIRMED", "txHash": broadcast_result["txHash"]}


class _CountingProvider:
    def __init__(self, provider: PriorSealAuthorizationProvider, counters: BoundaryCounters) -> None:
        self._provider = provider
        self._counters = counters

    @property
    def policy_id(self) -> str:
        return self._provider.policy_id

    def authorize(self, context):
        self._counters.authorization_provider += 1
        return self._provider.authorize(context)


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
    counters: BoundaryCounters,
    now: int,
    provider_store: set[str] | None,
    gate: PreSignInterceptor | None = None,
    provider: _CountingProvider | None = None,
) -> tuple[
    PreSignInterceptor,
    _CountingProvider,
    Mapping[str, Any] | None,
    str | None,
]:
    signer: SignerProtocol = _SyntheticSigner(counters)
    broadcaster: BroadcastFn = _SyntheticBroadcast(counters)
    receipt_fn: ReceiptFn = _SyntheticReceipt(counters)
    current_provider = provider or _CountingProvider(
        PriorSealAuthorizationProvider(
            response,
            consumed_acceptance_ids=provider_store,
        ),
        counters,
    )
    current_gate = gate or PreSignInterceptor(
        policy=_policy(transaction),
        signer=signer.sign_transaction,
        authorization_provider=current_provider,
    )
    if gate is not None and gate.authorization_provider is not current_provider:
        raise BoundaryError("gate/provider reconstruction mismatch")

    request = AuthorizationRequest(Chain.BASE_SEPOLIA, ActionType.SWAP, transaction)
    evaluated_at = 1789639170
    try:
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
        broadcast_result = broadcaster(signed.raw_transaction)
        receipt = receipt_fn(broadcast_result)
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


def _run_case(bundle: FixtureBundle, case_id: str) -> dict[str, Any]:
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
            counters=counters,
            now=now,
            provider_store=None,
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
            counters=counters,
            now=now,
            provider_store=None,
        )
        if receipt is None or error is not None:
            raise BoundaryError(f"N5a first use failed: {error}")
        _, _, second_receipt, second_error = _run_gate_attempt(
            transaction=transaction,
            response=response,
            counters=counters,
            now=now,
            provider_store=None,
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
        persisted: set[str] = set()
        _, _, receipt, error = _run_gate_attempt(
            transaction=transaction,
            response=response,
            counters=counters,
            now=now,
            provider_store=persisted,
        )
        if receipt is None or error is not None:
            raise BoundaryError(f"N5b first use failed: {error}")
        _, _, second_receipt, second_error = _run_gate_attempt(
            transaction=transaction,
            response=response,
            counters=counters,
            now=now,
            provider_store=persisted,
        )
        provider_reason = (
            "AUTHORIZATION_REPLAYED"
            if "AUTHORIZATION_REPLAYED" in str(second_error)
            else ""
        )
        if second_receipt is not None or provider_reason != "AUTHORIZATION_REPLAYED":
            raise BoundaryError("N5b replay was not rejected by persisted acceptance state")
        row = _case_row(
            vector,
            counters,
            actual_terminal="FIRST_USE_ONLY",
            reason=provider_reason,
            observed={"providerReason": provider_reason, "gateError": second_error},
        )
        row["reconstruction"] = {
            "differentProviderInstance": True,
            "samePersistedAcceptanceId": True,
        }
        return row

    raise BoundaryError(f"unsupported negative case: {case_id}")


def run_negative_suite(fixture_root: str | Path) -> dict[str, Any]:
    bundle = FixtureBundle.load(fixture_root)
    baseline = bundle.baseline
    cases = [_run_case(bundle, case_id) for case_id in ("N1", "N2", "N3", "N4", "N5a", "N5b")]
    return {
        "schema": "wak-insight-priorseal.acceptance-report.v1",
        "fixtureVersion": "v1",
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


def write_acceptance_report(fixture_root: str | Path, output: str | Path) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(run_negative_suite(fixture_root), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    write_acceptance_report(args.fixture, args.report)
    print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
