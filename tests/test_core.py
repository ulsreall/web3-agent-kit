"""Tests for core agent functionality."""

import pytest
from unittest.mock import MagicMock

from src.agent.core import Agent, AgentConfig
from src.wallet.wallet import Wallet
from src.chains.chain import Chain


class TestWallet:
    """Test wallet creation and management."""

    def test_from_key(self):
        """Test wallet creation from private key."""
        # This is a test key, never use in production
        key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        wallet = Wallet.from_key(key)
        assert wallet.address.startswith("0x")
        assert len(wallet.address) == 42

    def test_from_env_missing(self, monkeypatch):
        """Test wallet creation from missing env var."""
        monkeypatch.delenv("PRIVATE_KEY", raising=False)
        with pytest.raises(ValueError, match="not set"):
            Wallet.from_env("PRIVATE_KEY")

    def test_from_env(self, monkeypatch):
        """Test wallet creation from env var."""
        key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        monkeypatch.setenv("TEST_KEY", key)
        wallet = Wallet.from_env("TEST_KEY")
        assert wallet.address.startswith("0x")


class TestChain:
    """Test chain configuration."""

    def test_chain_enum(self):
        """Test chain enum values."""
        assert Chain.ETHEREUM.value == "ethereum"
        assert Chain.BASE.value == "base"
        assert Chain.SOLANA.value == "solana"

    def test_chain_config(self):
        """Test chain configuration."""
        from src.chains.chain import ChainConfig
        config = ChainConfig(chain=Chain.BASE)
        assert config.is_evm is True
        assert config.chain_id == 8453
        assert "base" in config.explorer.lower()

    def test_solana_not_evm(self):
        """Test Solana is not EVM."""
        from src.chains.chain import ChainConfig
        config = ChainConfig(chain=Chain.SOLANA)
        assert config.is_evm is False


class TestGovernor:
    """Test spend governor."""

    def test_within_limits(self):
        """Test transaction within limits."""
        from src.utils import SpendGovernor, SpendLimits
        governor = SpendGovernor(
            limits=SpendLimits(max_per_tx=1.0, daily_limit=10.0),
            require_confirm=False,
        )
        decision = governor.authorize(0.5)
        assert decision.allowed is True

    def test_exceeds_per_tx(self):
        """Test transaction exceeds per-tx limit."""
        from src.utils import SpendGovernor, SpendLimits
        governor = SpendGovernor(
            limits=SpendLimits(max_per_tx=1.0),
            require_confirm=False,
        )
        decision = governor.authorize(2.0)
        assert decision.allowed is False
        assert "per-tx limit" in decision.reason

    def test_kill_switch(self):
        """Test kill switch blocks transactions."""
        from src.utils import SpendGovernor, SpendLimits
        governor = SpendGovernor(
            limits=SpendLimits(max_per_tx=1.0),
            require_confirm=False,
        )
        governor.kill()
        decision = governor.authorize(0.1)
        assert decision.allowed is False
        assert "Kill switch" in decision.reason

    def test_daily_limit(self):
        """Test daily spending limit."""
        from src.utils import SpendGovernor, SpendLimits
        governor = SpendGovernor(
            limits=SpendLimits(max_per_tx=1.0, daily_limit=2.0),
            require_confirm=False,
        )
        # First transaction
        assert governor.authorize(1.0).allowed is True
        # Second transaction
        assert governor.authorize(1.0).allowed is True
        # Third transaction (exceeds daily)
        assert governor.authorize(1.0).allowed is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
