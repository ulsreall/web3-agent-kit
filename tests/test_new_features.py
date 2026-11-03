"""Tests for Gas Optimizer, Wallet Watcher, and Approval Manager."""

from unittest.mock import MagicMock, patch

import pytest

from web3_agent_kit.chains.chain import Chain, ChainManager
from web3_agent_kit.gas.optimizer import GasOptimizer, GasPriority
from web3_agent_kit.wallet.approval import (
    ApprovalManager,
    ApprovalRisk,
    RevokeResult,
    TokenApproval,
)
from web3_agent_kit.wallet.wallet import Wallet, WalletConfig
from web3_agent_kit.wallet.watcher import AlertSeverity, AlertType, WalletAlert, WalletWatcher


@pytest.fixture
def wallet():
    from eth_account import Account

    acct = Account.create()
    return Wallet(
        config=WalletConfig(private_key=acct.key.hex()),
        chain_manager=ChainManager(chains=[Chain.ETHEREUM, Chain.BASE]),
    )


@pytest.fixture
def chain_manager():
    return ChainManager(chains=[Chain.ETHEREUM, Chain.BASE])


@pytest.fixture
def mock_gas_price():
    """Mock gas price to avoid real network calls."""
    with patch.object(GasOptimizer, "_get_base_fee", return_value=20.0):
        yield


# === Gas Optimizer ===


class TestGasOptimizer:
    def test_init(self, wallet, chain_manager):
        opt = GasOptimizer(wallet, chain_manager)
        assert opt.eth_price_usd == 3500.0

    def test_gas_limit_suggestions(self, wallet, chain_manager):
        opt = GasOptimizer(wallet, chain_manager)
        assert opt.suggest_gas_limit("transfer") == 21000
        assert opt.suggest_gas_limit("swap") == 180000
        assert opt.suggest_gas_limit("bridge") == 300000
        assert opt.suggest_gas_limit("unknown") == 21000

    def test_gas_level(self):
        assert GasOptimizer._gas_level(5) == "🟢 Low"
        assert GasOptimizer._gas_level(20) == "🟡 Medium"
        assert GasOptimizer._gas_level(50) == "🟠 High"
        assert GasOptimizer._gas_level(100) == "🔴 Very High"

    def test_estimate_transfer(self, wallet, chain_manager, mock_gas_price):
        opt = GasOptimizer(wallet, chain_manager)
        est = opt.estimate(to="0x123", value=0.1, chain=Chain.ETHEREUM)
        assert est.gas_limit == 21000
        assert est.priority == GasPriority.MEDIUM
        assert est.total_cost_eth > 0

    def test_estimate_swap(self, wallet, chain_manager, mock_gas_price):
        opt = GasOptimizer(wallet, chain_manager)
        est = opt.estimate(to="0x123", chain=Chain.ETHEREUM, operation="swap")
        assert est.gas_limit == 180000

    def test_estimate_priority_levels(self, wallet, chain_manager, mock_gas_price):
        opt = GasOptimizer(wallet, chain_manager)
        low = opt.estimate(to="0x123", chain=Chain.ETHEREUM, priority=GasPriority.LOW)
        high = opt.estimate(to="0x123", chain=Chain.ETHEREUM, priority=GasPriority.HIGH)
        assert low.priority_fee < high.priority_fee

    def test_get_gas_price(self, wallet, chain_manager, mock_gas_price):
        opt = GasOptimizer(wallet, chain_manager)
        price = opt.get_gas_price(Chain.ETHEREUM)
        assert "gwei" in price
        assert "level" in price

    def test_update_eth_price(self, wallet, chain_manager):
        opt = GasOptimizer(wallet, chain_manager)
        opt.update_eth_price(4000)
        assert opt.eth_price_usd == 4000

    def test_recommend_timing_urgent(self, wallet, chain_manager, mock_gas_price):
        opt = GasOptimizer(wallet, chain_manager)
        rec = opt.recommend_timing(Chain.ETHEREUM, GasPriority.URGENT)
        assert rec.recommended_action == "execute_now"

    def test_batch_estimate(self, wallet, chain_manager, mock_gas_price):
        opt = GasOptimizer(wallet, chain_manager)
        txs = [
            {"to": "0xA", "value": 0.01},
            {"to": "0xB", "value": 0.02},
        ]
        batch = opt.batch_estimate(txs, Chain.ETHEREUM)
        assert batch["count"] == 2
        assert batch["total_cost_eth"] > 0

    def test_batch_execute(self, wallet, chain_manager, mock_gas_price):
        opt = GasOptimizer(wallet, chain_manager)
        txs = [{"to": "0xA", "value": 0.01}, {"to": "0xB", "value": 0.02}]
        result = opt.batch_execute(txs, Chain.ETHEREUM)
        assert result.tx_count == 2
        assert result.status == "not_submitted"

    def test_priority_fee_defaults(self):
        assert GasPriority.LOW.value == "low"
        assert GasPriority.URGENT.value == "urgent"


