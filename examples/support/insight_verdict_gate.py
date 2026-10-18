"""Live Insight verdict gate for the WAK P1 leg.

Consumes the issuer's Insight drop (signed OracleSafetyCheck attestations plus the
registry that published their keys), verifies each attestation, and decides whether
the pair may proceed.

Policy (agreed with the issuer, spec draft v0.1 §2/§4):

* ``PASS`` on both sides proceeds.
* ``CAUTION`` refuses. Under policy-decision v1 there is no opt-in field, so this is
  unconditional; the v2 opt-in path is deliberately absent until both sides agree on
  the payload bump.
* ``BLOCK``, ``FAIL``, any unrecognised value, a missing value or an empty string
  refuses. "Not BLOCK" is explicitly not good enough.

The verdicts are read from the signed attestation payloads, never from the sheet's
copies; the copies are cross-checked and a mismatch refuses. Verifying against the
fixture's pinned attester would always fail closed, so the attester and registry come
from the drop and the source is recorded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

try:  # package import (tests) then direct script import (examples/)
    from examples.support.insight_priorseal_boundary import (
        BoundaryError,
        insight_pair_commitment,
        verify_insight_attestation,
    )
except ModuleNotFoundError:  # pragma: no cover - direct execution
    from support.insight_priorseal_boundary import (  # type: ignore[no-redef]
        BoundaryError,
        insight_pair_commitment,
        verify_insight_attestation,
    )

VERDICT_ALLOWING = "PASS"

REASON_ALLOW = "ALLOW"
REASON_BLOCK = "VERDICT_BLOCK"
REASON_CAUTION = "VERDICT_CAUTION_NO_OPTIN"
REASON_UNKNOWN = "VERDICT_UNKNOWN"
REASON_COPY_MISMATCH = "VERDICT_COPY_MISMATCH"
REASON_STALE = "VERDICT_STALE"
REASON_MATERIALS_MISSING = "MATERIALS_MISSING"
REASON_PAIR_MISMATCH = "VERDICT_PAIR_MISMATCH"
REASON_UNTRUSTED = "VERDICT_UNTRUSTED"

SOURCE_FILE = "source-oracle-safety-check-v3.json"
DESTINATION_FILE = "destination-oracle-safety-check-v3.json"
REGISTRY_FILE = "insight-oracle-keys.json"


class InsightGateError(BoundaryError):
    """Verification of the drop itself failed; carries the reason code."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"insight verdict gate refused: {reason} ({detail})")
        self.reason = reason
        self.detail = detail


class InsightVerdictDenied(BoundaryError):
    """The pair may not proceed, with the reason code carried for the report."""

    def __init__(self, reason: str, detail: str, record: Mapping[str, Any]) -> None:
        super().__init__(f"insight verdict gate refused: {reason} ({detail})")
        self.reason = reason
        self.detail = detail
        self.record = dict(record)


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BoundaryError(f"cannot read insight drop file {path.name}: {exc}") from exc
    except ValueError as exc:
        raise BoundaryError(f"insight drop file {path.name} is not valid JSON: {exc}") from exc


