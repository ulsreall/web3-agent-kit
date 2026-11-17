"""Portfolio API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import build_wallet, resolve_chain

router = APIRouter()


def _summary(chain_name: str, note: str) -> dict:
    chain = resolve_chain(chain_name)
    wallet = build_wallet(chain)
    return {
        "address": wallet.address,
        "chain": chain.value,
        "native_balance": str(wallet.get_balance(chain)),
        "note": note,
    }


@router.get("/")
async def get_portfolio(chain: str = "ethereum"):
    """Get full portfolio with token balances and USD values."""
    try:
        return _summary(chain, "Full portfolio tracking requires token list configuration")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/value")
async def get_portfolio_value(chain: str = "ethereum"):
    """Get total portfolio value in USD."""
    try:
        return _summary(chain, "USD value requires price feed integration")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
