"""API routes package."""

from . import (
    approval,
    bridge,
    dca,
    gas,
    portfolio,
    swap,
    wallet,
    watcher,
    yield_opt,
)

__all__ = [
    "wallet",
    "swap",
    "portfolio",
    "gas",
    "watcher",
    "approval",
    "dca",
    "yield_opt",
    "bridge",
]
