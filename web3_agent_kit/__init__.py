"""Web3 Agent Kit — Open-source framework for autonomous Web3 AI agents."""

__version__ = "1.15.0"
__author__ = "Maulana"

# Core
# Account Abstraction
from .account_abstraction import (
    BUNDLER_RPCS,
    ENTRY_POINTS,
    KNOWN_FACTORIES,
    AAChain,
    AAPaymaster,
    AAWallet,
    AAWalletInfo,
    UserOperation,
    UserOpResult,
)
from .agent import LLM, Agent, AgentConfig, LLMConfig
from .bridge import BridgeAgent, BridgeResult, BridgeRoute
from .chains import CHAIN_IDS, DEFAULT_RPCS, Chain, ChainConfig, ChainManager

# DeFi & Yield
from .defi import (
    YieldConfig,
    YieldOpportunity,
    YieldOptimizer,
    YieldPosition,
    YieldProtocol,
)

# Events
from .events import EventConfig, EventListener, Subscription
from .gas import GasEstimate, GasOptimizer, GasPriority, GasRecommendation

# Governance
from .governance import (
    KNOWN_DAOS,
    DelegateInfo,
    GovConfig,
    GovernanceTracker,
    Proposal,
    ProposalStatus,
    VoteChoice,
    VotingPower,
)

# Cross-chain Messaging
from .messaging import (
    CCIP_CHAIN_SELECTORS,
    LZ_CHAIN_IDS,
    LZ_ENDPOINTS,
    WORMHOLE_CHAIN_IDS,
    BridgeProtocol,
    CrossChainMessenger,
    MessageConfig,
    MessageResult,
    MessageStatus,
)

# MEV
from .mev import MEVConfig, MEVProtector

# NFT
from .nft import NFTConfig, NFTManager

# Oracle
from .oracle import AggregatedPrice, OracleAggregator, OracleSource, PricePoint

# Plugins
from .plugins import Plugin, PluginManager, PluginMeta, PluginRegistry

# Features
from .portfolio import PortfolioSummary, PortfolioTracker

# Security
from .security import (
    ContractAudit,
    ContractPattern,
    HolderInfo,
    LiquidityInfo,
    SecurityConfig,
    SecurityReport,
    TaxInfo,
    TokenAnalyzer,
    TokenInfo,
)
from .security import (
    RiskLevel as SecurityRiskLevel,
)

# Simulator
from .simulator import SimConfig, SimMode, SimResult, TxSimulator
from .trading import (
    DCABot,
    DCAOrder,
    DCAResult,
    DCAStatus,
    Interval,
    NewPair,
    RiskLevel,
    SniperConfig,
    TokenSniper,
)

# Notifications (merged into utils)
from .utils import Notifier, NotifierConfig  # noqa: F811
from .wallet import (
    AlertSeverity,
    AlertType,
    ApprovalManager,
    ApprovalRisk,
    BatchTxResult,
    ConsolidatedBalance,
    MultiWalletManager,
    RevokeResult,
    TokenApproval,
    Wallet,
    WalletAlert,
    WalletConfig,
    WalletInfo,
    WalletWatcher,
    WatchedWallet,
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
