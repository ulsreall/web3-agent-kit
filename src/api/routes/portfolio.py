"""Portfolio API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/")
async def get_portfolio(chain: str = "ethereum"):
    """Get full portfolio with token balances and USD values."""
    from ...wallet.wallet import Wallet

    try:
        wallet = Wallet.from_env(chain)
        balance = wallet.get_balance()
        return {
            "address": wallet.address,
            "chain": chain,
            "native_balance": str(balance),
            "note": "Full portfolio tracking requires token list configuration",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/value")
async def get_portfolio_value(chain: str = "ethereum"):
    """Get total portfolio value in USD."""
    from ...wallet.wallet import Wallet

    try:
        wallet = Wallet.from_env(chain)
        balance = wallet.get_balance()
        return {
            "address": wallet.address,
            "chain": chain,
            "native_balance": str(balance),
            "note": "USD value requires price feed integration",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
