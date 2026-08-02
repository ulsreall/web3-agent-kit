"""Deterministic, offline authorization policy for transaction intents."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType

from ..chains import Chain
from .errors import ExecutionError
from .intent import ActionType, TransactionIntent

__all__ = [
    "ExecutionPolicy",
    "InvalidPolicyAllowlistError",
    "InvalidPolicyError",
    "InvalidPolicyLimitError",
    "PolicyDecision",
    "PolicyReason",
    "UINT256_MAX",
]

UINT256_MAX = 2**256 - 1
_EVM_ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")


class InvalidPolicyError(ExecutionError, ValueError):
    """Base error for invalid execution policy configuration."""


class InvalidPolicyAllowlistError(InvalidPolicyError):
    """Raised when a policy allowlist contains an invalid value."""


class InvalidPolicyLimitError(InvalidPolicyError):
    """Raised when a policy limit is absent or malformed."""


class PolicyReason(str, Enum):
    """Stable, machine-readable reasons for a policy denial."""

    CHAIN_NOT_ALLOWED = "chain_not_allowed"
    ACTION_NOT_ALLOWED = "action_not_allowed"
    CONTRACT_NOT_ALLOWED = "contract_not_allowed"
    TOKEN_NOT_ALLOWED = "token_not_allowed"
    NATIVE_VALUE_EXCEEDED = "native_value_exceeded"
    TOKEN_LIMIT_NOT_CONFIGURED = "token_limit_not_configured"
    TOKEN_AMOUNT_EXCEEDED = "token_amount_exceeded"
    APPROVAL_LIMIT_NOT_CONFIGURED = "approval_limit_not_configured"
    APPROVAL_AMOUNT_EXCEEDED = "approval_amount_exceeded"
    UNLIMITED_APPROVAL_DENIED = "unlimited_approval_denied"


@dataclass(frozen=True)
class PolicyDecision:
    """Immutable result of evaluating one intent against one policy."""

    allowed: bool
    reasons: tuple[PolicyReason, ...]
    intent_id: str
    requires_confirmation: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise InvalidPolicyError("allowed must be a boolean")
        if not isinstance(self.requires_confirmation, bool):
            raise InvalidPolicyError("requires_confirmation must be a boolean")
        if not isinstance(self.intent_id, str) or not self.intent_id:
            raise InvalidPolicyError("intent_id must be a non-empty string")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(reason, PolicyReason) for reason in self.reasons
        ):
            raise InvalidPolicyError("reasons must be a tuple of PolicyReason values")
        if len(set(self.reasons)) != len(self.reasons):
            raise InvalidPolicyError("reasons cannot contain duplicates")
        if self.allowed and self.reasons:
            raise InvalidPolicyError("an allowed decision cannot contain denial reasons")
        if not self.allowed and not self.reasons:
            raise InvalidPolicyError("a denied decision requires at least one reason")

    @property
    def primary_reason(self) -> PolicyReason | None:
        """Return the first denial reason, if any."""
        return self.reasons[0] if self.reasons else None

    def has_reason(self, reason: PolicyReason) -> bool:
        """Return whether this decision includes a specific denial reason."""
        return reason in self.reasons


def _copy_typed_set(
    values: Iterable[object], expected_type: type, field_name: str
) -> frozenset:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise InvalidPolicyAllowlistError(f"{field_name} must be an iterable")
    copied = frozenset(values)
    if any(not isinstance(value, expected_type) for value in copied):
        raise InvalidPolicyAllowlistError(
            f"{field_name} must contain only {expected_type.__name__} values"
        )
    return copied


def _normalize_address(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _EVM_ADDRESS_PATTERN.fullmatch(value):
        raise InvalidPolicyAllowlistError(
            f"{field_name} keys must be 20-byte 0x-prefixed EVM addresses"
        )
    return value.lower()


def _copy_address_set(values: Iterable[object], field_name: str) -> frozenset[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise InvalidPolicyAllowlistError(f"{field_name} must be an iterable")
    return frozenset(_normalize_address(value, field_name) for value in values)


def _validate_limit(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidPolicyLimitError(f"{field_name} must be an integer in base units")
    if value < 0:
        raise InvalidPolicyLimitError(f"{field_name} cannot be negative")
    return value


def _copy_limit_mapping(
    values: Mapping[object, object], field_name: str
) -> Mapping[str, int]:
    if not isinstance(values, Mapping):
        raise InvalidPolicyLimitError(f"{field_name} must be a mapping")
    copied: dict[str, int] = {}
    for address, limit in values.items():
        normalized = _normalize_address(address, field_name)
        validated = _validate_limit(limit, f"{field_name}[{normalized}]")
        if normalized in copied:
            raise InvalidPolicyLimitError(
                f"{field_name} contains duplicate normalized address {normalized}"
            )
        copied[normalized] = validated
    return MappingProxyType(copied)


@dataclass(frozen=True)
class ExecutionPolicy:
    """Fail-closed allowlists and limits for EVM transaction intents.

    Empty allowlists deny all matching resources; they never mean unrestricted.
    Policy evaluation is deterministic and performs no network operations.
    """

    allowed_chains: frozenset[Chain]
    allowed_actions: frozenset[ActionType]
    allowed_contracts: frozenset[str] = frozenset()
    allowed_tokens: frozenset[str] = frozenset()
    max_native_value_wei: int = 0
    max_token_amounts: Mapping[str, int] = field(default_factory=dict)
    max_approval_amounts: Mapping[str, int] = field(default_factory=dict)
    deny_unlimited_approval: bool = True
    require_confirmation: bool = True

    def __post_init__(self) -> None:
        chains = _copy_typed_set(self.allowed_chains, Chain, "allowed_chains")
        actions = _copy_typed_set(self.allowed_actions, ActionType, "allowed_actions")
        contracts = _copy_address_set(self.allowed_contracts, "allowed_contracts")
        tokens = _copy_address_set(self.allowed_tokens, "allowed_tokens")
        native_limit = _validate_limit(self.max_native_value_wei, "max_native_value_wei")
        token_limits = _copy_limit_mapping(self.max_token_amounts, "max_token_amounts")
        approval_limits = _copy_limit_mapping(
            self.max_approval_amounts, "max_approval_amounts"
        )
        if not isinstance(self.deny_unlimited_approval, bool):
            raise InvalidPolicyError("deny_unlimited_approval must be a boolean")
        if not isinstance(self.require_confirmation, bool):
            raise InvalidPolicyError("require_confirmation must be a boolean")

        object.__setattr__(self, "allowed_chains", chains)
        object.__setattr__(self, "allowed_actions", actions)
        object.__setattr__(self, "allowed_contracts", contracts)
        object.__setattr__(self, "allowed_tokens", tokens)
        object.__setattr__(self, "max_native_value_wei", native_limit)
        object.__setattr__(self, "max_token_amounts", token_limits)
        object.__setattr__(self, "max_approval_amounts", approval_limits)

    @classmethod
    def deny_all(cls, *, require_confirmation: bool = True) -> ExecutionPolicy:
        """Return an explicit policy that denies every transaction intent."""
        return cls(
            allowed_chains=frozenset(),
            allowed_actions=frozenset(),
            require_confirmation=require_confirmation,
        )

    def evaluate(self, intent: TransactionIntent) -> PolicyDecision:
        """Evaluate all rules and return every applicable denial reason."""
        if not isinstance(intent, TransactionIntent):
            raise InvalidPolicyError("intent must be a TransactionIntent")

        reasons: list[PolicyReason] = []
        if intent.chain not in self.allowed_chains:
            reasons.append(PolicyReason.CHAIN_NOT_ALLOWED)
        if intent.action not in self.allowed_actions:
            reasons.append(PolicyReason.ACTION_NOT_ALLOWED)
        if intent.contract is not None and intent.contract not in self.allowed_contracts:
            reasons.append(PolicyReason.CONTRACT_NOT_ALLOWED)
        if intent.token is not None and intent.token not in self.allowed_tokens:
            reasons.append(PolicyReason.TOKEN_NOT_ALLOWED)
        if intent.native_value_wei > self.max_native_value_wei:
            reasons.append(PolicyReason.NATIVE_VALUE_EXCEEDED)

        if intent.action == ActionType.TRANSFER_TOKEN:
            token_limit = self.max_token_amounts.get(intent.token)
            if token_limit is None:
                reasons.append(PolicyReason.TOKEN_LIMIT_NOT_CONFIGURED)
            elif intent.amount_base_units > token_limit:
                reasons.append(PolicyReason.TOKEN_AMOUNT_EXCEEDED)

        if intent.action == ActionType.APPROVE_TOKEN:
            approval_limit = self.max_approval_amounts.get(intent.token)
            if approval_limit is None:
                reasons.append(PolicyReason.APPROVAL_LIMIT_NOT_CONFIGURED)
            elif intent.amount_base_units > approval_limit:
                reasons.append(PolicyReason.APPROVAL_AMOUNT_EXCEEDED)
            if (
                self.deny_unlimited_approval
                and intent.amount_base_units == UINT256_MAX
            ):
                reasons.append(PolicyReason.UNLIMITED_APPROVAL_DENIED)

        return PolicyDecision(
            allowed=not reasons,
            reasons=tuple(reasons),
            intent_id=intent.intent_id,
            requires_confirmation=self.require_confirmation,
        )
