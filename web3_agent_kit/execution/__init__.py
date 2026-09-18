"""Safety-first transaction execution primitives."""

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
    "ActionType",
    "AuditEntry",
    "AuthorizationRequest",
    "AuthorizationVerdict",
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
    "PolicyDecision",
    "PolicyReason",
    "PreSignInterceptor",
    "TransactionIntent",
    "UINT256_MAX",
    "UnapprovedSignerError",
    "UnsupportedActionError",
    "UnsupportedChainError",
]