def load_live_insight_trust(drop_dir: str | Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build the registry/trust-root pair for verifying the drop's attestations.

    Returns ``(source, destination, trust)`` where ``trust`` carries the baseline and
    trust roots shaped for :func:`verify_insight_attestation`, plus the recorded
    provenance the report needs.
    """
    root = Path(drop_dir)
    if not root.is_dir():
        raise BoundaryError(f"insight drop directory does not exist: {root}")

    source = _load(root / SOURCE_FILE)
    destination = _load(root / DESTINATION_FILE)
    registry = _load(root / REGISTRY_FILE)

    public_keys = registry.get("public_keys")
    if not isinstance(public_keys, list) or not public_keys:
        raise InsightGateError(REASON_UNTRUSTED, "insight registry carries no public_keys")

    attesters = {str(source.get("attester", "")).lower(), str(destination.get("attester", "")).lower()}
    if len(attesters) != 1:
        raise InsightGateError(REASON_UNTRUSTED, "attestations were not signed by the same attester")
    attester = attesters.pop()
    if not attester:
        raise InsightGateError(REASON_UNTRUSTED, "attestation carries no attester")

    matches = [entry for entry in public_keys if str(entry.get("public_key", "")).lower() == attester]
    if len(matches) != 1:
        raise InsightGateError(
            REASON_UNTRUSTED,
            f"attester is not bound to exactly one registry key ({len(matches)} matches)",
        )
    entry = matches[0]
    if entry.get("revoked"):
        raise InsightGateError(REASON_UNTRUSTED, f"attester key {entry.get('key_id')} is revoked")

    baseline = {"insight": {"keyRegistry": {"public_keys": public_keys, "revoked_keys": []}}}
    trust_roots = {"insight": {"attester": attester, "historicalKeyId": entry.get("key_id")}}
    provenance = {
        "source": "live-insight-drop",
        "attester": attester,
        "keyId": entry.get("key_id"),
        "registryRevision": registry.get("registryRevision"),
        "registryRelease": registry.get("registryRelease"),
        "publicKeys": len(public_keys),
    }
    return source, destination, {"baseline": baseline, "trust_roots": trust_roots, "provenance": provenance}


def collect_attestation_verdict(
    source: Mapping[str, Any],
    destination: Mapping[str, Any],
    trust: Mapping[str, Any],
    now: int,
    expected_pair_commitment: str | None = None,
) -> dict[str, Any]:
    """Verify both attestations and return their signed verdicts."""
    verdicts: dict[str, Any] = {}
    for label, attestation in (("source", source), ("destination", destination)):
        verify_insight_attestation(attestation, trust["baseline"], trust["trust_roots"])
        valid_until = int(attestation["validUntil"])
        if now >= valid_until:
            raise InsightGateError(
                REASON_STALE, f"{label} attestation expired at {valid_until} (now {now})"
            )
        data = attestation["data"]
        verdicts[label] = {
            "verdict": data.get("verdict"),
            "uid": attestation.get("uid"),
            "validUntil": valid_until,
            "checkedAt": int(data.get("checkedAt")),
            "coverageStatus": data.get("coverageStatus"),
            "independenceStatus": data.get("independenceStatus"),
            "participantCount": int(data.get("participantCount", 0)),
            "requiredParticipantCount": int(data.get("requiredParticipantCount", 0)),
        }
    computed = insight_pair_commitment(source, destination)
    if expected_pair_commitment is None:
        raise InsightGateError(
            REASON_PAIR_MISMATCH,
            "no pair commitment was declared, so the two attestations cannot be bound",
        )
    if str(computed).lower() != str(expected_pair_commitment).lower():
        raise InsightGateError(
            REASON_PAIR_MISMATCH,
            f"attestations hash to {computed}, authorization declares {expected_pair_commitment}",
        )
    verdicts["pairCommitmentComputed"] = computed
    verdicts["pairCommitmentDeclared"] = expected_pair_commitment
    return verdicts


def evaluate_insight_verdict_gate(
    *,
    verdicts: Mapping[str, Mapping[str, Any]],
    sheet_insight: Mapping[str, Any],
    trust: Mapping[str, Any],
    pair_commitment: str | None = None,
) -> dict[str, Any]:
    """Apply the agreed policy to the verified verdicts. Returns the report record."""

    def normalise(value: Any) -> str:
        return value.strip().upper() if isinstance(value, str) else ""

    source_verdict = normalise(verdicts["source"].get("verdict"))
    destination_verdict = normalise(verdicts["destination"].get("verdict"))

    record: dict[str, Any] = {
        "schema": "wak-p1.insight-verdict-gate.v1",
        "verdicts": {
            "source": verdicts["source"].get("verdict"),
            "destination": verdicts["destination"].get("verdict"),
        },
        "signedVerdicts": {"source": source_verdict, "destination": destination_verdict},
        "pairCommitment": verdicts.get("pairCommitmentComputed", pair_commitment),
        "pairCommitmentDeclared": verdicts.get("pairCommitmentDeclared", pair_commitment),
        "trust": trust.get("provenance"),
        "policy": {
            "allowing": VERDICT_ALLOWING,
            "refuseOn": ["BLOCK", "FAIL", "CAUTION", "UNKNOWN"],
            "cautionOptIn": "unavailable in policy-decision v1",
        },
    }

    # 1. The sheet's copies must equal what the attester actually signed.
    copies = {
        "source": normalise(sheet_insight.get("sourceVerdict")),
        "destination": normalise(sheet_insight.get("destinationVerdict")),
    }
    record["sheetVerdicts"] = {
        "source": sheet_insight.get("sourceVerdict"),
        "destination": sheet_insight.get("destinationVerdict"),
    }
    mismatched = [
        label
        for label in ("source", "destination")
        if copies[label] != record["signedVerdicts"][label]
    ]
    if mismatched:
        record.update(decision="DENY", reason=REASON_COPY_MISMATCH, mismatched=mismatched)
        raise InsightVerdictDenied(REASON_COPY_MISMATCH, f"sheet copy differs on {mismatched}", record)

    # 2. Only an explicit PASS on both sides proceeds.
    for label in ("source", "destination"):
        value = record["signedVerdicts"][label]
        if value == VERDICT_ALLOWING:
            continue
        reason = {
            "BLOCK": REASON_BLOCK,
            "FAIL": REASON_BLOCK,
            "CAUTION": REASON_CAUTION,
        }.get(value, REASON_UNKNOWN)
        record.update(decision="DENY", reason=reason, refusedOn=label, refusedValue=value or None)
        raise InsightVerdictDenied(reason, f"{label} attestation signed {value or '<missing>'}", record)

    record.update(decision="ALLOW", reason=REASON_ALLOW)
    return record
