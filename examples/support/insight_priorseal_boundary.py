"""JSON-only boundary for the bounded Insight / PriorSeal example.

This module intentionally depends on WAK and the Python standard library only.
It never imports Insight or PriorSeal packages and never rebuilds WAK digests.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import zipfile
from base64 import urlsafe_b64decode, urlsafe_b64encode
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

from web3_agent_kit.execution import AuthorizationDenied, AuthorizationEvidence
from web3_agent_kit.execution.envelope import CallEnvelopeV1


class BoundaryError(ValueError):
    """Raised when fixture or boundary data violates the agreed contract."""


_UNDEFINED = object()


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


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _hash_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


_PRIORSEAL_AUTHORIZATION_TYPES = {
    "PriorSealAuthorization": [
        {"name": "intentHash", "type": "bytes32"},
        {"name": "principalType", "type": "string"},
        {"name": "principalId", "type": "string"},
        {"name": "principalAccount", "type": "address"},
        {"name": "authorizerType", "type": "string"},
        {"name": "authorizer", "type": "address"},
        {"name": "agentId", "type": "string"},
        {"name": "executor", "type": "address"},
        {"name": "issuedAt", "type": "uint256"},
        {"name": "notBefore", "type": "uint256"},
        {"name": "expiresAt", "type": "uint256"},
        {"name": "authorizationNonce", "type": "bytes32"},
        {"name": "maxUses", "type": "uint256"},
        {"name": "audience", "type": "string"},
        {"name": "policyHash", "type": "bytes32"},
    ]
}


def _only_fields(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise AuthorizationDenied(
            f"PriorSeal {label} contains unsupported field(s): {', '.join(sorted(unknown))}"
        )


def _js_string(value: Any) -> str:
    """Mirror JavaScript String() for JSON-compatible scalar values."""

    if value is _UNDEFINED:
        return "undefined"
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:
            return "NaN"
        if value == float("inf"):
            return "Infinity"
        if value == float("-inf"):
            return "-Infinity"
        if value == 0:
            return "0"
        absolute = abs(value)
        shortest = repr(value)
        if 1e-6 <= absolute < 1e21:
            fixed = format(Decimal(shortest), "f")
            return fixed[:-2] if fixed.endswith(".0") else fixed
        if "e" not in shortest and "E" not in shortest:
            return shortest
        mantissa, exponent = re.split(r"[eE]", shortest)
        sign = "+" if not exponent.startswith("-") else "-"
        digits = exponent.lstrip("+-0") or "0"
        return f"{mantissa}e{sign}{digits}"
    if isinstance(value, list):
        return ",".join("" if item is None else _js_string(item) for item in value)
    if isinstance(value, Mapping):
        return "[object Object]"
    return str(value)


def _js_number(value: Any) -> int | float | None:
    """Mirror the finite JSON subset of JavaScript Number()."""

    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (str, list)):
        text = _js_string(value).strip()
        if not text:
            return 0
        try:
            if re.fullmatch(r"0[xX][0-9a-fA-F]+", text):
                return int(text[2:], 16)
            if re.fullmatch(r"0[bB][01]+", text):
                return int(text[2:], 2)
            if re.fullmatch(r"0[oO][0-7]+", text):
                return int(text[2:], 8)
            return float(text)
        except ValueError:
            return None
    return None


def _js_truthy(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)):
        return value != 0 and value == value
    if isinstance(value, str):
        return bool(value)
    return True


def _protocol_id(value: Any, field: str) -> str:
    result = _js_string(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", result):
        raise AuthorizationDenied(f"PriorSeal {field} contains unsupported characters")
    return result


def _evm_address(value: Any, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise AuthorizationDenied(f"PriorSeal {field} must be a 20-byte EVM address")
    return value.lower()


def _uint_string(value: Any, field: str) -> str:
    result = _js_string(value)
    if not re.fullmatch(r"0|[1-9][0-9]*", result):
        raise AuthorizationDenied(f"PriorSeal {field} must be an unsigned integer")
    return result


def _positive_time(value: Any, field: str) -> int:
    value = _js_number(value)
    if (
        value is None
        or isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value != value
        or value in {float("inf"), float("-inf")}
        or int(value) != value
        or value <= 0
        or value > 9_007_199_254_740_991
    ):
        raise AuthorizationDenied(f"PriorSeal {field} must be a positive Unix timestamp")
    return int(value)


def _chain_id(value: Any) -> int:
    if isinstance(value, str) and re.fullmatch(r"eip155:[1-9][0-9]*", value):
        value = value.removeprefix("eip155:")
    value = _js_number(value)
    if (
        value is None
        or value != value
        or value in {float("inf"), float("-inf")}
        or int(value) != value
        or value < 1
        or value > 9_007_199_254_740_991
    ):
        raise AuthorizationDenied("PriorSeal chainId is invalid")
    return int(value)


def _normalize_priorseal_intent(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AuthorizationDenied("PriorSeal intent must be an object")
    _only_fields(
        value,
        {
            "schema", "executionProfile", "intentId", "chainId", "chainIds",
            "action", "asset", "amount", "sender", "recipient", "validUntil",
            "nonce", "callTarget", "calldataHash", "transactionValue",
            "contextCommitments", "constraints", "intentHash",
        },
        "intent",
    )
    schema = value.get("schema")
    if schema is None:
        schema = "priorseal.intent.v2" if value.get("executionProfile") else "priorseal.intent.v1"
    if schema != "priorseal.intent.v2":
        raise AuthorizationDenied("PriorSeal intent schema must be priorseal.intent.v2")
    if value.get("executionProfile") != "priorseal.execution-profile.exact-call.v1":
        raise AuthorizationDenied("PriorSeal intent execution profile is invalid")
    if value.get("action") != "CONTRACT_CALL":
        raise AuthorizationDenied("PriorSeal exact-call intent action is invalid")
    raw_chain_id = value.get("chainId")
    if isinstance(raw_chain_id, bool) or not isinstance(raw_chain_id, (int, float)):
        raise AuthorizationDenied("PriorSeal intent chainId is invalid")
    chain_id = _chain_id(raw_chain_id)
    required = (
        "intentId", "asset", "amount", "sender", "recipient", "validUntil",
        "nonce", "callTarget", "calldataHash", "transactionValue",
    )
    if any(value.get(field) is None for field in required):
        raise AuthorizationDenied("PriorSeal exact-call intent is incomplete")
    calldata_hash = str(value["calldataHash"]).lower()
    if not re.fullmatch(r"0x[0-9a-f]{64}", calldata_hash):
        raise AuthorizationDenied("PriorSeal calldataHash must be a 32-byte hex value")
    commitments = value.get("contextCommitments")
    if not isinstance(commitments, list) or not 1 <= len(commitments) <= 16:
        raise AuthorizationDenied("PriorSeal contextCommitments are invalid")
    normalized_commitments: list[dict[str, str]] = []
    for index, entry in enumerate(commitments):
        if not isinstance(entry, Mapping):
            raise AuthorizationDenied("PriorSeal context commitment must be an object")
        _only_fields(entry, {"namespace", "algorithm", "digest"}, f"contextCommitments[{index}]")
        algorithm = str(entry.get("algorithm", "")).lower()
        digest = str(entry.get("digest", "")).lower()
        if algorithm not in {"keccak256", "sha256"}:
            raise AuthorizationDenied("PriorSeal context commitment algorithm is invalid")
        if not re.fullmatch(r"0x[0-9a-f]{64}", digest):
            raise AuthorizationDenied("PriorSeal context commitment digest is invalid")
        normalized_commitments.append({
            "namespace": _protocol_id(
                entry["namespace"] if "namespace" in entry else _UNDEFINED,
                "context namespace",
            ),
            "algorithm": algorithm,
            "digest": digest,
        })
    normalized_commitments.sort(
        key=lambda item: f"{item['namespace']}:{item['algorithm']}:{item['digest']}"
    )
    commitment_keys = {
        f"{item['namespace']}:{item['algorithm']}:{item['digest']}"
        for item in normalized_commitments
    }
    if len(commitment_keys) != len(normalized_commitments):
        raise AuthorizationDenied("PriorSeal context commitments contain duplicates")
    asset = str(value["asset"])
    asset_match = re.fullmatch(
        r"eip155:([1-9][0-9]*)/(native|erc20:0x[0-9a-fA-F]{40})", asset
    )
    if asset_match is None or int(asset_match.group(1)) != chain_id:
        raise AuthorizationDenied("PriorSeal intent asset is invalid")
    normalized: dict[str, Any] = {
        "schema": "priorseal.intent.v2",
        "executionProfile": "priorseal.execution-profile.exact-call.v1",
        "intentId": _protocol_id(value["intentId"], "intentId"),
        "chainId": chain_id,
        "action": "CONTRACT_CALL",
        "asset": asset,
        "amount": _uint_string(value["amount"], "amount"),
        "sender": _evm_address(value["sender"], "sender"),
        "recipient": _evm_address(value["recipient"], "recipient"),
        "validUntil": _positive_time(value["validUntil"], "validUntil"),
        "nonce": _uint_string(value["nonce"], "nonce"),
        "callTarget": _evm_address(value["callTarget"], "callTarget"),
        "calldataHash": calldata_hash,
        "transactionValue": _uint_string(value["transactionValue"], "transactionValue"),
        "contextCommitments": normalized_commitments,
    }
    if value.get("chainIds") is not None:
        chain_ids = value["chainIds"]
        if not isinstance(chain_ids, list):
            raise AuthorizationDenied("PriorSeal intent chainIds are invalid")
        normalized["chainIds"] = [_chain_id(item) for item in chain_ids]
    if value.get("constraints") is not None:
        constraints = value["constraints"]
        if not isinstance(constraints, Mapping):
            raise AuthorizationDenied("PriorSeal intent constraints must be an object")
        _only_fields(constraints, {"minConfirmations", "maxGasUsed"}, "intent.constraints")
        normalized_constraints = dict(constraints)
        min_confirmations = normalized_constraints.get("minConfirmations")
        if min_confirmations is not None:
            numeric_min_confirmations = _js_number(min_confirmations)
            if (
                numeric_min_confirmations is None
                or numeric_min_confirmations != numeric_min_confirmations
                or numeric_min_confirmations in {float("inf"), float("-inf")}
                or int(numeric_min_confirmations) != numeric_min_confirmations
                or not 0 <= numeric_min_confirmations <= 10_000
            ):
                raise AuthorizationDenied(
                    "PriorSeal minConfirmations must be an integer between 0 and 10000"
                )
            if isinstance(min_confirmations, (int, float)) and not isinstance(
                min_confirmations, bool
            ):
                normalized_constraints["minConfirmations"] = int(numeric_min_confirmations)
        if "maxGasUsed" in normalized_constraints:
            normalized_constraints["maxGasUsed"] = _uint_string(
                normalized_constraints["maxGasUsed"], "maxGasUsed"
            )
        normalized["constraints"] = normalized_constraints
    intent_hash = _hash_json(normalized)
    if value.get("intentHash") not in {None, intent_hash}:
        raise AuthorizationDenied("PriorSeal intent hash binding failed")
    return {**normalized, "intentHash": intent_hash}


def _verify_priorseal_authorization(signed: Mapping[str, Any]) -> dict[str, Any]:
    _only_fields(
        signed,
        {
            "schema", "domain", "authorizationId", "intent", "intentHash",
            "principal", "authorizer", "delegate", "issuedAt", "notBefore",
            "expiresAt", "authorizationNonce", "maxUses", "audience",
            "policyHash", "signature",
        },
        "authorization",
    )
    schema = signed.get("schema")
    if schema is None:
        schema = "priorseal.authorization.v2"
    if schema != "priorseal.authorization.v2":
        raise AuthorizationDenied("PriorSeal authorization schema is invalid")
    if _js_truthy(signed.get("domain")) and signed.get("domain") != "priorseal/authorization/v2":
        raise AuthorizationDenied("PriorSeal authorization domain is invalid")
    intent_value = signed.get("intent")
    if not isinstance(intent_value, Mapping):
        raise AuthorizationDenied("PriorSeal authorization intent must be an object")
    intent = _normalize_priorseal_intent(
        {key: value for key, value in intent_value.items() if key != "intentHash"}
    )
    principal = signed.get("principal")
    authorizer = signed.get("authorizer")
    delegate = signed.get("delegate")
    if (
        not isinstance(principal, Mapping)
        or not isinstance(authorizer, Mapping)
        or not isinstance(delegate, Mapping)
    ):
        raise AuthorizationDenied("PriorSeal signed authorization is malformed")
    _only_fields(principal, {"type", "id", "account"}, "authorization.principal")
    _only_fields(authorizer, {"type", "address"}, "authorization.authorizer")
    _only_fields(delegate, {"agentId", "executor"}, "authorization.delegate")
    if not _js_truthy(principal.get("id")) or not _js_truthy(delegate.get("agentId")):
        raise AuthorizationDenied("PriorSeal principal.id and delegate.agentId are required")
    principal_type = _js_string(principal.get("type") if principal.get("type") is not None else "")
    if principal_type not in {"user", "organization"}:
        raise AuthorizationDenied("PriorSeal principal type is invalid")
    authorizer_type = _js_string(
        authorizer.get("type") if authorizer.get("type") is not None else ""
    )
    if authorizer_type != "eip712":
        raise AuthorizationDenied("PriorSeal authorizer type must be eip712")
    normalized_principal = {
        "type": principal_type,
        "id": _protocol_id(principal.get("id"), "principal.id"),
        "account": _evm_address(principal.get("account"), "principal.account"),
    }
    normalized_authorizer = {
        "type": authorizer_type,
        "address": _evm_address(authorizer.get("address"), "authorizer.address"),
    }
    normalized_delegate = {
        "agentId": _protocol_id(delegate.get("agentId"), "delegate.agentId"),
        "executor": _evm_address(delegate.get("executor"), "delegate.executor"),
    }
    if normalized_principal["account"] != normalized_authorizer["address"]:
        raise AuthorizationDenied("PriorSeal principal/authorizer binding failed")
    issued_at = _positive_time(signed.get("issuedAt"), "issuedAt")
    not_before_value = signed.get("notBefore")
    expires_at_value = signed.get("expiresAt")
    not_before = _positive_time(
        issued_at if not_before_value is None else not_before_value, "notBefore"
    )
    expires_at = _positive_time(
        intent["validUntil"] if expires_at_value is None else expires_at_value,
        "expiresAt",
    )
    if not_before < issued_at or expires_at < not_before or expires_at > intent["validUntil"]:
        raise AuthorizationDenied("PriorSeal authorization time window is invalid")
    authorization_nonce_value = signed.get("authorizationNonce")
    policy_hash_value = signed.get("policyHash")
    authorization_nonce = _js_string(
        "" if authorization_nonce_value is None else authorization_nonce_value
    ).lower()
    policy_hash = _js_string(
        "0x" + "0" * 64 if policy_hash_value is None else policy_hash_value
    ).lower()
    if not re.fullmatch(r"0x[0-9a-f]{64}", authorization_nonce):
        raise AuthorizationDenied("PriorSeal authorization nonce is invalid")
    if not re.fullmatch(r"0x[0-9a-f]{64}", policy_hash):
        raise AuthorizationDenied("PriorSeal policy hash is invalid")
    max_uses_value = signed.get("maxUses")
    max_uses = _uint_string("1" if max_uses_value is None else max_uses_value, "maxUses")
    if max_uses != "1":
        raise AuthorizationDenied("PriorSeal maxUses must be 1")
    audience_value = signed.get("audience")
    audience = _protocol_id("priorseal" if audience_value is None else audience_value, "audience")
    if audience != "priorseal":
        raise AuthorizationDenied("PriorSeal authorization audience must be priorseal")
    if _js_truthy(signed.get("intentHash")) and signed.get("intentHash") != intent["intentHash"]:
        raise AuthorizationDenied("PriorSeal intent hash binding failed")
    signature = signed.get("signature")
    if not isinstance(signature, str) or not signature:
        raise AuthorizationDenied("PriorSeal authorization signature is missing")
    normalized = {
        "schema": "priorseal.authorization.v2",
        "domain": "priorseal/authorization/v2",
        "intent": intent,
        "intentHash": intent["intentHash"],
        "principal": normalized_principal,
        "authorizer": normalized_authorizer,
        "delegate": normalized_delegate,
        "issuedAt": issued_at,
        "notBefore": not_before,
        "expiresAt": expires_at,
        "authorizationNonce": authorization_nonce,
        "maxUses": max_uses,
        "audience": audience,
        "policyHash": policy_hash,
        "signature": signature,
    }
    unsigned = {key: value for key, value in normalized.items() if key != "signature"}
    authorization_id = f"auth_{_hash_json(unsigned)[:32]}"
    if _js_truthy(signed.get("authorizationId")) and signed.get("authorizationId") != authorization_id:
        raise AuthorizationDenied("PriorSeal authorization identity binding failed")
    normalized["authorizationId"] = authorization_id
    try:
        signable = encode_typed_data(
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
                "domain": {"name": "PriorSeal", "version": "2", "chainId": intent["chainId"]},
                "message": {
                    "intentHash": bytes.fromhex(intent["intentHash"]),
                    "principalType": normalized_principal["type"],
                    "principalId": normalized_principal["id"],
                    "principalAccount": normalized_principal["account"],
                    "authorizerType": normalized_authorizer["type"],
                    "authorizer": normalized_authorizer["address"],
                    "agentId": normalized_delegate["agentId"],
                    "executor": normalized_delegate["executor"],
                    "issuedAt": issued_at,
                    "notBefore": not_before,
                    "expiresAt": expires_at,
                    "authorizationNonce": authorization_nonce,
                    "maxUses": int(max_uses),
                    "audience": audience,
                    "policyHash": policy_hash,
                },
            }
        )
        recovered = Account.recover_message(signable, signature=signature)
    except Exception as exc:
        raise AuthorizationDenied("PriorSeal authorization signature is invalid") from exc
    if recovered.lower() != normalized_authorizer["address"]:
        raise AuthorizationDenied("PriorSeal authorization signature is invalid")
    return {
        "authorization_id": authorization_id,
        "authorization_hash": _hash_json(normalized),
        "intent_hash": intent["intentHash"],
        "intent": MappingProxyType(intent),
        "principal": MappingProxyType(normalized_principal),
        "authorizer": MappingProxyType(normalized_authorizer),
        "delegate": MappingProxyType(normalized_delegate),
        "not_before": not_before,
        "expires_at": expires_at,
        "issued_at": issued_at,
        "authorization_nonce": authorization_nonce,
        "normalized": MappingProxyType(normalized),
    }


def _verify_priorseal_acceptance(
    acceptance: Mapping[str, Any],
    verified: Mapping[str, Any],
    trust_roots: Mapping[str, Any],
) -> None:
    root = trust_roots.get("priorSeal")
    if not isinstance(root, Mapping):
        raise AuthorizationDenied("PriorSeal acceptance trust root is missing")
    _only_fields(
        acceptance,
        {
            "schema", "domain", "authorizationId", "authorizationHash", "intentHash",
            "acceptedAt", "sequence", "previousEntryHash", "entryHash", "status",
            "issuer", "algorithm", "keyId", "signature",
        },
        "acceptance",
    )
    if (
        acceptance.get("schema") != "priorseal.authorization-receipt.v1"
        or acceptance.get("domain") != "priorseal/authorization-receipt/v1"
        or acceptance.get("status") != "ACCEPTED"
        or acceptance.get("algorithm") != "Ed25519"
    ):
        raise AuthorizationDenied("PriorSeal acceptance is invalid")
    if acceptance.get("issuer") != root.get("issuer"):
        raise AuthorizationDenied("PriorSeal acceptance issuer is untrusted")
    if acceptance.get("keyId") != root.get("keyId"):
        raise AuthorizationDenied("PriorSeal acceptance key binding failed")
    if (
        acceptance.get("authorizationId") != verified["authorization_id"]
        or acceptance.get("authorizationHash") != verified["authorization_hash"]
        or acceptance.get("intentHash") != verified["intent_hash"]
    ):
        raise AuthorizationDenied("PriorSeal acceptance authorization binding failed")
    accepted_at = acceptance.get("acceptedAt")
    if (
        isinstance(accepted_at, bool)
        or not isinstance(accepted_at, int)
        or accepted_at < verified["not_before"]
        or accepted_at > verified["expires_at"]
        or verified["issued_at"] > accepted_at
    ):
        raise AuthorizationDenied("PriorSeal acceptance timing is invalid")
    expected_entry_hash = _hash_json(
        {
            "sequence": acceptance.get("sequence"),
            "authorizationHash": acceptance.get("authorizationHash"),
            "acceptedAt": accepted_at,
            "previousEntryHash": acceptance.get("previousEntryHash"),
        }
    )
    if acceptance.get("entryHash") != expected_entry_hash:
        raise AuthorizationDenied("PriorSeal acceptance entry hash is invalid")

    try:
        public_key = serialization.load_pem_public_key(
            str(root["publicKeyPem"]).encode("ascii")
        )
        if not isinstance(public_key, Ed25519PublicKey):
            raise TypeError("not an Ed25519 key")
        spki = public_key.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if hashlib.sha256(spki).hexdigest() != root.get("publicKeySpkiSha256"):
            raise AuthorizationDenied("PriorSeal acceptance SPKI pin mismatch")
        signature = acceptance["signature"]
        if not isinstance(signature, str) or not re.fullmatch(r"[A-Za-z0-9_-]{86}", signature):
            raise AuthorizationDenied("PriorSeal acceptance signature is invalid")
        signature_bytes = urlsafe_b64decode(signature + "==")
        if (
            len(signature_bytes) != 64
            or urlsafe_b64encode(signature_bytes).decode("ascii").rstrip("=") != signature
        ):
            raise AuthorizationDenied("PriorSeal acceptance signature is invalid")
        unsigned = {key: value for key, value in acceptance.items() if key != "signature"}
        public_key.verify(signature_bytes, _canonical_json(unsigned))
    except AuthorizationDenied:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthorizationDenied("PriorSeal acceptance signature is invalid") from exc
    except Exception as exc:
        raise AuthorizationDenied("PriorSeal acceptance signature is invalid") from exc


class SQLiteAcceptanceStore:
    """Atomic, durable single-use acceptance state backed by SQLite."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS consumed_acceptances "
                "(authorization_id TEXT PRIMARY KEY)"
            )
            connection.commit()

    def consume(self, authorization_id: str) -> bool:
        try:
            with closing(sqlite3.connect(self.database_path)) as connection:
                connection.execute(
                    "INSERT INTO consumed_acceptances (authorization_id) VALUES (?)",
                    (authorization_id,),
                )
                connection.commit()
        except sqlite3.IntegrityError:
            return False
        return True


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
        trust_roots: Mapping[str, Any],
        acceptance_store: SQLiteAcceptanceStore | None = None,
    ) -> None:
        self._response = response
        self._trust_roots = trust_roots
        self._acceptance_store = acceptance_store
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

        signed = response.get("signedAuthorization")
        if not isinstance(signed, Mapping):
            raise AuthorizationDenied("PriorSeal signed authorization is missing")
        verified = _verify_priorseal_authorization(signed)
        intent = verified["intent"]
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
        if envelope_commitment.get("algorithm") != "sha256":
            raise AuthorizationDenied("PriorSeal envelope commitment mismatch")
        if policy_commitment.get("algorithm") != "sha256":
            raise AuthorizationDenied("PriorSeal policy commitment mismatch")
        envelope_matches = (
            str(envelope_commitment.get("digest", "")).lower() == envelope_digest.lower()
        )
        policy_matches = (
            str(policy_commitment.get("digest", "")).lower()
            == policy_commitment_digest.lower()
        )
        if envelope_matches and not policy_matches:
            raise AuthorizationDenied(
                "PriorSeal authorization covers another policy decision"
            )
        if self._acceptance_store is not None:
            if not envelope_matches:
                raise AuthorizationDenied("PriorSeal authorization covers another envelope")
            if not policy_matches:
                raise AuthorizationDenied(
                    "PriorSeal authorization covers another policy decision"
                )

        acceptance = response.get("acceptance")
        if not isinstance(acceptance, Mapping):
            raise AuthorizationDenied("PriorSeal acceptance is missing")
        _verify_priorseal_acceptance(acceptance, verified, self._trust_roots)

        derived = {
            "authorization_id": verified["authorization_id"],
            "envelope_digest": envelope_commitment["digest"],
            "executor": verified["delegate"]["executor"],
            "authorizer": verified["authorizer"]["address"],
            "valid_from": verified["not_before"],
            "valid_until": verified["expires_at"],
            "nonce": verified["authorization_nonce"],
            "policy_commitment_digest": policy_commitment["digest"],
        }
        for field, value in derived.items():
            actual = response.get(field)
            if isinstance(value, str) and value.startswith("0x"):
                matches = str(actual).lower() == value.lower()
            else:
                matches = actual == value
            if not matches:
                raise AuthorizationDenied(f"PriorSeal top-level {field} mapping mismatch")

        authorization_id = str(derived["authorization_id"])
        evidence = AuthorizationEvidence(
            authorization_id=authorization_id,
            envelope_digest=str(derived["envelope_digest"]),
            executor=str(derived["executor"]),
            authorizer=str(derived["authorizer"]),
            valid_from=int(derived["valid_from"]),
            valid_until=int(derived["valid_until"]),
            nonce=str(derived["nonce"]),
            policy_commitment_digest=str(derived["policy_commitment_digest"]),
            raw=MappingProxyType(
                {
                    "signedAuthorization": response["signedAuthorization"],
                    "verificationResult": response["verificationResult"],
                    "acceptance": response["acceptance"],
                }
            ),
        )
        if evidence.executor.lower() != envelope.executor.lower():
            raise AuthorizationDenied("PriorSeal authorization names another executor")
        if self._acceptance_store is not None:
            if not evidence.is_fresh():
                raise AuthorizationDenied("PriorSeal authorization is outside its validity window")
            if not self._acceptance_store.consume(authorization_id):
                raise AuthorizationDenied(
                    "AUTHORIZATION_REPLAYED: PriorSeal acceptance "
                    f"{authorization_id} has already been consumed"
                )

        return evidence

    def authorize(self, context) -> AuthorizationEvidence:
        return self.evidence_for(
            envelope=context.envelope,
            envelope_digest=context.envelope_digest,
            policy_commitment_digest=context.policy_commitment.digest(),
        )
