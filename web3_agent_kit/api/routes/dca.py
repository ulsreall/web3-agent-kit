"""DCA bot API routes."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from ..deps import build_wallet, chain_manager, resolve_chain

router = APIRouter()


def _serialize(order) -> dict:
    """Return a JSON-safe view of an order (Chain/Interval enums become values)."""
    if isinstance(order, dict):
        return order
    data = asdict(order)
    data["chain"] = order.chain.value
    data["interval"] = order.interval.name.lower()
    data["status"] = order.status.value
    return data


def _bot(chain: str):
    """Build a bot for ``chain`` with a wallet that is gate-bound when configured.

    The Uniswap tool is wired in so executions are real swaps instead of the
    bot's simulated demo branch.
    """
    from ...defi import Uniswap
    from ...trading.dca import DCABot

    chain_enum = resolve_chain(chain)
    manager = chain_manager(chain_enum)
    return DCABot(build_wallet(chain_enum), manager, uniswap=Uniswap(manager)), chain_enum


@router.get("/orders")
async def list_orders(chain: str = "ethereum", status: str = "active"):
    """List DCA orders."""
    from ...trading.dca import DCAStatus

    try:
        bot, chain_enum = _bot(chain)
        try:
            status_enum = DCAStatus(status.lower())
        except ValueError as exc:
            raise ValueError(f"unknown status {status!r}") from exc
        orders = bot.list_orders(status_enum, chain_enum)
        return {"orders": [_serialize(order) for order in orders]}
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
    from ...trading.dca import Interval

    try:
        bot, chain_enum = _bot(chain)
        try:
            interval = Interval[frequency.upper()]
        except KeyError as exc:
            raise ValueError(
                f"unknown frequency {frequency!r}; use one of {[i.name.lower() for i in Interval]}"
            ) from exc

        order = bot.create_order(
            from_token=token_in,
            to_token=token_out,
            amount=float(amount_per_buy),
            chain=chain_enum,
            interval=interval,
            max_buys=total_buys if total_buys > 0 else None,
        )
        return _serialize(order)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/orders/{order_id}")
async def get_order(order_id: str, chain: str = "ethereum"):
    """Get DCA order status."""
    try:
        bot, _ = _bot(chain)
        order = bot.get_order(order_id)
        if order is None:
            raise LookupError(f"order {order_id} not found")
        return _serialize(order)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str, chain: str = "ethereum"):
    """Cancel a DCA order."""
    try:
        bot, _ = _bot(chain)
        return {"cancelled": bot.cancel_order(order_id)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/pause")
async def pause_order(order_id: str, chain: str = "ethereum"):
    """Pause a DCA order."""
    try:
        bot, _ = _bot(chain)
        return {"paused": bot.pause_order(order_id)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/resume")
async def resume_order(order_id: str, chain: str = "ethereum"):
    """Resume a paused DCA order."""
    try:
        bot, _ = _bot(chain)
        return {"resumed": bot.resume_order(order_id)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/execute")
async def execute_order(order_id: str, chain: str = "ethereum"):
    """Execute one buy for an order now."""
    try:
        bot, _ = _bot(chain)
        return asdict(bot.execute_order(order_id))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats")
async def get_stats(chain: str = "ethereum"):
    """Get DCA bot statistics."""
    try:
        bot, _ = _bot(chain)
        return bot.get_summary()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
