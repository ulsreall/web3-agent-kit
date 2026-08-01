"""Portfolio API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/")
async def get_portfolio(chain: str = "ethereum"):
    """Get full portfolio with token balances and USD values."""
    from ...chains.chain import Chain, ChainManager
    from ...wallet.wallet import Wallet

    try:
        chain_enum = Chain(chain)
        manager = ChainManager([chain_enum])
        wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=manager)
        balance = wallet.get_balance(chain_enum)
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
    from ...chains.chain import Chain, ChainManager
    from ...wallet.wallet import Wallet

    try:
        chain_enum = Chain(chain)
        manager = ChainManager([chain_enum])
        wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=manager)
        balance = wallet.get_balance(chain_enum)
        return {
            "address": wallet.address,
            "chain": chain,
            "native_balance": str(balance),
            "note": "USD value requires price feed integration",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
