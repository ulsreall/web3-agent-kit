"""Mandatory principal exact-call authorization, after policy and before signing.

Why this exists
---------------
A local execution policy answers "may this shape of transaction be signed at
all": is this chain allowed, is this contract allowlisted, is the native value
inside the limit. It does **not** answer "did the principal authorize this exact
call". A policy allow and a principal authorization are different claims, and
collapsing them means an allowlisted contract plus a generous limit is enough to
move funds with no principal in the loop.

This module makes the second claim mandatory. It sits between policy evaluation
and the raw signer, so a raw signature is unreachable until a verifier has
confirmed an unexpired, single-use authorization covering the exact call
envelope being signed.

Contract
--------
An implementation receives an :class:`AuthorizationContext` and returns an
:class:`AuthorizationEvidence`, or raises :class:`AuthorizationDenied`. It
**must** reject when:

* no authorization covers the call,
* the covered call identity differs from the requested envelope digest,
* the authorization has expired or its validity window has not started,
* the executor in the authorization is not the transaction sender,
* the single-use nonce has already been consumed.

Verifiers are also required to be single-use: consuming the same authorization
twice must fail the second time. That property is enforced against *this gate's*
view of consumption as well, so a verifier with no internal replay state cannot
silently reopen the hole.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .envelope import CallEnvelopeV1, PolicyDecisionCommitment
from .errors import ExecutionError

__all__ = [
    "AuthorizationContext",
    "AuthorizationDenied",
    "AuthorizationEvidence",
    "AuthorizationProvider",
    "CallableAuthorizationProvider",
    "NullAuthorizationProvider",
]


class AuthorizationDenied(ExecutionError):
    """Raised when principal authorization is absent, stale or mismatched.

    This is a hard stop. Callers must not catch and continue: a missing
    authorization is the gate working as designed.
    """


class AuthorizationContextError(ExecutionError):
    """Raised when an authorization provider misbehaves."""


@dataclass(frozen=True)
class AuthorizationContext:
    """Everything a verifier needs to decide one exact call.

    Deliberately carries the already-computed envelope rather than raw
    transaction fields: the verifier compares identities, it does not rebuild
    them. Rebuilding would reintroduce exactly the normalization drift the
    canonical envelope exists to remove.
    """

    envelope: CallEnvelopeV1
    envelope_digest: str
    policy_commitment: PolicyDecisionCommitment
    action: str
    chain: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthorizationEvidence:
    """Proof that a principal authorized one exact call.

    ``authorization_id`` identifies the authorization. ``executor`` and
    ``authorizer`` are separate fields because they are separate roles: an
    authorization that names the same account for both proves role separation
    on paper and nothing about custody separation in practice, and a caller
    that cares can compare them.
    """

    authorization_id: str
    envelope_digest: str
    executor: str
    authorizer: str
    valid_from: int
    valid_until: int
    nonce: str
    policy_commitment_digest: str
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.authorization_id:
            raise AuthorizationContextError("authorization_id must be non-empty")
        if not self.envelope_digest.startswith("0x"):
            raise AuthorizationContextError(
                "envelope_digest must be a 0x-prefixed digest"
            )
        if not self.nonce:
            raise AuthorizationContextError("nonce must be non-empty")
        if self.valid_until <= self.valid_from:
            raise AuthorizationContextError(
                "valid_until must be later than valid_from"
            )

    def covers(self, *, envelope_digest: str, executor: str) -> bool:
        """Return whether this authorization covers the given call exactly."""
        return (
            self.envelope_digest == envelope_digest
            and self.executor.lower() == executor.lower()
        )

    def is_fresh(self, *, now: int | None = None) -> bool:
        """Return whether the validity window contains ``now``."""
        moment = int(time.time()) if now is None else int(now)
        return self.valid_from <= moment <= self.valid_until


@runtime_checkable
class AuthorizationProvider(Protocol):
    """Structural type for a principal exact-call authorization verifier."""

    @property
    def policy_id(self) -> str:
        """Return a stable identifier for this provider's policy."""
        ...

    def authorize(self, context: AuthorizationContext) -> AuthorizationEvidence:
        """Verify authorization for one exact call or raise.

        Implementations must not return evidence for a call they did not
        actually verify.
        """
        ...


class NullAuthorizationProvider:
    """A provider that verifies nothing and therefore authorizes nothing.

    Exists so the intent is explicit at call sites. Passing this to a gate is
    legal but the gate will refuse every write-capable transaction, which is the
    correct behaviour for "no authorization provider is configured".
    """

    @property
    def policy_id(self) -> str:
        return "null-authorization"

    def authorize(self, context: AuthorizationContext) -> AuthorizationEvidence:
        raise AuthorizationDenied(
            "no principal authorization provider is configured; refusing to "
            "sign without an exact-call authorization (fail-closed)"
        )


class CallableAuthorizationProvider:
    """Adapts a plain callable into an :class:`AuthorizationProvider`.

    The callable receives an :class:`AuthorizationContext` and must return an
    :class:`AuthorizationEvidence` or raise :class:`AuthorizationDenied`. Useful
    for tests and for wrapping a client that cannot be changed.
    """

    def __init__(
        self, verifier: Callable[[AuthorizationContext], AuthorizationEvidence]
    ) -> None:
        if not callable(verifier):
            raise AuthorizationContextError("verifier must be callable")
        self._verifier = verifier

    @property
    def policy_id(self) -> str:
        return "callable-authorization"

    def authorize(self, context: AuthorizationContext) -> AuthorizationEvidence:
        result = self._verifier(context)
        if not isinstance(result, AuthorizationEvidence):
            raise AuthorizationContextError(
                "authorization verifier returned "
                f"{type(result).__name__}, expected AuthorizationEvidence"
            )
        return result
