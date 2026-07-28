"""Extra tests for Agent core — run loop, observe, decide, LLM mocked."""

from unittest.mock import MagicMock, patch

import pytest

from web3_agent_kit.agent.core import Agent, AgentConfig
from web3_agent_kit.chains.chain import Chain
from web3_agent_kit.wallet.wallet import Wallet

TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def _wallet():
    return Wallet.from_key(TEST_KEY)


def _make_tool(name="swap", chains=None, result="ok"):
    tool = MagicMock()
    tool.name = name
    tool.supported_chains = chains or [Chain.ETHEREUM]
    tool.execute.return_value = result
    return tool


class TestAgentConstruction:
    def test_init_with_private_key(self):
        agent = Agent(private_key=TEST_KEY, governor=None)
        assert agent.wallet.address.startswith("0x")

    def test_init_with_wallet_kwarg(self):
        agent = Agent(wallet=_wallet(), governor=None)
        assert agent.wallet is not None

    def test_init_missing_wallet_raises(self):
        with pytest.raises(TypeError, match="requires wallet"):
            Agent(governor=None)

    def test_init_with_config(self):
        cfg = AgentConfig(wallet=_wallet(), governor=None)
        agent = Agent(config=cfg)
        assert agent.config is cfg

    def test_repr(self):
        agent = Agent(wallet=_wallet(), governor=None, chains=[Chain.BASE])
        r = repr(agent)
        assert "Agent" in r
        assert "BASE" in r

    def test_confirm_fn_wired_into_default_governor(self):
        confirm = MagicMock(return_value=True)
        cfg = AgentConfig(wallet=_wallet(), confirm_fn=confirm)
        agent = Agent(config=cfg)
        assert agent.config.governor.confirm_fn is confirm


class TestObserve:
    def test_observe_success(self):
        wallet = MagicMock()
        wallet.address = "0xabc"
        wallet.get_balance.return_value = 1.23
        cfg = AgentConfig(wallet=wallet, chains=[Chain.ETHEREUM], governor=None)
        agent = Agent(config=cfg)
        obs = agent._observe()
        assert "ETHEREUM" in obs
        assert "1.23" in obs

    def test_observe_error(self):
        wallet = MagicMock()
        wallet.address = "0xabc"
        wallet.get_balance.side_effect = RuntimeError("rpc fail")
        cfg = AgentConfig(wallet=wallet, chains=[Chain.ETHEREUM], governor=None)
        agent = Agent(config=cfg)
        obs = agent._observe()
        assert "error" in obs


class TestDecide:
    def test_decide_returns_llm_response(self):
        agent = Agent(wallet=_wallet(), governor=None, tools=[_make_tool()])
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {"tool": "swap", "args": {"amount": 0.01}}
        agent._llm = mock_llm
        action = agent._decide("do a swap", "obs")
        assert action["tool"] == "swap"

    def test_decide_no_tools_uses_placeholder(self):
        agent = Agent(wallet=_wallet(), governor=None)
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {"tool": "done", "answer": "hi"}
        agent._llm = mock_llm
        action = agent._decide("goal", "obs")
        assert action["tool"] == "done"

    def test_decide_missing_tool_key_defaults_to_done(self):
        agent = Agent(wallet=_wallet(), governor=None)
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {"thought": "just thinking"}
        agent._llm = mock_llm
        action = agent._decide("goal", "obs")
        assert action["tool"] == "done"
        assert action["answer"] == "just thinking"

    def test_decide_llm_exception_returns_done_error(self):
        agent = Agent(wallet=_wallet(), governor=None)
        mock_llm = MagicMock()
        mock_llm.chat_json.side_effect = RuntimeError("llm broke")
        agent._llm = mock_llm
        action = agent._decide("goal", "obs")
        assert action["tool"] == "done"
        assert "LLM error" in action["answer"]

    def test_decide_uses_history_context(self):
        agent = Agent(wallet=_wallet(), governor=None, tools=[_make_tool()])
        agent.history = [{"step": 1, "action": {"tool": "swap"}, "result": "done step"}]
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {"tool": "done", "answer": "fin"}
        agent._llm = mock_llm
        action = agent._decide("goal", "obs")
        # Ensure prompt building with history didn't crash
        assert action["tool"] == "done"
        assert mock_llm.chat_json.called


