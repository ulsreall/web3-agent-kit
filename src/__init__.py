"""Web3 Agent Kit — Open-source framework for autonomous Web3 AI agents."""

__version__ = "0.2.0"
__author__ = "Maulana"

from .agent import Agent, AgentConfig
from .wallet import Wallet
from .chain import Chain, ChainManager
from .llm import LLM, LLMConfig

__all__ = [
    "Agent",
    "AgentConfig",
    "Wallet",
    "Chain",
    "ChainManager",
    "LLM",
    "LLMConfig",
]
