"""Web3 Agent Kit — Open-source framework for autonomous Web3 AI agents."""

__version__ = "0.1.0"
__author__ = "Maulana"

from .agent import Agent
from .wallet import Wallet
from .chain import Chain

__all__ = ["Agent", "Wallet", "Chain"]
