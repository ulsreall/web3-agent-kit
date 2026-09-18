"""Canonical call identity and domain-separated evidence commitments.

Two different claims are produced about a transaction before it is signed:

1. **What the transaction is** — a canonical, chain-agnostic description of one
   exact EVM call. This is :class:`CallEnvelopeV1`.
2. **What our policy said about it** — the local execution-policy verdict and
   its reasons. This is :class:`PolicyDecisionCommitment`.

They are deliberately *not* the same object, and their digests are not
interchangeable. "Policy allowed this" and "the principal authorized this exact
call" are different facts, and a single hash cannot carry both without making
one of them unverifiable.

The envelope is the shared identity: an external authorization layer (for
example PriorSeal's exact-call authorization) binds to the same envelope digest
and receives the policy commitment separately, through its context commitments.
That keeps one identity across both systems while keeping the two evidence
objects domain-separated.

Canonical encoding
------------------
Every field has exactly one legal representation:

============================  ==================================================
field                         canonical rule
============================  ==================================================
``chainId``                   positive integer, EIP-155
``executor``                  lowercase 20-byte address of the sender
``nonce``                     unsigned integer, decimal string in the payload
``target``                    lowercase 20-byte address, or absent for contract
                              creation (see ``executionProfile``)
``calldataHash``              Keccak-256 of the raw calldata bytes, including
                              empty calldata (``keccak256(b"")``)
``nativeValue``               unsigned integer wei, decimal string in the payload
============================  ==================================================

The action label, policy identifiers, verdicts, reason codes, evaluation time
and any user confirmation are **outside** the envelope. They describe policy
context, not the raw transaction, and folding them in would make two identical
calls hash differently for reasons unrelated to what will be signed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..chains import Chain

__all__ = [
    "CALL_ENVELOPE_SCHEMA",
    "POLICY_DECISION_SCHEMA",
    "CallEnvelopeError",
    "CallEnvelopeV1",
    "PolicyDecisionCommitment",
    "keccak256",
]

CALL_ENVELOPE_SCHEMA = "agent-call-envelope.v1"
POLICY_DECISION_SCHEMA = "web3-agent-kit.policy-decision.v1"

_ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")
_EXECUTION_PROFILE_CALL = "call"
_EXECUTION_PROFILE_CREATE = "create"


class CallEnvelopeError(ValueError):
    """Raised when a transaction cannot be reduced to a canonical envelope.

    This is a hard failure. An envelope that cannot be built unambiguously
    means the call cannot be named, and an unnamed call must never be signed.
    """


def keccak256(data: bytes) -> bytes:
    """Return the Keccak-256 digest of ``data``.

    Keccak-256 is the EVM's own hash. Using it for calldata means the digest is
    the same value Solidity would compute, so an on-chain verifier and an
    off-chain envelope agree without a translation step.
    """
    try:
        from eth_hash.auto import keccak
    except ImportError:  # pragma: no cover - eth-hash ships with eth-account
        from eth_utils import keccak  # type: ignore[no-redef]

    return keccak(data)


def _canonical_int(value: Any, field_name: str) -> int:
    """Coerce ``value`` to a non-negative integer or fail.

    Accepts ints and decimal strings only. Booleans are rejected explicitly:
    ``True`` is an ``int`` in Python, and silently reading it as ``1`` would let
    a malformed transaction produce a valid-looking envelope.
    """
    if isinstance(value, bool):
        raise CallEnvelopeError(f"{field_name} must be an integer, not a boolean")
    if isinstance(value, int):
        candidate = value
    elif isinstance(value, str):
        text = value.strip()
        if text.startswith(("0x", "0X")):
            try:
                candidate = int(text, 16)
            except ValueError as exc:
                raise CallEnvelopeError(
                    f"{field_name} is not valid hexadecimal: {value!r}"
                ) from exc
        else:
            try:
                candidate = int(text, 10)
            except ValueError as exc:
                raise CallEnvelopeError(
                    f"{field_name} is not a decimal integer: {value!r}"
                ) from exc
    else:
        raise CallEnvelopeError(
            f"{field_name} must be an int or a numeric string, got {type(value).__name__}"
        )
    if candidate < 0:
        raise CallEnvelopeError(f"{field_name} cannot be negative")
    return candidate


def _canonical_address(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _ADDRESS_PATTERN.fullmatch(value):
        raise CallEnvelopeError(
            f"{field_name} must be a 20-byte 0x-prefixed EVM address"
        )
    return value.lower()


def _canonical_calldata(value: Any) -> bytes:
    """Return raw calldata bytes.

    ``None`` normalizes to empty rather than propagating ambiguity: a
    transaction with no ``data`` field and one with ``data="0x"`` describe the
    same call, and they must produce the same envelope.
    """
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, str):
        if not value.startswith("0x"):
            raise CallEnvelopeError("hex calldata must start with 0x")
        try:
            return bytes.fromhex(value[2:])
        except ValueError as exc:
            raise CallEnvelopeError("calldata is not valid hexadecimal") from exc
    raise CallEnvelopeError(
        f"calldata must be bytes or a 0x-prefixed hex string, "
        f"got {type(value).__name__}"
    )


@dataclass(frozen=True)
class CallEnvelopeV1:
    """Canonical identity of one exact EVM call.

    Contract creation (``target is None``) is a distinct execution profile
    rather than an absent target, so a creation can never be confused with a
    call to the zero address or with an unset field.
    """

    chain_id: int
    executor: str
    nonce: int
    calldata: bytes
    native_value: int
    target: str | None = None

    def __post_init__(self) -> None:
        if self.chain_id <= 0:
            raise CallEnvelopeError("chain_id must be a positive EIP-155 chain ID")
        if self.target is None and self.calldata == b"":
            raise CallEnvelopeError(
                "contract creation requires init code; calldata cannot be empty "
                "when target is None"
            )

    @property
    def schema(self) -> str:
        return CALL_ENVELOPE_SCHEMA

    @property
    def execution_profile(self) -> str:
        """Return ``call`` or ``create``."""
        return _EXECUTION_PROFILE_CALL if self.target else _EXECUTION_PROFILE_CREATE

    @property
    def calldata_hash(self) -> str:
        """Keccak-256 of the exact raw calldata bytes."""
        return "0x" + keccak256(self.calldata).hex()

    def to_payload(self) -> dict[str, Any]:
        """Return the canonical field payload used for hashing.

        ``target`` is omitted entirely for creation rather than set to null, so
        the serialized bytes cannot be confused with a call to a real address.
        """
        payload: dict[str, Any] = {
            "schema": CALL_ENVELOPE_SCHEMA,
            "chainId": self.chain_id,
            "executionProfile": self.execution_profile,
            "executor": self.executor,
            "nonce": str(self.nonce),
            "calldataHash": self.calldata_hash,
            "nativeValue": str(self.native_value),
        }
        if self.target is not None:
            payload["target"] = self.target
        return payload

    def digest(self) -> str:
        """Return the domain-separated envelope digest.

        The schema label is inside the hashed payload, so an envelope digest can
        never be mistaken for a digest computed over some other object's fields.
        """
        return _domain_hash(CALL_ENVELOPE_SCHEMA, self.to_payload())

    # -- construction --------------------------------------------------

    @classmethod
    def from_transaction(
        cls,
        *,
        transaction: Mapping[str, Any],
        chain: Chain,
    ) -> CallEnvelopeV1:
        """Build an envelope from a fully constructed transaction mapping.

        Raises:
            CallEnvelopeError: when a required field is missing or ambiguous.
        """
        if not isinstance(transaction, Mapping):
            raise CallEnvelopeError("transaction must be a mapping")

        chain_id = transaction.get("chainId")
        if chain_id is None:
            raise CallEnvelopeError(
                "transaction is missing chainId; an unsigned chain cannot be described"
            )
        resolved_chain_id = _canonical_int(chain_id, "chainId")

        expected_chain_id = _chain_id_of(chain)
        if resolved_chain_id != expected_chain_id:
            raise CallEnvelopeError(
                "chain mismatch: the transaction targets chainId "
                f"{resolved_chain_id} but the policy and intent describe "
                f"{chain.value} (chainId {expected_chain_id}). Refusing to sign a "
                "call whose evaluated chain and signed chain differ."
            )

        raw_sender = transaction.get("from")
        if raw_sender is None:
            raise CallEnvelopeError(
                "transaction is missing from; the executor cannot be inferred"
            )
        executor = _canonical_address(raw_sender, "from")

        nonce = _canonical_int(transaction.get("nonce", 0), "nonce")
        native_value = _canonical_int(transaction.get("value", 0), "value")
        calldata = _canonical_calldata(transaction.get("data"))

        raw_target = transaction.get("to")
        target = None if raw_target is None else _canonical_address(raw_target, "to")

        return cls(
            chain_id=resolved_chain_id,
            executor=executor,
            nonce=nonce,
            calldata=calldata,
            native_value=native_value,
            target=target,
        )


@dataclass(frozen=True)
class PolicyDecisionCommitment:
    """Domain-separated commitment over a policy verdict.

    Carries what the *policy* concluded. It binds to a :class:`CallEnvelopeV1`
    digest rather than repeating the transaction fields, so the call identity
    has exactly one source of truth.
    """

    call_identity: str
    policy_id: str
    verdict: str
    reason_codes: tuple[str, ...]
    evaluated_at: int
    policy_version: str = "1"

    @property
    def schema(self) -> str:
        return POLICY_DECISION_SCHEMA

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": POLICY_DECISION_SCHEMA,
            "callIdentity": self.call_identity,
            "policyId": self.policy_id,
            "policyVersion": self.policy_version,
            "verdict": self.verdict,
            "reasonCodes": list(self.reason_codes),
            "evaluatedAt": self.evaluated_at,
        }

    def digest(self) -> str:
        """Return the policy-decision digest, in its own domain."""
        return _domain_hash(POLICY_DECISION_SCHEMA, self.to_payload())

    def as_context_commitment(self) -> dict[str, str]:
        """Return the representation an external authorization layer receives.

        This is what enters PriorSeal's ``contextCommitments``: a namespaced
        digest plus the algorithm used, so a verifier never has to guess which
        hash function produced a bare hex string.
        """
        return {
            "namespace": POLICY_DECISION_SCHEMA,
            "algorithm": "sha256",
            "digest": self.digest(),
        }


def _chain_id_of(chain: Chain) -> int:
    """Return the EIP-155 chain ID for a :class:`Chain`, rejecting non-EVM.

    The mapping lives in :mod:`web3_agent_kit.chains.chain` and is the single
    source of truth. Imported lazily so this module stays importable without
    pulling in the chain package at definition time.
    """
    if not isinstance(chain, Chain):
        raise CallEnvelopeError("chain must be a Chain enum member")

    from ..chains.chain import CHAIN_IDS

    numeric = CHAIN_IDS.get(chain)
    if numeric is None:
        raise CallEnvelopeError(
            f"{chain.value} has no EIP-155 chain ID and cannot be described by "
            "an EVM call envelope"
        )
    return int(numeric)


def _domain_hash(namespace: str, payload: Mapping[str, Any]) -> str:
    """Hash ``payload`` with the namespace mixed in as a domain separator.

    The namespace is prepended to the canonical bytes rather than stored only
    inside the JSON, so two payloads that happen to be byte-identical under
    different labels still produce different digests.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    body = f"{namespace}\x00{canonical}".encode("utf-8")
    return "0x" + hashlib.sha256(body).hexdigest()
