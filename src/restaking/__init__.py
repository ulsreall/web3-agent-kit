"""Restaking module — EigenLayer, Babylon, Solana restaking, and yield optimization."""

from __future__ import annotations

# Support both `from src.restaking import *` and `from restaking import *` (when src is on sys.path)
try:
    from .eigenlayer import (
        EigenLayer,
        EigenLayerConfig,
        RestakeResult,
        OperatorInfo,
        RestakingStrategy,
        EIGENLAYER_ABI,
        EIGENLAYER_STRATEGY_MANAGER,
        EIGENLAYER_DELEGATION_MANAGER,
        EIGENLAYER_SLASHER,
        EIGEN_TOKEN,
    )
    from .protocols import (
        RestakingProtocol,
        BabylonBtcRestaking,
        SolanaRestaking,
        ProtocolPosition,
        ProtocolReward,
        BABYLON_STAKING_ABI,
        BABYLON_VAULT_ADDRESS,
        SOLAYER_RESTAKING_ABI,
        SOLAYER_VAULT_ADDRESS,
    )
    from .optimizer import (
        RestakingOptimizer,
        RestakingOpportunity,
        RiskAdjustedYield,
        OptimizationStrategy,
        OptimizationResult,
    )
    from .monitor import (
        RestakingMonitor,
        MonitoredPosition,
        SlashingEvent,
        AlertType,
        Alert,
        PortfolioSnapshot,
    )
except ImportError:
    # Fallback: when imported as top-level package (sys.path includes src/)
    from eigenlayer import (  # type: ignore[no-redef]
        EigenLayer,
        EigenLayerConfig,
        RestakeResult,
        OperatorInfo,
        RestakingStrategy,
        EIGENLAYER_ABI,
        EIGENLAYER_STRATEGY_MANAGER,
        EIGENLAYER_DELEGATION_MANAGER,
        EIGENLAYER_SLASHER,
        EIGEN_TOKEN,
    )
    from protocols import (  # type: ignore[no-redef]
        RestakingProtocol,
        BabylonBtcRestaking,
        SolanaRestaking,
        ProtocolPosition,
        ProtocolReward,
        BABYLON_STAKING_ABI,
        BABYLON_VAULT_ADDRESS,
        SOLAYER_RESTAKING_ABI,
        SOLAYER_VAULT_ADDRESS,
    )
    from optimizer import (  # type: ignore[no-redef]
        RestakingOptimizer,
        RestakingOpportunity,
        RiskAdjustedYield,
        OptimizationStrategy,
        OptimizationResult,
    )
    from monitor import (  # type: ignore[no-redef]
        RestakingMonitor,
        MonitoredPosition,
        SlashingEvent,
        AlertType,
        Alert,
        PortfolioSnapshot,
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
