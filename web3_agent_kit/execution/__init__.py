"""Safety-first transaction execution primitives."""

from .authorization import (
    AuthorizationContext,
    AuthorizationDenied,
    AuthorizationEvidence,
    AuthorizationProvider,
    CallableAuthorizationProvider,
    NullAuthorizationProvider,
)
from .envelope import (
    CALL_ENVELOPE_SCHEMA,
    POLICY_DECISION_SCHEMA,
    CallEnvelopeError,
    CallEnvelopeV1,
    PolicyDecisionCommitment,
)
from .errors import (
    ExecutionError,
    InvalidAddressError,
    InvalidAmountError,
    InvalidCalldataError,
    InvalidIntentError,
    InvalidMetadataError,
    UnsupportedActionError,
    UnsupportedChainError,
)
from .intent import ActionType, TransactionIntent
from .interceptor import (
    AuditEntry,
    AuthorizationRequest,
    AuthorizationVerdict,
    EnforcementDenied,
    InterceptionResult,
    PreSignInterceptor,
    UnapprovedSignerError,
)
from .policy import (
    ExecutionPolicy,
    InvalidPolicyAllowlistError,
    InvalidPolicyError,
    InvalidPolicyLimitError,
    PolicyDecision,
    PolicyReason,
    UINT256_MAX,
)

__all__ = [
    "CALL_ENVELOPE_SCHEMA",
    "POLICY_DECISION_SCHEMA",
    "ActionType",
    "AuditEntry",
    "AuthorizationContext",
    "AuthorizationDenied",
    "AuthorizationEvidence",
    "AuthorizationProvider",
    "AuthorizationRequest",
    "AuthorizationVerdict",
    "CallEnvelopeError",
    "CallEnvelopeV1",
    "CallableAuthorizationProvider",
    "EnforcementDenied",
    "ExecutionError",
    "ExecutionPolicy",
    "InterceptionResult",
    "InvalidAddressError",
    "InvalidAmountError",
    "InvalidCalldataError",
    "InvalidIntentError",
    "InvalidMetadataError",
    "InvalidPolicyAllowlistError",
    "InvalidPolicyError",
    "InvalidPolicyLimitError",
    "NullAuthorizationProvider",
    "PolicyDecision",
    "PolicyDecisionCommitment",
    "PolicyReason",
    "PreSignInterceptor",
    "TransactionIntent",
    "UINT256_MAX",
    "UnapprovedSignerError",
    "UnsupportedActionError",
    "UnsupportedChainError",
]
