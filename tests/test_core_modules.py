"""Tests for core modules — chains, gas optimizer, and portfolio."""

import pytest
from unittest.mock import MagicMock, patch

from src.chains.chain import Chain, CHAIN_IDS, DEFAULT_RPCS, ChainConfig, ChainManager


class TestChain:
    def test_chain_enum_values(self):
        assert Chain.ETHEREUM.value == "ethereum"
        assert Chain.BASE.value == "base"
        assert Chain.SOLANA.value == "solana"
        assert Chain.BSC.value == "bsc"

    def test_chain_ids(self):
        assert CHAIN_IDS[Chain.ETHEREUM] == 1
        assert CHAIN_IDS[Chain.BASE] == 8453
        assert CHAIN_IDS[Chain.ARBITRUM] == 42161
        assert CHAIN_IDS[Chain.POLYGON] == 137
        assert CHAIN_IDS[Chain.OPTIMISM] == 10
        assert CHAIN_IDS[Chain.BSC] == 56
        assert CHAIN_IDS[Chain.AVALANCHE] == 43114

    def test_solana_not_in_chain_ids(self):
        # Solana doesn't have an EVM chain ID
        assert Chain.SOLANA not in CHAIN_IDS

    def test_default_rpcs(self):
        assert "https://" in DEFAULT_RPCS[Chain.ETHEREUM]
        assert "solana" in DEFAULT_RPCS[Chain.SOLANA]
        assert "base" in DEFAULT_RPCS[Chain.BASE]


class TestChainConfig:
    def test_default_config(self):
        config = ChainConfig(chain=Chain.ETHEREUM)
        assert config.chain == Chain.ETHEREUM
        assert config.rpc_url is not None
        assert config.chain_id == 1

    def test_custom_config(self):
        config = ChainConfig(
            chain=Chain.POLYGON,
            rpc_url="https://custom.rpc",
            chain_id=137,
        )
        assert config.chain == Chain.POLYGON
        assert config.rpc_url == "https://custom.rpc"
        assert config.chain_id == 137

    def test_is_evm(self):
        eth_config = ChainConfig(chain=Chain.ETHEREUM)
        sol_config = ChainConfig(chain=Chain.SOLANA)
        assert eth_config.is_evm is True
        assert sol_config.is_evm is False

    def test_explorer_url(self):
        config = ChainConfig(chain=Chain.ETHEREUM)
        assert "etherscan.io" in config.explorer

        config2 = ChainConfig(chain=Chain.SOLANA)
        assert "solscan.io" in config2.explorer

    def test_auto_fill_rpc(self):
        config = ChainConfig(chain=Chain.BASE)
        assert config.rpc_url is not None
        assert "base" in config.rpc_url.lower()

    def test_auto_fill_chain_id(self):
        config = ChainConfig(chain=Chain.ARBITRUM)
        assert config.chain_id == 42161


class TestChainManager:
    def test_init(self):
        manager = ChainManager(chains=[Chain.ETHEREUM])
        assert manager is not None

    def test_init_with_chains(self):
        manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE, Chain.POLYGON])
        assert manager is not None

    def test_get_config(self):
        manager = ChainManager(chains=[Chain.ETHEREUM])
        config = manager.get_config(Chain.ETHEREUM)
        assert config.chain == Chain.ETHEREUM
        assert config.chain_id == 1

    def test_get_config_nonexistent(self):
        manager = ChainManager(chains=[Chain.ETHEREUM])
        with pytest.raises(ValueError):
            manager.get_config(Chain.BASE)

    def test_get_web3(self):
        manager = ChainManager(chains=[Chain.ETHEREUM])
        web3 = manager.get_web3(Chain.ETHEREUM)
        assert web3 is not None

    def test_multiple_chains(self):
        manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM])
        assert manager.get_config(Chain.ETHEREUM).chain_id == 1
        assert manager.get_config(Chain.BASE).chain_id == 8453
        assert manager.get_config(Chain.ARBITRUM).chain_id == 42161


class TestGasOptimizer:
    """Test gas estimation logic."""

    def test_init(self):
        mock_wallet = MagicMock()
        mock_cm = MagicMock()
        from src.gas.optimizer import GasOptimizer
        optimizer = GasOptimizer(wallet=mock_wallet, chain_manager=mock_cm)
        assert optimizer is not None

    def test_estimate_gas(self):
        mock_wallet = MagicMock()
        mock_cm = MagicMock()
        from src.gas.optimizer import GasOptimizer
        optimizer = GasOptimizer(wallet=mock_wallet, chain_manager=mock_cm)
        estimate = optimizer.estimate(
            to="0xRecipient",
            value=0.1,
            chain=Chain.ETHEREUM,
        )
        assert estimate is not None
        assert estimate.gas_limit > 0
        assert estimate.chain == Chain.ETHEREUM

    def test_estimate_returns_gas_limit(self):
        mock_wallet = MagicMock()
        mock_cm = MagicMock()
        from src.gas.optimizer import GasOptimizer
        optimizer = GasOptimizer(wallet=mock_wallet, chain_manager=mock_cm)
        estimate = optimizer.estimate(to="0xABC", value=0, chain=Chain.BASE)
        assert isinstance(estimate.gas_limit, int)
        assert estimate.gas_limit >= 21000

    def test_recommend_timing(self):
        mock_wallet = MagicMock()
        mock_cm = MagicMock()
        from src.gas.optimizer import GasOptimizer
        optimizer = GasOptimizer(wallet=mock_wallet, chain_manager=mock_cm)
        rec = optimizer.recommend_timing(chain=Chain.ETHEREUM)
        assert rec is not None
        assert rec.recommended_action in ("execute_now", "wait", "batch")
        assert rec.current_gwei > 0

    def test_recommend_timing_high_gas(self):
        mock_wallet = MagicMock()
        mock_cm = MagicMock()
        from src.gas.optimizer import GasOptimizer
        optimizer = GasOptimizer(wallet=mock_wallet, chain_manager=mock_cm)
        rec = optimizer.recommend_timing(chain=Chain.ETHEREUM)
        assert rec.recommended_action in ("execute_now", "wait", "batch")
        assert rec.estimated_savings_pct >= 0

    def test_batch_estimate(self):
        mock_wallet = MagicMock()
        mock_cm = MagicMock()
        from src.gas.optimizer import GasOptimizer
        optimizer = GasOptimizer(wallet=mock_wallet, chain_manager=mock_cm)
        result = optimizer.batch_estimate(
            transactions=[{"to": "0xA", "value": 0.01}, {"to": "0xB", "value": 0.02}],
            chain=Chain.ETHEREUM,
        )
        assert result is not None
        assert result["count"] == 2
        assert result["total_gas_limit"] >= 0

    def test_get_gas_price(self):
        mock_wallet = MagicMock()
        mock_cm = MagicMock()
        from src.gas.optimizer import GasOptimizer
        optimizer = GasOptimizer(wallet=mock_wallet, chain_manager=mock_cm)
        price = optimizer.get_gas_price(chain=Chain.ETHEREUM)
        assert isinstance(price, dict)
        assert "gwei" in price

    def test_suggest_gas_limit(self):
        mock_wallet = MagicMock()
        mock_cm = MagicMock()
        from src.gas.optimizer import GasOptimizer
        optimizer = GasOptimizer(wallet=mock_wallet, chain_manager=mock_cm)
        limit = optimizer.suggest_gas_limit("eth_transfer")
        assert limit >= 21000