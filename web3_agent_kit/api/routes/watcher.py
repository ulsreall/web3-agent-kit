"""Wallet watcher API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import chain_manager, resolve_chain

router = APIRouter()


def _watcher(chain_name: str):
    from ...wallet.watcher import WalletWatcher

    chain = resolve_chain(chain_name)
    return WalletWatcher(chain_manager(chain)), chain


@router.get("/list")
async def list_watched(chain: str = "ethereum"):
    """List all watched wallets."""
    try:
        watcher, chain_enum = _watcher(chain)
        return {"wallets": watcher.list_wallets(chain_enum)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/add")
async def add_watched(
    address: str,
    chain: str = "ethereum",
    label: str = "",
):
    """Add a wallet to watch."""
    try:
        watcher, chain_enum = _watcher(chain)
        return watcher.add_wallet(address, label or address, chain_enum)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/remove")
async def remove_watched(address: str, chain: str = "ethereum"):
    """Remove a wallet from watchlist."""
    try:
        watcher, chain_enum = _watcher(chain)
        return watcher.remove_wallet(address, chain_enum)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/alerts")
async def get_alerts(chain: str = "ethereum", limit: int = 50):
    """Get alerts for watched wallets."""
    try:
        watcher, _ = _watcher(chain)
        return {"alerts": watcher.get_alerts(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/check")
async def check_wallets(chain: str = "ethereum"):
    """Manually trigger wallet check for all watched addresses."""
    try:
        watcher, _ = _watcher(chain)
        return watcher.check_all()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/summary")
async def get_summary(chain: str = "ethereum"):
    """Get watcher summary statistics."""
    try:
        watcher, _ = _watcher(chain)
        return watcher.get_summary()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
