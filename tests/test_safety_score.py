"""The token safety score and its risk buckets.

This is the arithmetic a user leans on before buying: each deduction is worth a
fixed number of points, and the total decides a label from ``safe`` to
``critical``. Both are pure functions, so they can be pinned exactly — and a
silent change to one of them changes what the tool tells someone about a token.
"""

from __future__ import annotations

import pytest

from web3_agent_kit.security import (
    ContractAudit,
    HolderInfo,
    LiquidityInfo,
    RiskLevel,
    TaxInfo,
    TokenAnalyzer,
    TokenInfo,
)


@pytest.fixture
def analyzer() -> TokenAnalyzer:
    return TokenAnalyzer()


def _score(
    analyzer,
    *,
    tax: TaxInfo | None = None,
    liquidity: LiquidityInfo | None = None,
    holders: HolderInfo | None = None,
    contract: ContractAudit | None = None,
) -> int:
    return analyzer._calculate_safety_score(
        TokenInfo(address="0x" + "aa" * 20, symbol="TKN"),
        tax or TaxInfo(),
        liquidity or LiquidityInfo(total_liquidity_usd=1_000_000, is_locked=True),
        holders or HolderInfo(),
        contract or ContractAudit(is_verified=True),
    )


class TestScore:
    def test_clean_token_scores_full_marks(self, analyzer):
        assert _score(analyzer) == 100

    def test_honeypot_is_zero_regardless_of_the_rest(self, analyzer):
        assert _score(analyzer, tax=TaxInfo(is_honeypot=True)) == 0

    @pytest.mark.parametrize(("buy", "sell", "expected"), [(11, 0, 80), (0, 11, 80), (51, 0, 50)])
    def test_high_tax_deductions(self, analyzer, buy, sell, expected):
        assert _score(analyzer, tax=TaxInfo(buy_tax=buy, sell_tax=sell)) == expected

    def test_both_sides_over_ten_tax_twice(self, analyzer):
        assert _score(analyzer, tax=TaxInfo(buy_tax=11, sell_tax=11)) == 60

    def test_low_liquidity_and_unlocked_stack(self, analyzer):
        liquidity = LiquidityInfo(total_liquidity_usd=0, is_locked=False)
        assert _score(analyzer, liquidity=liquidity) == 65

    def test_holder_concentration(self, analyzer):
        assert _score(analyzer, holders=HolderInfo(top10_percent=60)) == 80

    def test_unverified_contract(self, analyzer):
        assert _score(analyzer, contract=ContractAudit(is_verified=False)) == 75

    def test_hidden_mint_is_the_heaviest_single_penalty(self, analyzer):
        assert (
            _score(analyzer, contract=ContractAudit(is_verified=True, has_hidden_mint=True)) == 70
        )

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"has_blacklist": True}, 85),
            ({"has_pause": True}, 90),
            ({"is_proxy": True}, 90),
        ],
    )
    def test_smaller_contract_penalties(self, analyzer, kwargs, expected):
        assert _score(analyzer, contract=ContractAudit(is_verified=True, **kwargs)) == expected

    def test_score_never_goes_negative(self, analyzer):
        worst = dict(
            tax=TaxInfo(buy_tax=99, sell_tax=99),
            liquidity=LiquidityInfo(total_liquidity_usd=0, is_locked=False),
            holders=HolderInfo(top10_percent=99),
            contract=ContractAudit(
                is_verified=False, has_hidden_mint=True, has_blacklist=True, is_proxy=True
            ),
        )
        assert _score(analyzer, **worst) == 0


class TestRiskLevel:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (100, RiskLevel.SAFE),
            (80, RiskLevel.SAFE),
            (79, RiskLevel.LOW),
            (60, RiskLevel.LOW),
            (59, RiskLevel.MEDIUM),
            (40, RiskLevel.MEDIUM),
            (39, RiskLevel.HIGH),
            (20, RiskLevel.HIGH),
            (19, RiskLevel.CRITICAL),
            (0, RiskLevel.CRITICAL),
        ],
    )
    def test_bucket_boundaries(self, analyzer, score, expected):
        assert analyzer._determine_risk_level(score) == expected
