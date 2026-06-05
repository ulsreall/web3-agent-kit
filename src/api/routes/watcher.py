"""Wallet watcher API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/list")
async def list_watched(chain: str = "ethereum"):
    """List all watched wallets."""
    from ...wallet.watcher import WalletWatcher

    try:
        watcher = WalletWatcher(chain)
        wallets = watcher.list_wallets()
        return {"wallets": wallets}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/add")
async def add_watched(
    address: str,
    chain: str = "ethereum",
    label: str = "",
):
    """Add a wallet to watch."""
    from ...wallet.watcher import WalletWatcher

    try:
        watcher = WalletWatcher(chain)
        result = watcher.add_wallet(address, label)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/remove")
async def remove_watched(address: str, chain: str = "ethereum"):
    """Remove a wallet from watchlist."""
    from ...wallet.watcher import WalletWatcher

    try:
        watcher = WalletWatcher(chain)
        result = watcher.remove_wallet(address)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/alerts")
async def get_alerts(chain: str = "ethereum", limit: int = 50):
    """Get alerts for watched wallets."""
    from ...wallet.watcher import WalletWatcher

    try:
        watcher = WalletWatcher(chain)
        alerts = watcher.get_alerts(limit)
        return {"alerts": alerts}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/check")
async def check_wallets(chain: str = "ethereum"):
    """Manually trigger wallet check for all watched addresses."""
    from ...wallet.watcher import WalletWatcher

    try:
        watcher = WalletWatcher(chain)
        result = watcher.check_all()
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/summary")
async def get_summary(chain: str = "ethereum"):
    """Get watcher summary statistics."""
    from ...wallet.watcher import WalletWatcher

    try:
        watcher = WalletWatcher(chain)
        summary = watcher.get_summary()
        return summary
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
