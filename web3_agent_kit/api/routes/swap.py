"""Swap API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import build_wallet, chain_manager, resolve_chain, resolve_token

router = APIRouter()


def _uniswap(chain, slippage: float):
    from ...defi import Uniswap

    return Uniswap(chain_manager=chain_manager(chain), slippage=slippage)


@router.get("/quote")
async def get_swap_quote(
    chain: str = "ethereum",
    token_in: str = "ETH",
    token_out: str = "USDC",
    amount_in: str = "1.0",
    slippage: float = 0.5,
):
    """Get swap quote without executing."""
    try:
        chain_enum = resolve_chain(chain)
        uni = _uniswap(chain_enum, slippage)
        quote = uni.get_quote(
            resolve_token(chain_enum, token_in),
            resolve_token(chain_enum, token_out),
            float(amount_in),
            chain_enum,
        )
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
    """Execute a token swap through the enforced pre-sign gate."""
    from ...defi import Uniswap

    try:
        chain_enum = resolve_chain(chain)
        token_in_addr = resolve_token(chain_enum, token_in)
        token_out_addr = resolve_token(chain_enum, token_out)

        router_address = Uniswap.ROUTERS.get(chain_enum)
        if router_address is None:
            raise ValueError(f"no Uniswap V2 router configured for {chain_enum.value}")

        wallet = build_wallet(chain_enum, targets={router_address})
        uni = _uniswap(chain_enum, slippage)
        return uni.execute(
            wallet,
            token_in_addr,
            token_out_addr,
            float(amount_in),
            chain=chain_enum,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tokens")
async def list_tokens(chain: str = "ethereum"):
    """List supported tokens on a chain."""
    from ...defi import Uniswap
    from ...portfolio.tracker import KNOWN_TOKENS

    try:
        chain_enum = resolve_chain(chain)
        uni = Uniswap()
        return {
            "chain": chain,
            "router": uni.ROUTERS.get(chain_enum, "unknown"),
            "supported_chains": uni.supported_chains,
            "tokens": KNOWN_TOKENS.get(chain_enum, {}),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