class TestLLMProperty:
    def test_llm_lazy_load(self):
        agent = Agent(wallet=_wallet(), governor=None)
        with patch("web3_agent_kit.agent.llm.LLM") as MockLLM:
            MockLLM.return_value = "llm-instance"
            llm = agent.llm
            assert llm == "llm-instance"
            # cached
            assert agent.llm == "llm-instance"
            MockLLM.assert_called_once()


class TestRun:
    def _agent_with_llm(self, responses, tools=None, governor=None, verbose=False):
        wallet = MagicMock()
        wallet.address = "0xabc"
        wallet.get_balance.return_value = 1.0
        cfg = AgentConfig(
            wallet=wallet,
            chains=[Chain.ETHEREUM],
            tools=tools or [],
            governor=governor,
            verbose=verbose,
        )
        agent = Agent(config=cfg)
        mock_llm = MagicMock()
        mock_llm.chat_json.side_effect = responses
        agent._llm = mock_llm
        return agent

    def test_run_completes_immediately(self):
        agent = self._agent_with_llm([{"tool": "done", "answer": "all set"}])
        result = agent.run("goal")
        assert result == "all set"
        assert len(agent.history) == 1

    def test_run_executes_then_done(self):
        tool = _make_tool(result="swapped 0.01")
        agent = self._agent_with_llm(
            [
                {"tool": "swap", "args": {"amount": 0.01}},
                {"tool": "done", "answer": "finished"},
            ],
            tools=[tool],
        )
        result = agent.run("swap something")
        assert result == "finished"
        assert len(agent.history) == 2
        tool.execute.assert_called_once()

    def test_run_max_steps_reached(self):
        # Always returns a non-done action -> loop exhausts steps
        tool = _make_tool()
        agent = self._agent_with_llm(
            [{"tool": "swap", "args": {"amount": 0.001}}] * 5,
            tools=[tool],
        )
        result = agent.run("goal", max_steps=3)
        assert "Max steps (3) reached" in result
        assert len(agent.history) == 3

    def test_run_verbose(self):
        tool = _make_tool()
        agent = self._agent_with_llm(
            [
                {"tool": "swap", "args": {"amount": 0.001}, "thought": "thinking"},
                {"tool": "done", "answer": "done!", "thought": "wrapping up"},
            ],
            tools=[tool],
            verbose=True,
        )
        result = agent.run("goal")
        assert result == "done!"

    def test_execute_alias(self):
        agent = self._agent_with_llm([{"tool": "done", "answer": "via execute"}])
        assert agent.execute("goal") == "via execute"


class TestAct:
    def test_act_unknown_tool(self):
        agent = Agent(wallet=_wallet(), governor=None, tools=[_make_tool("swap")])
        result = agent._act({"tool": "nonexistent", "args": {}})
        assert "Unknown tool" in result

    def test_act_tool_raises(self):
        tool = _make_tool("swap")
        tool.execute.side_effect = RuntimeError("execution failed")
        agent = Agent(wallet=_wallet(), governor=None, tools=[tool])
        result = agent._act({"tool": "swap", "args": {}})
        assert "Error:" in result

    def test_act_no_governor_executes(self):
        tool = _make_tool("swap", result="did it")
        agent = Agent(wallet=_wallet(), governor=None, tools=[tool])
        result = agent._act({"tool": "swap", "args": {"amount": 100.0}})
        assert result == "did it"


class TestEstimateTxValue:
    def test_value_key(self):
        assert Agent._estimate_tx_value({"value": "0.5"}) == 0.5

    def test_amount_in_key(self):
        assert Agent._estimate_tx_value({"amount_in": 2}) == 2.0

    def test_bad_value_returns_none(self):
        assert Agent._estimate_tx_value({"amount": "not-a-number"}) is None

    def test_no_key_returns_none(self):
        assert Agent._estimate_tx_value({"foo": 1}) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
