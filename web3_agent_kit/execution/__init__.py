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
    "run_all_probes",
]


def run_all_probes():
    """Run the P0 enforcement probes and return their results.

    Imported lazily. ``web3_agent_kit.execution`` must not import
    ``p0_probe`` at package-import time: doing so places the module in
    ``sys.modules`` before ``runpy`` executes it, so
    ``python -m web3_agent_kit.execution.p0_probe`` emits a RuntimeWarning
    about unpredictable behaviour. The warning is cosmetic and the exit code
    was always correct, but the documented invocation should be clean.

    The console entry point (``wak-p0-probe``) was unaffected because it never
    went through ``runpy`` -- which is exactly why the warning survived a test
    suite that only exercised the entry point.
    """
    from .p0_probe import run_all_probes as _run

    return _run()

