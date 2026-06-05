"""Tests for token sniper."""

import pytest
from unittest.mock import MagicMock, patch

from src.trading.sniper import TokenSniper, SniperConfig, NewPair, RiskLevel
from src.chains.chain import Chain


class TestSniperConfig:
    """Test SniperConfig dataclass."""

    def test_defaults(self):
        """Test default configuration."""
        config = SniperConfig()
        assert config.max_buy == 0.05
        assert config.auto_buy is True
        assert config.honeypot_check is True
        assert config.min_liquidity == 1.0
        assert config.max_buy_tax == 10.0
        assert config.max_sell_tax == 10.0

    def test_custom_config(self):
        """Test custom configuration."""
        config = SniperConfig(
            max_buy=0.01,
            auto_buy=False,
            min_liquidity=0.5,
        )
        assert config.max_buy == 0.01
        assert config.auto_buy is False
        assert config.min_liquidity == 0.5


class TestNewPair:
    """Test NewPair dataclass."""

    def test_creation(self):
        """Test creating a NewPair."""
        pair = NewPair(
            pair_address="0xabc",
            token0="0x123",
            token1="0x456",
            chain=Chain.BASE,
            timestamp=1234567890.0,
            risk_level=RiskLevel.LOW,
            token_name="Test Token",
            token_symbol="TEST",
            reserves=(1000, 2000),
            liquidity_eth=1.5,
            score=85.0,
        )
        assert pair.pair_address == "0xabc"
        assert pair.token_symbol == "TEST"
        assert pair.risk_level == RiskLevel.LOW

    def test_is_weth_pair(self):
        """Test WETH pair detection."""
        weth_addr = "0x4200000000000000000000000000000000000006"
        pair = NewPair(
            pair_address="0xabc",
            token0=weth_addr,
            token1="0x123",
            chain=Chain.BASE,
            timestamp=1234567890.0,
            risk_level=RiskLevel.LOW,
        )
        assert pair.is_weth_pair is True
        assert pair.non_weth_token == "0x123"

    def test_is_not_weth_pair(self):
        """Test non-WETH pair detection."""
        pair = NewPair(
            pair_address="0xabc",
            token0="0x123",
            token1="0x456",
            chain=Chain.BASE,
            timestamp=1234567890.0,
            risk_level=RiskLevel.MEDIUM,
        )
        assert pair.is_weth_pair is False

    def test_to_dict(self):
        """Test converting to dict."""
        pair = NewPair(
            pair_address="0xabc",
            token0="0x123",
            token1="0x456",
            chain=Chain.BASE,
            timestamp=1234567890.0,
            risk_level=RiskLevel.HIGH,
            token_name="Scam Token",
            token_symbol="SCAM",
            liquidity_eth=0.1,
            score=20.0,
        )
        d = pair.to_dict()
        assert d["pair"] == "0xabc"
        assert d["symbol"] == "SCAM"
        assert d["risk"] == "high"
        assert d["liquidity_eth"] == 0.1


class TestRiskLevel:
    """Test RiskLevel enum."""

    def test_values(self):
        """Test risk level values."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.SCAM.value == "scam"


class TestTokenSniper:
    """Test TokenSniper."""

    def test_creation(self):
        """Test creating a TokenSniper."""
        wallet = MagicMock()
        wallet.address = "0x1234"
        chain_manager = MagicMock()

        sniper = TokenSniper(chain_manager, wallet)
        assert sniper.wallet.address == "0x1234"
        assert len(sniper.detected_pairs) == 0

    def test_custom_config(self):
        """Test custom configuration."""
        wallet = MagicMock()
        chain_manager = MagicMock()
        config = SniperConfig(max_buy=0.01, auto_buy=False)

        sniper = TokenSniper(chain_manager, wallet, config)
        assert sniper.config.max_buy == 0.01
        assert sniper.config.auto_buy is False

    def test_get_detected_pairs_empty(self):
        """Test getting detected pairs when empty."""
        wallet = MagicMock()
        chain_manager = MagicMock()

        sniper = TokenSniper(chain_manager, wallet)
        pairs = sniper.get_detected_pairs()
        assert len(pairs) == 0

    def test_get_detected_pairs_with_filter(self):
        """Test getting detected pairs with risk filter."""
        wallet = MagicMock()
        chain_manager = MagicMock()

        sniper = TokenSniper(chain_manager, wallet)
        sniper.detected_pairs = [
            NewPair("0x1", "0xa", "0xb", Chain.BASE, 0, RiskLevel.LOW),
            NewPair("0x2", "0xc", "0xd", Chain.BASE, 0, RiskLevel.HIGH),
            NewPair("0x3", "0xe", "0xf", Chain.BASE, 0, RiskLevel.LOW),
        ]

        low_pairs = sniper.get_detected_pairs(RiskLevel.LOW)
        assert len(low_pairs) == 2

        high_pairs = sniper.get_detected_pairs(RiskLevel.HIGH)
        assert len(high_pairs) == 1

    def test_callback(self):
        """Test callback configuration."""
        wallet = MagicMock()
        chain_manager = MagicMock()
        callback = MagicMock()
        config = SniperConfig(callback=callback)

        sniper = TokenSniper(chain_manager, wallet, config)
        assert sniper.config.callback == callback

    def test_repr(self):
        """Test string representation."""
        wallet = MagicMock()
        chain_manager = MagicMock()

        sniper = TokenSniper(chain_manager, wallet)
        assert "TokenSniper" in repr(sniper)
        assert "detected=0" in repr(sniper)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
