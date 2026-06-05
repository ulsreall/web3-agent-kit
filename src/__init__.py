"""Web3 Agent Kit — Open-source framework for autonomous Web3 AI agents."""

__version__ = "1.2.0"
__author__ = "Maulana"

from .agent import Agent, AgentConfig
from .wallet import Wallet
from .chain import Chain, ChainManager
from .llm import LLM, LLMConfig
from .portfolio import PortfolioTracker, PortfolioSummary
from .bridge import BridgeAgent, BridgeRoute, BridgeResult
from .sniper import TokenSniper, SniperConfig, NewPair, RiskLevel
from .yield_optimizer import (
    YieldOptimizer,
    YieldConfig,
    YieldOpportunity,
    YieldPosition,
    Protocol as YieldProtocol,
)
from .multi_wallet import (
    MultiWalletManager,
    WalletInfo,
    BatchTxResult,
    ConsolidatedBalance,
)
from .plugins import Plugin, PluginMeta, PluginRegistry, PluginManager
from .dca_bot import DCABot, DCAOrder, DCAResult, Interval, DCAStatus
from .gas_optimizer import GasOptimizer, GasEstimate, GasRecommendation, GasPriority
from .wallet_watcher import WalletWatcher, WatchedWallet, WalletAlert, AlertType, AlertSeverity
from .approval_manager import ApprovalManager, TokenApproval, RevokeResult, ApprovalRisk
from .security import (
    TokenAnalyzer,
    SecurityConfig,
    SecurityReport,
    TokenInfo,
    TaxInfo,
    LiquidityInfo,
    HolderInfo,
    ContractAudit,
    RiskLevel as SecurityRiskLevel,
    ContractPattern,
)

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
    # Yield Optimizer
    "YieldOptimizer",
    "YieldConfig",
    "YieldOpportunity",
    "YieldPosition",
    "YieldProtocol",
    # Multi-Wallet
    "MultiWalletManager",
    "WalletInfo",
    "BatchTxResult",
    "ConsolidatedBalance",
    # Plugin System
    "Plugin",
    "PluginMeta",
    "PluginRegistry",
    "PluginManager",
    # DCA Bot
    "DCABot",
    "DCAOrder",
    "DCAResult",
    "Interval",
    "DCAStatus",
    # Gas Optimizer
    "GasOptimizer",
    "GasEstimate",
    "GasRecommendation",
    "GasPriority",
    # Wallet Watcher
    "WalletWatcher",
    "WatchedWallet",
    "WalletAlert",
    "AlertType",
    "AlertSeverity",
    # Approval Manager
    "ApprovalManager",
    "TokenApproval",
    "RevokeResult",
    "ApprovalRisk",
    # Security
    "TokenAnalyzer",
    "SecurityConfig",
    "SecurityReport",
    "TokenInfo",
    "TaxInfo",
    "LiquidityInfo",
    "HolderInfo",
    "ContractAudit",
    "SecurityRiskLevel",
    "ContractPattern",
]
