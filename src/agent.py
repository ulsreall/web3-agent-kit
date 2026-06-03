"""Core agent framework — goal-driven autonomous agents with LLM reasoning."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .wallet import Wallet
from .chain import Chain

logger = logging.getLogger(__name__)


# System prompt for the agent
AGENT_SYSTEM_PROMPT = """You are an autonomous Web3 agent. You observe blockchain state, reason about goals, and execute on-chain actions using available tools.

TOOLS:
{tools}

RESPONSE FORMAT:
You must respond with a JSON object:
{{
    "thought": "your reasoning about what to do next",
    "tool": "tool_name",
    "args": {{"key": "value"}}
}}

When the goal is complete, respond with:
{{
    "thought": "summary of what was accomplished",
    "tool": "done",
    "answer": "final answer to the user"
}}

RULES:
- Always use the cheapest available option
- Check balances before swaps
- Consider gas costs in your reasoning
- Never exceed the governor limits
- If a tool fails, try an alternative approach
- Be precise with token addresses and amounts
"""


@dataclass
class AgentConfig:
    """Configuration for an autonomous agent."""

    wallet: Wallet
    chains: list[Chain] = field(default_factory=lambda: [Chain.ETHEREUM])
    llm: str = "auto"  # "auto" for auto-detect, or specific model
    max_steps: int = 20
    tools: list[Any] = field(default_factory=list)
    governor: Optional[Any] = None
    confirm_fn: Optional[Callable] = None
    verbose: bool = False


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
        self._llm = None

    @property
    def llm(self):
        """Lazy-load LLM client."""
        if self._llm is None:
            from .llm import LLM, LLMConfig
            self._llm = LLM()
        return self._llm

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

            if self.config.verbose:
                thought = action.get("thought", "")
                logger.info(f"Thought: {thought}")

            if action.get("tool") == "done":
                result = action.get("answer", "Task completed")
                self.history.append({
                    "step": step + 1,
                    "action": action,
                    "result": result,
                })
                return result

            # Execute action
            result = self._act(action)
            observation = result

            # Log action
            self.history.append({
                "step": step + 1,
                "action": action,
                "result": result,
            })

            if self.config.verbose:
                logger.info(f"Result: {result}")

        return f"Max steps ({steps}) reached without completion"

    def _observe(self) -> str:
        """Observe current blockchain state."""
        observations = []

        for chain in self.chains:
            try:
                balance = self.wallet.get_balance(chain)
                observations.append(f"{chain.name}: {balance} ETH")
            except Exception as e:
                observations.append(f"{chain.name}: error ({e})")

        return " | ".join(observations)

    def _decide(self, goal: str, observation: str) -> dict:
        """
        Decide next action using LLM.

        Returns action dict: {"tool": "name", "args": {...}}
        """
        # Build tool descriptions
        tool_descriptions = []
        for name, tool in self.tools.items():
            chains = [c.value for c in tool.supported_chains]
            tool_descriptions.append(f"- {name}: chains={chains}")

        if not tool_descriptions:
            tool_descriptions = ["- No tools available"]

        system_prompt = AGENT_SYSTEM_PROMPT.format(
            tools="\n".join(tool_descriptions)
        )

        # Build conversation context
        context_parts = [f"OBSERVATION: {observation}"]

        if self.history:
            for h in self.history[-3:]:  # Last 3 steps
                context_parts.append(
                    f"Step {h['step']}: tool={h['action'].get('tool')}, result={str(h['result'])[:200]}"
                )

        context_parts.append(f"GOAL: {goal}")

        user_prompt = "\n".join(context_parts)

        try:
            response = self.llm.chat_json(user_prompt, system=system_prompt)

            # Validate response
            if "tool" not in response:
                response["tool"] = "done"
                response["answer"] = response.get("thought", "Invalid LLM response")

            return response

        except Exception as e:
            logger.error(f"LLM failed: {e}")
            # Fallback: return done with error
            return {
                "tool": "done",
                "args": {},
                "answer": f"LLM error: {e}",
            }

    def _act(self, action: dict) -> str:
        """Execute an action using the appropriate tool."""
        tool_name = action.get("tool")
        args = action.get("args", {})

        if tool_name not in self.tools:
            return f"Unknown tool: {tool_name}. Available: {list(self.tools.keys())}"

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
