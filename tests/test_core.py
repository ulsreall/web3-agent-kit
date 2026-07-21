"""Tests for core agent functionality."""

import pytest
from unittest.mock import MagicMock

from web3_agent_kit.agent.core import Agent, AgentConfig
from web3_agent_kit.wallet.wallet import Wallet
from web3_agent_kit.chains.chain import Chain


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
        from web3_agent_kit.chains.chain import ChainConfig
        config = ChainConfig(chain=Chain.BASE)
        assert config.is_evm is True
        assert config.chain_id == 8453
        assert "base" in config.explorer.lower()

    def test_solana_not_evm(self):
        """Test Solana is not EVM."""
        from web3_agent_kit.chains.chain import ChainConfig
        config = ChainConfig(chain=Chain.SOLANA)
        assert config.is_evm is False


class TestGovernor:
    """Test spend governor."""

    def test_within_limits(self):
        """Test transaction within limits."""
        from web3_agent_kit.utils import SpendGovernor, SpendLimits
        governor = SpendGovernor(
            limits=SpendLimits(max_per_tx=1.0, daily_limit=10.0),
            require_confirm=False,
        )
        decision = governor.authorize(0.5)
        assert decision.allowed is True

    def test_exceeds_per_tx(self):
        """Test transaction exceeds per-tx limit."""
        from web3_agent_kit.utils import SpendGovernor, SpendLimits
        governor = SpendGovernor(
            limits=SpendLimits(max_per_tx=1.0),
            require_confirm=False,
        )
        decision = governor.authorize(2.0)
        assert decision.allowed is False
        assert "per-tx limit" in decision.reason

    def test_kill_switch(self):
        """Test kill switch blocks transactions."""
        from web3_agent_kit.utils import SpendGovernor, SpendLimits
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
        from web3_agent_kit.utils import SpendGovernor, SpendLimits
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


class TestAgentGovernorIntegration:
    """Integration test: Agent._act() must actually call the governor
    correctly (tx_value as float, action as tool name string) and must
    block over-limit actions gracefully instead of crashing with a
    TypeError (regression test for the dict-vs-float bug)."""

    def _make_agent(self, governor):
        key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        wallet = Wallet.from_key(key)

        mock_tool = MagicMock()
        mock_tool.name = "swap"
        mock_tool.execute.return_value = "swapped ok"

        config = AgentConfig(
            wallet=wallet,
            chains=[Chain.ETHEREUM],
            tools=[mock_tool],
            governor=governor,
        )
        return Agent(config=config), mock_tool

    def test_act_blocks_over_limit_tx_without_crashing(self):
        """A tool call whose args imply a tx value above the governor's
        per-tx limit must be blocked with a clean message, not raise."""
        from web3_agent_kit.utils import SpendGovernor, SpendLimits

        governor = SpendGovernor(
            SpendLimits(max_per_tx=0.05, daily_limit=0.5, session_limit=1.0)
        )
        agent, mock_tool = self._make_agent(governor)

        result = agent._act({"tool": "swap", "args": {"amount": 1.0}})

        assert result.startswith("Blocked by governor:")
        mock_tool.execute.assert_not_called()

    def test_act_allows_under_limit_tx(self):
        """A tool call under the governor's limits must pass through and
        actually execute the tool."""
        from web3_agent_kit.utils import SpendGovernor, SpendLimits

        governor = SpendGovernor(
            SpendLimits(max_per_tx=0.05, daily_limit=0.5, session_limit=1.0)
        )
        agent, mock_tool = self._make_agent(governor)

        result = agent._act({"tool": "swap", "args": {"amount": 0.01}})

        assert result == "swapped ok"
        mock_tool.execute.assert_called_once()

    def test_act_defaults_to_zero_value_for_read_only_tools(self):
        """Tools with no recognizable value arg (e.g. get_balance) must
        not be blocked by the governor (tx_value defaults to 0.0)."""
        from web3_agent_kit.utils import SpendGovernor, SpendLimits

        governor = SpendGovernor(
            SpendLimits(max_per_tx=0.05, daily_limit=0.5, session_limit=1.0)
        )
        agent, mock_tool = self._make_agent(governor)

        result = agent._act({"tool": "swap", "args": {"address": "0xabc"}})

        assert result == "swapped ok"
        mock_tool.execute.assert_called_once()

    def test_agent_config_has_default_governor(self):
        """AgentConfig must attach a conservative governor by default so
        agents never run with unbounded spending out of the box."""
        key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        wallet = Wallet.from_key(key)
        config = AgentConfig(wallet=wallet)

        assert config.governor is not None
        assert config.governor.limits.max_per_tx == 0.05
        assert config.governor.limits.daily_limit == 0.5
        assert config.governor.limits.session_limit == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
