"""Generate fresh signed rehearsal material for the inert-boundary P1 rehearsal.

The rehearsal is **not** an authorization for any transaction and must never be used
for a real GO. It derives fresh synthetic keys, re-signs the Insight attestations, the
PriorSeal authorization, and the PriorSeal acceptance, and writes a rehearsal run sheet
with a live validity window so the full runner path (GO binding, session-store arrival,
live clock, cutoff rechecks, event retention, counters) can be exercised with inert
broadcast/receipt boundaries from the actual entry point.

Nothing here touches a network, funds a wallet, or authorizes signing or broadcast.
All keys are generated at runtime and never persisted.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

try:
    from examples.support.insight_priorseal_boundary import (
        FixtureBundle,
        _INSIGHT_FIELDS,
        _PRIORSEAL_AUTHORIZATION_TYPES,
        _canonical_json,
        _hash_json,
        insight_pair_commitment,
    )
except ModuleNotFoundError:  # running from examples/
    from support.insight_priorseal_boundary import (
        FixtureBundle,
        _INSIGHT_FIELDS,
        _PRIORSEAL_AUTHORIZATION_TYPES,
        _canonical_json,
        _hash_json,
        insight_pair_commitment,
    )

RUN_SHEET_SCHEMA = "wak-p1.run-sheet.rehearsal.v1"
GO_FILE_SCHEMA = "wak-p1.go-file.v1"
REHEARSAL_INSIGHT_KEY_ID = "insight-wak-rehearsal-eip712-1"
REHEARSAL_PRIORSEAL_ISSUER = "priorseal.wak-rehearsal-synthetic"
REHEARSAL_PRIORSEAL_KEY_ID = "priorseal-wak-rehearsal-1"
REHEARSAL_INTENT_ID = "wak-insight-priorseal-rehearsal-v1"
REHEARSAL_AGENT_ID = "wak-rehearsal-agent"
REHEARSAL_PRINCIPAL_ID = "wak-rehearsal-principal"

SHEET_VALIDITY_SECONDS = 900
SHEET_MARGIN_SECONDS = 180
INSIGHT_VALID_FOR_SECONDS = 600


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _now() -> int:
    return int(time.time())


def _insight_signable(data: Mapping[str, Any]) -> Any:
    message: dict[str, Any] = {}
    for name, field_type in _INSIGHT_FIELDS:
        value = data[name]
        if field_type == "uint256":
            value = int(value)
        elif field_type == "bytes32":
            value = bytes.fromhex(str(value)[2:])
        message[name] = value
    return encode_typed_data(
        full_message={
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                ],
                "OracleSafetyCheck": [
                    {"name": name, "type": field_type} for name, field_type in _INSIGHT_FIELDS
                ],
            },
            "primaryType": "OracleSafetyCheck",
            "domain": {"name": "Insight Oracle Safety", "version": "3", "chainId": 1},
            "message": message,
        }
    )


def _sign_insight_attestation(template: Mapping[str, Any], *, key: str, attester: str, checked_at: int, valid_until: int) -> dict[str, Any]:
    data = dict(template["data"])
    data["checkedAt"] = checked_at
    data["validUntil"] = valid_until
    signable = _insight_signable(data)
    digest = "0x" + keccak(b"\x19" + signable.version + signable.header + signable.body).hex()
    signature = Account.sign_message(signable, private_key=key)
    signed_at = _iso(checked_at)
    return {
        "schemaVersion": 3,
        "attester": attester,
        "attesterLabel": template.get("attesterLabel", "Insight Oracle Safety Attestation"),
        "signedAt": signed_at,
        "validForSeconds": template.get("validForSeconds", INSIGHT_VALID_FOR_SECONDS),
        "validUntil": valid_until,
        "verifyUrl": template.get("verifyUrl", "https://www.oracleinsight.xyz"),
        "evidence": template.get("evidence"),
        "uid": digest,
        "signature": signature.signature.hex() if hasattr(signature.signature, "hex") else str(signature.signature),
        "data": data,
    }


def _authorization_signable(intent: Mapping[str, Any], *, authorizer_address: str, issued_at: int, not_before: int, expires_at: int, nonce_hex: str, max_uses: str, audience: str, policy_hash: str, principal_type: str, principal_id: str, agent_id: str, executor: str) -> Any:
    return encode_typed_data(
        full_message={
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                ],
                **_PRIORSEAL_AUTHORIZATION_TYPES,
            },
            "primaryType": "PriorSealAuthorization",
            "domain": {"name": "PriorSeal", "version": "2", "chainId": int(intent["chainId"])},
            "message": {
                "intentHash": bytes.fromhex(intent["intentHash"]),
                "principalType": principal_type,
                "principalId": principal_id,
                "principalAccount": authorizer_address,
                "authorizerType": "eip712",
                "authorizer": authorizer_address,
                "agentId": agent_id,
                "executor": executor,
                "issuedAt": issued_at,
                "notBefore": not_before,
                "expiresAt": expires_at,
                "authorizationNonce": bytes.fromhex(nonce_hex[2:]),
                "maxUses": int(max_uses),
                "audience": audience,
                "policyHash": bytes.fromhex(policy_hash[2:]),
            },
        }
    )


def _build_priorseal_response(
    *,
    intent: Mapping[str, Any],
    authorization_nonce: str,
    principal_address: str,
    executor: str,
    issued_at: int,
    not_before: int,
    expires_at: int,
    envelope_digest: str,
    policy_digest: str,
    principal_key: str,
    priorseal_ed25519: Ed25519PrivateKey,
    issuer: str,
    key_id: str,
    accepted_at: int,
) -> dict[str, Any]:
    draft = {
        "schema": "priorseal.authorization.v2",
        "domain": "priorseal/authorization/v2",
        "intent": intent,
        "principal": {"type": "user", "id": REHEARSAL_PRINCIPAL_ID, "account": principal_address.lower()},
        "authorizer": {"type": "eip712", "address": principal_address.lower()},
        "delegate": {"agentId": REHEARSAL_AGENT_ID, "executor": executor.lower()},
        "issuedAt": issued_at,
        "notBefore": not_before,
        "expiresAt": expires_at,
        "authorizationNonce": authorization_nonce,
        "maxUses": "1",
        "audience": "priorseal",
        "policyHash": "0x" + "0" * 64,
    }
    signable = _authorization_signable(
        intent,
        authorizer_address=principal_address.lower(),
        issued_at=issued_at,
        not_before=not_before,
        expires_at=expires_at,
        nonce_hex=authorization_nonce,
        max_uses="1",
        audience="priorseal",
        policy_hash="0x" + "0" * 64,
        principal_type="user",
        principal_id=REHEARSAL_PRINCIPAL_ID,
        agent_id=REHEARSAL_AGENT_ID,
        executor=executor.lower(),
    )
    signature = Account.sign_message(signable, private_key=principal_key)
    signed = {**draft, "signature": signature.signature.hex() if hasattr(signature.signature, "hex") else str(signature.signature)}

    intent_hash = str(intent["intentHash"])
    # The WAK verifier normalizes the signed authorization, includes the recomputed
    # intentHash, then appends authorizationId before hashing. Mirror that exactly so
    # authorization_id and authorization_hash bind in the acceptance.
    normalized_with_intent = {**signed, "intentHash": intent_hash}
    unsigned = {key: value for key, value in normalized_with_intent.items() if key != "signature"}
    authorization_id = "auth_" + _hash_json(unsigned)[:32]
    authorization_hash = _hash_json({**normalized_with_intent, "authorizationId": authorization_id})

    acceptance = {
        "schema": "priorseal.authorization-receipt.v1",
        "domain": "priorseal/authorization-receipt/v1",
        "authorizationId": authorization_id,
        "authorizationHash": authorization_hash,
        "intentHash": intent_hash,
        "acceptedAt": accepted_at,
        "sequence": 1,
        "previousEntryHash": "0x" + "0" * 64,
        "status": "ACCEPTED",
        "issuer": issuer,
        "algorithm": "Ed25519",
        "keyId": key_id,
    }
    entry_hash = _hash_json(
        {
            "sequence": acceptance["sequence"],
            "authorizationHash": authorization_hash,
            "acceptedAt": accepted_at,
            "previousEntryHash": acceptance["previousEntryHash"],
        }
    )
    acceptance["entryHash"] = entry_hash
    unsigned_acceptance = {key: value for key, value in acceptance.items() if key != "signature"}
    import base64

    signature_bytes = priorseal_ed25519.sign(_canonical_json(unsigned_acceptance))
    acceptance["signature"] = base64.urlsafe_b64encode(signature_bytes).decode("ascii").rstrip("=")

    response = {
        "schema": "priorseal.wak-authorization-response.v1",
        "authorization_id": authorization_id,
        "envelope_digest": envelope_digest,
        "executor": executor.lower(),
        "authorizer": principal_address.lower(),
        "valid_from": not_before,
        "valid_until": expires_at,
        "nonce": authorization_nonce,
        "policy_commitment_digest": policy_digest,
        "signedAuthorization": signed,
        "verificationResult": {"valid": True, "code": "OK"},
        "acceptance": acceptance,
    }
    return response


def _write_go_message(db_path: Path, message_id: int, content: str, timestamp_epoch: int) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, role TEXT, content TEXT, timestamp REAL)")
        con.execute(
            "INSERT OR REPLACE INTO messages (id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (message_id, "user", content, timestamp_epoch),
        )
        con.commit()
    finally:
        con.close()


@dataclass
class RehearsalMaterials:
    sheet: dict[str, Any]
    sheet_bytes: bytes
    sheet_text: str
    go_file: dict[str, Any]
    session_db: Path
    go_message_id: int
    trust_roots: dict[str, Any]
    baseline_insight: dict[str, Any]
    executor_key: str
    executor_address: str
    envelope_digest: str
    policy_commitment_digest: str
    insight_pair_commitment: str
    evaluated_at: int
    generated_at: int = field(default_factory=_now)
    scratch_dir: Path | None = None


def generate_rehearsal_materials(
    *,
    fixture_root: str | Path,
    output_dir: str | Path | None = None,
    now: int | None = None,
    go_message_id: int = 90001,
) -> RehearsalMaterials:
    """Generate a complete fresh rehearsal bundle (sheet + GO + session store + keys).

    The sheet's ``evaluatedAt`` is the current wall-clock second; the caller should run
    the rehearsal leg immediately so the gate's live policy evaluation lands in the same
    second. If it does not, regenerate with a fresh ``now`` and retry (the runner's
    rehearsal mode does this automatically).
    """
    bundle = FixtureBundle.load(fixture_root)
    baseline = bundle.baseline

    now_epoch = int(time.time()) if now is None else int(now)
    evaluated_at = now_epoch
    # The policy decision is pinned to the current wall-clock second (the gate
    # re-evaluates with its live clock during the run). The authorization window is
    # backdated a few seconds so valid_from is never in the future even if the host
    # clock steps backwards (NTP corrections observed on this host).
    issued_at = now_epoch - 5
    valid_until = issued_at + SHEET_VALIDITY_SECONDS
    accepted_at = issued_at + 1
    checked_at = now_epoch
    latest_broadcast_at = valid_until - SHEET_MARGIN_SECONDS

    # Fresh rehearsal keys (runtime only, never persisted).
    insight_key = secrets.token_hex(32)
    principal_key = secrets.token_hex(32)
    executor_key = secrets.token_hex(32)
    insight_account = Account.from_key(insight_key)
    principal_account = Account.from_key(principal_key)
    executor_account = Account.from_key(executor_key)
    priorseal_ed25519 = Ed25519PrivateKey.generate()
    priorseal_public = priorseal_ed25519.public_key()
    pem = priorseal_public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")
    spki = priorseal_public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    spki_sha256 = hashlib.sha256(spki).hexdigest()

    # Transaction: fixture call shape, rehearsal executor + fresh nonce.
    fixture_tx = baseline["transaction"]
    data = str(fixture_tx["data"])
    router = str(fixture_tx["to"])
    value = str(fixture_tx["value"])
    nonce = "0"
    transaction = {
        "chainId": 84532,
        "from": executor_account.address.lower(),
        "to": router,
        "data": data,
        "value": value,
        "nonce": nonce,
        # Inert gas fields: the rehearsal leg never broadcasts, but the live
        # SignerProtocol (eth_account) requires them to build the signed payload.
        "gas": 500000,
        "gasPrice": 30000000,
    }
    calldata_hash = "0x" + keccak(bytes.fromhex(data[2:])).hex()

    # Digests exactly as the WAK gate will compute them.
    from web3_agent_kit.execution.envelope import CallEnvelopeV1, PolicyDecisionCommitment

    envelope = CallEnvelopeV1(
        chain_id=84532,
        executor=executor_account.address.lower(),
        nonce=int(nonce),
        calldata=bytes.fromhex(data[2:]),
        native_value=int(value),
        target=router.lower(),
    )
    envelope_digest = envelope.digest()
    commitment = PolicyDecisionCommitment(
        call_identity=envelope_digest,
        policy_id="wak-insight-priorseal-spike-v1",
        verdict="allow",
        reason_codes=(),
        evaluated_at=evaluated_at,
    )
    policy_digest = commitment.digest()

    # Fresh Insight attestations (positive pair).
    insight_template_source = baseline["insight"]["sourceAttestation"]
    insight_template_destination = baseline["insight"]["destinationAttestation"]
    attester = insight_account.address
    source = _sign_insight_attestation(
        insight_template_source, key=insight_key, attester=attester, checked_at=checked_at, valid_until=valid_until
    )
    destination = _sign_insight_attestation(
        insight_template_destination, key=insight_key, attester=attester, checked_at=checked_at, valid_until=valid_until
    )
    pair_commitment = insight_pair_commitment(source, destination)

    intent = {
        "schema": "priorseal.intent.v2",
        "executionProfile": "priorseal.execution-profile.exact-call.v1",
        "intentId": REHEARSAL_INTENT_ID,
        "chainId": 84532,
        "action": "CONTRACT_CALL",
        "asset": "eip155:84532/native",
        "amount": value,
        "sender": executor_account.address.lower(),
        "recipient": router,
        "validUntil": valid_until,
        "nonce": nonce,
        "callTarget": router,
        "calldataHash": calldata_hash,
        "transactionValue": value,
        "contextCommitments": [
            {"namespace": "agent-call-envelope.v1", "algorithm": "sha256", "digest": envelope_digest},
            {"namespace": "insight.pretrade-pair.v1", "algorithm": "keccak256", "digest": pair_commitment},
            {"namespace": "web3-agent-kit.policy-decision.v1", "algorithm": "sha256", "digest": policy_digest},
        ],
    }
    intent_hash = _hash_json({key: value for key, value in intent.items() if key != "intentHash"})
    intent["intentHash"] = intent_hash

    authorization_nonce = "0x" + "01" * 32
    response = _build_priorseal_response(
        intent=intent,
        authorization_nonce=authorization_nonce,
        principal_address=principal_account.address,
        executor=executor_account.address,
        issued_at=issued_at,
        not_before=issued_at,
        expires_at=valid_until,
        envelope_digest=envelope_digest,
        policy_digest=policy_digest,
        principal_key=principal_key,
        priorseal_ed25519=priorseal_ed25519,
        issuer=REHEARSAL_PRIORSEAL_ISSUER,
        key_id=REHEARSAL_PRIORSEAL_KEY_ID,
        accepted_at=accepted_at,
    )

    key_registry = {
        "issuer": "https://www.oracleinsight.xyz",
        "registryRevision": "synthetic-wak-rehearsal-1",
        "public_keys": [
            {
                "key_id": REHEARSAL_INSIGHT_KEY_ID,
                "public_key": attester,
                "algorithm": "EIP-712/secp256k1",
                "validFrom": _iso(now_epoch - 86400),
                "validUntil": None,
                "revoked": False,
                "role": "attester",
            }
        ],
        "revoked_keys": [],
    }

    sheet: dict[str, Any] = {
        "schema": RUN_SHEET_SCHEMA,
        "mode": "REHEARSAL",
        "generatedAtEpoch": now_epoch,
        "evaluatedAt": evaluated_at,
        "offChainValidity": {
            "expiresAt": valid_until,
            "broadcastMarginSeconds": SHEET_MARGIN_SECONDS,
            "latestBroadcastAt": latest_broadcast_at,
            "insightValidUntil": valid_until,
        },
        "transaction": transaction,
        "priorSeal": {"response": response},
        "insight": {
            "subjectChainId": baseline["insight"]["subjectChainId"],
            "executionChainId": baseline["insight"]["executionChainId"],
            "sourceAttestation": source,
            "destinationAttestation": destination,
            "keyRegistry": key_registry,
        },
        "wak": {
            "sourceVersion": "1.18.5",
            "callEnvelope": {"payload": envelope.to_payload(), "digest": envelope_digest},
            "policyDecisionCommitment": {"payload": commitment.to_payload(), "digest": policy_digest},
        },
        "pairCommitment": pair_commitment,
    }
    sheet_bytes = (json.dumps(sheet, indent=2, sort_keys=True) + "\n").encode("utf-8")
    run_sheet_sha256 = hashlib.sha256(sheet_bytes).hexdigest()

    go_file: dict[str, Any] = {
        "schema": GO_FILE_SCHEMA,
        "latestBroadcastAt": latest_broadcast_at,
        "runSheetSha256": run_sheet_sha256,
        "receiverFloorSeconds": 120,
        "marginSeconds": SHEET_MARGIN_SECONDS,
        "mode": "REHEARSAL",
    }

    scratch = Path(output_dir) if output_dir is not None else None
    if scratch is not None:
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "rehearsal-run-sheet.json").write_bytes(sheet_bytes)
        (scratch / "rehearsal-go.json").write_text(json.dumps(go_file, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (scratch / "rehearsal-trust-roots.json").write_text(
            json.dumps(
                {
                    "schema": "wak-insight-priorseal.trust-roots.v1",
                    "synthetic": True,
                    "rehearsal": True,
                    "insight": {"attester": attester, "historicalKeyId": REHEARSAL_INSIGHT_KEY_ID},
                    "priorSeal": {
                        "issuer": REHEARSAL_PRIORSEAL_ISSUER,
                        "keyId": REHEARSAL_PRIORSEAL_KEY_ID,
                        "publicKeyPem": pem,
                        "publicKeySpkiSha256": spki_sha256,
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    session_db = scratch / "rehearsal-go.db" if scratch is not None else Path("/tmp") / f"wak-rehearsal-go-{now_epoch}.db"
    go_content = (
        "REHEARSAL GO (inert) — run-specific rehearsal sheet bound, "
        f"latestBroadcastAt {latest_broadcast_at}, runSheetSha256 {run_sheet_sha256}"
    )
    _write_go_message(session_db, go_message_id, go_content, now_epoch)

    trust_roots = {
        "schema": "wak-insight-priorseal.trust-roots.v1",
        "synthetic": True,
        "rehearsal": True,
        "insight": {"attester": attester, "historicalKeyId": REHEARSAL_INSIGHT_KEY_ID},
        "priorSeal": {
            "issuer": REHEARSAL_PRIORSEAL_ISSUER,
            "keyId": REHEARSAL_PRIORSEAL_KEY_ID,
            "publicKeyPem": pem,
            "publicKeySpkiSha256": spki_sha256,
        },
    }

    return RehearsalMaterials(
        sheet=sheet,
        sheet_bytes=sheet_bytes,
        sheet_text=json.dumps(sheet, indent=2, sort_keys=True),
        go_file=go_file,
        session_db=session_db,
        go_message_id=go_message_id,
        trust_roots=trust_roots,
        baseline_insight=sheet["insight"],
        executor_key=executor_key,
        executor_address=executor_account.address.lower(),
        envelope_digest=envelope_digest,
        policy_commitment_digest=policy_digest,
        insight_pair_commitment=pair_commitment,
        evaluated_at=evaluated_at,
        scratch_dir=scratch,
    )
