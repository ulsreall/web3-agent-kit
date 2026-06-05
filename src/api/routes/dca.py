"""DCA bot API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/orders")
async def list_orders(chain: str = "ethereum", status: str = "active"):
    """List DCA orders."""
    from ...trading.dca import DCABot

    try:
        bot = DCABot(chain)
        orders = bot.list_orders(status)
        return {"orders": orders}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders")
async def create_order(
    chain: str = "ethereum",
    token_in: str = "USDC",
    token_out: str = "ETH",
    amount_per_buy: str = "100",
    frequency: str = "daily",
    total_buys: int = 0,
):
    """Create a new DCA order."""
    from ...trading.dca import DCABot

    try:
        bot = DCABot(chain)
        order = bot.create_order(
            token_in=token_in,
            token_out=token_out,
            amount_per_buy=amount_per_buy,
            frequency=frequency,
            total_buys=total_buys if total_buys > 0 else None,
        )
        return order
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/orders/{order_id}")
async def get_order(order_id: str, chain: str = "ethereum"):
    """Get DCA order status."""
    from ...trading.dca import DCABot

    try:
        bot = DCABot(chain)
        order = bot.get_order(order_id)
        return order
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str, chain: str = "ethereum"):
    """Cancel a DCA order."""
    from ...trading.dca import DCABot

    try:
        bot = DCABot(chain)
        result = bot.cancel_order(order_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/pause")
async def pause_order(order_id: str, chain: str = "ethereum"):
    """Pause a DCA order."""
    from ...trading.dca import DCABot

    try:
        bot = DCABot(chain)
        result = bot.pause_order(order_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/resume")
async def resume_order(order_id: str, chain: str = "ethereum"):
    """Resume a paused DCA order."""
    from ...trading.dca import DCABot

    try:
        bot = DCABot(chain)
        result = bot.resume_order(order_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats")
async def get_stats(chain: str = "ethereum"):
    """Get DCA bot statistics."""
    from ...trading.dca import DCABot

    try:
        bot = DCABot(chain)
        summary = bot.get_summary()
        return summary
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
