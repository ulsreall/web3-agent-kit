"""Tests for src/gas/ — Gas optimizer, estimation, batching."""

import pytest
from unittest.mock import MagicMock, patch

from src.gas import (
    GasOptimizer,
    GasEstimate,
    GasRecommendation,
    GasPriority,
    BatchResult,
)
from src.chains.chain import Chain, ChainManager
from src.wallet.wallet import Wallet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_w3():
    w3 = MagicMock()
    block = MagicMock()
    block.get.return_value = 20e9  # 20 gwei baseFeePerGas
    w3.eth.get_block.return_value = block
    w3.from_wei.return_value = 20.0
    return w3


def _mock_chain_manager(w3=None):
    cm = MagicMock(spec=ChainManager)
    cm.get_web3.return_value = w3 or _mock_w3()
    return cm


def _mock_wallet():
    w = MagicMock(spec=Wallet)
    w.address = "0xDeadBeef00000000000000000000000000000000"
    return w


def _make_optimizer(w3=None, eth_price=3500.0):
    w3 = w3 or _mock_w3()
    cm = _mock_chain_manager(w3)
    wallet = _mock_wallet()
    return GasOptimizer(wallet, cm, eth_price_usd=eth_price), w3


# ===========================================================================
# Enums & data classes
# ===========================================================================

class TestGasPriority:
    def test_enum_values(self):
        assert GasPriority.LOW.value == "low"
        assert GasPriority.MEDIUM.value == "medium"
        assert GasPriority.HIGH.value == "high"
        assert GasPriority.URGENT.value == "urgent"


class TestGasEstimate:
    def test_fields(self):
        est = GasEstimate(
            gas_limit=21000, base_fee=20.0, priority_fee=1.5,
            max_fee=41.5, total_cost_eth=0.00087,
            total_cost_usd=3.05, priority=GasPriority.MEDIUM,
            chain=Chain.ETHEREUM,
        )
        assert est.gas_limit == 21000
        assert est.chain == Chain.ETHEREUM


class TestGasRecommendation:
    def test_fields(self):
        rec = GasRecommendation(
            current_gwei=50.0, recommended_action="wait",
            estimated_savings_pct=60.0, optimal_gwei=20.0,
            estimated_wait_hours=2.0, reason="Gas is high",
        )
        assert rec.recommended_action == "wait"
        assert rec.estimated_savings_pct == 60.0


class TestBatchResult:
    def test_fields(self):
        br = BatchResult(tx_count=5, total_gas_saved=0.001, estimated_time_s=60.0, status="batched")
        assert br.tx_count == 5
        assert br.status == "batched"


# ===========================================================================
# GasOptimizer
# ===========================================================================

class TestGasOptimizerInit:
    def test_defaults(self):
        opt, _ = _make_optimizer()
        assert opt.eth_price_usd == 3500.0

    def test_custom_price(self):
        opt, _ = _make_optimizer(eth_price=4000.0)
        assert opt.eth_price_usd == 4000.0


class TestGasOptimizerEstimate:
    def test_transfer_estimate(self):
        opt, _ = _make_optimizer()
        est = opt.estimate(to="0xRecipient", value=0.1, chain=Chain.ETHEREUM)
        assert isinstance(est, GasEstimate)
        assert est.gas_limit == 21000
        assert est.priority == GasPriority.MEDIUM

    def test_contract_call_estimate(self):
        opt, _ = _make_optimizer()
        est = opt.estimate(to="0xContract", data="0xabcdef", chain=Chain.ETHEREUM)
        assert est.gas_limit == 200_000  # default for contract calls

    def test_named_operation_estimate(self):
        opt, _ = _make_optimizer()
        est = opt.estimate(to="0xRouter", operation="swap", chain=Chain.ETHEREUM)
        assert est.gas_limit == 180_000

    def test_high_priority_estimate(self):
        opt, _ = _make_optimizer()
        est = opt.estimate(to="0xR", value=0.1, priority=GasPriority.URGENT, chain=Chain.ETHEREUM)
        assert est.priority_fee == 5.0

    def test_low_priority_estimate(self):
        opt, _ = _make_optimizer()
        est = opt.estimate(to="0xR", value=0.1, priority=GasPriority.LOW, chain=Chain.ETHEREUM)
        assert est.priority_fee == 0.5

    def test_base_chain_estimate(self):
        opt, _ = _make_optimizer()
        est = opt.estimate(to="0xR", value=0.1, chain=Chain.BASE)
        assert est.chain == Chain.BASE

    def test_total_cost_positive(self):
        opt, _ = _make_optimizer()
        est = opt.estimate(to="0xR", value=0.1, chain=Chain.ETHEREUM)
        assert est.total_cost_eth > 0
        assert est.total_cost_usd > 0


