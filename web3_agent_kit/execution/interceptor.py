"""Single enforced pre-sign authorization gate for EVM transaction signing.

Every write-capable module in Web3 Agent Kit must sign through this module.
A direct ``Account.sign_transaction`` call anywhere else in the package is a
policy bypass: the transaction is built, the policy layer is skipped, and the
signature produced is indistinguishable from an authorized one.

Design contract
---------------
1. The interceptor is the only approved signing API.
2. Input is a *complete* transaction mapping (to, data, value, nonce, chainId).
3. No executable policy outcome may skip exact-call authorization.
4. Every decision, denial and signature is recorded in an append-only audit log.
5. Fail-closed: a missing policy is a denial, never an implicit allow.

This module performs no network operations. Policy evaluation is deterministic.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol

from ..chains import Chain
from .errors import ExecutionError, InvalidIntentError
from .intent import ActionType, TransactionIntent
from .policy import ExecutionPolicy, PolicyDecision

__all__ = [
    "AuthorizationRequest",
    "AuthorizationVerdict",
    "AuditEntry",
    "EnforcementDenied",
    "InterceptionResult",
    "PreSignInterceptor",
    "SignerFn",
    "UnapprovedSignerError",
]


class EnforcementDenied(ExecutionError):
    """Raised when the pre-sign gate refuses to authorize a signature.

    This is a hard stop. Callers must not catch and continue: a denied
    signature is the gate working as designed.
    """


class UnapprovedSignerError(ExecutionError):
    """Raised when a module attempts to sign outside the interceptor."""


class AuthorizationVerdict(str, Enum):
    """Terminal outcome of a pre-sign gate evaluation."""

    AUTHORIZED = "authorized"
    DENIED = "denied"
    CONFIRMATION_REQUIRED = "confirmation_required"


class _DenialReason(str, Enum):
    POLICY_DENIED = "policy_denied"
    POLICY_NOT_CONFIGURED = "policy_not_configured"
    CONFIRMATION_REFUSED = "confirmation_refused"
    CONFIRMATION_HANDLER_MISSING = "confirmation_handler_missing"
    INCOMPLETE_TRANSACTION = "incomplete_transaction"
    INTENT_CONSTRUCTION_FAILED = "intent_construction_failed"


_REQUIRED_TX_FIELDS = ("to", "nonce", "chainId")


@dataclass(frozen=True)
class AuthorizationRequest:
    """An immutable request to sign one fully constructed transaction."""

    chain: Chain
    action: ActionType
    transaction: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.transaction, Mapping):
            raise InvalidIntentError("transaction must be a mapping")
        missing = [name for name in _REQUIRED_TX_FIELDS if self.transaction.get(name) is None]
        if missing:
            raise InvalidIntentError(
                "transaction must be fully constructed before signing; missing: "
                + ", ".join(sorted(missing))
            )
        object.__setattr__(self, "transaction", MappingProxyType(dict(self.transaction)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def call_fingerprint(self) -> str:
        """Deterministic digest over the exact call envelope being authorized.

        Binds chain, target, calldata, native value and nonce. This is the
        value an external evidence layer may commit to.
        """
        payload = {
            "chain": self.chain.value,
            "chainId": self.transaction.get("chainId"),
            "to": _lower(self.transaction.get("to")),
            "data": _hex_of(self.transaction.get("data")),
            "value": int(self.transaction.get("value") or 0),
            "nonce": int(self.transaction.get("nonce") or 0),
            "action": self.action.value,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "0x" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    """One append-only record of a gate evaluation."""

    sequence: int
    recorded_at: float
    verdict: AuthorizationVerdict
    chain: str
    action: str
    call_fingerprint: str
    intent_id: str | None
    reasons: tuple[str, ...]
    signature_hash: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "recorded_at": self.recorded_at,
            "verdict": self.verdict.value,
            "chain": self.chain,
            "action": self.action,
            "call_fingerprint": self.call_fingerprint,
            "intent_id": self.intent_id,
            "reasons": list(self.reasons),
            "signature_hash": self.signature_hash,
        }


@dataclass(frozen=True)
class InterceptionResult:
    """Outcome of one successful interception."""

    raw_transaction: bytes
    decision: PolicyDecision
    call_fingerprint: str
    audit_sequence: int


class SignerFn(Protocol):
    """The single low-level signing callable the gate wraps."""

    def __call__(self, tx: Mapping[str, Any]) -> bytes: ...


ConfirmationFn = Callable[[AuthorizationRequest, PolicyDecision], bool]


def _lower(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


def _hex_of(value: Any) -> str:
    if value is None:
        return "0x"
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, str):
        return value if value.startswith("0x") else "0x" + value
    return str(value)


class PreSignInterceptor:
    """The only approved signing API for write-capable Web3 Agent Kit modules.

    Example:
        gate = PreSignInterceptor(policy=policy, signer=raw_signer)
        result = gate.sign(AuthorizationRequest(chain, action, tx))
    """

    def __init__(
        self,
        *,
        policy: ExecutionPolicy | None,
        signer: SignerFn,
        confirmation_fn: ConfirmationFn | None = None,
        allow_unattended: bool = False,
    ) -> None:
        if not callable(signer):
            raise ExecutionError("signer must be callable")
        if policy is not None and not isinstance(policy, ExecutionPolicy):
            raise ExecutionError("policy must be an ExecutionPolicy or None")
        self._policy = policy
        self._signer = signer
        self._confirmation_fn = confirmation_fn
        self._allow_unattended = bool(allow_unattended)
        self._lock = threading.Lock()
        self._audit: list[AuditEntry] = []
        self._sequence = 0

    # -- introspection -------------------------------------------------

    @property
    def policy(self) -> ExecutionPolicy | None:
        """Return the policy this gate enforces, if one is configured."""
        return self._policy

    # -- audit ---------------------------------------------------------

    @property
    def audit_log(self) -> tuple[AuditEntry, ...]:
        """Return an immutable snapshot of every recorded evaluation."""
        with self._lock:
            return tuple(self._audit)

    def _record(
        self,
        *,
        verdict: AuthorizationVerdict,
        request: AuthorizationRequest,
        intent_id: str | None,
        reasons: tuple[str, ...],
        signature_hash: str | None,
    ) -> int:
        with self._lock:
            self._sequence += 1
            entry = AuditEntry(
                sequence=self._sequence,
                recorded_at=time.time(),
                verdict=verdict,
                chain=request.chain.value,
                action=request.action.value,
                call_fingerprint=request.call_fingerprint,
                intent_id=intent_id,
                reasons=reasons,
                signature_hash=signature_hash,
            )
            self._audit.append(entry)
            return entry.sequence

    # -- enforcement ---------------------------------------------------

    def sign(self, request: AuthorizationRequest) -> InterceptionResult:
        """Evaluate policy and sign only when the gate authorizes.

        Raises:
            EnforcementDenied: when the gate refuses to produce a signature.
        """
        if not isinstance(request, AuthorizationRequest):
            raise InvalidIntentError("request must be an AuthorizationRequest")

        if self._policy is None:
            self._deny(request, (_DenialReason.POLICY_NOT_CONFIGURED.value,), None)
            raise EnforcementDenied(
                "no ExecutionPolicy configured; refusing to sign (fail-closed)"
            )

        try:
            intent = TransactionIntent.from_evm_transaction(
                chain=request.chain,
                action=request.action,
                transaction=request.transaction,
                metadata=request.metadata,
            )
        except ExecutionError as exc:
            self._deny(
                request, (_DenialReason.INTENT_CONSTRUCTION_FAILED.value,), None
            )
            raise EnforcementDenied(
                f"transaction could not be described as an intent: {exc}"
            ) from exc

        decision = self._policy.evaluate(intent)

        if not decision.allowed:
            reasons = tuple(reason.value for reason in decision.reasons)
            self._deny(request, reasons, intent.intent_id)
            raise EnforcementDenied(
                "policy denied transaction "
                f"{intent.intent_id}: {', '.join(reasons)}"
            )

        if decision.requires_confirmation:
            self._require_confirmation(request, decision)

        raw = self._signer(request.transaction)
        signature_hash = "0x" + hashlib.sha256(raw).hexdigest()

        sequence = self._record(
            verdict=AuthorizationVerdict.AUTHORIZED,
            request=request,
            intent_id=intent.intent_id,
            reasons=(),
            signature_hash=signature_hash,
        )
        return InterceptionResult(
            raw_transaction=raw,
            decision=decision,
            call_fingerprint=request.call_fingerprint,
            audit_sequence=sequence,
        )

    # -- internals -----------------------------------------------------

    def _require_confirmation(
        self, request: AuthorizationRequest, decision: PolicyDecision
    ) -> None:
        if self._confirmation_fn is None:
            if self._allow_unattended:
                return
            self._deny(
                request,
                (_DenialReason.CONFIRMATION_HANDLER_MISSING.value,),
                decision.intent_id,
            )
            raise EnforcementDenied(
                "policy requires confirmation but no confirmation handler is "
                "configured; refusing to sign unattended"
            )
        if not self._confirmation_fn(request, decision):
            self._deny(
                request,
                (_DenialReason.CONFIRMATION_REFUSED.value,),
                decision.intent_id,
            )
            raise EnforcementDenied("operator refused the transaction")

    def _deny(
        self,
        request: AuthorizationRequest,
        reasons: tuple[str, ...],
        intent_id: str | None,
    ) -> None:
        self._record(
            verdict=AuthorizationVerdict.DENIED,
            request=request,
            intent_id=intent_id,
            reasons=reasons,
            signature_hash=None,
        )
