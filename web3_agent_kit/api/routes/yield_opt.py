"""Yield optimizer API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import build_wallet, resolve_chain

router = APIRouter()


def _optimizer(chain_name: str):
    from ...defi.yield_optimizer import YieldOptimizer

    chain = resolve_chain(chain_name)
    return YieldOptimizer(build_wallet(chain), chain), chain


@router.get("/opportunities")
async def scan_yields(chain: str = "ethereum", asset: str = "", min_apy: float = 0.0):
    """Scan yield opportunities across protocols."""
    try:
        optimizer, _ = _optimizer(chain)
        opportunities = optimizer.scan_opportunities(asset or None)
        if min_apy:
            opportunities = [
                o
                for o in opportunities
                if (o.get("apy", 0) if isinstance(o, dict) else o.apy) >= min_apy
            ]
        return {"opportunities": opportunities, "total": len(opportunities)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/best")
async def find_best_yield(chain: str = "ethereum", asset: str = "USDC", amount: float = 1000.0):
    """Find the best yield opportunity for an asset and amount."""
    try:
        optimizer, _ = _optimizer(chain)
        return optimizer.find_best(asset, amount)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/compare")
async def compare_protocols(chain: str = "ethereum", asset: str = "USDC"):
    """Compare yields across supported protocols."""
    try:
        optimizer, _ = _optimizer(chain)
        return optimizer.compare_protocols(asset)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/portfolio")
async def get_yield_portfolio(chain: str = "ethereum"):
    """Get current yield-earning positions."""
    try:
        optimizer, _ = _optimizer(chain)
        return optimizer.get_portfolio_summary()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/compound")
async def auto_compound(chain: str = "ethereum"):
    """Auto-compound all yield positions."""
    try:
        optimizer, _ = _optimizer(chain)
        return optimizer.auto_compound_all()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
