"""Yield optimizer API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/opportunities")
async def scan_yields(chain: str = "ethereum", min_apy: float = 0.0):
    """Scan yield opportunities across protocols."""
    from ...yield_optimizer import YieldOptimizer

    try:
        optimizer = YieldOptimizer(chain)
        opportunities = optimizer.scan_opportunities(min_apy=min_apy)
        return {"opportunities": opportunities, "total": len(opportunities)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/best")
async def find_best_yield(chain: str = "ethereum"):
    """Find the best yield opportunity."""
    from ...yield_optimizer import YieldOptimizer

    try:
        optimizer = YieldOptimizer(chain)
        best = optimizer.find_best()
        return best
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/compare")
async def compare_protocols(chain: str = "ethereum"):
    """Compare yields across supported protocols."""
    from ...yield_optimizer import YieldOptimizer

    try:
        optimizer = YieldOptimizer(chain)
        comparison = optimizer.compare_protocols()
        return comparison
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/portfolio")
async def get_yield_portfolio(chain: str = "ethereum"):
    """Get current yield-earning positions."""
    from ...yield_optimizer import YieldOptimizer

    try:
        optimizer = YieldOptimizer(chain)
        portfolio = optimizer.get_portfolio_summary()
        return portfolio
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/compound")
async def auto_compound(chain: str = "ethereum"):
    """Auto-compound all yield positions."""
    from ...yield_optimizer import YieldOptimizer

    try:
        optimizer = YieldOptimizer(chain)
        result = optimizer.auto_compound_all()
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
