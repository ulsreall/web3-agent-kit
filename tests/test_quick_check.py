"""`quick_check` and the contract risk score.

`quick_check` is the cheap "is this a honeypot" answered straight from an API,
and ``ContractAudit.risk_score`` is the same question from static flags. Both
were partly unexercised, and the API parse is the shape that tends to break:
GoPlus sends numbers as strings and omits fields it has no answer for.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from web3_agent_kit.security import ContractAudit, SecurityConfig, TokenAnalyzer

ADDRESS = "0x" + "aa" * 20


def _analyzer(response=None, *, raises=None) -> TokenAnalyzer:
    analyzer = TokenAnalyzer(SecurityConfig())

    def get(url, params=None, timeout=None):
        if raises:
            raise raises
        return response

    analyzer.session = SimpleNamespace(get=get)
    return analyzer


def _response(payload, status=200):
    return SimpleNamespace(status_code=status, json=lambda: payload)


class TestQuickCheck:
    def test_honeypot_is_high_risk(self):
        analyzer = _analyzer(_response({"result": {ADDRESS.lower(): {"is_honeypot": "1"}}}))
        result = analyzer.quick_check(ADDRESS)
        assert result["is_honeypot"] is True
        assert result["risk_level"] == "high"

    def test_clean_token_is_low_risk(self):
        analyzer = _analyzer(
            _response({"result": {ADDRESS.lower(): {"is_honeypot": "0", "buy_tax": "0.05"}}})
        )
        result = analyzer.quick_check(ADDRESS)
        assert result["is_honeypot"] is False
        assert result["risk_level"] == "low"
        assert result["buy_tax"] == 0.05

    def test_missing_field_stays_unknown_rather_than_safe(self):
        # GoPlus omits is_honeypot when it has no verdict; that is not a "no".
        analyzer = _analyzer(_response({"result": {ADDRESS.lower(): {}}}))
        result = analyzer.quick_check(ADDRESS)
        assert result["is_honeypot"] is None
        assert result["risk_level"] == "unknown"

    def test_empty_tax_string_does_not_discard_the_verdict(self):
        # GoPlus sends "" for an unmeasured tax; float("") used to escape to the
        # outer handler and drop the honeypot answer that was already parsed.
        analyzer = _analyzer(
            _response({"result": {ADDRESS.lower(): {"is_honeypot": "1", "buy_tax": ""}}})
        )
        result = analyzer.quick_check(ADDRESS)
        assert result["is_honeypot"] is True
        assert result["risk_level"] == "high"
        assert result["buy_tax"] == 0.0
        assert result["error"] is None

    def test_non_200_leaves_the_defaults(self):
        analyzer = _analyzer(_response({"result": {}}, status=500))
        result = analyzer.quick_check(ADDRESS)
        assert result["risk_level"] == "unknown"
        assert result["is_honeypot"] is None

    def test_address_missing_from_the_result_is_not_a_pass(self):
        analyzer = _analyzer(_response({"result": {"0xother": {"is_honeypot": "0"}}}))
        assert analyzer.quick_check(ADDRESS)["is_honeypot"] is None

    def test_transport_error_is_reported(self):
        analyzer = _analyzer(raises=RuntimeError("boom"))
        result = analyzer.quick_check(ADDRESS)
        assert "boom" in result["error"]
        assert result["is_honeypot"] is None


class TestContractRiskScore:
    def test_clean_verified_contract_scores_zero(self):
        assert ContractAudit(is_verified=True).risk_score == 0

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"is_verified": False}, 30),
            ({"is_proxy": True}, 20),
            ({"has_hidden_mint": True}, 40),
            ({"has_blacklist": True}, 25),
            ({"has_pause": True}, 20),
            ({"has_self_destruct": True}, 30),
            ({"has_fee_change": True}, 20),
            ({"has_transfer_restriction": True}, 15),
            ({"has_ownership": True}, 15),
        ],
    )
    def test_each_flag_costs_its_points(self, kwargs, expected):
        kwargs.setdefault("is_verified", True)
        assert ContractAudit(**kwargs).risk_score == expected

    def test_renounced_ownership_costs_nothing(self):
        assert (
            ContractAudit(
                is_verified=True, has_ownership=True, is_ownership_renounced=True
            ).risk_score
            == 0
        )

    def test_score_is_capped_at_one_hundred(self):
        assert (
            ContractAudit(
                is_verified=False,
                is_proxy=True,
                has_hidden_mint=True,
                has_blacklist=True,
                has_pause=True,
                has_self_destruct=True,
                has_fee_change=True,
                has_transfer_restriction=True,
                has_ownership=True,
            ).risk_score
            == 100
        )


class TestOtherParsers:
    """The same empty-string tolerance in the on-chain-adjacent parsers."""

    def test_tax_check_keeps_the_honeypot_verdict_with_empty_tax(self):
        analyzer = _analyzer(
            _response(
                {"result": {ADDRESS.lower(): {"is_honeypot": "1", "buy_tax": "", "sell_tax": ""}}}
            )
        )
        tax = analyzer._check_tax(ADDRESS)
        assert tax.is_honeypot is True
        assert tax.buy_tax == 0.0
        assert tax.error is None

    def test_tax_check_doubles_as_percent(self):
        analyzer = _analyzer(_response({"result": {ADDRESS.lower(): {"buy_tax": "0.05"}}}))
        assert analyzer._check_tax(ADDRESS).buy_tax == pytest.approx(5.0)

    def test_liquidity_survives_an_empty_usd_field(self):
        analyzer = _analyzer(_response({"pairs": [{"liquidity": {"usd": ""}, "dexId": "uniswap"}]}))
        liquidity = analyzer._check_liquidity(ADDRESS)
        assert liquidity.total_liquidity_usd == 0.0
        assert liquidity.dex == "uniswap"

    def test_holders_survive_an_empty_count_and_percent(self):
        analyzer = _analyzer(
            _response(
                {
                    "result": {
                        ADDRESS.lower(): {
                            "holder_count": "",
                            "holders": [{"percent": ""}, {"percent": "0.7"}],
                        }
                    }
                }
            )
        )
        holders = analyzer._check_holders(ADDRESS)
        assert holders.total_holders == 0
        assert holders.top10_percent == pytest.approx(70.0)
        assert holders.is_concentrated is True
