"""DCA Bot — Dollar-Cost Averaging automation for recurring buys."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

from .chain import Chain, ChainManager
from .wallet import Wallet


class Interval(Enum):
    """DCA execution intervals."""
    HOURLY = 3600
    DAILY = 86400
    WEEKLY = 604800
    BIWEEKLY = 1209600
    MONTHLY = 2592000


class DCAStatus(Enum):
    """DCA order status."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class DCAOrder:
    """A single DCA order configuration."""
    id: str                           # Unique order ID
    from_token: str                   # Token to spend (e.g. "USDC", "ETH")
    to_token: str                     # Token to buy (e.g. "ETH", "WBTC")
    amount_per_buy: float             # Amount of from_token per execution
    chain: Chain                      # Which chain
    interval: Interval                # How often
    max_buys: Optional[int] = None    # None = unlimited
    max_total: Optional[float] = None # Max total to spend (None = unlimited)
    slippage: float = 0.5             # Slippage tolerance %
    status: DCAStatus = DCAStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    last_executed: float = 0
    next_execution: float = 0
    total_spent: float = 0
    total_bought: float = 0
    execution_count: int = 0
    buy_history: list[dict] = field(default_factory=list)


@dataclass
class DCAResult:
    """Result of a DCA execution."""
    order_id: str
    success: bool
    amount_spent: float
    amount_received: float
    price: float                      # Effective price
    tx_hash: Optional[str] = None
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class DCABot:
    """Dollar-Cost Averaging bot for recurring token purchases.

    Supports scheduled buys across multiple chains with configurable
    intervals, slippage protection, and spending limits.

    Example::

        bot = DCABot(wallet, chain_manager)

        # Buy $100 of ETH every day on Base
        order = bot.create_order(
            from_token="USDC",
            to_token="ETH",
            amount=100,
            chain=Chain.BASE,
            interval=Interval.DAILY,
        )

        # Buy $50 of WBTC every week on Ethereum
        bot.create_order(
            from_token="USDC",
            to_token="WBTC",
            amount=50,
            chain=Chain.ETHEREUM,
            interval=Interval.WEEKLY,
            max_buys=52,  # 1 year
        )

        # Run the bot (blocking loop)
        bot.run()
    """

    STORAGE_PATH = os.path.expanduser("~/.web3-agent-kit/dca_orders.json")

    def __init__(
        self,
        wallet: Wallet,
        chain_manager: ChainManager,
        uniswap=None,  # Optional Uniswap instance for swaps
    ):
        self.wallet = wallet
        self.chain_manager = chain_manager
        self.uniswap = uniswap
        self.orders: dict[str, DCAOrder] = {}
        self.results: list[DCAResult] = []
        self._callbacks: list[Callable[[DCAResult], None]] = []
        self._load_orders()

    def create_order(
        self,
        from_token: str,
        to_token: str,
        amount: float,
        chain: Chain,
        interval: Interval,
        max_buys: Optional[int] = None,
        max_total: Optional[float] = None,
        slippage: float = 0.5,
    ) -> DCAOrder:
        """Create a new DCA order.

        Args:
            from_token: Token to spend (e.g. "USDC").
            to_token: Token to buy (e.g. "ETH").
            amount: Amount of from_token per execution.
            chain: Which chain to execute on.
            interval: How often to buy.
            max_buys: Maximum number of buys (None = unlimited).
            max_total: Maximum total to spend (None = unlimited).
            slippage: Slippage tolerance percentage.

        Returns:
            Created DCAOrder.
        """
        order_id = f"dca_{int(time.time())}_{from_token}_{to_token}"
        now = time.time()

        order = DCAOrder(
            id=order_id,
            from_token=from_token.upper(),
            to_token=to_token.upper(),
            amount_per_buy=amount,
            chain=chain,
            interval=interval,
            max_buys=max_buys,
            max_total=max_total,
            slippage=slippage,
            next_execution=now,  # First buy immediately
        )

        self.orders[order_id] = order
        self._save_orders()
        return order

    def execute_order(self, order_id: str) -> DCAResult:
        """Execute a single DCA order now.

        Args:
            order_id: The order ID to execute.

        Returns:
            DCAResult with execution details.
        """
        order = self.orders.get(order_id)
        if not order:
            return DCAResult(
                order_id=order_id,
                success=False,
                amount_spent=0,
                amount_received=0,
                price=0,
                error=f"Order '{order_id}' not found",
            )

        # Check limits
        if order.status != DCAStatus.ACTIVE:
            return DCAResult(
                order_id=order_id,
                success=False,
                amount_spent=0,
                amount_received=0,
                price=0,
                error=f"Order is {order.status.value}",
            )

        if order.max_buys and order.execution_count >= order.max_buys:
            order.status = DCAStatus.COMPLETED
            self._save_orders()
            return DCAResult(
                order_id=order_id,
                success=False,
                amount_spent=0,
                amount_received=0,
                price=0,
                error="Max buys reached",
            )

        if order.max_total and order.total_spent + order.amount_per_buy > order.max_total:
            order.status = DCAStatus.COMPLETED
            self._save_orders()
            return DCAResult(
                order_id=order_id,
                success=False,
                amount_spent=0,
                amount_received=0,
                price=0,
                error="Max total spend reached",
            )

        # Execute swap
        result = self._execute_swap(order)

        if result.success:
            order.last_executed = time.time()
            order.next_execution = time.time() + order.interval.value
            order.total_spent += result.amount_spent
            order.total_bought += result.amount_received
            order.execution_count += 1
            order.buy_history.append({
                "timestamp": result.timestamp,
                "spent": result.amount_spent,
                "received": result.amount_received,
                "price": result.price,
                "tx_hash": result.tx_hash,
            })

        self.results.append(result)
        self._save_orders()

        # Fire callbacks
        for cb in self._callbacks:
            try:
                cb(result)
            except Exception:
                pass

        return result

    def pause_order(self, order_id: str) -> bool:
        """Pause a DCA order."""
        order = self.orders.get(order_id)
        if order and order.status == DCAStatus.ACTIVE:
            order.status = DCAStatus.PAUSED
            self._save_orders()
            return True
        return False

    def resume_order(self, order_id: str) -> bool:
        """Resume a paused DCA order."""
        order = self.orders.get(order_id)
        if order and order.status == DCAStatus.PAUSED:
            order.status = DCAStatus.ACTIVE
            order.next_execution = time.time()  # Execute now
            self._save_orders()
            return True
        return False

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a DCA order permanently."""
        order = self.orders.get(order_id)
        if order:
            order.status = DCAStatus.CANCELLED
            self._save_orders()
            return True
        return False

    def get_order(self, order_id: str) -> Optional[DCAOrder]:
        """Get a DCA order by ID."""
        return self.orders.get(order_id)

    def list_orders(
        self,
        status: Optional[DCAStatus] = None,
        chain: Optional[Chain] = None,
    ) -> list[DCAOrder]:
        """List all DCA orders with optional filters."""
        result = list(self.orders.values())
        if status:
            result = [o for o in result if o.status == status]
        if chain:
            result = [o for o in result if o.chain == chain]
        return result

    def get_pending_orders(self) -> list[DCAOrder]:
        """Get orders that are due for execution."""
        now = time.time()
        return [
            o for o in self.orders.values()
            if o.status == DCAStatus.ACTIVE and o.next_execution <= now
        ]

    def on_execution(self, callback: Callable[[DCAResult], None]):
        """Register a callback for DCA executions.

        Args:
            callback: Function called with DCAResult after each execution.
        """
        self._callbacks.append(callback)

    def get_summary(self) -> dict:
        """Get DCA portfolio summary."""
        active = [o for o in self.orders.values() if o.status == DCAStatus.ACTIVE]
        completed = [o for o in self.orders.values() if o.status == DCAStatus.COMPLETED]

        total_spent = sum(o.total_spent for o in self.orders.values())
        total_bought = sum(o.total_bought for o in self.orders.values())
        total_executions = sum(o.execution_count for o in self.orders.values())

        avg_price = total_spent / total_bought if total_bought > 0 else 0

        return {
            "active_orders": len(active),
            "completed_orders": len(completed),
            "total_spent": total_spent,
            "total_bought": total_bought,
            "total_executions": total_executions,
            "average_price": avg_price,
            "orders": [
                {
                    "id": o.id,
                    "pair": f"{o.from_token} → {o.to_token}",
                    "chain": o.chain.value,
                    "amount": o.amount_per_buy,
                    "interval": o.interval.name,
                    "status": o.status.value,
                    "executions": o.execution_count,
                    "total_spent": o.total_spent,
                    "total_bought": o.total_bought,
                    "avg_price": o.total_spent / o.total_bought if o.total_bought > 0 else 0,
                }
                for o in self.orders.values()
            ],
        }

    def get_cost_average(self, order_id: str) -> dict:
        """Get cost average analysis for an order."""
        order = self.orders.get(order_id)
        if not order or not order.buy_history:
            return {"error": "No data"}

        prices = [b["price"] for b in order.buy_history]
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)

        return {
            "order_id": order_id,
            "pair": f"{order.from_token} → {order.to_token}",
            "executions": len(prices),
            "average_price": avg_price,
            "min_price": min_price,
            "max_price": max_price,
            "total_spent": order.total_spent,
            "total_bought": order.total_bought,
            "price_range": f"${min_price:.2f} — ${max_price:.2f}",
        }

    def run(self, check_interval: int = 60):
        """Run the DCA bot in a blocking loop.

        Args:
            check_interval: Seconds between checking for pending orders.
        """
        print(f"🤖 DCA Bot started — {len(self.list_orders(DCAStatus.ACTIVE))} active orders")
        print(f"   Checking every {check_interval}s...")

        while True:
            pending = self.get_pending_orders()
            for order in pending:
                print(f"⏰ Executing: {order.from_token} → {order.to_token} ({order.amount_per_buy})")
                result = self.execute_order(order.id)

                if result.success:
                    print(f"   ✅ Bought {result.amount_received:.6f} {order.to_token} @ ${result.price:.2f}")
                else:
                    print(f"   ❌ Failed: {result.error}")

            time.sleep(check_interval)

    # === Internal ===

    def _execute_swap(self, order: DCAOrder) -> DCAResult:
        """Execute a swap for a DCA order."""
        if self.uniswap:
            try:
                result = self.uniswap.swap(
                    from_token=order.from_token,
                    to_token=order.to_token,
                    amount=order.amount_per_buy,
                    slippage=order.slippage,
                )
                return DCAResult(
                    order_id=order.id,
                    success=True,
                    amount_spent=order.amount_per_buy,
                    amount_received=result.get("amount_out", 0),
                    price=order.amount_per_buy / result.get("amount_out", 1),
                    tx_hash=result.get("tx_hash"),
                )
            except Exception as e:
                return DCAResult(
                    order_id=order.id,
                    success=False,
                    amount_spent=0,
                    amount_received=0,
                    price=0,
                    error=str(e),
                )
        else:
            # Demo mode — simulate
            return DCAResult(
                order_id=order.id,
                success=True,
                amount_spent=order.amount_per_buy,
                amount_received=order.amount_per_buy * 0.0003,  # Simulated
                price=3333.33,  # Simulated ETH price
                tx_hash="0x" + "0" * 64,
            )

    def _save_orders(self):
        """Persist orders to disk."""
        os.makedirs(os.path.dirname(self.STORAGE_PATH), exist_ok=True)
        data = {}
        for oid, order in self.orders.items():
            data[oid] = {
                "id": order.id,
                "from_token": order.from_token,
                "to_token": order.to_token,
                "amount_per_buy": order.amount_per_buy,
                "chain": order.chain.value,
                "interval": order.interval.value,
                "max_buys": order.max_buys,
                "max_total": order.max_total,
                "slippage": order.slippage,
                "status": order.status.value,
                "created_at": order.created_at,
                "last_executed": order.last_executed,
                "next_execution": order.next_execution,
                "total_spent": order.total_spent,
                "total_bought": order.total_bought,
                "execution_count": order.execution_count,
                "buy_history": order.buy_history,
            }
        with open(self.STORAGE_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def _load_orders(self):
        """Load orders from disk."""
        if not os.path.exists(self.STORAGE_PATH):
            return
        try:
            with open(self.STORAGE_PATH) as f:
                data = json.load(f)
            for oid, d in data.items():
                self.orders[oid] = DCAOrder(
                    id=d["id"],
                    from_token=d["from_token"],
                    to_token=d["to_token"],
                    amount_per_buy=d["amount_per_buy"],
                    chain=Chain(d["chain"]),
                    interval=Interval(d["interval"]),
                    max_buys=d.get("max_buys"),
                    max_total=d.get("max_total"),
                    slippage=d.get("slippage", 0.5),
                    status=DCAStatus(d["status"]),
                    created_at=d.get("created_at", 0),
                    last_executed=d.get("last_executed", 0),
                    next_execution=d.get("next_execution", 0),
                    total_spent=d.get("total_spent", 0),
                    total_bought=d.get("total_bought", 0),
                    execution_count=d.get("execution_count", 0),
                    buy_history=d.get("buy_history", []),
                )
        except Exception:
            pass
