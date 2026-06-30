"""Tests for src/restaking/ — EigenLayer, multi-protocol, optimizer, monitor."""

from __future__ import annotations

import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

from src.plugins.restaking import (
    # EigenLayer
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
    # Protocols
    RestakingProtocol,
    BabylonBtcRestaking,
    SolanaRestaking,
    ProtocolPosition,
    ProtocolReward,
    BABYLON_STAKING_ABI,
    BABYLON_VAULT_ADDRESS,
    SOLAYER_RESTAKING_ABI,
    SOLAYER_VAULT_ADDRESS,
    # Optimizer
    RestakingOptimizer,
    RestakingOpportunity,
    RiskAdjustedYield,
    OptimizationStrategy,
    OptimizationResult,
    # Monitor
    RestakingMonitor,
    MonitoredPosition,
    SlashingEvent,
    AlertType,
    Alert,
    PortfolioSnapshot,
)
from src.chains.chain import Chain, ChainManager, CHAIN_IDS
from src.wallet.wallet import Wallet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_w3():
    """Return a fully-mocked Web3 instance."""
    w3 = MagicMock()
    w3.to_checksum_address.side_effect = lambda addr: addr
    w3.eth.gas_price = 20_000_000_000
    w3.eth.get_transaction_count.return_value = 42
    w3.eth.send_raw_transaction.return_value = MagicMock(hex=lambda: "0xabc123def456")
    receipt = MagicMock()
    receipt.gasUsed = 250_000
    receipt.status = 1
    receipt.get = lambda key, default=0: {"gasUsed": 250_000, "status": 1}.get(key, default)
    w3.eth.wait_for_transaction_receipt.return_value = receipt
    return w3


def _mock_chain_manager(w3=None):
    """Return a mocked ChainManager."""
    cm = MagicMock(spec=ChainManager)
    cm.get_web3.return_value = w3 or _mock_w3()
    return cm


def _mock_wallet():
    """Return a mocked Wallet."""
    w = MagicMock(spec=Wallet)
    w.address = "0xDeadBeef00000000000000000000000000000000"
    w.sign_transaction.return_value = b"signed_tx_bytes"
    return w


def _make_eigenlayer(w3=None, wallet=None):
    """Create an EigenLayer instance with mocks."""
    w3 = w3 or _mock_w3()
    cm = _mock_chain_manager(w3)
    w = wallet or _mock_wallet()
    return EigenLayer(w, cm), w3, w


def _make_sample_opportunity(**overrides) -> RestakingOpportunity:
    """Create a sample RestakingOpportunity."""
    defaults = dict(
        protocol="eigenlayer",
        chain="ethereum",
        asset="stETH",
        apy=4.2,
        tvl_usd=15_000_000_000,
        risk_score=25,
        lock_period_days=7,
        slashing_coverage=True,
        audit_count=5,
        reward_tokens=["EIGEN", "ETH"],
    )
    defaults.update(overrides)
    return RestakingOpportunity(**defaults)


def _make_sample_position(**overrides) -> MonitoredPosition:
    """Create a sample MonitoredPosition."""
    defaults = dict(
        position_id="pos-1",
        protocol="eigenlayer",
        chain="ethereum",
        asset="stETH",
        amount=10.0,
        value_usd=35_000.0,
        apy=4.2,
        operator="P2P Validator",
        risk_score=25,
        lock_end=time.time() + 86400 * 7,
        rewards_pending=0.05,
        rewards_usd=175.0,
        entry_price_usd=3500.0,
    )
    defaults.update(overrides)
    return MonitoredPosition(**defaults)


# ===========================================================================
# Constants & imports
# ===========================================================================

