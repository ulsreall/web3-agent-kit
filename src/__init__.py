"""Web3 Agent Kit — Open-source framework for autonomous Web3 AI agents."""

__version__ = "0.3.0"
__author__ = "Maulana"

from .agent import Agent, AgentConfig
from .wallet import Wallet
from .chain import Chain, ChainManager
from .llm import LLM, LLMConfig
from .portfolio import PortfolioTracker, PortfolioSummary
from .bridge import BridgeAgent, BridgeRoute, BridgeResult
from .sniper import TokenSniper, SniperConfig, NewPair, RiskLevel

__all__ = [
    # Core
    "Agent",
    "AgentConfig",
    "Wallet",
    "Chain",
    "ChainManager",
    "LLM",
    "LLMConfig",
    # Features
    "PortfolioTracker",
    "PortfolioSummary",
    "BridgeAgent",
    "BridgeRoute",
    "BridgeResult",
    "TokenSniper",
    "SniperConfig",
    "NewPair",
    "RiskLevel",
]
