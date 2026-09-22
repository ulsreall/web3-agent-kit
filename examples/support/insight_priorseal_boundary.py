"""JSON-only boundary for the bounded Insight / PriorSeal example.

This module intentionally depends on WAK and the Python standard library only.
It never imports Insight or PriorSeal packages and never rebuilds WAK digests.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

from web3_agent_kit.execution import AuthorizationDenied, AuthorizationEvidence
from web3_agent_kit.execution.envelope import CallEnvelopeV1


class BoundaryError(ValueError):
    """Raised when fixture or boundary data violates the agreed contract."""


_INSIGHT_FIELDS = (
    ("verdict", "string"),
    ("sourceAssetId", "string"),
    ("destinationAssetId", "string"),
    ("subjectChainId", "uint256"),
    ("action", "string"),
    ("tradeAmountUsd", "uint256"),
    ("consensusPrice", "uint256"),
    ("maxDeviationBps", "uint256"),
    ("manipulationRiskBps", "uint256"),
    ("participantCount", "uint256"),
    ("requiredParticipantCount", "uint256"),
    ("coverageStatus", "string"),
    ("independenceStatus", "string"),
    ("sourceGroupCount", "uint256"),
    ("crossProviderAgreementBps", "uint256"),
    ("maxStablecoinDepegBps", "uint256"),
    ("maxDataAgeSeconds", "uint256"),
    ("recommendedMaxPositionUsd", "uint256"),
    ("reasonCodesHash", "bytes32"),
    ("requestHash", "bytes32"),
    ("evaluationScope", "string"),
    ("evaluatedAssetIdsHash", "bytes32"),
    ("providerObservationsHash", "bytes32"),
    ("validUntil", "uint256"),
    ("checkedAt", "uint256"),
    ("schemaVersion", "uint256"),
    ("requiredSourceGroupCount", "uint256"),
)


def _iso_timestamp(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def verify_insight_attestation(
    attestation: Mapping[str, Any],
    baseline: Mapping[str, Any],
    trust_roots: Mapping[str, Any],
) -> None:
    """Verify the pinned Insight EIP-712 attestation independently in WAK."""
    data = attestation.get("data")
    if not isinstance(data, Mapping):
        raise BoundaryError("INSIGHT_SCHEMA_INVALID")
    if attestation.get("schemaVersion") != 3 or data.get("schemaVersion") != 3:
        raise BoundaryError("INSIGHT_SCHEMA_INVALID")

    trusted = str(trust_roots["insight"]["attester"])
    attester = str(attestation.get("attester", ""))
    if attester.lower() != trusted.lower():
        raise BoundaryError("INSIGHT_ATTESTER_UNTRUSTED")

    registry = baseline["insight"]["keyRegistry"]
    key_id = trust_roots["insight"]["historicalKeyId"]
    keys = [entry for entry in registry["public_keys"] if entry["key_id"] == key_id]
    if len(keys) != 1 or str(keys[0]["public_key"]).lower() != attester.lower():
        raise BoundaryError("INSIGHT_KEY_MISMATCH")
    key = keys[0]
    if key["revoked"] or any(item["key_id"] == key_id for item in registry["revoked_keys"]):
        raise BoundaryError("INSIGHT_KEY_REVOKED")
    checked_at = int(data["checkedAt"])
    if checked_at < _iso_timestamp(key["validFrom"]):
        raise BoundaryError("INSIGHT_KEY_TIME_INVALID")
    if key["validUntil"] is not None and checked_at >= _iso_timestamp(key["validUntil"]):
        raise BoundaryError("INSIGHT_KEY_TIME_INVALID")

    message: dict[str, Any] = {}
    for name, field_type in _INSIGHT_FIELDS:
        value = data[name]
        if field_type == "uint256":
            value = int(value)
        elif field_type == "bytes32":
            value = bytes.fromhex(str(value)[2:])
        message[name] = value
    signable = encode_typed_data(
        full_message={
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                ],
                "OracleSafetyCheck": [
                    {"name": name, "type": field_type}
                    for name, field_type in _INSIGHT_FIELDS
                ],
            },
            "primaryType": "OracleSafetyCheck",
            "domain": {"name": "Insight Oracle Safety", "version": "3", "chainId": 1},
            "message": message,
        }
    )
    digest = "0x" + keccak(b"\x19" + signable.version + signable.header + signable.body).hex()
    if digest != attestation.get("uid"):
        raise BoundaryError("INSIGHT_UID_MISMATCH")
    try:
        recovered = Account.recover_message(signable, signature=attestation["signature"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BoundaryError("INSIGHT_SIGNATURE_INVALID") from exc
    if recovered.lower() != attester.lower():
        raise BoundaryError("INSIGHT_SIGNATURE_INVALID")
    if attestation.get("validUntil") != data.get("validUntil"):
        raise BoundaryError("INSIGHT_WINDOW_INVALID")
    if int(data["checkedAt"]) >= int(data["validUntil"]):
        raise BoundaryError("INSIGHT_WINDOW_INVALID")


def insight_pair_commitment(
    source: Mapping[str, Any], destination: Mapping[str, Any]
) -> str:
    encoded = encode(
        ["bytes32", "bytes32", "bytes32", "bytes32", "uint16"],
        [
            bytes.fromhex(str(source["uid"])[2:]),
            bytes.fromhex(str(destination["uid"])[2:]),
            bytes.fromhex(str(source["data"]["requestHash"])[2:]),
            bytes.fromhex(str(destination["data"]["requestHash"])[2:]),
            50,
        ],
    )
    return "0x" + keccak(encoded).hex()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BoundaryError(f"{path.name} must contain a JSON object")
    return value


@dataclass(frozen=True)
class FixtureBundle:
    """Verified, separately versioned conformance inputs."""

    root: Path
    manifest: Mapping[str, Any]
    baseline: Mapping[str, Any]
    cases: Mapping[str, Any]
    trust_roots: Mapping[str, Any]

    @classmethod
    def load(cls, root: str | Path) -> "FixtureBundle":
        directory = Path(root).resolve()
        manifest = _read_json(directory / "fixture" / "manifest.json")
        if manifest.get("schema") != "wak-insight-priorseal.fixture-manifest.v1":
            raise BoundaryError("unsupported fixture manifest schema")
        if manifest.get("version") != "v1":
            raise BoundaryError("unsupported fixture version")

        declared = manifest.get("files")
        if not isinstance(declared, dict):
            raise BoundaryError("fixture manifest files must be an object")
        expected = {
            "README.md",
            "fixture/baseline.json",
            "fixture/cases.json",
            "fixture/trust-roots.json",
            "verify.mjs",
        }
        if set(declared) != expected:
            raise BoundaryError("fixture manifest file set mismatch")
        for relative, expected_hash in declared.items():
            payload = (directory / relative).read_bytes()
            actual = hashlib.sha256(payload).hexdigest()
            if actual != expected_hash:
                raise BoundaryError(f"fixture hash mismatch: {relative}")

        archive = directory.parent / "2026-09-21-wak-insight-priorseal-conformance-v1.zip"
        pin_path = directory.parent / "UPSTREAM_BUNDLE.sha256"
        if not archive.is_file() or not pin_path.is_file():
            raise BoundaryError("pinned archive and SHA-256 file are required")
        pinned_hash = pin_path.read_text(encoding="ascii").split()[0]
        if hashlib.sha256(archive.read_bytes()).hexdigest() != pinned_hash:
            raise BoundaryError("pinned archive SHA-256 mismatch")
        archive_files = expected | {"fixture/manifest.json"}
        with zipfile.ZipFile(archive) as source:
            names = {info.filename for info in source.infolist() if not info.is_dir()}
            if names != archive_files:
                raise BoundaryError("pinned archive file set mismatch")
            for relative in archive_files:
                if source.read(relative) != (directory / relative).read_bytes():
                    raise BoundaryError(
                        f"vendored extraction differs from pinned archive: {relative}"
                    )

        baseline = _read_json(directory / "fixture" / "baseline.json")
        cases = _read_json(directory / "fixture" / "cases.json")
        roots = _read_json(directory / "fixture" / "trust-roots.json")
        return cls(
            root=directory,
            manifest=MappingProxyType(manifest),
            baseline=MappingProxyType(baseline),
            cases=MappingProxyType(cases),
            trust_roots=MappingProxyType(roots),
        )

    @property
    def version(self) -> str:
        return str(self.manifest["version"])

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(str(case["id"]) for case in self.cases["cases"])

    def case(self, case_id: str) -> Mapping[str, Any]:
        for case in self.cases["cases"]:
            if case["id"] == case_id:
                return case
        raise BoundaryError(f"unknown fixture case: {case_id}")


class PriorSealAuthorizationProvider:
    """Map verified PriorSeal JSON into the existing WAK evidence type."""

    def __init__(
        self,
        response: Mapping[str, Any],
        *,
        consumed_acceptance_ids: set[str] | None = None,
    ) -> None:
        self._response = response
        self._consumed = consumed_acceptance_ids
        self.calls = 0

    @property
    def policy_id(self) -> str:
        return "priorseal-bounded-spike-v1"

    def evidence_for(
        self,
        *,
        envelope: CallEnvelopeV1,
        envelope_digest: str,
        policy_commitment_digest: str,
    ) -> AuthorizationEvidence:
        self.calls += 1
        response = self._response
        if response.get("schema") != "priorseal.wak-authorization-response.v1":
            raise AuthorizationDenied("unsupported PriorSeal response schema")
        verification = response.get("verificationResult")
        if not isinstance(verification, Mapping) or verification.get("valid") is not True:
            raise AuthorizationDenied("PriorSeal authorization verification failed")
        if (
            response.get("envelope_digest") == envelope_digest
            and response.get("policy_commitment_digest") != policy_commitment_digest
        ):
            raise AuthorizationDenied("PriorSeal authorization covers another policy decision")

        signed = response.get("signedAuthorization")
        if not isinstance(signed, Mapping) or not isinstance(signed.get("intent"), Mapping):
            raise AuthorizationDenied("PriorSeal signed authorization is missing")
        intent = signed["intent"]
        commitments = intent.get("contextCommitments")
        if not isinstance(commitments, list):
            raise AuthorizationDenied("PriorSeal context commitments are missing")

        def commitment(namespace: str) -> Mapping[str, Any]:
            matches = [item for item in commitments if item.get("namespace") == namespace]
            if len(matches) != 1:
                raise AuthorizationDenied(
                    f"PriorSeal commitment is not unique: {namespace}"
                )
            return matches[0]

        envelope_commitment = commitment("agent-call-envelope.v1")
        policy_commitment = commitment("web3-agent-kit.policy-decision.v1")
        if (
            envelope_commitment.get("algorithm") != "sha256"
            or envelope_commitment.get("digest") != response.get("envelope_digest")
        ):
            raise AuthorizationDenied("PriorSeal envelope commitment mismatch")
        if (
            policy_commitment.get("algorithm") != "sha256"
            or policy_commitment.get("digest") != response.get("policy_commitment_digest")
        ):
            raise AuthorizationDenied("PriorSeal policy commitment mismatch")
        if str(intent.get("sender", "")).lower() != str(response.get("executor", "")).lower():
            raise AuthorizationDenied("PriorSeal executor mapping mismatch")

        authorization_id = str(response.get("authorization_id", ""))
        if signed.get("authorizationId") != authorization_id:
            raise AuthorizationDenied("PriorSeal authorization identity mismatch")
        acceptance = response.get("acceptance")
        if not isinstance(acceptance, Mapping) or acceptance.get("status") != "ACCEPTED":
            raise AuthorizationDenied("PriorSeal acceptance is missing")
        if acceptance.get("authorizationId") != authorization_id:
            raise AuthorizationDenied("PriorSeal acceptance identity mismatch")
        if self._consumed is not None:
            if authorization_id in self._consumed:
                raise AuthorizationDenied(
                    "AUTHORIZATION_REPLAYED: PriorSeal acceptance has already been consumed"
                )
            self._consumed.add(authorization_id)

        return AuthorizationEvidence(
            authorization_id=authorization_id,
            envelope_digest=str(response["envelope_digest"]),
            executor=str(response["executor"]),
            authorizer=str(response["authorizer"]),
            valid_from=int(response["valid_from"]),
            valid_until=int(response["valid_until"]),
            nonce=str(response["nonce"]),
            policy_commitment_digest=str(response["policy_commitment_digest"]),
            raw=MappingProxyType(
                {
                    "signedAuthorization": response["signedAuthorization"],
                    "verificationResult": response["verificationResult"],
                    "acceptance": response["acceptance"],
                }
            ),
        )

    def authorize(self, context) -> AuthorizationEvidence:
        return self.evidence_for(
            envelope=context.envelope,
            envelope_digest=context.envelope_digest,
            policy_commitment_digest=context.policy_commitment.digest(),
        )
