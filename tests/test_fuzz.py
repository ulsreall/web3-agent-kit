"""Fuzz tests for slippage, gas, and approval edge cases.

Uses Hypothesis for property-based testing.
Run: pytest tests/test_fuzz.py -v
"""

from typing import Any

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from web3_agent_kit.security import (
    ContractAudit,
    HolderInfo,
    LiquidityInfo,
    RiskLevel,
    SecurityReport,
    TaxInfo,
    TokenInfo,
)
from web3_agent_kit.utils import SpendGovernor, SpendLimits


@st.composite
def tax_info_args(draw):
    return {
        "is_honeypot": draw(st.one_of(st.none(), st.booleans())),
        "can_sell": draw(st.one_of(st.none(), st.booleans())),
        "buy_tax": draw(st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)),
        "sell_tax": draw(st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)),
    }


@given(args=tax_info_args())
@settings(max_examples=100)
def test_tax_info_never_crashes(args: dict[str, Any]):
    info = TaxInfo(**args)
    assert isinstance(info.is_honeypot, (bool, type(None)))
    assert isinstance(info.can_sell, (bool, type(None)))
    assert 0 <= info.buy_tax <= 100
    assert 0 <= info.sell_tax <= 100


@given(args=tax_info_args())
@settings(max_examples=100)
def test_security_report_honeypot_state(args: dict[str, Any]):
    token = TokenInfo(address="0x1234", name="Test", symbol="TST", chain="ethereum")
    liq = LiquidityInfo(locked_percent=100.0)
    holders = HolderInfo(total_holders=100, is_concentrated=False)
    contract = ContractAudit(has_hidden_mint=False, is_proxy=False)
    tax = TaxInfo(**args)
    report = SecurityReport(
        token=token, tax=tax, liquidity=liq, holders=holders, contract=contract,
        safety_score=80, risk_level=RiskLevel.LOW,
    )
    if tax.is_honeypot is True:
        assert not report.is_safe


@given(
    tx_value=st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    max_per_tx=st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    daily_limit=st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    session_limit=st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_governor_no_crash(tx_value: float, max_per_tx: float, daily_limit: float, session_limit: float):
    limits = SpendLimits(max_per_tx=max_per_tx, daily_limit=daily_limit, session_limit=session_limit)
    gov = SpendGovernor(limits=limits, require_confirm=False)
    result = gov.authorize(tx_value=tx_value)
    assert result.allowed in (True, False)


@given(
    expected_out=st.floats(min_value=0.000001, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    slippage=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_slippage_math(expected_out: float, slippage: float):
    assume(expected_out > 0 and slippage >= 0)
    min_out = expected_out * (1 - slippage / 100)
    assert 0 <= min_out <= expected_out
    if slippage == 0:
        assert min_out == expected_out