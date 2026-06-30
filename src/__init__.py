"""Web3 Agent Kit — Open-source framework for autonomous Web3 AI agents."""

__version__ = "1.9.0"
__author__ = "Maulana"

# Core
from .agent import Agent, AgentConfig, LLM, LLMConfig
from .wallet import (
    Wallet, WalletConfig,
    MultiWalletManager, WalletInfo, BatchTxResult, ConsolidatedBalance,
    WalletWatcher, WatchedWallet, WalletAlert, AlertType, AlertSeverity,
    ApprovalManager, TokenApproval, RevokeResult, ApprovalRisk,
)
from .chains import Chain, ChainManager, ChainConfig, CHAIN_IDS, DEFAULT_RPCS

# Features
from .portfolio import PortfolioTracker, PortfolioSummary
from .bridge import BridgeAgent, BridgeRoute, BridgeResult
from .trading import TokenSniper, SniperConfig, NewPair, RiskLevel, DCABot, DCAOrder, DCAResult, Interval, DCAStatus
from .gas import GasOptimizer, GasEstimate, GasRecommendation, GasPriority

# DeFi & Yield
from .defi import (
    YieldOptimizer, YieldConfig, YieldOpportunity, YieldPosition,
    YieldProtocol,
)

# Security
from .security import (
    TokenAnalyzer, SecurityConfig, SecurityReport, TokenInfo,
    TaxInfo, LiquidityInfo, HolderInfo, ContractAudit,
    RiskLevel as SecurityRiskLevel, ContractPattern,
)

# Plugins
from .plugins import Plugin, PluginMeta, PluginRegistry, PluginManager

# MEV
from .mev import MEVProtector, MEVConfig

# NFT
from .nft import NFTManager, NFTConfig

# Notifications (merged into utils)
from .utils import Notifier, NotifierConfig  # noqa: F811

# Oracle
from .oracle import OracleAggregator, AggregatedPrice, PricePoint, OracleSource

# Events
from .events import EventListener, EventConfig, Subscription

# Simulator
from .simulator import TxSimulator, SimResult, SimConfig, SimMode

# Account Abstraction
from .account_abstraction import (
    AAWallet, AAPaymaster, UserOperation, UserOpResult,
    AAWalletInfo, AAChain, ENTRY_POINTS, BUNDLER_RPCS, KNOWN_FACTORIES,
)

# Cross-chain Messaging
from .messaging import (
    CrossChainMessenger, MessageConfig, MessageResult, MessageStatus,
    BridgeProtocol, LZ_ENDPOINTS, LZ_CHAIN_IDS,
    WORMHOLE_CHAIN_IDS, CCIP_CHAIN_SELECTORS,
)

# Governance
from .governance import (
    GovernanceTracker, GovConfig, Proposal, ProposalStatus,
    VoteChoice, VotingPower, DelegateInfo, KNOWN_DAOS,
)

__all__ = [
    # Version
    "__version__",
    "__author__",
    # Core
    "Agent",
    "AgentConfig",
    "LLM",
    "LLMConfig",
    "Wallet",
    "WalletConfig",
    "Chain",
    "ChainManager",
    "ChainConfig",
    "CHAIN_IDS",
    "DEFAULT_RPCS",
    # Portfolio
    "PortfolioTracker",
    "PortfolioSummary",
    # Bridge
    "BridgeAgent",
    "BridgeRoute",
    "BridgeResult",
    # Trading
    "TokenSniper",
    "SniperConfig",
    "NewPair",
    "RiskLevel",
    "DCABot",
    "DCAOrder",
    "DCAResult",
    "Interval",
    "DCAStatus",
    # Gas
    "GasOptimizer",
    "GasEstimate",
    "GasRecommendation",
    "GasPriority",
    # Yield
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
    # Wallet Watcher
    "WalletWatcher",
    "WatchedWallet",
    "WalletAlert",
    "AlertType",
    "AlertSeverity",
    # Approvals
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
    # Plugins
    "Plugin",
    "PluginMeta",
    "PluginRegistry",
    "PluginManager",
    # MEV
    "MEVProtector",
    "MEVConfig",
    # NFT
    "NFTManager",
    "NFTConfig",
    # Notifications
    "Notifier",
    "NotifierConfig",
    # Oracle
    "OracleAggregator",
    "AggregatedPrice",
    "PricePoint",
    "OracleSource",
    # Events
    "EventListener",
    "EventConfig",
    "Subscription",
    # Simulator
    "TxSimulator",
    "SimResult",
    "SimConfig",
    "SimMode",
    # Account Abstraction
    "AAWallet",
    "AAPaymaster",
    "UserOperation",
    "UserOpResult",
    "AAWalletInfo",
    "AAChain",
    "ENTRY_POINTS",
    "BUNDLER_RPCS",
    "KNOWN_FACTORIES",
    # Cross-chain Messaging
    "CrossChainMessenger",
    "MessageConfig",
    "MessageResult",
    "MessageStatus",
    "BridgeProtocol",
    "LZ_ENDPOINTS",
    "LZ_CHAIN_IDS",
    "WORMHOLE_CHAIN_IDS",
    "CCIP_CHAIN_SELECTORS",
    # Governance
    "GovernanceTracker",
    "GovConfig",
    "Proposal",
    "ProposalStatus",
    "VoteChoice",
    "VotingPower",
    "DelegateInfo",
    "KNOWN_DAOS",
]
