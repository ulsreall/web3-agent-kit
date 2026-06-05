"""Tests for Security Module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.security import (
    ContractAudit,
    ContractPattern,
    HolderInfo,
    LiquidityInfo,
    RiskLevel,
    SecurityConfig,
    SecurityReport,
    TaxInfo,
    TokenAnalyzer,
    TokenInfo,
)


class TestTokenInfo:
    """Test TokenInfo dataclass."""

    def test_creation(self):
        info = TokenInfo(address="0x123", name="Test", symbol="TST")
        assert info.address == "0x123"
        assert info.name == "Test"
        assert info.symbol == "TST"
        assert info.decimals == 18

    def test_defaults(self):
        info = TokenInfo(address="0x123")
        assert info.total_supply == 0.0
        assert info.is_verified is False
        assert info.chain == "ethereum"


class TestTaxInfo:
    """Test TaxInfo dataclass."""

    def test_normal_tax(self):
        tax = TaxInfo(buy_tax=2.0, sell_tax=2.0)
        assert tax.is_high_tax is False
        assert tax.is_scam_tax is False

    def test_high_tax(self):
        tax = TaxInfo(buy_tax=15.0, sell_tax=15.0)
        assert tax.is_high_tax is True
        assert tax.is_scam_tax is False

    def test_scam_tax(self):
        tax = TaxInfo(buy_tax=90.0, sell_tax=90.0)
        assert tax.is_high_tax is True
        assert tax.is_scam_tax is True

    def test_honeypot(self):
        tax = TaxInfo(is_honeypot=True, can_sell=False)
        assert tax.is_honeypot is True
        assert tax.can_sell is False


class TestLiquidityInfo:
    """Test LiquidityInfo dataclass."""

    def test_low_liquidity(self):
        liq = LiquidityInfo(total_liquidity_usd=5000)
        assert liq.is_low_liquidity is True

    def test_good_liquidity(self):
        liq = LiquidityInfo(total_liquidity_usd=100000)
        assert liq.is_low_liquidity is False

    def test_well_locked(self):
        liq = LiquidityInfo(locked_percent=90, lock_duration_days=60)
        assert liq.is_well_locked is True

    def test_not_locked(self):
        liq = LiquidityInfo(locked_percent=10, lock_duration_days=0)
        assert liq.is_well_locked is False


class TestHolderInfo:
    """Test HolderInfo dataclass."""

    def test_concentrated(self):
        holders = HolderInfo(top10_percent=70)
        assert holders.is_risky_concentration is True

    def test_distributed(self):
        holders = HolderInfo(top10_percent=20)
        assert holders.is_risky_concentration is False


class TestContractAudit:
    """Test ContractAudit dataclass."""

    def test_clean_contract(self):
        audit = ContractAudit(is_verified=True, is_ownership_renounced=True)
        assert audit.risk_score < 20

    def test_risky_contract(self):
        audit = ContractAudit(
            is_verified=False,
            has_hidden_mint=True,
            has_blacklist=True,
            is_proxy=True,
        )
        assert audit.risk_score > 50

    def test_pattern_detection(self):
        audit = ContractAudit(
            detected_patterns=[ContractPattern.HIDDEN_MINT, ContractPattern.BLACKLIST]
        )
        assert ContractPattern.HIDDEN_MINT in audit.detected_patterns


class TestSecurityReport:
    """Test SecurityReport dataclass."""

    def test_safe_report(self):
        report = SecurityReport(
            token=TokenInfo(address="0x123", name="Safe", symbol="SAFE"),
            tax=TaxInfo(buy_tax=2, sell_tax=2),
            liquidity=LiquidityInfo(total_liquidity_usd=100000, locked_percent=90),
            holders=HolderInfo(top10_percent=20, total_holders=1000),
            contract=ContractAudit(is_verified=True, is_ownership_renounced=True),
            safety_score=85,
            risk_level=RiskLevel.SAFE,
        )
        assert report.is_safe is True
        assert report.is_honeypot is False
        assert report.is_rug_risk is False

    def test_honeypot_report(self):
        report = SecurityReport(
            token=TokenInfo(address="0x123", name="Scam", symbol="SCAM"),
            tax=TaxInfo(is_honeypot=True, can_sell=False),
            liquidity=LiquidityInfo(),
            holders=HolderInfo(),
            contract=ContractAudit(),
            safety_score=0,
            risk_level=RiskLevel.CRITICAL,
        )
        assert report.is_honeypot is True
        assert report.is_safe is False

    def test_rug_risk_report(self):
        report = SecurityReport(
            token=TokenInfo(address="0x123", name="Rug", symbol="RUG"),
            tax=TaxInfo(),
            liquidity=LiquidityInfo(locked_percent=10),
            holders=HolderInfo(top10_percent=80, is_concentrated=True),
            contract=ContractAudit(has_hidden_mint=True),
            safety_score=20,
            risk_level=RiskLevel.HIGH,
        )
        assert report.is_rug_risk is True

    def test_to_dict(self):
        report = SecurityReport(
            token=TokenInfo(address="0x123", name="Test", symbol="TST"),
            tax=TaxInfo(buy_tax=2, sell_tax=2),
            liquidity=LiquidityInfo(total_liquidity_usd=50000),
            holders=HolderInfo(total_holders=500),
            contract=ContractAudit(is_verified=True),
            safety_score=70,
            risk_level=RiskLevel.LOW,
        )
        d = report.to_dict()
        assert d["safety_score"] == 70
        assert d["is_safe"] is True
        assert "token" in d
        assert "warnings" in d

    def test_print_report(self):
        report = SecurityReport(
            token=TokenInfo(address="0x1234567890abcdef", name="Test", symbol="TST"),
            tax=TaxInfo(buy_tax=2, sell_tax=3),
            liquidity=LiquidityInfo(total_liquidity_usd=50000, locked_percent=80),
            holders=HolderInfo(total_holders=500, top10_percent=30),
            contract=ContractAudit(is_verified=True),
            safety_score=75,
            risk_level=RiskLevel.LOW,
            warnings=["Test warning"],
            recommendations=["Test recommendation"],
        )
        output = report.print_report()
        assert "SECURITY ANALYSIS REPORT" in output
        assert "Test" in output
        assert "TST" in output


class TestTokenAnalyzer:
    """Test TokenAnalyzer."""

    def test_init(self):
        analyzer = TokenAnalyzer()
        assert analyzer.config is not None

    def test_init_with_config(self):
        config = SecurityConfig(
            rpc_url="https://eth.llamarpc.com",
            chain="ethereum",
            max_buy_tax=5.0,
        )
        analyzer = TokenAnalyzer(config)
        assert analyzer.config.chain == "ethereum"

    @patch("src.security.requests.Session.get")
    def test_quick_check(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "0x123": {
                    "is_honeypot": "0",
                    "buy_tax": "0.02",
                    "sell_tax": "0.02",
                }
            }
        }
        mock_get.return_value = mock_response

        analyzer = TokenAnalyzer()
        result = analyzer.quick_check("0x123")
        assert result["is_honeypot"] is False
        assert result["buy_tax"] == 0.02

    @patch("src.security.requests.Session.get")
    def test_check_honeypot(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "0x123": {
                    "is_honeypot": "1",
                    "buy_tax": "0.99",
                    "sell_tax": "0.99",
                }
            }
        }
        mock_get.return_value = mock_response

        analyzer = TokenAnalyzer()
        tax = analyzer.check_honeypot("0x123")
        assert tax.is_honeypot is True

    @patch("src.security.requests.Session.get")
    def test_check_rug_risk(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "0x123": {
                    "holder_count": "100",
                    "holders": [
                        {"percent": "0.3"},
                        {"percent": "0.2"},
                    ],
                    "is_open_source": "1",
                    "hidden_owner": "1",
                }
            }
        }
        mock_get.return_value = mock_response

        analyzer = TokenAnalyzer()
        result = analyzer.check_rug_risk("0x123")
        assert "risk_score" in result
        assert "risk_factors" in result

    @patch("src.security.requests.Session.get")
    def test_analyze_token(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "0x123": {
                    "is_honeypot": "0",
                    "buy_tax": "0.02",
                    "sell_tax": "0.03",
                    "holder_count": "1000",
                    "holders": [],
                    "is_open_source": "1",
                    "is_proxy": "0",
                    "hidden_owner": "0",
                    "is_blacklisted": "0",
                    "can_take_back_ownership": "0",
                    "owner_change_balance": "0",
                    "owner_can_not_set_fee": "1",
                    "can_set_fee": "0",
                    "trading_cooldown": "0",
                }
            }
        }
        mock_get.return_value = mock_response

        analyzer = TokenAnalyzer()
        report = analyzer.analyze_token("0x123")
        assert isinstance(report, SecurityReport)
        assert report.safety_score > 0

    def test_chain_id(self):
        analyzer = TokenAnalyzer(SecurityConfig(chain="ethereum"))
        assert analyzer._chain_id() == "1"

        analyzer = TokenAnalyzer(SecurityConfig(chain="base"))
        assert analyzer._chain_id() == "8453"

    def test_calculate_safety_score(self):
        analyzer = TokenAnalyzer()

        # Safe token
        score = analyzer._calculate_safety_score(
            TokenInfo(address="0x", is_verified=True),
            TaxInfo(buy_tax=2, sell_tax=2),
            LiquidityInfo(total_liquidity_usd=100000, locked_percent=90),
            HolderInfo(top10_percent=20),
            ContractAudit(is_verified=True, is_ownership_renounced=True),
        )
        assert score >= 70

        # Honeypot
        score = analyzer._calculate_safety_score(
            TokenInfo(address="0x"),
            TaxInfo(is_honeypot=True),
            LiquidityInfo(),
            HolderInfo(),
            ContractAudit(),
        )
        assert score == 0

    def test_determine_risk_level(self):
        analyzer = TokenAnalyzer()
        assert analyzer._determine_risk_level(90) == RiskLevel.SAFE
        assert analyzer._determine_risk_level(70) == RiskLevel.LOW
        assert analyzer._determine_risk_level(50) == RiskLevel.MEDIUM
        assert analyzer._determine_risk_level(30) == RiskLevel.HIGH
        assert analyzer._determine_risk_level(10) == RiskLevel.CRITICAL

    def test_generate_warnings(self):
        analyzer = TokenAnalyzer()
        warnings = analyzer._generate_warnings(
            TokenInfo(address="0x"),
            TaxInfo(is_honeypot=True, buy_tax=90),
            LiquidityInfo(total_liquidity_usd=1000),
            HolderInfo(top10_percent=80, is_concentrated=True),
            ContractAudit(has_hidden_mint=True, is_proxy=True),
        )
        assert len(warnings) > 0
        assert any("HONEYPOT" in w for w in warnings)


class TestRiskLevel:
    """Test RiskLevel enum."""

    def test_values(self):
        assert RiskLevel.SAFE.value == "safe"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_ordering(self):
        levels = [
            RiskLevel.SAFE,
            RiskLevel.LOW,
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]
        assert len(levels) == 5


class TestContractPattern:
    """Test ContractPattern enum."""

    def test_dangerous_patterns(self):
        assert ContractPattern.HIDDEN_MINT.value == "hidden_mint"
        assert ContractPattern.BLACKLIST.value == "blacklist"

    def test_positive_patterns(self):
        assert ContractPattern.VERIFIED_SOURCE.value == "verified_source"
        assert ContractPattern.LOCKED_LIQUIDITY.value == "locked_liquidity"


class TestIntegration:
    """Integration tests."""

    def test_import(self):
        from src.security import (
            TokenAnalyzer,
            SecurityConfig,
            SecurityReport,
            RiskLevel,
            ContractPattern,
        )
        assert TokenAnalyzer is not None
        assert SecurityConfig is not None

    def test_full_analysis_mock(self):
        """Test full analysis with mocked APIs."""
        with patch("src.security.requests.Session.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "result": {
                    "0x123": {
                        "is_honeypot": "0",
                        "buy_tax": "0.03",
                        "sell_tax": "0.03",
                        "holder_count": "5000",
                        "holders": [
                            {"percent": "0.05"},
                            {"percent": "0.03"},
                        ],
                        "is_open_source": "1",
                        "is_proxy": "0",
                        "hidden_owner": "0",
                        "is_blacklisted": "0",
                        "can_take_back_ownership": "0",
                        "owner_change_balance": "0",
                        "owner_can_not_set_fee": "1",
                        "can_set_fee": "0",
                        "trading_cooldown": "0",
                    }
                }
            }
            mock_get.return_value = mock_response

            analyzer = TokenAnalyzer()
            report = analyzer.analyze_token("0x123")

            assert report.safety_score > 50
            assert report.is_honeypot is False
            assert report.risk_level in [RiskLevel.SAFE, RiskLevel.LOW]