# === Wallet Watcher ===


@pytest.fixture
def watcher(chain_manager, tmp_path):
    return WalletWatcher(chain_manager, storage_path=str(tmp_path / "watcher.json"))


class TestWalletWatcher:
    def test_add_wallet(self, watcher):
        w = watcher.add_wallet("0x123", "test", Chain.ETHEREUM)
        assert w.label == "test"
        assert len(watcher.wallets) == 1

    def test_add_wallet_with_tags(self, watcher):
        w = watcher.add_wallet("0x123", "test", Chain.ETHEREUM, tags=["whale", "defi"])
        assert "whale" in w.tags

    def test_remove_wallet(self, watcher):
        watcher.add_wallet("0x123", "test", Chain.ETHEREUM)
        assert watcher.remove_wallet("0x123", Chain.ETHEREUM) is True
        assert len(watcher.wallets) == 0

    def test_remove_nonexistent(self, watcher):
        assert watcher.remove_wallet("0x123", Chain.ETHEREUM) is False

    def test_list_wallets(self, watcher):
        watcher.add_wallet("0xA", "w1", Chain.ETHEREUM)
        watcher.add_wallet("0xB", "w2", Chain.ETHEREUM)
        watcher.add_wallet("0xC", "w3", Chain.BASE)
        assert len(watcher.list_wallets()) == 3
        assert len(watcher.list_wallets(chain=Chain.ETHEREUM)) == 2
        assert len(watcher.list_wallets(chain=Chain.BASE)) == 1

    def test_list_by_tag(self, watcher):
        watcher.add_wallet("0xA", "w1", Chain.ETHEREUM, tags=["whale"])
        watcher.add_wallet("0xB", "w2", Chain.ETHEREUM, tags=["retail"])
        assert len(watcher.list_wallets(tag="whale")) == 1

    def test_alert_callback(self, watcher):
        alerts = []
        watcher.on_alert(lambda a: alerts.append(a))
        assert len(watcher._callbacks) == 1

    def test_alerts_empty(self, watcher):
        assert len(watcher.get_alerts()) == 0

    def test_acknowledge_alert(self, watcher):
        watcher.alerts.append(
            WalletAlert(
                wallet_address="0x123",
                wallet_label="test",
                chain=Chain.ETHEREUM,
                alert_type=AlertType.LARGE_TRANSFER,
                severity=AlertSeverity.HIGH,
                message="test alert",
            )
        )
        assert watcher.acknowledge_alert(0) is True
        assert watcher.alerts[0].acknowledged is True

    def test_acknowledge_all(self, watcher):
        watcher.alerts.append(
            WalletAlert(
                wallet_address="0x123",
                wallet_label="test",
                chain=Chain.ETHEREUM,
                alert_type=AlertType.BALANCE_CHANGE,
                severity=AlertSeverity.LOW,
                message="a1",
            )
        )
        watcher.alerts.append(
            WalletAlert(
                wallet_address="0x456",
                wallet_label="test2",
                chain=Chain.ETHEREUM,
                alert_type=AlertType.BALANCE_CHANGE,
                severity=AlertSeverity.LOW,
                message="a2",
            )
        )
        count = watcher.acknowledge_all()
        assert count == 2

    def test_summary(self, watcher):
        watcher.add_wallet("0xA", "w1", Chain.ETHEREUM, tags=["whale"])
        summary = watcher.get_summary()
        assert summary["watched_wallets"] == 1
        assert len(summary["wallets"]) == 1

    def test_wallet_persistence(self, watcher, tmp_path):
        watcher.add_wallet("0x123", "test", Chain.ETHEREUM)
        w2 = WalletWatcher(
            ChainManager(chains=[Chain.ETHEREUM, Chain.BASE]), storage_path=watcher.STORAGE_PATH
        )
        assert len(w2.wallets) == 1


