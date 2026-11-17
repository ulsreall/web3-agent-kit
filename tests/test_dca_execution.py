"""DCA execution must call the swap tool it was given, not a method it lacks."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from web3_agent_kit.chains import Chain
from web3_agent_kit.defi import SwapResult
from web3_agent_kit.trading.dca import DCABot, Interval


@dataclass
class _Order:
    id: str = "order-1"
    from_token: str = "USDC"
    to_token: str = "ETH"
    amount_per_buy: float = 100.0
    slippage: float = 1.0
    chain: Chain = Chain.BASE


def _bot(uniswap) -> DCABot:
    return DCABot(MagicMock(), MagicMock(), uniswap=uniswap)


def test_execute_swap_uses_execute_and_reads_the_dataclass():
    uniswap = MagicMock()
    uniswap.execute.return_value = SwapResult(
        tx_hash="0xhash",
        token_in="USDC",
        token_out="ETH",
        amount_in=100.0,
        amount_out=0.05,
        gas_used=100_000,
        chain=Chain.BASE,
    )
    bot = _bot(uniswap)

    result = bot._execute_swap(_Order())

    assert result.success is True
    assert result.tx_hash == "0xhash"
    assert result.price == 2000.0
    assert uniswap.slippage == 1.0
    args = uniswap.execute.call_args
    assert args.args[0] is bot.wallet
    assert args.args[1:4] == ("USDC", "ETH", 100.0)
    assert args.kwargs["chain"] is Chain.BASE


def test_execute_swap_without_output_does_not_divide_by_zero():
    uniswap = MagicMock()
    uniswap.execute.return_value = SwapResult(
        tx_hash="0xhash",
        token_in="USDC",
        token_out="ETH",
        amount_in=100.0,
        amount_out=0.0,
        gas_used=100_000,
        chain=Chain.BASE,
    )

    result = _bot(uniswap)._execute_swap(_Order())

    assert result.success is True
    assert result.price == 0


def test_execute_swap_reports_a_swap_failure():
    uniswap = MagicMock()
    uniswap.execute.side_effect = RuntimeError("no route")

    result = _bot(uniswap)._execute_swap(_Order())

    assert result.success is False
    assert "no route" in result.error


def test_interval_names_are_available():
    assert Interval.DAILY.name == "DAILY"
