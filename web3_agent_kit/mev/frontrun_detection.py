"""Frontrunning detection for pending transactions."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def detect_frontrun(
    tx: dict[str, Any],
    pending_txs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Detect if a transaction is being frontrun.

    Checks the pending transaction pool for competing transactions that
    target the same contract with higher gas prices.

    Args:
        tx: The transaction to check.
        pending_txs: Optional list of pending transactions from the mempool.
            If ``None``, returns a baseline assessment.

    Returns:
        Frontrun risk assessment dict with keys ``at_risk``, ``risk_score``,
        ``competing_txs``, and ``recommendation``.
    """
    at_risk = False
    risk_score = 0
    competing_txs: list[dict[str, Any]] = []

    to_addr = tx.get("to", "").lower()
    tx.get("data", "0x")

    # Get our gas price
    gas_price_raw = tx.get("gasPrice", "0x0")
    our_gas_price: int = (
        int(gas_price_raw, 16) if isinstance(gas_price_raw, str) else int(gas_price_raw)
    )

    if not pending_txs:
        pending_txs = []

    for pending in pending_txs:
        pending_to = pending.get("to", "").lower()
        pending.get("data", "0x")

        # Same target contract?
        if to_addr and pending_to == to_addr:
            pending_gas_raw = pending.get("gasPrice", "0x0")
            pending_gas: int = (
                int(pending_gas_raw, 16)
                if isinstance(pending_gas_raw, str)
                else int(pending_gas_raw)
            )

            # Higher gas = likely frontrun attempt
            if pending_gas > our_gas_price and our_gas_price > 0:
                gas_ratio = pending_gas / our_gas_price
                competing_txs.append({
                    "hash": pending.get("hash", "unknown"),
                    "gas_price": pending_gas,
                    "gas_ratio": round(gas_ratio, 2),
                })
                risk_score += min(30, int(gas_ratio * 10))

    if competing_txs:
        at_risk = True

    risk_score = min(100, risk_score)

    if at_risk and risk_score > 50:
        recommendation = "Use Flashbots bundle to avoid frontrunning"
    elif at_risk:
        recommendation = "Consider increasing gas price or using private RPC"
    else:
        recommendation = "No frontrunning detected"

    return {
        "at_risk": at_risk,
        "risk_score": risk_score,
        "competing_txs": competing_txs,
        "recommendation": recommendation,
    }