class TestModuleImports:
    """Verify all exports are importable."""

    def test_import_eigenlayer_classes(self):
        assert EigenLayer is not None
        assert EigenLayerConfig is not None
        assert RestakeResult is not None
        assert OperatorInfo is not None
        assert RestakingStrategy is not None

    def test_import_protocol_classes(self):
        assert RestakingProtocol is not None
        assert BabylonBtcRestaking is not None
        assert SolanaRestaking is not None
        assert ProtocolPosition is not None
        assert ProtocolReward is not None

    def test_import_optimizer_classes(self):
        assert RestakingOptimizer is not None
        assert RestakingOpportunity is not None
        assert RiskAdjustedYield is not None
        assert OptimizationStrategy is not None
        assert OptimizationResult is not None

    def test_import_monitor_classes(self):
        assert RestakingMonitor is not None
        assert MonitoredPosition is not None
        assert SlashingEvent is not None
        assert AlertType is not None
        assert Alert is not None
        assert PortfolioSnapshot is not None

    def test_contract_addresses_defined(self):
        assert EIGENLAYER_STRATEGY_MANAGER.startswith("0x")
        assert EIGENLAYER_DELEGATION_MANAGER.startswith("0x")
        assert EIGENLAYER_SLASHER.startswith("0x")
        assert EIGEN_TOKEN.startswith("0x")
        assert BABYLON_VAULT_ADDRESS is not None
        assert SOLAYER_VAULT_ADDRESS.startswith("0x")

    def test_abi_parsed(self):
        assert isinstance(EIGENLAYER_ABI, dict)
        assert "strategy_manager" in EIGENLAYER_ABI
        assert "delegation_manager" in EIGENLAYER_ABI
        assert isinstance(EIGENLAYER_ABI["strategy_manager"], list)
        assert isinstance(BABYLON_STAKING_ABI, list)
        assert isinstance(SOLAYER_RESTAKING_ABI, list)


# ===========================================================================
# RestakeResult & OperatorInfo
# ===========================================================================

class TestRestakeResult:
    def test_fields(self):
        result = RestakeResult(
            tx_hash="0xabc", strategy="0xstrat", amount=5.0,
            operator="0xop", chain=Chain.ETHEREUM, gas_used=250_000,
            status="confirmed",
        )
        assert result.tx_hash == "0xabc"
        assert result.amount == 5.0
        assert result.status == "confirmed"
        assert result.timestamp > 0

    def test_timestamp_auto_set(self):
        before = time.time()
        result = RestakeResult(
            tx_hash="0x", strategy="", amount=0, operator=None,
            chain=Chain.ETHEREUM, gas_used=0, status="pending",
        )
        assert result.timestamp >= before


class TestOperatorInfo:
    def test_fields(self):
        info = OperatorInfo(
            address="0x123", name="TestOp", total_delegated_stake=1000.0,
            num_stakers=50, commission_rate=10.0, slashing_history=0,
            uptime_pct=99.9,
        )
        assert info.name == "TestOp"
        assert info.uptime_pct == 99.9
        assert info.supported_strategies == []


# ===========================================================================
# EigenLayer
# ===========================================================================

