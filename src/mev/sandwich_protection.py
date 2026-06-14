"""Sandwich attack protection and risk assessment."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Known swap method signatures
SWAP_SIGNATURES: dict[str, str] = {
    "0x38ed1739": "swapExactTokensForTokens",
    "0x7ff36ab5": "swapExactETHForTokens",
    "0x8803dbee": "swapTokensForExactTokens",
    "0xfb3bdb41": "swapETHForExactTokens",
    "0x18cbafe5": "swapExactTokensForETH",
    "0x791ac947": "swapExactTokensForETHSupportingFeeOnTransferTokens",
    "0x5c11d795": "swapExactTokensForTokensSupportingFeeOnTransferTokens",
}


def check_sandwich_risk(tx: dict[str, Any]) -> dict[str, Any]:
    """Check if a transaction is at risk of sandwich attack.

    Args:
        tx: Raw transaction dict with optional keys: ``data``, ``value``,
            ``gasPrice``.

    Returns:
        Risk assessment dict with keys ``risk_score``, ``risk_factors``,
        and ``recommendation``.
    """
    risk_factors: list[str] = []
    risk_score = 0

    # Check if it's a swap (high MEV risk)
    data = tx.get("data", "0x")
    for sig, name in SWAP_SIGNATURES.items():
        if data.startswith(sig):
            risk_factors.append(f"Swap transaction ({name}, high MEV risk)")
            risk_score += 30
            break

    # Check value
    value_raw = tx.get("value", "0x0")
    value: int = (
        int(value_raw, 16) if isinstance(value_raw, str) else int(value_raw)
    )
    if value > 1e18:  # > 1 ETH
        risk_factors.append("High value transaction")
        risk_score += 20

    # Check gas price
    gas_price_raw = tx.get("gasPrice", "0x0")
    gas_price: int = (
        int(gas_price_raw, 16) if isinstance(gas_price_raw, str) else int(gas_price_raw)
    )
    if gas_price > 50e9:  # > 50 Gwei
        risk_factors.append("High gas price (competitive)")
        risk_score += 10

    # Check slippage (if present in data)
    if len(data) > 138:  # Has sufficient calldata for slippage param
        risk_factors.append("Calldata contains slippage-sensitive parameters")
        risk_score += 5

    risk_score = min(100, risk_score)

    if risk_score > 30:
        recommendation = "Use Flashbots Protect or private RPC"
    elif risk_score > 15:
        recommendation = "Consider using a private RPC"
    else:
        recommendation = "Standard RPC is fine"

    return {
        "risk_score": risk_score,
        "risk_factors": risk_factors,
        "recommendation": recommendation,
    }
