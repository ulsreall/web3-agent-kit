"""Tests for DCA Bot."""

import json
import os
import tempfile
import time

import pytest

from src.dca_bot import (
    DCABot,
    DCAOrder,
    DCAResult,
    Interval,
    DCAStatus,
)
from src.chain import Chain, ChainManager
from src.wallet import Wallet, WalletConfig


@pytest.fixture
def wallet():
    """Create a test wallet."""
    from eth_account import Account
    acct = Account.create()
    return Wallet(
        config=WalletConfig(private_key=acct.key.hex()),
        chain_manager=ChainManager(chains=[Chain.ETHEREUM, Chain.BASE]),
    )


@pytest.fixture
def bot(wallet, tmp_path):
    """Create a DCA bot with temp storage."""
    b = DCABot(wallet, ChainManager(chains=[Chain.ETHEREUM, Chain.BASE]))
    b.STORAGE_PATH = str(tmp_path / "dca_orders.json")
    return b


class TestDCAOrder:
    def test_create_order(self, bot):
        order = bot.create_order(
            from_token="USDC",
            to_token="ETH",
            amount=100,
            chain=Chain.BASE,
            interval=Interval.DAILY,
        )
        assert order.from_token == "USDC"
        assert order.to_token == "ETH"
        assert order.amount_per_buy == 100
        assert order.chain == Chain.BASE
        assert order.interval == Interval.DAILY
        assert order.status == DCAStatus.ACTIVE
        assert order.execution_count == 0

    def test_create_with_limits(self, bot):
        order = bot.create_order(
            from_token="USDC",
            to_token="ETH",
            amount=100,
            chain=Chain.BASE,
            interval=Interval.WEEKLY,
            max_buys=10,
            max_total=1000,
            slippage=1.0,
        )
        assert order.max_buys == 10
        assert order.max_total == 1000
        assert order.slippage == 1.0

    def test_order_persistence(self, bot):
        bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        bot.create_order("USDC", "WBTC", 50, Chain.ETHEREUM, Interval.WEEKLY)

        # Reload from disk
        bot2 = DCABot(bot.wallet, ChainManager(chains=[Chain.ETHEREUM, Chain.BASE]))
        bot2.STORAGE_PATH = bot.STORAGE_PATH
        bot2._load_orders()

        assert len(bot2.orders) == 2


class TestDCAExecution:
    def test_execute_order(self, bot):
        order = bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        result = bot.execute_order(order.id)

        assert result.success is True
        assert result.amount_spent == 100
        assert result.amount_received > 0

    def test_execute_updates_order(self, bot):
        order = bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        bot.execute_order(order.id)

        updated = bot.get_order(order.id)
        assert updated.execution_count == 1
        assert updated.total_spent == 100
        assert updated.last_executed > 0
        assert len(updated.buy_history) == 1

    def test_execute_nonexistent(self, bot):
        result = bot.execute_order("nonexistent")
        assert result.success is False
        assert "not found" in result.error

    def test_max_buys_limit(self, bot):
        order = bot.create_order(
            "USDC", "ETH", 100, Chain.BASE, Interval.DAILY, max_buys=2
        )

        bot.execute_order(order.id)
        bot.execute_order(order.id)
        result = bot.execute_order(order.id)

        assert result.success is False
        assert "Max buys" in result.error

        updated = bot.get_order(order.id)
        assert updated.status == DCAStatus.COMPLETED

    def test_max_total_limit(self, bot):
        order = bot.create_order(
            "USDC", "ETH", 100, Chain.BASE, Interval.DAILY, max_total=250
        )

        bot.execute_order(order.id)  # 100
        bot.execute_order(order.id)  # 200
        result = bot.execute_order(order.id)  # 300 > 250

        assert result.success is False
        assert "Max total" in result.error

    def test_paused_order_fails(self, bot):
        order = bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        bot.pause_order(order.id)

        result = bot.execute_order(order.id)
        assert result.success is False
        assert "paused" in result.error


class TestDCAStatus:
    def test_pause_resume(self, bot):
        order = bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)

        assert bot.pause_order(order.id) is True
        assert bot.get_order(order.id).status == DCAStatus.PAUSED

        assert bot.resume_order(order.id) is True
        assert bot.get_order(order.id).status == DCAStatus.ACTIVE

    def test_cancel(self, bot):
        order = bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)

        assert bot.cancel_order(order.id) is True
        assert bot.get_order(order.id).status == DCAStatus.CANCELLED

    def test_pause_nonexistent(self, bot):
        assert bot.pause_order("nonexistent") is False


class TestDCAList:
    def test_list_all(self, bot):
        bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        bot.create_order("USDC", "WBTC", 50, Chain.ETHEREUM, Interval.WEEKLY)

        orders = bot.list_orders()
        assert len(orders) == 2

    def test_list_by_status(self, bot):
        o1 = bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        bot.create_order("USDC", "WBTC", 50, Chain.ETHEREUM, Interval.WEEKLY)
        bot.pause_order(o1.id)

        active = bot.list_orders(status=DCAStatus.ACTIVE)
        paused = bot.list_orders(status=DCAStatus.PAUSED)
        assert len(active) == 1
        assert len(paused) == 1

    def test_list_by_chain(self, bot):
        bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        bot.create_order("USDC", "WBTC", 50, Chain.ETHEREUM, Interval.WEEKLY)

        base_orders = bot.list_orders(chain=Chain.BASE)
        eth_orders = bot.list_orders(chain=Chain.ETHEREUM)
        assert len(base_orders) == 1
        assert len(eth_orders) == 1


class TestPendingOrders:
    def test_pending_orders(self, bot):
        order = bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        pending = bot.get_pending_orders()
        assert len(pending) == 1

    def test_no_pending_after_execute(self, bot):
        order = bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        bot.execute_order(order.id)

        # Next execution should be in the future
        pending = bot.get_pending_orders()
        assert len(pending) == 0


class TestDCASummary:
    def test_summary_empty(self, bot):
        summary = bot.get_summary()
        assert summary["active_orders"] == 0
        assert summary["total_spent"] == 0

    def test_summary_with_orders(self, bot):
        bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        bot.create_order("USDC", "WBTC", 50, Chain.ETHEREUM, Interval.WEEKLY)

        summary = bot.get_summary()
        assert summary["active_orders"] == 2


class TestCostAverage:
    def test_cost_average(self, bot):
        order = bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        bot.execute_order(order.id)
        bot.execute_order(order.id)

        avg = bot.get_cost_average(order.id)
        assert avg["executions"] == 2
        assert avg["total_spent"] == 200
        assert "price_range" in avg

    def test_cost_average_empty(self, bot):
        order = bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        avg = bot.get_cost_average(order.id)
        assert "error" in avg


class TestCallback:
    def test_callback_fires(self, bot):
        results = []
        bot.on_execution(lambda r: results.append(r))

        order = bot.create_order("USDC", "ETH", 100, Chain.BASE, Interval.DAILY)
        bot.execute_order(order.id)

        assert len(results) == 1
        assert results[0].success is True


class TestInterval:
    def test_interval_values(self):
        assert Interval.HOURLY.value == 3600
        assert Interval.DAILY.value == 86400
        assert Interval.WEEKLY.value == 604800
        assert Interval.MONTHLY.value == 2592000