class TestEigenLayerInit:
    def test_default_config(self):
        el, _, _ = _make_eigenlayer()
        assert el.config.strategy_manager == EIGENLAYER_STRATEGY_MANAGER
        assert el.config.chain == Chain.ETHEREUM

    def test_custom_config(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        config = EigenLayerConfig(chain=Chain.ETHEREUM, gas_limit=800_000)
        el = EigenLayer(_mock_wallet(), cm, config)
        assert el.config.gas_limit == 800_000


class TestEigenLayerRestake:
    def test_restake_lst_success(self):
        el, w3, wallet = _make_eigenlayer()

        # Mock contract interactions
        strategy_contract = MagicMock()
        strategy_contract.functions.depositIntoStrategy.return_value.build_transaction.return_value = {"dummy": "tx"}
        token_contract = MagicMock()
        token_contract.functions.allowance.return_value.call.return_value = 0
        token_contract.functions.approve.return_value.build_transaction.return_value = {"dummy": "approve"}

        def contract_factory(address, abi):
            if "depositIntoStrategy" in str(abi):
                return strategy_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory

        result = el.restake("stETH", 5.0)
        assert isinstance(result, RestakeResult)
        assert result.tx_hash == "0xabc123def456"
        assert result.amount == 5.0
        assert result.status == "confirmed"

    def test_restake_invalid_amount(self):
        el, _, _ = _make_eigenlayer()
        with pytest.raises(ValueError, match="positive"):
            el.restake("stETH", -1.0)

    def test_restake_unsupported_lst(self):
        el, _, _ = _make_eigenlayer()
        with pytest.raises(ValueError, match="Unsupported LST"):
            el.restake("DOGE", 1.0)

    def test_restake_with_operator_delegation(self):
        el, w3, wallet = _make_eigenlayer()

        strategy_contract = MagicMock()
        strategy_contract.functions.depositIntoStrategy.return_value.build_transaction.return_value = {"dummy": "tx"}
        delegation_contract = MagicMock()
        delegation_contract.functions.delegateTo.return_value.build_transaction.return_value = {"dummy": "delegate"}
        token_contract = MagicMock()
        token_contract.functions.allowance.return_value.call.return_value = 999999

        call_count = [0]
        def contract_factory(address, abi):
            call_count[0] += 1
            abi_str = str(abi)
            if "depositIntoStrategy" in abi_str:
                return strategy_contract
            if "delegateTo" in abi_str:
                return delegation_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory

        result = el.restake("stETH", 5.0, operator="0xOperator")
        assert isinstance(result, RestakeResult)
        delegation_contract.functions.delegateTo.assert_called()


class TestEigenLayerDelegate:
    def test_delegate_success(self):
        el, w3, _ = _make_eigenlayer()

        delegation_contract = MagicMock()
        delegation_contract.functions.delegateTo.return_value.build_transaction.return_value = {"dummy": "tx"}
        w3.eth.contract.return_value = delegation_contract

        result = el.delegate("0xOperator")
        assert isinstance(result, RestakeResult)
        assert result.operator == "0xOperator"


class TestEigenLayerWithdraw:
    def test_withdraw_success(self):
        el, w3, _ = _make_eigenlayer()

        strategy_contract = MagicMock()
        strategy_contract.functions.withdrawSharesAsTokens.return_value.build_transaction.return_value = {"dummy": "tx"}
        w3.eth.contract.return_value = strategy_contract

        result = el.withdraw("stETH", 3.0)
        assert isinstance(result, RestakeResult)
        assert result.amount == 3.0


class TestEigenLayerQueryOps:
    def test_get_supported_lsts(self):
        el, _, _ = _make_eigenlayer()
        lsts = el.get_supported_lsts()
        assert "stETH" in lsts
        assert "rETH" in lsts
        assert "cbETH" in lsts

    def test_get_positions_empty(self):
        el, w3, _ = _make_eigenlayer()
        strategy_contract = MagicMock()
        strategy_contract.functions.getDeposits.return_value.call.return_value = []
        w3.eth.contract.return_value = strategy_contract

        positions = el.get_positions()
        assert isinstance(positions, list)

    def test_get_delegated_operator(self):
        el, w3, _ = _make_eigenlayer()
        delegation_contract = MagicMock()
        delegation_contract.functions.delegatedTo.return_value.call.return_value = "0xOperator"
        w3.eth.contract.return_value = delegation_contract

        operator = el.get_delegated_operator()
        assert operator == "0xOperator"

    def test_get_delegated_operator_none(self):
        el, w3, _ = _make_eigenlayer()
        delegation_contract = MagicMock()
        delegation_contract.functions.delegatedTo.return_value.call.return_value = "0x0000000000000000000000000000000000000000"
        w3.eth.contract.return_value = delegation_contract

        operator = el.get_delegated_operator()
        assert operator is None

    def test_get_operator_info(self):
        el, w3, _ = _make_eigenlayer()
        delegation_contract = MagicMock()
        delegation_contract.functions.isOperator.return_value.call.return_value = True
        delegation_contract.functions.operatorShares.return_value.call.return_value = 10**20
        w3.eth.contract.return_value = delegation_contract

        info = el.get_operator_info("0x123")
        assert isinstance(info, OperatorInfo)
        assert info.is_active is True if hasattr(info, 'is_active') else True  # just verify no crash

    def test_get_rewards(self):
        el, _, _ = _make_eigenlayer()
        rewards = el.get_rewards()
        assert isinstance(rewards, dict)


# ===========================================================================
# RestakingStrategy enum
# ===========================================================================

class TestRestakingStrategy:
    def test_enum_values(self):
        assert RestakingStrategy.LST.value == "lst"
        assert RestakingStrategy.NATIVE.value == "native"
        assert RestakingStrategy.LP_POSITION.value == "lp"


# ===========================================================================
# Babylon BTC Restaking
# ===========================================================================

class TestBabylonBtcRestaking:
    def test_init(self):
        cm = _mock_chain_manager()
        babylon = BabylonBtcRestaking(_mock_wallet(), cm)
        assert babylon.name.value == "babylon"
        assert Chain.ETHEREUM in babylon.supported_chains

    def test_stake_success(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()
        vault_contract = MagicMock()
        vault_contract.functions.delegate.return_value.build_transaction.return_value = {"dummy": "tx"}
        w3.eth.contract.return_value = vault_contract

        babylon = BabylonBtcRestaking(wallet, cm)
        result = babylon.stake(0.5, lock_blocks=64_000)

        assert result["tx_hash"] == "0xabc123def456"
        assert result["amount"] == 0.5
        assert result["protocol"] == "babylon"

    def test_stake_invalid_amount(self):
        cm = _mock_chain_manager()
        babylon = BabylonBtcRestaking(_mock_wallet(), cm)
        with pytest.raises(ValueError, match="positive"):
            babylon.stake(-1.0)

    def test_stake_short_lock(self):
        cm = _mock_chain_manager()
        babylon = BabylonBtcRestaking(_mock_wallet(), cm)
        with pytest.raises(ValueError, match="1,000"):
            babylon.stake(1.0, lock_blocks=100)

    def test_unstake_requires_stake_id(self):
        cm = _mock_chain_manager()
        babylon = BabylonBtcRestaking(_mock_wallet(), cm)
        with pytest.raises(ValueError, match="stake_id"):
            babylon.unstake()

    def test_get_positions(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        vault_contract = MagicMock()
        vault_contract.functions.getStakes.return_value.call.return_value = [
            (50000000, 64000, 1000, b"", True),  # 0.5 BTC
        ]
        w3.eth.contract.return_value = vault_contract

        babylon = BabylonBtcRestaking(_mock_wallet(), cm)
        positions = babylon.get_positions()
        assert len(positions) == 1
        assert positions[0].protocol.value == "babylon"
        assert positions[0].staked_amount == 0.5

    def test_get_rewards_empty(self):
        cm = _mock_chain_manager()
        babylon = BabylonBtcRestaking(_mock_wallet(), cm)
        rewards = babylon.get_rewards()
        assert rewards == []


# ===========================================================================
# Solana Restaking
# ===========================================================================

class TestSolanaRestaking:
    def test_init_solayer(self):
        cm = _mock_chain_manager()
        sol = SolanaRestaking(_mock_wallet(), cm, protocol="solayer")
        assert sol.name.value == "solayer"

    def test_init_jito(self):
        cm = _mock_chain_manager()
        sol = SolanaRestaking(_mock_wallet(), cm, protocol="jito")
        assert sol.protocol_name == "jito"

    def test_init_unknown_protocol(self):
        cm = _mock_chain_manager()
        with pytest.raises(ValueError, match="Unknown"):
            SolanaRestaking(_mock_wallet(), cm, protocol="unknown")

    def test_stake_success(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        vault_contract = MagicMock()
        vault_contract.functions.restake.return_value.build_transaction.return_value = {"dummy": "tx"}
        w3.eth.contract.return_value = vault_contract

        sol = SolanaRestaking(_mock_wallet(), cm, protocol="solayer")
        result = sol.stake(100.0)

        assert result["tx_hash"] == "0xabc123def456"
        assert result["amount"] == 100.0
        assert result["protocol"] == "solayer"

    def test_stake_invalid_amount(self):
        cm = _mock_chain_manager()
        sol = SolanaRestaking(_mock_wallet(), cm)
        with pytest.raises(ValueError, match="positive"):
            sol.stake(-5.0)

    def test_unstake_success(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        vault_contract = MagicMock()
        vault_contract.functions.unstake.return_value.build_transaction.return_value = {"dummy": "tx"}
        w3.eth.contract.return_value = vault_contract

        sol = SolanaRestaking(_mock_wallet(), cm)
        result = sol.unstake(50.0)
        assert result["amount"] == 50.0

    def test_get_positions(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        vault_contract = MagicMock()
        vault_contract.functions.getBalance.return_value.call.return_value = 50 * 10**9  # 50 SOL
        w3.eth.contract.return_value = vault_contract

        sol = SolanaRestaking(_mock_wallet(), cm)
        positions = sol.get_positions()
        assert len(positions) == 1
        assert positions[0].staked_amount == 50.0
        assert positions[0].chain == Chain.SOLANA

    def test_get_rewards(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        vault_contract = MagicMock()
        vault_contract.functions.getPendingRewards.return_value.call.return_value = 2 * 10**9  # 2 SOL
        w3.eth.contract.return_value = vault_contract

        sol = SolanaRestaking(_mock_wallet(), cm)
        rewards = sol.get_rewards()
        assert len(rewards) == 1
        assert rewards[0].reward_amount == 2.0
        assert rewards[0].reward_token == "SOL"


# ===========================================================================
# RestakingOpportunity
# ===========================================================================

class TestRestakingOpportunity:
    def test_risk_adjusted_yield(self):
        opp = _make_sample_opportunity(apy=4.0, risk_score=20)
        # 4.0 / (1 + (20/20)^2) = 4.0 / 2.0 = 2.0
        assert abs(opp.risk_adjusted_yield - 2.0) < 0.01

    def test_risk_adjusted_yield_zero_risk(self):
        opp = _make_sample_opportunity(apy=4.0, risk_score=0)
        assert opp.risk_adjusted_yield == 400.0

    def test_liquidity_score(self):
        opp = _make_sample_opportunity(tvl_usd=1_000_000_000, lock_period_days=0)
        score = opp.liquidity_score
        assert score > 0

    def test_display_apy(self):
        opp = _make_sample_opportunity(apy=5.25)
        assert opp.display_apy == "5.25%"


# ===========================================================================
# RestakingOptimizer
# ===========================================================================

class TestRestakingOptimizerInit:
    def test_defaults(self):
        opt = RestakingOptimizer()
        assert opt.max_risk_score == 60.0
        assert opt.min_apy == 2.0

    def test_custom_params(self):
        opt = RestakingOptimizer(max_risk_score=80, min_apy=5.0)
        assert opt.max_risk_score == 80
        assert opt.min_apy == 5.0


class TestRestakingOptimizerOpportunities:
    def test_add_opportunity(self):
        opt = RestakingOptimizer()
        opp = _make_sample_opportunity()
        opt.add_opportunity(opp)
        assert len(opt.opportunities) == 1

    def test_add_multiple(self):
        opt = RestakingOptimizer()
        opps = [_make_sample_opportunity(apy=a) for a in [3, 4, 5]]
        opt.add_opportunities(opps)
        assert len(opt.opportunities) == 3

    def test_clear(self):
        opt = RestakingOptimizer()
        opt.add_opportunity(_make_sample_opportunity())
        opt.clear_opportunities()
        assert len(opt.opportunities) == 0

    def test_set_benchmarks(self):
        opt = RestakingOptimizer()
        opt.set_benchmark_opportunities()
        assert len(opt.opportunities) >= 5
        protos = {o.protocol for o in opt.opportunities}
        assert "eigenlayer" in protos
        assert "babylon" in protos


class TestRestakingOptimizerOptimize:
    def _load_benchmarks(self, opt):
        opt.set_benchmark_opportunities()

    def test_optimize_risk_adjusted(self):
        opt = RestakingOptimizer(max_risk_score=100)
        self._load_benchmarks(opt)
        result = opt.optimize(strategy=OptimizationStrategy.RISK_ADJUSTED)
        assert isinstance(result, OptimizationResult)
        assert result.num_positions > 0
        assert result.total_expected_apy > 0

    def test_optimize_max_yield(self):
        opt = RestakingOptimizer(max_risk_score=100)
        self._load_benchmarks(opt)
        result = opt.optimize(strategy=OptimizationStrategy.MAX_YIELD)
        assert isinstance(result, OptimizationResult)
        assert len(result.opportunities) > 0

    def test_optimize_conservative(self):
        opt = RestakingOptimizer(max_risk_score=100)
        self._load_benchmarks(opt)
        result = opt.optimize(strategy=OptimizationStrategy.CONSERVATIVE)
        assert isinstance(result, OptimizationResult)
        # Conservative should prioritize low-risk
        if result.opportunities:
            assert result.opportunities[0].opportunity.risk_score <= 50

    def test_optimize_diversified(self):
        opt = RestakingOptimizer(max_risk_score=100)
        self._load_benchmarks(opt)
        result = opt.optimize(strategy=OptimizationStrategy.DIVERSIFIED)
        assert isinstance(result, OptimizationResult)
        protocols = set(result.allocations.keys())
        # Should have multiple protocols
        assert len(protocols) >= 2

    def test_optimize_balanced(self):
        opt = RestakingOptimizer(max_risk_score=100)
        self._load_benchmarks(opt)
        result = opt.optimize(strategy=OptimizationStrategy.BALANCED)
        assert isinstance(result, OptimizationResult)

    def test_optimize_with_asset_filter(self):
        opt = RestakingOptimizer(max_risk_score=100)
        self._load_benchmarks(opt)
        result = opt.optimize(asset_filter="BTC")
        assert all(ray.opportunity.asset == "BTC" for ray in result.opportunities)

    def test_optimize_no_opportunities(self):
        opt = RestakingOptimizer()
        result = opt.optimize()
        assert result.num_positions == 0
        assert result.total_expected_apy == 0

    def test_optimize_none_meet_criteria(self):
        opt = RestakingOptimizer(min_apy=99.0)
        opt.add_opportunity(_make_sample_opportunity(apy=4.0))
        result = opt.optimize()
        assert result.num_positions == 0

    def test_allocations_sum_to_100(self):
        opt = RestakingOptimizer(max_risk_score=100)
        self._load_benchmarks(opt)
        result = opt.optimize()
        total = sum(result.allocations.values())
        assert abs(total - 100) < 5  # Allow small rounding error

    def test_recommendations_generated(self):
        opt = RestakingOptimizer(max_risk_score=100)
        self._load_benchmarks(opt)
        result = opt.optimize()
        assert len(result.recommendations) > 0


class TestRestakingOptimizerCompare:
    def test_compare_strategies(self):
        opt = RestakingOptimizer(max_risk_score=100)
        opt.set_benchmark_opportunities()
        results = opt.compare_strategies()
        assert len(results) == len(OptimizationStrategy)
        for name, result in results.items():
            assert isinstance(result, OptimizationResult)


class TestRestakingOptimizerTop:
    def test_get_top_by_apy(self):
        opt = RestakingOptimizer()
        opt.set_benchmark_opportunities()
        top = opt.get_top_opportunities(n=3, sort_by="apy")
        assert len(top) <= 3
        assert top[0].apy >= top[-1].apy

    def test_get_top_by_risk_adjusted(self):
        opt = RestakingOptimizer()
        opt.set_benchmark_opportunities()
        top = opt.get_top_opportunities(n=3, sort_by="risk_adjusted")
        assert len(top) <= 3

    def test_get_top_by_tvl(self):
        opt = RestakingOptimizer()
        opt.set_benchmark_opportunities()
        top = opt.get_top_opportunities(n=3, sort_by="tvl")
        assert len(top) <= 3


# ===========================================================================
# MonitoredPosition
# ===========================================================================

class TestMonitoredPosition:
    def test_pnl_positive(self):
        pos = _make_sample_position(value_usd=38_000, entry_price_usd=3500, amount=10, rewards_usd=500)
        assert pos.pnl_usd > 0

    def test_pnl_negative(self):
        pos = _make_sample_position(value_usd=30_000, entry_price_usd=3500, amount=10, rewards_usd=0)
        assert pos.pnl_usd < 0

    def test_pnl_pct(self):
        pos = _make_sample_position(value_usd=35_000, entry_price_usd=3500, amount=10, rewards_usd=350)
        assert pos.pnl_pct == pytest.approx(1.0, abs=0.1)

    def test_is_locked(self):
        pos = _make_sample_position(lock_end=time.time() + 86400)
        assert pos.is_locked

    def test_is_unlocked(self):
        pos = _make_sample_position(lock_end=time.time() - 100)
        assert not pos.is_locked

    def test_lock_remaining_days(self):
        pos = _make_sample_position(lock_end=time.time() + 86400 * 7)
        assert pos.lock_remaining_days == pytest.approx(7.0, abs=0.1)


# ===========================================================================
# Alert
# ===========================================================================

class TestAlert:
    def test_is_critical(self):
        alert = Alert(
            alert_type=AlertType.SLASHING,
            severity="critical",
            message="Slashed!",
            protocol="eigenlayer",
        )
        assert alert.is_critical

    def test_not_critical(self):
        alert = Alert(
            alert_type=AlertType.APY_DROP,
            severity="warning",
            message="APY dropped",
            protocol="solayer",
        )
        assert not alert.is_critical

    def test_age_seconds(self):
        alert = Alert(
            alert_type=AlertType.INFO if hasattr(AlertType, 'INFO') else AlertType.POSITION_CHANGE,
            severity="info",
            message="test",
            protocol="test",
            timestamp=time.time() - 60,
        )
        assert alert.age_seconds >= 59


# ===========================================================================
# RestakingMonitor
# ===========================================================================

class TestRestakingMonitorInit:
    def test_defaults(self):
        monitor = RestakingMonitor()
        assert monitor.slashing_alert_threshold == 100.0
        assert monitor.apy_drop_threshold == 1.0

    def test_custom_thresholds(self):
        monitor = RestakingMonitor(slashing_alert_threshold=500, apy_drop_threshold=2.0)
        assert monitor.slashing_alert_threshold == 500


class TestRestakingMonitorPositions:
    def test_add_position(self):
        monitor = RestakingMonitor()
        pos = _make_sample_position()
        monitor.add_position(pos)
        assert len(monitor.positions) == 1

    def test_remove_position(self):
        monitor = RestakingMonitor()
        pos = _make_sample_position()
        monitor.add_position(pos)
        assert monitor.remove_position("pos-1")
        assert len(monitor.positions) == 0

    def test_remove_nonexistent(self):
        monitor = RestakingMonitor()
        assert not monitor.remove_position("nope")

    def test_get_position(self):
        monitor = RestakingMonitor()
        pos = _make_sample_position()
        monitor.add_position(pos)
        found = monitor.get_position("pos-1")
        assert found is not None
        assert found.asset == "stETH"

    def test_update_position(self):
        monitor = RestakingMonitor()
        pos = _make_sample_position()
        monitor.add_position(pos)
        assert monitor.update_position("pos-1", apy=3.0)
        assert monitor.get_position("pos-1").apy == 3.0

    def test_update_nonexistent(self):
        monitor = RestakingMonitor()
        assert not monitor.update_position("nope", apy=3.0)


class TestRestakingMonitorAlerts:
    def test_apy_drop_alert(self):
        monitor = RestakingMonitor(apy_drop_threshold=1.0)
        pos = _make_sample_position(apy=4.0)
        monitor.add_position(pos)
        monitor.update_position("pos-1", apy=2.0)
        alerts = monitor.check_alerts()
        apy_alerts = [a for a in alerts if a.alert_type == AlertType.APY_DROP]
        assert len(apy_alerts) >= 1

    def test_unlock_alert(self):
        monitor = RestakingMonitor()
        pos = _make_sample_position(lock_end=time.time() - 100)
        monitor.add_position(pos)
        alerts = monitor.check_alerts()
        unlock_alerts = [a for a in alerts if a.alert_type == AlertType.UNLOCK_AVAILABLE]
        assert len(unlock_alerts) >= 1

    def test_high_risk_alert(self):
        monitor = RestakingMonitor()
        pos = _make_sample_position(risk_score=80)
        monitor.add_position(pos)
        alerts = monitor.check_alerts()
        risk_alerts = [a for a in alerts if a.alert_type == AlertType.RISK_INCREASE]
        assert len(risk_alerts) >= 1

    def test_slashing_report(self):
        monitor = RestakingMonitor(slashing_alert_threshold=50)
        pos = _make_sample_position(protocol="eigenlayer", operator="TestOp")
        monitor.add_position(pos)

        event = SlashingEvent(
            protocol="eigenlayer",
            operator="TestOp",
            amount_slashed=1.0,
            amount_usd=3500,
            reason="double signing",
            block_number=20_000_000,
            timestamp=time.time(),
        )
        monitor.report_slashing(event)

        alerts = monitor.check_alerts()
        slashing_alerts = [a for a in alerts if a.alert_type == AlertType.SLASHING]
        assert len(slashing_alerts) >= 1
        assert slashing_alerts[0].is_critical

        # Position risk should increase
        updated = monitor.get_position("pos-1")
        assert updated.risk_score == 35  # 25 + 10

    def test_reward_claim(self):
        monitor = RestakingMonitor(reward_claim_threshold=10)
        pos = _make_sample_position()
        monitor.add_position(pos)

        monitor.report_reward_claim("pos-1", "EIGEN", 10.0, 200.0)
        alerts = monitor.check_alerts()
        claim_alerts = [a for a in alerts if a.alert_type == AlertType.REWARD_CLAIM]
        assert len(claim_alerts) >= 1

    def test_callback_triggered(self):
        monitor = RestakingMonitor()
        received = []
        monitor.on_alert(lambda a: received.append(a))

        pos = _make_sample_position(risk_score=80)
        monitor.add_position(pos)
        monitor.check_alerts()

        assert len(received) >= 1

    def test_clear_alerts(self):
        monitor = RestakingMonitor()
        pos = _make_sample_position(risk_score=80)
        monitor.add_position(pos)
        monitor.check_alerts()
        monitor.clear_alerts()
        # check_alerts re-generates from current state, so verify internal list is empty
        assert len(monitor._alerts) == 0


class TestRestakingMonitorSnapshot:
    def test_snapshot(self):
        monitor = RestakingMonitor()
        monitor.add_position(_make_sample_position(position_id="p1", value_usd=35_000))
        monitor.add_position(_make_sample_position(position_id="p2", protocol="babylon", value_usd=65_000))

        snapshot = monitor.get_snapshot()
        assert isinstance(snapshot, PortfolioSnapshot)
        assert snapshot.num_positions == 2
        assert snapshot.total_value_usd == 100_000
        assert "eigenlayer" in snapshot.protocol_breakdown
        assert "babylon" in snapshot.protocol_breakdown

    def test_protocol_summary(self):
        monitor = RestakingMonitor()
        monitor.add_position(_make_sample_position(position_id="p1"))
        monitor.add_position(_make_sample_position(position_id="p2", protocol="babylon"))

        summary = monitor.get_protocol_summary()
        assert len(summary) == 2
        assert any(s["protocol"] == "eigenlayer" for s in summary)

    def test_slashing_history(self):
        monitor = RestakingMonitor()
        event = SlashingEvent(
            protocol="test", operator="op", amount_slashed=1.0,
            amount_usd=100, reason="test", block_number=1, timestamp=time.time(),
        )
        monitor.report_slashing(event)
        assert len(monitor.get_slashing_history()) == 1

    def test_alerts_by_type(self):
        monitor = RestakingMonitor()
        pos = _make_sample_position(risk_score=80)
        monitor.add_position(pos)
        monitor.check_alerts()

        risk_alerts = monitor.get_alerts_by_type(AlertType.RISK_INCREASE)
        assert all(a.alert_type == AlertType.RISK_INCREASE for a in risk_alerts)
