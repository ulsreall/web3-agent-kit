"""Tests for Wallet Watcher module."""

import json
import os
import tempfile
import time

import pytest
from unittest.mock import MagicMock, patch

from src.wallet.watcher import (
    WalletWatcher,
    WatchedWallet,
    WalletAlert,
    BalanceSnapshot,
    AlertType,
    AlertSeverity,
)
from src.chains.chain import Chain


class TestAlertType:
    def test_values(self):
        assert AlertType.LARGE_TRANSFER.value == "large_transfer"
        assert AlertType.LARGE_SWAP.value == "large_swap"
        assert AlertType.NEW_TOKEN.value == "new_token"
        assert AlertType.APPROVAL.value == "approval"
        assert AlertType.CONTRACT_INTERACTION.value == "contract_interaction"
        assert AlertType.BALANCE_CHANGE.value == "balance_change"


class TestAlertSeverity:
    def test_values(self):
        assert AlertSeverity.LOW.value == "low"
        assert AlertSeverity.MEDIUM.value == "medium"
        assert AlertSeverity.HIGH.value == "high"
        assert AlertSeverity.CRITICAL.value == "critical"


class TestWatchedWallet:
    def test_defaults(self):
        w = WatchedWallet(address="0xabc", label="test", chain=Chain.ETHEREUM)
        assert w.alert_threshold_usd == 10000
        assert w.watch_balance is True
        assert w.watch_transfers is True
        assert w.watch_approvals is False
        assert w.is_active is True
        assert w.last_checked == 0
        assert w.tags == []

    def test_custom_values(self):
        w = WatchedWallet(
            address="0xabc",
            label="whale-01",
            chain=Chain.BASE,
            tags=["dex-trader"],
            alert_threshold_usd=50000,
            watch_balance=False,
            watch_transfers=True,
            watch_approvals=True,
            is_active=True,
        )
        assert w.label == "whale-01"
        assert w.chain == Chain.BASE
        assert "dex-trader" in w.tags
        assert w.alert_threshold_usd == 50000
        assert w.watch_balance is False
        assert w.watch_approvals is True


class TestWalletAlert:
    def test_creation(self):
        alert = WalletAlert(
            wallet_address="0xabc",
            wallet_label="test",
            chain=Chain.ETHEREUM,
            alert_type=AlertType.BALANCE_CHANGE,
            severity=AlertSeverity.HIGH,
            message="received 10 ETH",
        )
        assert alert.wallet_address == "0xabc"
        assert alert.alert_type == AlertType.BALANCE_CHANGE
        assert alert.severity == AlertSeverity.HIGH
        assert alert.acknowledged is False
        assert alert.timestamp > 0

    def test_default_details_empty(self):
        alert = WalletAlert(
            wallet_address="0xabc",
            wallet_label="test",
            chain=Chain.ETHEREUM,
            alert_type=AlertType.LARGE_TRANSFER,
            severity=AlertSeverity.LOW,
            message="test",
        )
        assert alert.details == {}


class TestBalanceSnapshot:
    def test_creation(self):
        snap = BalanceSnapshot(
            address="0xabc",
            chain=Chain.ETHEREUM,
            native_balance=1.5,
            token_balances={"USDC": 1000},
            total_value_usd=6250.0,
            timestamp=1234567890,
        )
        assert snap.address == "0xabc"
        assert snap.native_balance == 1.5
        assert snap.total_value_usd == 6250.0
        assert snap.token_balances["USDC"] == 1000