# === Approval Manager ===


class TestApprovalManager:
    def test_known_spender(self, wallet, chain_manager):
        mgr = ApprovalManager(wallet, chain_manager)
        is_known, label = mgr.is_known_spender("0x7a250d5630b4cf539739df2c5dacb4c659f2488d")
        assert is_known is True
        assert "Uniswap" in label

    def test_unknown_spender(self, wallet, chain_manager):
        mgr = ApprovalManager(wallet, chain_manager)
        is_known, label = mgr.is_known_spender("0xdeadbeef")
        assert is_known is False
        assert label == "Unknown"

    def test_assess_risk_safe(self, wallet, chain_manager):
        mgr = ApprovalManager(wallet, chain_manager)
        assert mgr._assess_risk(100, True) == ApprovalRisk.SAFE

    def test_assess_risk_moderate(self, wallet, chain_manager):
        mgr = ApprovalManager(wallet, chain_manager)
        assert mgr._assess_risk(5000, True) == ApprovalRisk.MODERATE

    def test_assess_risk_high(self, wallet, chain_manager):
        mgr = ApprovalManager(wallet, chain_manager)
        assert mgr._assess_risk(float("inf"), True) == ApprovalRisk.HIGH

    def test_assess_risk_critical(self, wallet, chain_manager):
        mgr = ApprovalManager(wallet, chain_manager)
        assert mgr._assess_risk(float("inf"), False) == ApprovalRisk.CRITICAL

    def test_get_risky(self, wallet, chain_manager):
        mgr = ApprovalManager(wallet, chain_manager)
        mgr.approvals = [
            TokenApproval(
                "0xA",
                "USDC",
                "0xB",
                "Uniswap",
                float("inf"),
                2**256 - 1,
                Chain.ETHEREUM,
                ApprovalRisk.HIGH,
            ),
            TokenApproval(
                "0xC", "DAI", "0xD", "Unknown", 100, 100e18, Chain.ETHEREUM, ApprovalRisk.SAFE
            ),
        ]
        risky = mgr.get_risky(ApprovalRisk.HIGH)
        assert len(risky) == 1

    def test_get_unlimited(self, wallet, chain_manager):
        mgr = ApprovalManager(wallet, chain_manager)
        mgr.approvals = [
            TokenApproval(
                "0xA",
                "USDC",
                "0xB",
                "Uniswap",
                float("inf"),
                2**256 - 1,
                Chain.ETHEREUM,
                ApprovalRisk.HIGH,
            ),
            TokenApproval(
                "0xC", "DAI", "0xD", "Aave", 1000, 1000e18, Chain.ETHEREUM, ApprovalRisk.MODERATE
            ),
        ]
        unlimited = mgr.get_unlimited()
        assert len(unlimited) == 1

    def test_summary(self, wallet, chain_manager):
        mgr = ApprovalManager(wallet, chain_manager)
        mgr.approvals = [
            TokenApproval(
                "0xA",
                "USDC",
                "0xB",
                "Uniswap",
                float("inf"),
                2**256 - 1,
                Chain.ETHEREUM,
                ApprovalRisk.HIGH,
            ),
        ]
        summary = mgr.get_summary()
        assert summary["total_approvals"] == 1
        assert summary["unlimited"] == 1

    def test_revoke_result_success(self):
        result = RevokeResult("0xA", "0xB", tx_hash="0x123", success=True)
        assert result.success is True

    def test_revoke_result_failure(self):
        result = RevokeResult("0xA", "0xB", success=False, error="insufficient gas")
        assert result.success is False
        assert "gas" in result.error

    def test_common_tokens_ethereum(self, wallet, chain_manager):
        mgr = ApprovalManager(wallet, chain_manager)
        tokens = mgr._get_common_tokens(Chain.ETHEREUM)
        assert len(tokens) >= 5
        symbols = [s for _, s in tokens]
        assert "WETH" in symbols
        assert "USDC" in symbols

    def test_common_tokens_base(self, wallet, chain_manager):
        mgr = ApprovalManager(wallet, chain_manager)
        tokens = mgr._get_common_tokens(Chain.BASE)
        assert len(tokens) >= 2

    def test_scan_checks_full_history_and_uses_token_decimals(self, wallet, chain_manager):
        manager = ApprovalManager(wallet, chain_manager)
        w3 = MagicMock()
        w3.to_checksum_address.side_effect = lambda address: address
        spender = "0x" + "12" * 20
        cleared_spender = "0x" + "34" * 20
        owner_topic = "0" * 24 + wallet.address[2:].lower()

        def approval_log(log_spender, amount):
            return {
                "topics": [
                    bytes.fromhex("00" * 32),
                    bytes.fromhex(owner_topic),
                    bytes.fromhex("00" * 12 + log_spender[2:]),
                ],
                "data": amount.to_bytes(32, "big"),
            }

        w3.eth.contract.return_value.functions.decimals.return_value.call.return_value = 6
        w3.eth.block_number = 2000
        w3.eth.get_logs.side_effect = [
            [
                approval_log(spender, 1_500_000),
                approval_log(cleared_spender, 9_000_000),
                approval_log(cleared_spender, 0),
            ],
            [],
        ]

        with patch.object(chain_manager, "get_web3", return_value=w3):
            approvals = manager._check_token_approvals("0x" + "ab" * 20, "USDC", Chain.ETHEREUM)

        assert len(approvals) == 1
        assert approvals[0].spender.lower() == spender.lower()
        assert approvals[0].amount == 1.5
        assert w3.eth.get_logs.call_count == 2
        assert w3.eth.get_logs.call_args_list[0].args[0]["fromBlock"] == 0
        assert w3.eth.get_logs.call_args_list[0].args[0]["toBlock"] == 1999
        assert w3.eth.get_logs.call_args_list[1].args[0]["fromBlock"] == 2000
        assert w3.eth.get_logs.call_args_list[1].args[0]["toBlock"] == 2000

    def test_scan_rpc_failure_is_reported(self, wallet, chain_manager):
        manager = ApprovalManager(wallet, chain_manager)
        with (
            patch.object(chain_manager, "get_web3", side_effect=RuntimeError("rpc unavailable")),
            pytest.raises(RuntimeError, match="Failed to scan approvals"),
        ):
            manager._check_token_approvals("0xtoken", "TKN", Chain.ETHEREUM)

    def test_revoke_only_reports_success_after_wallet_send(self, wallet, chain_manager):
        manager = ApprovalManager(wallet, chain_manager)
        with (
            patch.object(manager, "_build_revoke_tx", return_value={"to": "0xtoken"}),
            patch.object(wallet, "send_transaction", return_value="0xsent") as send,
        ):
            result = manager.revoke("0xtoken", "0xspender", Chain.ETHEREUM)

        assert result.success is True
        assert result.tx_hash == "0xsent"
        send.assert_called_once()

    def test_revoke_send_failure_is_not_reported_as_success(self, wallet, chain_manager):
        manager = ApprovalManager(wallet, chain_manager)
        with (
            patch.object(manager, "_build_revoke_tx", return_value={"to": "0xtoken"}),
            patch.object(wallet, "send_transaction", side_effect=ValueError("not authorized")),
        ):
            result = manager.revoke("0xtoken", "0xspender", Chain.ETHEREUM)

        assert result.success is False
        assert result.tx_hash is None
        assert "not authorized" in result.error

    def test_approval_risk_levels(self):
        assert ApprovalRisk.SAFE.value == "safe"
        assert ApprovalRisk.CRITICAL.value == "critical"
