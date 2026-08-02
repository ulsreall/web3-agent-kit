"""Swap API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/quote")
async def get_swap_quote(
    chain: str = "ethereum",
    token_in: str = "ETH",
    token_out: str = "USDC",
    amount_in: str = "1.0",
    slippage: float = 0.5,
):
    """Get swap quote without executing."""
    from ...defi import Uniswap

    try:
        uni = Uniswap(chain)
        quote = uni.get_quote(token_in, token_out, amount_in, slippage)
        return quote
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/execute")
async def execute_swap(
    chain: str = "ethereum",
    token_in: str = "ETH",
    token_out: str = "USDC",
    amount_in: str = "1.0",
    slippage: float = 0.5,
):
    """Execute a token swap."""
    from ...defi import Uniswap
    from ...wallet.wallet import Wallet

    try:
        wallet = Wallet.from_env(chain)
        uni = Uniswap(chain)
        result = uni.execute(wallet, token_in, token_out, amount_in, slippage)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tokens")
async def list_tokens(chain: str = "ethereum"):
    """List supported tokens on a chain."""
    from ...defi import Uniswap

    try:
        uni = Uniswap(chain)
        return {
            "chain": chain,
            "router": uni.ROUTERS.get(chain, "unknown"),
            "supported_chains": uni.supported_chains,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
