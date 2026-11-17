"""Gas optimizer API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import build_wallet, chain_manager, resolve_chain

router = APIRouter()

ZERO_ADDRESS = "0x" + "00" * 20


def _optimizer(chain_name: str):
    from ...gas.optimizer import GasOptimizer

    chain = resolve_chain(chain_name)
    return GasOptimizer(build_wallet(chain), chain_manager(chain)), chain


@router.get("/estimate")
async def estimate_gas(chain: str = "ethereum", to: str = ZERO_ADDRESS, operation: str = ""):
    """Get current gas estimates with EIP-1559 parameters."""
    try:
        optimizer, chain_enum = _optimizer(chain)
        return optimizer.estimate(to, chain=chain_enum, operation=operation or None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/recommendation")
async def get_gas_recommendation(chain: str = "ethereum"):
    """Get gas timing recommendation (execute now vs wait)."""
    try:
        optimizer, chain_enum = _optimizer(chain)
        return optimizer.recommend_timing(chain_enum)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/batch")
async def batch_estimate(chain: str = "ethereum", operation: str = "transfer"):
    """Estimate gas for a representative transaction."""
    try:
        optimizer, chain_enum = _optimizer(chain)
        return optimizer.batch_estimate([{"to": ZERO_ADDRESS, "operation": operation}], chain_enum)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
