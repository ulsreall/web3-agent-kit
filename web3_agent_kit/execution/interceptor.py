"""Single enforced pre-sign authorization gate for EVM transaction signing.

Every write-capable module in Web3 Agent Kit must sign through this module.
A direct ``Account.sign_transaction`` call anywhere else in the package is a
policy bypass: the transaction is built, the policy layer is skipped, and the
signature produced is indistinguishable from an authorized one.

Design contract
---------------
1. The interceptor is the only approved signing API.
2. Input is a *complete* transaction mapping. Every envelope field is validated
   and canonicalized before anything else happens.
3. The chain the policy evaluates and the chain the transaction targets must be
   the same numeric EIP-155 chain ID. A mismatch is a denial.
4. No executable policy outcome may skip principal exact-call authorization.
   Policy allow is not authority; the raw signer is unreachable until a
   verifier has confirmed an unexpired, single-use authorization for the exact
   call envelope.
5. Human confirmation is optional and never substitutes for authorization.
6. Every decision, denial and signature is recorded in an append-only audit log.
7. Fail-closed: a missing policy, a missing authorization provider, or an
   unbound wallet is a denial, never an implicit allow.

The audit log is process-local diagnostic history. It is append-only within one
Python object and is **not** durable or tamper-evident. Treating it as audit
evidence requires an external sink with integrity chaining, which this module
does not provide.

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
from .authorization import (
    AuthorizationContext,
    AuthorizationDenied,
    AuthorizationEvidence,
    AuthorizationProvider,
)
from .envelope import (
    CALL_ENVELOPE_SCHEMA,
    CallEnvelopeError,
    CallEnvelopeV1,
    PolicyDecisionCommitment,
)
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


class _DenialReason(str, Enum):
    POLICY_DENIED = "policy_denied"
    POLICY_NOT_CONFIGURED = "policy_not_configured"
    CHAIN_MISMATCH = "chain_mismatch"
    INCOMPLETE_TRANSACTION = "incomplete_transaction"
    INTENT_CONSTRUCTION_FAILED = "intent_construction_failed"
    AUTHORIZATION_NOT_CONFIGURED = "authorization_not_configured"
    AUTHORIZATION_DENIED = "authorization_denied"
    AUTHORIZATION_EXPIRED = "authorization_expired"
    AUTHORIZATION_CALL_MISMATCH = "authorization_call_mismatch"
    AUTHORIZATION_EXECUTOR_MISMATCH = "authorization_executor_mismatch"
    AUTHORIZATION_REPLAYED = "authorization_replayed"
    CONFIRMATION_REFUSED = "confirmation_refused"
    CONFIRMATION_HANDLER_MISSING = "confirmation_handler_missing"


_REQUIRED_TX_FIELDS = ("to", "from", "nonce", "chainId")


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

        missing = [
            name for name in _REQUIRED_TX_FIELDS if self.transaction.get(name) is None
        ]
        if missing:
            raise InvalidIntentError(
                "transaction must be fully constructed before signing; missing: "
                + ", ".join(sorted(missing))
            )

        object.__setattr__(self, "transaction", MappingProxyType(dict(self.transaction)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def envelope(self) -> CallEnvelopeV1:
        """Return the canonical envelope for this request.

        Raises:
            CallEnvelopeError: when the transaction cannot be canonicalized, or
                when the chain the policy names and the chain the transaction
                targets disagree.
        """
        return CallEnvelopeV1.from_transaction(
            transaction=self.transaction, chain=self.chain
        )

    @property
    def call_fingerprint(self) -> str:
        """Deterministic digest over the exact call envelope being authorized.

        This is the canonical :class:`CallEnvelopeV1` identity: chain, executor,
        nonce, target, calldata hash and native value. It deliberately excludes
        the action label and every policy fact, because those describe context
        rather than the raw call. An external authorization layer binds to this
        value; the policy verdict travels separately.
        """
        return self.envelope().digest()


@dataclass(frozen=True)
class AuditEntry:
    """One record of a gate evaluation in a process-local diagnostic log."""

    sequence: int
    recorded_at: float
    verdict: AuthorizationVerdict
    chain: str
    action: str
    call_fingerprint: str
    envelope_schema: str
    intent_id: str | None
    authorization_id: str | None
    policy_commitment_digest: str | None
    reasons: tuple[str, ...]
    signature_hash: str | None
    durable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "recorded_at": self.recorded_at,
            "verdict": self.verdict.value,
            "chain": self.chain,
            "action": self.action,
            "call_fingerprint": self.call_fingerprint,
            "envelope_schema": self.envelope_schema,
            "intent_id": self.intent_id,
            "authorization_id": self.authorization_id,
            "policy_commitment_digest": self.policy_commitment_digest,
            "reasons": list(self.reasons),
            "signature_hash": self.signature_hash,
            "durable": self.durable,
        }


@dataclass(frozen=True)
class InterceptionResult:
    """Outcome of one successful interception."""

    raw_transaction: bytes
    decision: PolicyDecision
    call_fingerprint: str
    policy_commitment: PolicyDecisionCommitment
    authorization: AuthorizationEvidence
    audit_sequence: int


class SignerFn(Protocol):
    """The single low-level signing callable the gate wraps."""

    def __call__(self, tx: Mapping[str, Any]) -> bytes: ...


ConfirmationFn = Callable[[AuthorizationRequest, PolicyDecision], bool]


class PreSignInterceptor:
    """The only approved signing API for write-capable Web3 Agent Kit modules.

    Example:
        gate = PreSignInterceptor(
            policy=policy,
            signer=raw_signer,
            authorization_provider=provider,
        )
        result = gate.sign(AuthorizationRequest(chain, action, tx))

    Both ``policy`` and ``authorization_provider`` are required for a signature
    to be produced. Either one missing is a denial.
    """

    def __init__(
        self,
        *,
        policy: ExecutionPolicy | None,
        signer: SignerFn,
        authorization_provider: AuthorizationProvider | None = None,
        confirmation_fn: ConfirmationFn | None = None,
    ) -> None:
        if not callable(signer):
            raise ExecutionError("signer must be callable")
        if policy is not None and not isinstance(policy, ExecutionPolicy):
            raise ExecutionError("policy must be an ExecutionPolicy or None")
        if authorization_provider is not None and not hasattr(
            authorization_provider, "authorize"
        ):
            raise ExecutionError(
                "authorization_provider must implement authorize(context)"
            )
        self._policy = policy
        self._signer = signer
        self._authorization_provider = authorization_provider
        self._confirmation_fn = confirmation_fn
        self._lock = threading.Lock()
        self._audit: list[AuditEntry] = []
        self._sequence = 0
        # Consumed authorization nonces, tracked by this gate so a verifier
        # without internal replay state cannot be replayed through it.
        self._consumed: set[tuple[str, str]] = set()

    # -- introspection -------------------------------------------------

    @property
    def policy(self) -> ExecutionPolicy | None:
        """Return the policy this gate enforces, if one is configured."""
        return self._policy

    @property
    def authorization_provider(self) -> AuthorizationProvider | None:
        """Return the principal authorization verifier, if one is configured."""
        return self._authorization_provider

    # -- audit ---------------------------------------------------------

    @property
    def audit_log(self) -> tuple[AuditEntry, ...]:
        """Return an immutable snapshot of every recorded evaluation.

        This is process-local history, not durable audit evidence.
        """
        with self._lock:
            return tuple(self._audit)

    def _record(
        self,
        *,
        verdict: AuthorizationVerdict,
        request: AuthorizationRequest,
        call_fingerprint: str,
        intent_id: str | None,
        authorization_id: str | None,
        policy_commitment_digest: str | None,
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
                call_fingerprint=call_fingerprint,
                envelope_schema=CALL_ENVELOPE_SCHEMA,
                intent_id=intent_id,
                authorization_id=authorization_id,
                policy_commitment_digest=policy_commitment_digest,
                reasons=reasons,
                signature_hash=signature_hash,
            )
            self._audit.append(entry)
            return entry.sequence

    # -- enforcement ---------------------------------------------------

    def sign(self, request: AuthorizationRequest) -> InterceptionResult:
        """Evaluate every gate stage and sign only when all of them pass.

        Order is deliberate and matches the review contract: normalize, policy,
        optional confirmation, principal authorization, then sign. The raw signer
        is unreachable until the fourth stage returns evidence.

        Raises:
            EnforcementDenied: when the gate refuses to produce a signature.
        """
        if not isinstance(request, AuthorizationRequest):
            raise InvalidIntentError("request must be an AuthorizationRequest")

        # Stage 1 -- normalize. This also enforces chain equality: the envelope
        # cannot be built when the policy chain and the transaction chainId
        # disagree, so a cross-chain signature never reaches the signer.
        try:
            envelope = request.envelope()
        except CallEnvelopeError as exc:
            fingerprint = self._fallback_fingerprint(request)
            self._deny(
                request,
                fingerprint,
                (_DenialReason.CHAIN_MISMATCH.value,)
                if "chain mismatch" in str(exc)
                else (_DenialReason.INCOMPLETE_TRANSACTION.value,),
                intent_id=None,
                authorization_id=None,
                policy_commitment_digest=None,
            )
            raise EnforcementDenied(str(exc)) from exc

        call_fingerprint = envelope.digest()

        # Stage 2 -- policy.
        if self._policy is None:
            self._deny(
                request,
                call_fingerprint,
                (_DenialReason.POLICY_NOT_CONFIGURED.value,),
                intent_id=None,
                authorization_id=None,
                policy_commitment_digest=None,
            )
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
                request,
                call_fingerprint,
                (_DenialReason.INTENT_CONSTRUCTION_FAILED.value,),
                intent_id=None,
                authorization_id=None,
                policy_commitment_digest=None,
            )
            raise EnforcementDenied(
                f"transaction could not be described as an intent: {exc}"
            ) from exc

        decision = self._policy.evaluate(intent)
        commitment = PolicyDecisionCommitment(
            call_identity=call_fingerprint,
            policy_id=self._policy_id(),
            verdict="allow" if decision.allowed else "deny",
            reason_codes=tuple(reason.value for reason in decision.reasons),
            evaluated_at=int(time.time()),
        )

        if not decision.allowed:
            reasons = tuple(reason.value for reason in decision.reasons)
            self._deny(
                request,
                call_fingerprint,
                reasons,
                intent_id=intent.intent_id,
                authorization_id=None,
                policy_commitment_digest=commitment.digest(),
            )
            raise EnforcementDenied(
                "policy denied transaction "
                f"{intent.intent_id}: {', '.join(reasons)}"
            )

        # Stage 3 -- optional human confirmation. Never a substitute for
        # authorization, and never able to skip it.
        if decision.requires_confirmation:
            self._require_confirmation(
                request,
                decision,
                call_fingerprint=call_fingerprint,
                policy_commitment_digest=commitment.digest(),
            )

        # Stage 4 -- principal exact-call authorization. Mandatory.
        evidence = self._authorize(
            request=request,
            envelope=envelope,
            call_fingerprint=call_fingerprint,
            commitment=commitment,
            intent_id=intent.intent_id,
        )

        # Stage 5 -- sign. Only reachable with policy allow AND fresh, matching,
        # single-use authorization evidence in hand.
        raw = self._signer(request.transaction)
        signature_hash = "0x" + hashlib.sha256(raw).hexdigest()

        sequence = self._record(
            verdict=AuthorizationVerdict.AUTHORIZED,
            request=request,
            call_fingerprint=call_fingerprint,
            intent_id=intent.intent_id,
            authorization_id=evidence.authorization_id,
            policy_commitment_digest=commitment.digest(),
            reasons=(),
            signature_hash=signature_hash,
        )
        return InterceptionResult(
            raw_transaction=raw,
            decision=decision,
            call_fingerprint=call_fingerprint,
            policy_commitment=commitment,
            authorization=evidence,
            audit_sequence=sequence,
        )

    # -- internals -----------------------------------------------------

    def _policy_id(self) -> str:
        return type(self._policy).__name__ if self._policy is not None else "none"

    def _authorize(
        self,
        *,
        request: AuthorizationRequest,
        envelope: CallEnvelopeV1,
        call_fingerprint: str,
        commitment: PolicyDecisionCommitment,
        intent_id: str,
    ) -> AuthorizationEvidence:
        provider = self._authorization_provider
        if provider is None:
            self._deny(
                request,
                call_fingerprint,
                (_DenialReason.AUTHORIZATION_NOT_CONFIGURED.value,),
                intent_id=intent_id,
                authorization_id=None,
                policy_commitment_digest=commitment.digest(),
            )
            raise EnforcementDenied(
                "policy allowed the transaction but no principal authorization "
                "provider is configured; policy allow is not authority "
                "(fail-closed)"
            )

        context = AuthorizationContext(
            envelope=envelope,
            envelope_digest=call_fingerprint,
            policy_commitment=commitment,
            action=request.action.value,
            chain=request.chain.value,
            metadata=request.metadata,
        )

        try:
            evidence = provider.authorize(context)
        except AuthorizationDenied as exc:
            self._deny(
                request,
                call_fingerprint,
                (_DenialReason.AUTHORIZATION_DENIED.value,),
                intent_id=intent_id,
                authorization_id=None,
                policy_commitment_digest=commitment.digest(),
            )
            raise EnforcementDenied(
                f"principal authorization denied: {exc}"
            ) from exc

        if not isinstance(evidence, AuthorizationEvidence):
            raise EnforcementDenied(
                "authorization provider returned "
                f"{type(evidence).__name__}, expected AuthorizationEvidence"
            )

        # Verify the evidence independently of the provider's own claims. A
        # provider that returns mismatched or stale evidence is rejected here
        # rather than trusted.
        if evidence.envelope_digest != call_fingerprint:
            self._deny(
                request,
                call_fingerprint,
                (_DenialReason.AUTHORIZATION_CALL_MISMATCH.value,),
                intent_id=intent_id,
                authorization_id=evidence.authorization_id,
                policy_commitment_digest=commitment.digest(),
            )
            raise EnforcementDenied(
                "authorization covers a different call: authorized "
                f"{evidence.envelope_digest}, signing {call_fingerprint}"
            )

        if evidence.executor.lower() != envelope.executor.lower():
            self._deny(
                request,
                call_fingerprint,
                (_DenialReason.AUTHORIZATION_EXECUTOR_MISMATCH.value,),
                intent_id=intent_id,
                authorization_id=evidence.authorization_id,
                policy_commitment_digest=commitment.digest(),
            )
            raise EnforcementDenied(
                "authorization names executor "
                f"{evidence.executor} but the transaction is sent by "
                f"{envelope.executor}"
            )

        if not evidence.is_fresh():
            self._deny(
                request,
                call_fingerprint,
                (_DenialReason.AUTHORIZATION_EXPIRED.value,),
                intent_id=intent_id,
                authorization_id=evidence.authorization_id,
                policy_commitment_digest=commitment.digest(),
            )
            raise EnforcementDenied(
                "authorization is outside its validity window: "
                f"[{evidence.valid_from}, {evidence.valid_until}]"
            )

        replay_key = (evidence.authorization_id, evidence.nonce)
        with self._lock:
            if replay_key in self._consumed:
                replayed = True
            else:
                self._consumed.add(replay_key)
                replayed = False

        if replayed:
            self._deny(
                request,
                call_fingerprint,
                (_DenialReason.AUTHORIZATION_REPLAYED.value,),
                intent_id=intent_id,
                authorization_id=evidence.authorization_id,
                policy_commitment_digest=commitment.digest(),
            )
            raise EnforcementDenied(
                f"authorization {evidence.authorization_id} has already been "
                "consumed; authorizations are single-use"
            )

        return evidence

    def _require_confirmation(
        self,
        request: AuthorizationRequest,
        decision: PolicyDecision,
        *,
        call_fingerprint: str,
        policy_commitment_digest: str,
    ) -> None:
        if self._confirmation_fn is None:
            self._deny(
                request,
                call_fingerprint,
                (_DenialReason.CONFIRMATION_HANDLER_MISSING.value,),
                intent_id=decision.intent_id,
                authorization_id=None,
                policy_commitment_digest=policy_commitment_digest,
            )
            raise EnforcementDenied(
                "policy requires confirmation but no confirmation handler is "
                "configured; refusing to sign unattended"
            )
        if not self._confirmation_fn(request, decision):
            self._deny(
                request,
                call_fingerprint,
                (_DenialReason.CONFIRMATION_REFUSED.value,),
                intent_id=decision.intent_id,
                authorization_id=None,
                policy_commitment_digest=policy_commitment_digest,
            )
            raise EnforcementDenied("operator refused the transaction")

    def _deny(
        self,
        request: AuthorizationRequest,
        call_fingerprint: str,
        reasons: tuple[str, ...],
        *,
        intent_id: str | None,
        authorization_id: str | None,
        policy_commitment_digest: str | None,
    ) -> None:
        self._record(
            verdict=AuthorizationVerdict.DENIED,
            request=request,
            call_fingerprint=call_fingerprint,
            intent_id=intent_id,
            authorization_id=authorization_id,
            policy_commitment_digest=policy_commitment_digest,
            reasons=reasons,
            signature_hash=None,
        )

    @staticmethod
    def _fallback_fingerprint(request: AuthorizationRequest) -> str:
        """Best-effort identity for a request that could not be canonicalized.

        Only used to label a denial in the diagnostic log. It is not a
        substitute for the canonical envelope and callers must not treat it as
        one.
        """
        payload = {
            "chain": getattr(request.chain, "value", None),
            "chainId": request.transaction.get("chainId"),
            "to": str(request.transaction.get("to", "")).lower(),
            "nonce": str(request.transaction.get("nonce", "")),
            "action": getattr(request.action, "value", None),
            "canonical": False,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "0x" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