class TestGasOptimizerBatchEstimate:
    def test_batch_multiple(self):
        opt, _ = _make_optimizer()
        txs = [
            {"to": "0xA", "value": 0.01},
            {"to": "0xB", "value": 0.02, "operation": "swap"},
        ]
        result = opt.batch_estimate(txs, chain=Chain.ETHEREUM)
        assert result["count"] == 2
        assert result["total_gas_limit"] > 0
        assert result["total_cost_eth"] > 0

    def test_batch_empty(self):
        opt, _ = _make_optimizer()
        result = opt.batch_estimate([], chain=Chain.ETHEREUM)
        assert result["count"] == 0
        assert result["total_gas_limit"] == 0


class TestGasOptimizerBatchExecute:
    def test_batch_execute(self):
        opt, _ = _make_optimizer()
        txs = [{"to": "0xA", "value": 0.01}, {"to": "0xB", "value": 0.02}]
        result = opt.batch_execute(txs, chain=Chain.ETHEREUM)
        assert isinstance(result, BatchResult)
        assert result.tx_count == 2
        assert result.status == "batched"

    def test_batch_execute_single(self):
        opt, _ = _make_optimizer()
        result = opt.batch_execute([{"to": "0xA", "value": 0.01}])
        assert result.tx_count == 1


class TestGasOptimizerGasPrice:
    def test_get_gas_price(self):
        opt, _ = _make_optimizer()
        price = opt.get_gas_price(Chain.ETHEREUM)
        assert "gwei" in price
        assert "wei" in price
        assert "eth" in price
        assert "usd" in price
        assert "level" in price
        assert price["chain"] == "ethereum"


class TestGasOptimizerSuggestGasLimit:
    def test_known_operation(self):
        opt, _ = _make_optimizer()
        assert opt.suggest_gas_limit("swap") == 180_000
        assert opt.suggest_gas_limit("transfer") == 21_000
        assert opt.suggest_gas_limit("bridge") == 300_000

    def test_unknown_operation(self):
        opt, _ = _make_optimizer()
        assert opt.suggest_gas_limit("unknown") == 21_000


class TestGasOptimizerUpdatePrice:
    def test_update_eth_price(self):
        opt, _ = _make_optimizer()
        opt.update_eth_price(5000.0)
        assert opt.eth_price_usd == 5000.0


class TestGasOptimizerTiming:
    def test_recommend_timing_insufficient_history(self):
        opt, _ = _make_optimizer()
        rec = opt.recommend_timing(Chain.ETHEREUM)
        assert isinstance(rec, GasRecommendation)
        assert rec.recommended_action == "execute_now"

    def test_recommend_timing_urgent(self):
        opt, _ = _make_optimizer()
        # Even with history, URGENT should always execute now
        for _ in range(20):
            opt._gas_history.setdefault("ethereum", []).append((0, 50.0))
        rec = opt.recommend_timing(Chain.ETHEREUM, urgency=GasPriority.URGENT)
        assert rec.recommended_action == "execute_now"


class TestGasOptimizerGasLevel:
    def test_gas_level_low(self):
        assert "Low" in GasOptimizer._gas_level(5.0)

    def test_gas_level_medium(self):
        assert "Medium" in GasOptimizer._gas_level(20.0)

    def test_gas_level_high(self):
        assert "High" in GasOptimizer._gas_level(50.0)

    def test_gas_level_very_high(self):
        assert "Very High" in GasOptimizer._gas_level(100.0)


class TestGasOptimizerFallback:
    def test_fallback_on_connection_error(self):
        w3 = _mock_w3()
        w3.eth.get_block.side_effect = ConnectionError("no network")
        cm = _mock_chain_manager(w3)
        opt = GasOptimizer(_mock_wallet(), cm)
        base_fee = opt._get_base_fee(Chain.ETHEREUM)
        assert base_fee == 20.0  # fallback default
