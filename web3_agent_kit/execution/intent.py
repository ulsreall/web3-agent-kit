"""Immutable transaction intents for deterministic EVM execution planning.

An intent describes what a caller wants to do. It is not authorization to sign
or broadcast a transaction. Execution policy, simulation, confirmation, and a
signer remain separate stages of the execution lifecycle.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from ..chains import Chain
from .errors import (
    InvalidAddressError,
    InvalidAmountError,
    InvalidCalldataError,
    InvalidIntentError,
    InvalidMetadataError,
    UnsupportedActionError,
    UnsupportedChainError,
)

_EVM_ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")


class ActionType(str, Enum):
    """Supported high-level EVM transaction actions."""

    TRANSFER_NATIVE = "transfer_native"
    TRANSFER_TOKEN = "transfer_token"
    APPROVE_TOKEN = "approve_token"
    CONTRACT_CALL = "contract_call"
    SWAP = "swap"
    BRIDGE = "bridge"
    STAKE = "stake"
    UNSTAKE = "unstake"
    GOVERNANCE = "governance"


def _normalize_address(value: str | None, field_name: str, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise InvalidAddressError(f"{field_name} is required")
        return None
    if not isinstance(value, str) or not _EVM_ADDRESS_PATTERN.fullmatch(value):
        raise InvalidAddressError(f"{field_name} must be a 20-byte 0x-prefixed EVM address")
    return value.lower()


def _validate_amount(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidAmountError(f"{field_name} must be an integer in base units")
    if value < 0:
        raise InvalidAmountError(f"{field_name} cannot be negative")
    return value


def _freeze_metadata(value: Any) -> Any:
    """Copy supported metadata into recursively immutable containers."""
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise InvalidMetadataError("metadata keys must be strings")
            frozen[key] = _freeze_metadata(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_metadata(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_metadata(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    raise InvalidMetadataError(
        f"unsupported metadata value type: {type(value).__name__}"
    )


@dataclass(frozen=True)
class TransactionIntent:
    """A validated, immutable description of a future EVM transaction.

    Amounts are integers in their smallest units. Metadata is excluded from the
    deterministic intent ID and must never carry security-critical fields.
    """

    chain: Chain
    action: ActionType
    sender: str
    recipient: str | None = None
    contract: str | None = None
    token: str | None = None
    amount_base_units: int = 0
    native_value_wei: int = 0
    calldata: bytes = b""
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        if not isinstance(self.chain, Chain):
            raise UnsupportedChainError("chain must be a Chain enum member")
        if self.chain == Chain.SOLANA:
            raise UnsupportedChainError(
                "TransactionIntent currently supports EVM chains only"
            )
        if not isinstance(self.action, ActionType):
            raise UnsupportedActionError("action must be an ActionType enum member")

        sender = _normalize_address(self.sender, "sender", required=True)
        recipient = _normalize_address(self.recipient, "recipient", required=False)
        contract = _normalize_address(self.contract, "contract", required=False)
        token = _normalize_address(self.token, "token", required=False)

        if self.action == ActionType.TRANSFER_NATIVE and recipient is None:
            raise InvalidAddressError("recipient is required for a native transfer")
        if self.action == ActionType.TRANSFER_TOKEN:
            if recipient is None:
                raise InvalidAddressError("recipient is required for a token transfer")
            if token is None:
                raise InvalidAddressError("token is required for a token transfer")
        if self.action == ActionType.APPROVE_TOKEN:
            if recipient is None:
                raise InvalidAddressError("recipient must identify the approval spender")
            if token is None:
                raise InvalidAddressError("token is required for an approval")
        if self.action in {
            ActionType.CONTRACT_CALL,
            ActionType.SWAP,
            ActionType.BRIDGE,
            ActionType.STAKE,
            ActionType.UNSTAKE,
            ActionType.GOVERNANCE,
        } and contract is None:
            raise InvalidAddressError(f"contract is required for {self.action.value}")

        amount = _validate_amount(self.amount_base_units, "amount_base_units")
        native_value = _validate_amount(self.native_value_wei, "native_value_wei")
        if not isinstance(self.calldata, bytes):
            raise InvalidCalldataError("calldata must be bytes")
        if not isinstance(self.metadata, Mapping):
            raise InvalidMetadataError("metadata must be a mapping")

        object.__setattr__(self, "sender", sender)
        object.__setattr__(self, "recipient", recipient)
        object.__setattr__(self, "contract", contract)
        object.__setattr__(self, "token", token)
        object.__setattr__(self, "amount_base_units", amount)
        object.__setattr__(self, "native_value_wei", native_value)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    @property
    def intent_id(self) -> str:
        """Return a deterministic SHA-256 ID of security-critical fields."""
        payload = {
            "action": self.action.value,
            "amount_base_units": self.amount_base_units,
            "calldata": self.calldata.hex(),
            "chain": self.chain.value,
            "contract": self.contract,
            "native_value_wei": self.native_value_wei,
            "recipient": self.recipient,
            "sender": self.sender,
            "token": self.token,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_evm_transaction(
        cls,
        *,
        chain: Chain,
        action: ActionType,
        transaction: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> TransactionIntent:
        """Create an intent from a normalized Web3 transaction mapping."""
        if not isinstance(transaction, Mapping):
            raise InvalidIntentError("transaction must be a mapping")
        if action in {ActionType.TRANSFER_TOKEN, ActionType.APPROVE_TOKEN}:
            raise InvalidIntentError(
                "token transfers and approvals require decoded semantic fields"
            )
        calldata = transaction.get("data", b"")
        if isinstance(calldata, str):
            if not calldata.startswith("0x"):
                raise InvalidCalldataError("hex calldata must start with 0x")
            try:
                calldata = bytes.fromhex(calldata[2:])
            except ValueError as exc:
                raise InvalidCalldataError("calldata is not valid hexadecimal") from exc

        destination = transaction.get("to")
        contract_actions = {
            ActionType.CONTRACT_CALL,
            ActionType.SWAP,
            ActionType.BRIDGE,
            ActionType.STAKE,
            ActionType.UNSTAKE,
            ActionType.GOVERNANCE,
        }
        return cls(
            chain=chain,
            action=action,
            sender=transaction.get("from"),
            recipient=destination if action == ActionType.TRANSFER_NATIVE else None,
            contract=destination if action in contract_actions else None,
            token=destination
            if action in {ActionType.TRANSFER_TOKEN, ActionType.APPROVE_TOKEN}
            else None,
            native_value_wei=transaction.get("value", 0),
            calldata=calldata,
            metadata=metadata or {},
        )

    def to_evm_transaction(self) -> dict[str, Any]:
        """Return the normalized transaction fields represented by this intent."""
        if self.action in {ActionType.TRANSFER_TOKEN, ActionType.APPROVE_TOKEN}:
            destination = self.token
        else:
            destination = self.contract or self.recipient
        transaction: dict[str, Any] = {
            "from": self.sender,
            "value": self.native_value_wei,
            "data": self.calldata,
        }
        if destination is not None:
            transaction["to"] = destination
        return transaction