class TestWalletWatcher:
    @pytest.fixture
    def temp_storage(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("{}")
            yield f.name
        os.unlink(f.name)

    @pytest.fixture
    def chain_manager(self):
        cm = MagicMock()
        w3 = MagicMock()
        w3.eth.get_balance.return_value = 1000000000000000000  # 1 ETH
        w3.from_wei.return_value = 1.0
        w3.eth.chain_id = 1
        cm.get_web3.return_value = w3
        return cm

    @pytest.fixture
    def watcher(self, chain_manager, temp_storage):
        return WalletWatcher(chain_manager=chain_manager, storage_path=temp_storage)

    def test_init(self, watcher, temp_storage):
        assert watcher.STORAGE_PATH == temp_storage
        assert watcher.wallets == {}
        assert watcher.alerts == []
        assert watcher.snapshots == {}
        assert watcher._callbacks == []

    def test_add_wallet(self, watcher):
        w = watcher.add_wallet(
            address="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            label="vitalik.eth",
            chain=Chain.ETHEREUM,
            tags=["founder"],
            alert_threshold_usd=100000,
        )
        assert w.label == "vitalik.eth"
        assert w.chain == Chain.ETHEREUM
        assert "founder" in w.tags
        assert w.alert_threshold_usd == 100000

        key = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045:ethereum"
        assert key in watcher.wallets

    def test_add_wallet_defaults(self, watcher):
        w = watcher.add_wallet(
            address="0x1234",
            label="whale-01",
            chain=Chain.BASE,
        )
        assert w.alert_threshold_usd == 10000
        assert w.watch_balance is True
        assert w.watch_transfers is True
        assert w.watch_approvals is False

    def test_remove_wallet(self, watcher):
        watcher.add_wallet("0xabc", "test", Chain.ETHEREUM)
        assert len(watcher.wallets) == 1

        result = watcher.remove_wallet("0xabc", Chain.ETHEREUM)
        assert result is True
        assert len(watcher.wallets) == 0

    def test_remove_nonexistent(self, watcher):
        result = watcher.remove_wallet("0xnonexistent", Chain.ETHEREUM)
        assert result is False

    def test_list_wallets(self, watcher):
        watcher.add_wallet("0xabc", "w1", Chain.ETHEREUM)
        watcher.add_wallet("0xdef", "w2", Chain.BASE)
        watcher.add_wallet("0xghi", "w3", Chain.ETHEREUM, tags=["test"])

        all_w = watcher.list_wallets()
        assert len(all_w) == 3

        eth_w = watcher.list_wallets(chain=Chain.ETHEREUM)
        assert len(eth_w) == 2

        tagged = watcher.list_wallets(tag="test")
        assert len(tagged) == 1

    def test_list_wallets_inactive_filter(self, watcher):
        watcher.add_wallet("0xabc", "w1", Chain.ETHEREUM)
        key = "0xabc:ethereum"
        watcher.wallets[key].is_active = False

        active = watcher.list_wallets(active_only=True)
        assert len(active) == 0

        all_w = watcher.list_wallets(active_only=False)
        assert len(all_w) == 1

    def test_check_wallet_no_wallet(self, watcher):
        alerts = watcher.check_wallet("0xnonexistent", Chain.ETHEREUM)
        assert alerts == []

    def test_check_wallet_inactive(self, watcher):
        watcher.add_wallet("0xabc", "test", Chain.ETHEREUM)
        key = "0xabc:ethereum"
        watcher.wallets[key].is_active = False

        alerts = watcher.check_wallet("0xabc", Chain.ETHEREUM)
        assert alerts == []

    def test_check_wallet_balance_first_check(self, watcher, chain_manager):
        """First check should take a snapshot but not alert."""
        watcher.add_wallet("0xabc", "test", Chain.ETHEREUM, watch_transfers=False)

        alerts = watcher.check_wallet("0xabc", Chain.ETHEREUM)
        assert alerts == []
        # Should have stored a snapshot
        assert "0xabc" in watcher.snapshots

    def test_check_wallet_balance_changed(self, watcher, chain_manager):
        """Second check with different balance should alert."""
        watcher.add_wallet("0xabc", "test", Chain.ETHEREUM, watch_transfers=False)

        # First check - no alert, records baseline
        watcher.check_wallet("0xabc", Chain.ETHEREUM)

        # Change balance
        chain_manager.get_web3.return_value.from_wei.return_value = 2.0
        chain_manager.get_web3.return_value.eth.get_balance.return_value = 2000000000000000000

        # Second check - should alert
        alerts = watcher.check_wallet("0xabc", Chain.ETHEREUM)
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.BALANCE_CHANGE
        assert "received" in alerts[0].message
        assert "1.0000" in alerts[0].message  # diff = 2.0 - 1.0

    def test_check_wallet_balance_decrease(self, watcher, chain_manager):
        """Test alert on balance decrease."""
        watcher.add_wallet("0xabc", "test", Chain.ETHEREUM, watch_transfers=False)

        # First check - baseline at 1.0
        watcher.check_wallet("0xabc", Chain.ETHEREUM)

        # Balance decreases
        chain_manager.get_web3.return_value.from_wei.return_value = 0.5
        chain_manager.get_web3.return_value.eth.get_balance.return_value = 500000000000000000

        alerts = watcher.check_wallet("0xabc", Chain.ETHEREUM)
        assert len(alerts) == 1
        assert "sent" in alerts[0].message
        assert "0.5000" in alerts[0].message

    def test_check_wallet_balance_small_change(self, watcher, chain_manager):
        """Very small balance changes (<0.01 ETH) should not alert."""
        watcher.add_wallet("0xabc", "test", Chain.ETHEREUM, watch_transfers=False)

        watcher.check_wallet("0xabc", Chain.ETHEREUM)

        # Tiny change - 0.001 ETH diff which is < 0.01 threshold
        chain_manager.get_web3.return_value.from_wei.return_value = 1.001
        chain_manager.get_web3.return_value.eth.get_balance.return_value = 1001000000000000000

        alerts = watcher.check_wallet("0xabc", Chain.ETHEREUM)
        assert len(alerts) == 0  # 0.001 < 0.01, so no alert

    def test_check_wallet_balance_severity_low(self, watcher, chain_manager):
        """Balance change of 0.5 ETH should be LOW severity."""
        watcher.add_wallet("0xabc", "test", Chain.ETHEREUM, watch_transfers=False)
        watcher.check_wallet("0xabc", Chain.ETHEREUM)

        chain_manager.get_web3.return_value.from_wei.return_value = 1.5
        chain_manager.get_web3.return_value.eth.get_balance.return_value = 1500000000000000000

        alerts = watcher.check_wallet("0xabc", Chain.ETHEREUM)
        assert alerts[0].severity == AlertSeverity.LOW

    def test_check_wallet_balance_severity_medium(self, watcher, chain_manager):
        """Balance change of 5 ETH should be MEDIUM severity."""
        watcher.add_wallet("0xabc", "test", Chain.ETHEREUM, watch_transfers=False)
        watcher.check_wallet("0xabc", Chain.ETHEREUM)

        chain_manager.get_web3.return_value.from_wei.return_value = 6.0
        chain_manager.get_web3.return_value.eth.get_balance.return_value = 6000000000000000000

        alerts = watcher.check_wallet("0xabc", Chain.ETHEREUM)
        assert alerts[0].severity == AlertSeverity.MEDIUM

    def test_check_wallet_balance_severity_high(self, watcher, chain_manager):
        """Balance change of 50 ETH should be HIGH severity."""
        watcher.add_wallet("0xabc", "test", Chain.ETHEREUM, watch_transfers=False)
        watcher.check_wallet("0xabc", Chain.ETHEREUM)

        chain_manager.get_web3.return_value.from_wei.return_value = 51.0
        chain_manager.get_web3.return_value.eth.get_balance.return_value = 51000000000000000000

        alerts = watcher.check_wallet("0xabc", Chain.ETHEREUM)
        assert alerts[0].severity == AlertSeverity.HIGH

    def test_check_wallet_balance_severity_critical(self, watcher, chain_manager):
        """Balance change of 500 ETH should be CRITICAL severity."""
        watcher.add_wallet("0xabc", "test", Chain.ETHEREUM, watch_transfers=False)
        watcher.check_wallet("0xabc", Chain.ETHEREUM)

        chain_manager.get_web3.return_value.from_wei.return_value = 501.0
        chain_manager.get_web3.return_value.eth.get_balance.return_value = 501000000000000000000

        alerts = watcher.check_wallet("0xabc", Chain.ETHEREUM)
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_check_all(self, watcher, chain_manager):
        watcher.add_wallet("0xabc", "w1", Chain.ETHEREUM, watch_transfers=False)
        watcher.add_wallet("0xdef", "w2", Chain.BASE, watch_transfers=False)

        # First check_all - baseline snapshots
        alerts1 = watcher.check_all()
        assert len(alerts1) == 0

        # Second check_all - balance changed
        chain_manager.get_web3.return_value.from_wei.return_value = 2.0
        chain_manager.get_web3.return_value.eth.get_balance.return_value = 2000000000000000000

        alerts2 = watcher.check_all()
        assert len(alerts2) == 2  # Both wallets detected change

    def test_check_all_skips_inactive(self, watcher):
        watcher.add_wallet("0xabc", "w1", Chain.ETHEREUM)
        key = "0xabc:ethereum"
        watcher.wallets[key].is_active = False

        alerts = watcher.check_all()
        assert len(alerts) == 0

    def test_snapshot(self, watcher, chain_manager):
        snap = watcher.snapshot("0xabc", Chain.ETHEREUM)
        assert snap is not None
        assert snap.address == "0xabc"
        assert snap.native_balance == 1.0
        assert snap.chain == Chain.ETHEREUM
        assert "0xabc" in watcher.snapshots

    def test_snapshot_error(self, watcher, chain_manager):
        chain_manager.get_web3.side_effect = Exception("RPC error")
        snap = watcher.snapshot("0xabc", Chain.ETHEREUM)
        assert snap is None

    def test_snapshot_all(self, watcher, chain_manager):
        watcher.add_wallet("0xabc", "w1", Chain.ETHEREUM)
        watcher.add_wallet("0xdef", "w2", Chain.BASE)

        snaps = watcher.snapshot_all()
        assert len(snaps) == 2

    def test_snapshot_all_skips_inactive(self, watcher):
        watcher.add_wallet("0xabc", "w1", Chain.ETHEREUM)
        key = "0xabc:ethereum"
        watcher.wallets[key].is_active = False

        snaps = watcher.snapshot_all()
        assert len(snaps) == 0

    def test_get_alerts(self, watcher):
        # Manually add alerts
        a1 = WalletAlert("0xabc", "test", Chain.ETHEREUM, AlertType.BALANCE_CHANGE, AlertSeverity.LOW, "msg1")
        a2 = WalletAlert("0xdef", "test2", Chain.ETHEREUM, AlertType.LARGE_TRANSFER, AlertSeverity.HIGH, "msg2")
        a2.acknowledged = True
        watcher.alerts = [a1, a2]

        all_alerts = watcher.get_alerts(unacknowledged_only=False)
        assert len(all_alerts) == 2

        unacked = watcher.get_alerts(unacknowledged_only=True)
        assert len(unacked) == 1
        assert unacked[0].wallet_address == "0xabc"

    def test_get_alerts_filter_by_severity(self, watcher):
        a1 = WalletAlert("0xabc", "test", Chain.ETHEREUM, AlertType.BALANCE_CHANGE, AlertSeverity.LOW, "msg1")
        a2 = WalletAlert("0xdef", "test2", Chain.ETHEREUM, AlertType.LARGE_TRANSFER, AlertSeverity.HIGH, "msg2")
        watcher.alerts = [a1, a2]

        high_alerts = watcher.get_alerts(severity=AlertSeverity.HIGH, unacknowledged_only=False)
        assert len(high_alerts) == 1
        assert high_alerts[0].severity == AlertSeverity.HIGH

    def test_get_alerts_filter_by_label(self, watcher):
        a1 = WalletAlert("0xabc", "vitalik", Chain.ETHEREUM, AlertType.BALANCE_CHANGE, AlertSeverity.LOW, "msg1")
        a2 = WalletAlert("0xdef", "whale", Chain.ETHEREUM, AlertType.LARGE_TRANSFER, AlertSeverity.HIGH, "msg2")
        watcher.alerts = [a1, a2]

        vitalik_alerts = watcher.get_alerts(wallet_label="vitalik", unacknowledged_only=False)
        assert len(vitalik_alerts) == 1

    def test_get_alerts_limit(self, watcher):
        for i in range(10):
            watcher.alerts.append(WalletAlert(
                f"0x{i}", f"test{i}", Chain.ETHEREUM, AlertType.BALANCE_CHANGE, AlertSeverity.LOW, f"msg{i}",
            ))
        limited = watcher.get_alerts(limit=3, unacknowledged_only=False)
        assert len(limited) == 3

    def test_acknowledge_alert(self, watcher):
        alert = WalletAlert("0xabc", "test", Chain.ETHEREUM, AlertType.BALANCE_CHANGE, AlertSeverity.LOW, "msg")
        watcher.alerts = [alert]
        assert watcher.alerts[0].acknowledged is False

        result = watcher.acknowledge_alert(0)
        assert result is True
        assert watcher.alerts[0].acknowledged is True

    def test_acknowledge_alert_invalid_index(self, watcher):
        result = watcher.acknowledge_alert(0)
        assert result is False

        result = watcher.acknowledge_alert(-1)
        assert result is False

    def test_acknowledge_all(self, watcher):
        a1 = WalletAlert("0xabc", "test", Chain.ETHEREUM, AlertType.BALANCE_CHANGE, AlertSeverity.LOW, "msg1")
        a2 = WalletAlert("0xdef", "test2", Chain.ETHEREUM, AlertType.LARGE_TRANSFER, AlertSeverity.HIGH, "msg2")
        a2.acknowledged = True
        watcher.alerts = [a1, a2]

        count = watcher.acknowledge_all()
        assert count == 1
        assert watcher.alerts[0].acknowledged is True
        assert watcher.alerts[1].acknowledged is True

    def test_on_alert_callback(self, watcher):
        callback = MagicMock()
        watcher.on_alert(callback)

        watcher.wallets["0xabc:ethereum"] = WatchedWallet(
            address="0xabc", label="test", chain=Chain.ETHEREUM, watch_transfers=False,
        )
        watcher.snapshots["0xabc"] = [BalanceSnapshot("0xabc", Chain.ETHEREUM, 1.0, {}, 3500, 0)]
        watcher._check_balance(watcher.wallets["0xabc:ethereum"])

        # Trigger via check_wallet
        watcher.wallets["0xabc:ethereum"].last_checked = 0
        chain_manager = watcher.chain_manager
        chain_manager.get_web3.return_value.from_wei.return_value = 2.0

        alerts = watcher.check_wallet("0xabc", Chain.ETHEREUM)
        callback.assert_called()

    def test_callback_exception_handled(self, watcher):
        """Exception in callback should not propagate."""
        def bad_cb(alert):
            raise RuntimeError("callback error")

        watcher.on_alert(bad_cb)
        watcher.on_alert(MagicMock())

        watcher.wallets["0xabc:ethereum"] = WatchedWallet(
            address="0xabc", label="test", chain=Chain.ETHEREUM, watch_transfers=False,
        )
        watcher.snapshots["0xabc"] = [BalanceSnapshot("0xabc", Chain.ETHEREUM, 1.0, {}, 3500, 0)]

        chain_manager = watcher.chain_manager
        chain_manager.get_web3.return_value.from_wei.return_value = 2.0

        alerts = watcher.check_wallet("0xabc", Chain.ETHEREUM)
        assert len(alerts) == 1  # Should still get alerts

    def test_get_balance_history(self, watcher):
        snap = BalanceSnapshot("0xabc", Chain.ETHEREUM, 1.0, {}, 3500, 1000)
        watcher.snapshots["0xabc"] = [snap]

        history = watcher.get_balance_history("0xabc")
        assert len(history) == 1
        assert history[0].native_balance == 1.0

    def test_get_balance_history_empty(self, watcher):
        history = watcher.get_balance_history("0xnonexistent")
        assert history == []

    def test_get_summary(self, watcher):
        watcher.add_wallet("0xabc", "vitalik", Chain.ETHEREUM, tags=["founder"], alert_threshold_usd=50000)
        a1 = WalletAlert("0xabc", "vitalik", Chain.ETHEREUM, AlertType.BALANCE_CHANGE, AlertSeverity.HIGH, "big move")
        watcher.alerts = [a1]

        summary = watcher.get_summary()
        assert summary["watched_wallets"] == 1
        assert summary["total_alerts"] == 1
        assert summary["unacknowledged_alerts"] == 1
        assert "ethereum" in summary["chains"]
        assert summary["wallets"][0]["label"] == "vitalik"

    def test_persistence_save_and_load(self, temp_storage, chain_manager):
        watcher1 = WalletWatcher(chain_manager=chain_manager, storage_path=temp_storage)
        watcher1.add_wallet("0xabc", "test", Chain.ETHEREUM, tags=["tag1"], alert_threshold_usd=20000)

        watcher2 = WalletWatcher(chain_manager=chain_manager, storage_path=temp_storage)
        assert len(watcher2.wallets) == 1
        key = "0xabc:ethereum"
        assert key in watcher2.wallets
        assert watcher2.wallets[key].label == "test"
        assert watcher2.wallets[key].tags == ["tag1"]
        assert watcher2.wallets[key].alert_threshold_usd == 20000

    def test_persistence_load_corrupted(self, temp_storage):
        with open(temp_storage, "w") as f:
            f.write("invalid json{")

        watcher = WalletWatcher(chain_manager=MagicMock(), storage_path=temp_storage)
        assert len(watcher.wallets) == 0  # Gracefully handles corruption

    def test_persistence_load_missing_file(self, chain_manager):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "nonexistent.json")
            watcher = WalletWatcher(chain_manager=chain_manager, storage_path=path)
            assert len(watcher.wallets) == 0

    def test_snapshot_keeps_last_100(self, watcher, chain_manager):
        for i in range(150):
            chain_manager.get_web3.return_value.from_wei.return_value = float(i)
            watcher.snapshot("0xabc", Chain.ETHEREUM)

        assert len(watcher.snapshots["0xabc"]) == 100

    def test_remove_wallet_saves(self, watcher, temp_storage):
        watcher.add_wallet("0xabc", "test", Chain.ETHEREUM)
        watcher.remove_wallet("0xabc", Chain.ETHEREUM)

        # Load into fresh watcher
        watcher2 = WalletWatcher(chain_manager=MagicMock(), storage_path=temp_storage)
        assert len(watcher2.wallets) == 0

    def test_check_wallet_callback_fires(self, watcher, chain_manager):
        callback = MagicMock()
        watcher.on_alert(callback)

        watcher.add_wallet("0xabc", "test", Chain.ETHEREUM, watch_transfers=False)
        watcher.check_wallet("0xabc", Chain.ETHEREUM)  # baseline

        chain_manager.get_web3.return_value.from_wei.return_value = 2.0
        watcher.check_wallet("0xabc", Chain.ETHEREUM)

        callback.assert_called_once()

    def test_check_transfers_returns_empty(self, watcher):
        w = WatchedWallet("0xabc", "test", Chain.ETHEREUM)
        result = watcher._check_transfers(w)
        assert result == []