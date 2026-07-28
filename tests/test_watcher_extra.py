"""Extra tests for WalletWatcher — monitoring, alerts, snapshots, persistence."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from web3_agent_kit.chains.chain import Chain
from web3_agent_kit.wallet.watcher import (
    AlertSeverity,
    AlertType,
    BalanceSnapshot,
    WalletAlert,
    WalletWatcher,
    WatchedWallet,
)


@pytest.fixture
def temp_storage():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    os.unlink(path)  # start fresh
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def watcher(temp_storage):
    cm = MagicMock()
    return WalletWatcher(cm, storage_path=temp_storage)


def _mock_w3(balance_eth):
    w3 = MagicMock()
    w3.eth.get_balance.return_value = int(balance_eth * 10**18)
    w3.from_wei.side_effect = lambda wei, _: wei / 10**18
    return w3


class TestAddRemoveList:
    def test_add_wallet(self, watcher):
        w = watcher.add_wallet("0xABC", "whale", Chain.ETHEREUM, tags=["dex"])
        assert isinstance(w, WatchedWallet)
        assert w.label == "whale"
        assert "dex" in w.tags
        assert len(watcher.wallets) == 1

    def test_remove_wallet(self, watcher):
        watcher.add_wallet("0xABC", "whale", Chain.ETHEREUM)
        assert watcher.remove_wallet("0xABC", Chain.ETHEREUM) is True
        assert len(watcher.wallets) == 0

    def test_remove_nonexistent(self, watcher):
        assert watcher.remove_wallet("0xDEAD", Chain.ETHEREUM) is False

    def test_list_filters(self, watcher):
        watcher.add_wallet("0x1", "a", Chain.ETHEREUM, tags=["hot"])
        watcher.add_wallet("0x2", "b", Chain.BASE, tags=["cold"])
        watcher.add_wallet("0x3", "c", Chain.ETHEREUM, tags=["hot"])
        assert len(watcher.list_wallets()) == 3
        assert len(watcher.list_wallets(chain=Chain.ETHEREUM)) == 2
        assert len(watcher.list_wallets(tag="hot")) == 2

    def test_list_active_only(self, watcher):
        watcher.add_wallet("0x1", "a", Chain.ETHEREUM)
        key = list(watcher.wallets)[0]
        watcher.wallets[key].is_active = False
        assert len(watcher.list_wallets(active_only=True)) == 0
        assert len(watcher.list_wallets(active_only=False)) == 1


class TestSnapshot:
    def test_snapshot_success(self, watcher):
        watcher.chain_manager.get_web3.return_value = _mock_w3(3.0)
        with patch(
            "web3_agent_kit.wallet.watcher.get_eth_price_usd", return_value=2000.0
        ):
            snap = watcher.snapshot("0xABC", Chain.ETHEREUM)
        assert isinstance(snap, BalanceSnapshot)
        assert snap.native_balance == 3.0
        assert snap.total_value_usd == 6000.0
        assert len(watcher.get_balance_history("0xABC")) == 1

    def test_snapshot_error_returns_none(self, watcher):
        watcher.chain_manager.get_web3.side_effect = RuntimeError("rpc down")
        assert watcher.snapshot("0xABC", Chain.ETHEREUM) is None

    def test_snapshot_all(self, watcher):
        watcher.add_wallet("0x1", "a", Chain.ETHEREUM)
        watcher.add_wallet("0x2", "b", Chain.ETHEREUM)
        watcher.chain_manager.get_web3.return_value = _mock_w3(1.0)
        with patch(
            "web3_agent_kit.wallet.watcher.get_eth_price_usd", return_value=100.0
        ):
            snaps = watcher.snapshot_all()
        assert len(snaps) == 2

    def test_snapshot_history_capped(self, watcher):
        watcher.chain_manager.get_web3.return_value = _mock_w3(1.0)
        with patch(
            "web3_agent_kit.wallet.watcher.get_eth_price_usd", return_value=1.0
        ):
            for _ in range(105):
                watcher.snapshot("0xABC", Chain.ETHEREUM)
        assert len(watcher.get_balance_history("0xABC")) == 100


class TestCheckWallet:
    def test_check_wallet_not_found(self, watcher):
        assert watcher.check_wallet("0xNONE", Chain.ETHEREUM) == []

    def test_check_wallet_first_snapshot_no_alert(self, watcher):
        watcher.add_wallet("0xABC", "whale", Chain.ETHEREUM)
        watcher.chain_manager.get_web3.return_value = _mock_w3(5.0)
        with patch(
            "web3_agent_kit.wallet.watcher.get_eth_price_usd", return_value=1.0
        ):
            alerts = watcher.check_wallet("0xABC", Chain.ETHEREUM)
        assert alerts == []

    def test_check_wallet_balance_change_alert(self, watcher):
        watcher.add_wallet("0xABC", "whale", Chain.ETHEREUM)
        # Seed a history snapshot at 5 ETH
        watcher.snapshots["0xabc"] = [
            BalanceSnapshot("0xABC", Chain.ETHEREUM, 5.0, {}, 5.0, 0)
        ]
        # Now the balance jumps to 20 ETH -> HIGH severity
        watcher.chain_manager.get_web3.return_value = _mock_w3(20.0)
        callback = MagicMock()
        watcher.on_alert(callback)
        with patch(
            "web3_agent_kit.wallet.watcher.get_eth_price_usd", return_value=1.0
        ):
            alerts = watcher.check_wallet("0xABC", Chain.ETHEREUM)
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.BALANCE_CHANGE
        assert alerts[0].severity == AlertSeverity.HIGH
        callback.assert_called_once()

    def test_check_wallet_callback_exception_swallowed(self, watcher):
        watcher.add_wallet("0xABC", "whale", Chain.ETHEREUM)
        watcher.snapshots["0xabc"] = [
            BalanceSnapshot("0xABC", Chain.ETHEREUM, 1.0, {}, 1.0, 0)
        ]
        watcher.chain_manager.get_web3.return_value = _mock_w3(200.0)
        watcher.on_alert(MagicMock(side_effect=RuntimeError("boom")))
        with patch(
            "web3_agent_kit.wallet.watcher.get_eth_price_usd", return_value=1.0
        ):
            alerts = watcher.check_wallet("0xABC", Chain.ETHEREUM)
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_check_all(self, watcher):
        watcher.add_wallet("0x1", "a", Chain.ETHEREUM)
        watcher.snapshots["0x1"] = [
            BalanceSnapshot("0x1", Chain.ETHEREUM, 1.0, {}, 1.0, 0)
        ]
        watcher.chain_manager.get_web3.return_value = _mock_w3(3.0)
        with patch(
            "web3_agent_kit.wallet.watcher.get_eth_price_usd", return_value=1.0
        ):
            alerts = watcher.check_all()
        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.MEDIUM


class TestAlerts:
    def _mk_watcher(self, temp_storage):
        return WalletWatcher(MagicMock(), storage_path=temp_storage)

    def test_get_alerts_filters(self, watcher):
        a1 = WalletAlert(
            "0x1", "a", Chain.ETHEREUM, AlertType.BALANCE_CHANGE,
            AlertSeverity.LOW, "m1",
        )
        a2 = WalletAlert(
            "0x2", "b", Chain.ETHEREUM, AlertType.LARGE_TRANSFER,
            AlertSeverity.HIGH, "m2",
        )
        watcher.alerts = [a1, a2]
        assert len(watcher.get_alerts()) == 2
        assert len(watcher.get_alerts(severity=AlertSeverity.HIGH)) == 1
        assert len(watcher.get_alerts(wallet_label="a")) == 1

    def test_acknowledge_alert(self, watcher):
        watcher.alerts = [
            WalletAlert(
                "0x1", "a", Chain.ETHEREUM, AlertType.BALANCE_CHANGE,
                AlertSeverity.LOW, "m1",
            )
        ]
        assert watcher.acknowledge_alert(0) is True
        assert watcher.alerts[0].acknowledged is True
        assert watcher.acknowledge_alert(99) is False
        # acknowledged excluded by default
        assert len(watcher.get_alerts()) == 0

    def test_acknowledge_all(self, watcher):
        watcher.alerts = [
            WalletAlert(
                "0x1", "a", Chain.ETHEREUM, AlertType.BALANCE_CHANGE,
                AlertSeverity.LOW, str(i),
            )
            for i in range(3)
        ]
        assert watcher.acknowledge_all() == 3
        assert watcher.acknowledge_all() == 0


class TestSummaryAndPersistence:
    def test_get_summary(self, watcher):
        watcher.add_wallet("0x1234567890abcdef", "a", Chain.ETHEREUM, tags=["x"])
        watcher.alerts = [
            WalletAlert(
                "0x1", "a", Chain.ETHEREUM, AlertType.BALANCE_CHANGE,
                AlertSeverity.LOW, "m",
            )
        ]
        summary = watcher.get_summary()
        assert summary["watched_wallets"] == 1
        assert summary["total_alerts"] == 1
        assert summary["unacknowledged_alerts"] == 1
        assert "ethereum" in summary["chains"]
        assert summary["wallets"][0]["label"] == "a"

    def test_save_and_load_wallets(self, temp_storage):
        cm = MagicMock()
        w1 = WalletWatcher(cm, storage_path=temp_storage)
        w1.add_wallet("0xABC", "whale", Chain.BASE, tags=["t"],
                      alert_threshold_usd=5000)
        # New watcher loads the persisted file
        w2 = WalletWatcher(cm, storage_path=temp_storage)
        assert len(w2.wallets) == 1
        loaded = list(w2.wallets.values())[0]
        assert loaded.label == "whale"
        assert loaded.chain == Chain.BASE
        assert loaded.alert_threshold_usd == 5000

    def test_load_wallets_corrupt_file(self, temp_storage):
        with open(temp_storage, "w") as f:
            f.write("not valid json {{{")
        cm = MagicMock()
        w = WalletWatcher(cm, storage_path=temp_storage)
        assert len(w.wallets) == 0

    def test_load_missing_file_noop(self, temp_storage):
        cm = MagicMock()
        w = WalletWatcher(cm, storage_path=temp_storage)
        assert w.wallets == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
