"""Core agent framework — goal-driven autonomous agents with LLM reasoning."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .wallet import Wallet
from .chain import Chain

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for an autonomous agent."""

    wallet: Wallet
    chains: list[Chain] = field(default_factory=lambda: [Chain.ETHEREUM])
    llm: str = "gpt-4"
    max_steps: int = 20
    tools: list[Any] = field(default_factory=list)
    governor: Optional[Any] = None
    confirm_fn: Optional[Callable] = None


class Agent:
    """
    Autonomous AI agent for Web3 operations.

    The agent observes blockchain state, reasons about goals using an LLM,
    and executes on-chain transactions — all governed by safety caps.

    Example:
        agent = Agent(
            wallet=Wallet.from_key("0x..."),
            chains=[Chain.BASE],
            tools=[Uniswap(), Aave()],
        )
        result = agent.run("Swap 0.1 ETH to USDC")
    """

    def __init__(self, config: Optional[AgentConfig] = None, **kwargs):
        if config:
            self.config = config
        else:
            self.config = AgentConfig(**kwargs)

        self.wallet = self.config.wallet
        self.chains = self.config.chains
        self.tools = {t.name: t for t in self.config.tools}
        self.history: list[dict] = []

    def run(self, goal: str, max_steps: Optional[int] = None) -> str:
        """
        Run the agent toward a goal.

        Args:
            goal: Natural language description of what to accomplish
            max_steps: Override default max steps

        Returns:
            Result string (transaction hash, summary, etc.)
        """
        steps = max_steps or self.config.max_steps
        observation = self._observe()

        for step in range(steps):
            logger.info(f"Step {step + 1}/{steps}: Thinking...")

            # Decide next action via LLM
            action = self._decide(goal, observation)

            if action.get("tool") == "done":
                return action.get("answer", "Task completed")

            # Execute action
            result = self._act(action)
            observation = result

            # Log action
            self.history.append({
                "step": step + 1,
                "action": action,
                "result": result,
            })

        return f"Max steps ({steps}) reached without completion"

    def _observe(self) -> str:
        """Observe current blockchain state."""
        observations = []

        for chain in self.chains:
            balance = self.wallet.get_balance(chain)
            observations.append(f"{chain.name}: {balance} ETH")

        return " | ".join(observations)

    def _decide(self, goal: str, observation: str) -> dict:
        """
        Decide next action using LLM.

        Returns action dict: {"tool": "name", "args": {...}}
        """
        # TODO: Integrate with LLM providers
        # For now, return a placeholder
        return {
            "tool": "done",
            "args": {},
            "answer": f"Goal '{goal}' — LLM integration pending",
        }

    def _act(self, action: dict) -> str:
        """Execute an action using the appropriate tool."""
        tool_name = action.get("tool")
        args = action.get("args", {})

        if tool_name not in self.tools:
            return f"Unknown tool: {tool_name}"

        tool = self.tools[tool_name]

        # Check governor before executing
        if self.config.governor:
            decision = self.config.governor.authorize(action)
            if not decision.allowed:
                return f"Blocked by governor: {decision.reason}"

        # Execute
        try:
            result = tool.execute(self.wallet, **args)
            return str(result)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return f"Error: {e}"

    def get_history(self) -> list[dict]:
        """Get action history."""
        return self.history

    def __repr__(self) -> str:
        return f"Agent(chains={[c.name for c in self.chains]}, tools={list(self.tools.keys())})"
