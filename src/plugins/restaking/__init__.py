"""Restaking module — EigenLayer, Babylon, Solana restaking, and yield optimization."""

from __future__ import annotations

# Support both `from src.restaking import *` and `from restaking import *` (when src is on sys.path)
try:
    from .eigenlayer import (
        EIGEN_TOKEN,
        EIGENLAYER_ABI,
        EIGENLAYER_DELEGATION_MANAGER,
        EIGENLAYER_SLASHER,
        EIGENLAYER_STRATEGY_MANAGER,
        EigenLayer,
        EigenLayerConfig,
        OperatorInfo,
        RestakeResult,
        RestakingStrategy,
    )
    from .monitor import (
        Alert,
        AlertType,
        MonitoredPosition,
        PortfolioSnapshot,
        RestakingMonitor,
        SlashingEvent,
    )
    from .optimizer import (
        OptimizationResult,
        OptimizationStrategy,
        RestakingOpportunity,
        RestakingOptimizer,
        RiskAdjustedYield,
    )
    from .protocols import (
        BABYLON_STAKING_ABI,
        BABYLON_VAULT_ADDRESS,
        SOLAYER_RESTAKING_ABI,
        SOLAYER_VAULT_ADDRESS,
        BabylonBtcRestaking,
        ProtocolPosition,
        ProtocolReward,
        RestakingProtocol,
        SolanaRestaking,
    )
except ImportError:
    # Fallback: when imported as top-level package (sys.path includes src/)
    from src.plugins.restaking.eigenlayer import (  # type: ignore[no-redef]
        EIGEN_TOKEN,
        EIGENLAYER_ABI,
        EIGENLAYER_DELEGATION_MANAGER,
        EIGENLAYER_SLASHER,
        EIGENLAYER_STRATEGY_MANAGER,
        EigenLayer,
        EigenLayerConfig,
        OperatorInfo,
        RestakeResult,
        RestakingStrategy,
    )
    from src.plugins.restaking.monitor import (  # type: ignore[no-redef]
        Alert,
        AlertType,
        MonitoredPosition,
        PortfolioSnapshot,
        RestakingMonitor,
        SlashingEvent,
    )
    from src.plugins.restaking.optimizer import (  # type: ignore[no-redef]
        OptimizationResult,
        OptimizationStrategy,
        RestakingOpportunity,
        RestakingOptimizer,
        RiskAdjustedYield,
    )
    from src.plugins.restaking.protocols import (  # type: ignore[no-redef]
        BABYLON_STAKING_ABI,
        BABYLON_VAULT_ADDRESS,
        SOLAYER_RESTAKING_ABI,
        SOLAYER_VAULT_ADDRESS,
        BabylonBtcRestaking,
        ProtocolPosition,
        ProtocolReward,
        RestakingProtocol,
        SolanaRestaking,
    )

__all__ = [
    # EigenLayer
    "EigenLayer",
    "EigenLayerConfig",
    "RestakeResult",
    "OperatorInfo",
    "RestakingStrategy",
    "EIGENLAYER_ABI",
    "EIGENLAYER_STRATEGY_MANAGER",
    "EIGENLAYER_DELEGATION_MANAGER",
    "EIGENLAYER_SLASHER",
    "EIGEN_TOKEN",
    # Multi-protocol
    "RestakingProtocol",
    "BabylonBtcRestaking",
    "SolanaRestaking",
    "ProtocolPosition",
    "ProtocolReward",
    "BABYLON_STAKING_ABI",
    "BABYLON_VAULT_ADDRESS",
    "SOLAYER_RESTAKING_ABI",
    "SOLAYER_VAULT_ADDRESS",
    # Optimizer
    "RestakingOptimizer",
    "RestakingOpportunity",
    "RiskAdjustedYield",
    "OptimizationStrategy",
    "OptimizationResult",
    # Monitor
    "RestakingMonitor",
    "MonitoredPosition",
    "SlashingEvent",
    "AlertType",
    "Alert",
    "PortfolioSnapshot",
]
