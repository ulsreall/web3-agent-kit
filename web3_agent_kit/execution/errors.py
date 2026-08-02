"""Typed errors raised while creating and validating execution intents."""


class ExecutionError(Exception):
    """Base error for the transaction execution subsystem."""


class InvalidIntentError(ExecutionError, ValueError):
    """Base error for an invalid transaction intent."""


class UnsupportedActionError(InvalidIntentError):
    """Raised when an intent uses an unsupported action."""


class UnsupportedChainError(InvalidIntentError):
    """Raised when an intent targets a chain unsupported by this intent type."""


class InvalidAddressError(InvalidIntentError):
    """Raised when an EVM address is absent or malformed."""


class InvalidAmountError(InvalidIntentError):
    """Raised when an amount is not a non-negative integer in base units."""


class InvalidCalldataError(InvalidIntentError):
    """Raised when calldata is not represented as bytes."""


class InvalidMetadataError(InvalidIntentError):
    """Raised when metadata cannot be copied into an immutable representation."""
