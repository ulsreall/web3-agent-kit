"""Gas optimizer API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/estimate")
async def estimate_gas(chain: str = "ethereum"):
    """Get current gas estimates with EIP-1559 parameters."""
    from ...gas_optimizer import GasOptimizer

    try:
        optimizer = GasOptimizer(chain)
        estimate = optimizer.estimate()
        return estimate
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/recommendation")
async def get_gas_recommendation(chain: str = "ethereum"):
    """Get gas timing recommendation (execute now vs wait)."""
    from ...gas_optimizer import GasOptimizer

    try:
        optimizer = GasOptimizer(chain)
        rec = optimizer.recommend_timing()
        return rec
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/batch")
async def batch_estimate(chain: str = "ethereum"):
    """Estimate gas for multiple transaction types."""
    from ...gas_optimizer import GasOptimizer

    try:
        optimizer = GasOptimizer(chain)
        batch = optimizer.batch_estimate()
        return batch
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
