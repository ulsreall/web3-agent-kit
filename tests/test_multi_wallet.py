"""Tests for Multi-Wallet Manager."""

import json
import os
import tempfile
from unittest.mock import MagicMock

import pytest

from src.wallet.multi_wallet import (
    MultiWalletManager,
    WalletInfo,
    BatchTxResult,
    ConsolidatedBalance,
)
from src.chains.chain import Chain


@pytest.fixture
def temp_storage():
    """Create a temporary storage path."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def manager(temp_storage):
    """Create a multi-wallet manager."""
    return MultiWalletManager(chain=Chain.ETHEREUM, storage_path=temp_storage)


class TestWalletCreation:
    def test_create_wallet(self, manager):
        info = manager.create_wallet("test-01")
        assert info.label == "test-01"
        assert info.address.startswith("0x")
        assert len(info.address) == 42
        assert info.group == "default"

    def test_create_wallet_with_group(self, manager):
        info = manager.create_wallet("test-01", group="trading", tags=["hot"])
        assert info.group == "trading"
        assert "hot" in info.tags

    def test_create_duplicate_raises(self, manager):
        manager.create_wallet("test-01")
        with pytest.raises(ValueError, match="already exists"):
            manager.create_wallet("test-01")

    def test_import_wallet(self, manager):
        # Generate a test key
        from eth_account import Account
        acct = Account.create()

        info = manager.import_wallet("imported", private_key=acct.key.hex())
        assert info.address == acct.address
        assert info.label == "imported"

    def test_import_wallet_adds_0x_prefix(self, manager):
        from eth_account import Account
        acct = Account.create()
        key = acct.key.hex()  # Without 0x prefix

        info = manager.import_wallet("imported", private_key=key)
        assert info.address == acct.address


class TestWalletManagement:
    def test_list_wallets(self, manager):
        manager.create_wallet("w1", group="a")
        manager.create_wallet("w2", group="b")
        manager.create_wallet("w3", group="a")

        all_wallets = manager.list_wallets()
        assert len(all_wallets) == 3

    def test_list_wallets_by_group(self, manager):
        manager.create_wallet("w1", group="a")
        manager.create_wallet("w2", group="b")
        manager.create_wallet("w3", group="a")

        a_wallets = manager.list_wallets(group="a")
        assert len(a_wallets) == 2

    def test_list_wallets_by_tag(self, manager):
        manager.create_wallet("w1", tags=["hot"])
        manager.create_wallet("w2", tags=["cold"])
        manager.create_wallet("w3", tags=["hot", "sniper"])

        hot_wallets = manager.list_wallets(tag="hot")
        assert len(hot_wallets) == 2

    def test_remove_wallet(self, manager):
        manager.create_wallet("w1")
        assert len(manager.wallets) == 1

        result = manager.remove_wallet("w1")
        assert result is True
        assert len(manager.wallets) == 0

    def test_remove_nonexistent(self, manager):
        result = manager.remove_wallet("nonexistent")
        assert result is False

    def test_get_wallet(self, manager):
        manager.create_wallet("w1")
        wallet = manager.get_wallet("w1")
        assert wallet is not None

    def test_get_wallet_nonexistent(self, manager):
        wallet = manager.get_wallet("nonexistent")
        assert wallet is None

    def test_get_groups(self, manager):
        manager.create_wallet("w1", group="a")
        manager.create_wallet("w2", group="b")
        manager.create_wallet("w3", group="a")

        groups = manager.get_groups()
        assert "a" in groups
        assert "b" in groups
        assert len(groups["a"]) == 2
        assert len(groups["b"]) == 1


class TestWalletInfo:
    def test_short_address(self):
        info = WalletInfo(
            label="test",
            address="0x1234567890123456789012345678901234567890",
        )
        assert info.short_address == "0x1234...7890"


class TestPersistence:
    def test_save_and_load(self, temp_storage):
        manager1 = MultiWalletManager(chain=Chain.ETHEREUM, storage_path=temp_storage)
        manager1.create_wallet("w1", group="test")
        manager1.create_wallet("w2", group="other")

        # Create new manager from same storage
        manager2 = MultiWalletManager(chain=Chain.ETHEREUM, storage_path=temp_storage)
        assert len(manager2.wallets) == 2
        assert "w1" in manager2.wallets
        assert "w2" in manager2.wallets
        assert manager2.wallets["w1"].group == "test"


class TestExport:
    def test_export_json(self, manager):
        manager.create_wallet("w1", group="a")
        manager.create_wallet("w2", group="b")

        exported = manager.export_addresses(format="json")
        data = json.loads(exported)
        assert "w1" in data
        assert "w2" in data
        assert data["w1"].startswith("0x")

    def test_export_csv(self, manager):
        manager.create_wallet("w1", group="a")
        exported = manager.export_addresses(format="csv")
        lines = exported.strip().split("\n")
        assert lines[0] == "label,address,group"
        assert "w1" in lines[1]


class TestBatchTxResult:
    def test_success_result(self):
        result = BatchTxResult(
            wallet_label="test",
            wallet_address="0x123",
            tx_hash="0xabc",
            status="success",
        )
        assert result.status == "success"
        assert result.error is None

    def test_failed_result(self):
        result = BatchTxResult(
            wallet_label="test",
            wallet_address="0x123",
            tx_hash=None,
            status="failed",
            error="insufficient funds",
        )
        assert result.status == "failed"
        assert result.error == "insufficient funds"


class TestConsolidatedBalance:
    def test_consolidated_balance(self):
        balance = ConsolidatedBalance(
            total_native=1.5,
            total_tokens={"USDC": 1000, "WETH": 0.5},
            wallet_count=3,
            wallets=[],
        )
        assert balance.total_native == 1.5
        assert balance.total_tokens["USDC"] == 1000
        assert balance.wallet_count == 3


class TestBatchOperations:
    """Test batch operations on MultiWalletManager."""

    def test_batch_send_empty_recipients(self, manager):
        """Test batch_send with no recipients."""
        manager.create_wallet("w1")
        results = manager.batch_send(recipients=[], amount=0.01)
        assert len(results) == 0

    def test_batch_send_no_filter_match(self, manager):
        """Test batch_send with filter that matches nothing."""
        manager.create_wallet("w1", group="trading")
        results = manager.batch_send(
            recipients=["0xrecipient"],
            amount=0.01,
            group_filter="airdrop",
        )
        assert len(results) == 0

    def test_batch_send_skipped_no_wallet_instance(self, manager):
        """Test batch_send skips wallets without instance."""
        manager.create_wallet("w1")
        # Remove wallet instance to simulate missing
        label = "w1"
        key = "e8f3c8b9a6d4f2e1c0b7a5d3f9e6c4a2b8d0f7e5c3a1b9d6f4e2c0a8b7d5f3"
        # Manually create wallet info but skip instance
        from src.wallet.multi_wallet import WalletInfo
        info = WalletInfo(label="orphan", address="0x1234567890123456789012345678901234567890")
        manager.wallets["orphan"] = info
        # No instance in _wallet_instances

        results = manager.batch_send(
            recipients=["0xrecipient"],
            amount=0.01,
        )
        assert len(results) == 2  # w1 + orphan
        skipped = [r for r in results if r.status == "skipped"]
        assert len(skipped) == 1
        assert skipped[0].wallet_label == "orphan"

    def test_batch_send_success_and_failure(self, manager):
        """Test batch_send with mixed success/failure."""
        manager.create_wallet("w1")
        wallet = manager.get_wallet("w1")
        # Make wallet.send succeed
        wallet.send = MagicMock(return_value={"hash": "0xhash123", "gas": 21000})

        manager.create_wallet("w2")
        wallet2 = manager.get_wallet("w2")
        # Make wallet.send fail
        wallet2.send = MagicMock(side_effect=Exception("insufficient funds"))

        results = manager.batch_send(
            recipients=["0xrecipient"],
            amount=0.01,
            delay_between=0,
        )
        assert len(results) == 2
        successes = [r for r in results if r.status == "success"]
        failures = [r for r in results if r.status == "failed"]
        assert len(successes) == 1
        assert len(failures) == 1
        assert failures[0].error == "insufficient funds"

    def test_batch_send_with_label_filter(self, manager):
        """Test batch_send with label filter."""
        manager.create_wallet("trading-01", group="trading")
        manager.create_wallet("trading-02", group="trading")
        manager.create_wallet("airdrop-01", group="airdrop")

        for label in manager.wallets:
            w = manager.get_wallet(label)
            if w:
                w.send = MagicMock(return_value={"hash": "0xhash", "gas": 21000})

        results = manager.batch_send(
            recipients=["0xrecipient"],
            amount=0.01,
            label_filter="trading-*",
            delay_between=0,
        )
        assert len(results) == 2
        assert all(r.wallet_label.startswith("trading") for r in results)

    def test_batch_send_token(self, manager):
        """Test batch_send_token."""
        manager.create_wallet("w1")
        manager.create_wallet("w2")
        for label in manager.wallets:
            w = manager.get_wallet(label)
            if w:
                w.transfer_token = MagicMock(return_value={"hash": "0xhash", "gas": 50000})

        results = manager.batch_send_token(
            token_address="0xusdc",
            recipients=["0xrecipient"],
            amount=100.0,
            delay_between=0,
        )
        assert len(results) == 2
        assert all(r.status == "success" for r in results)

    def test_batch_send_token_skipped(self, manager):
        """Test batch_send_token skips wallets without instance."""
        from src.wallet.multi_wallet import WalletInfo
        info = WalletInfo(label="orphan", address="0x1234567890123456789012345678901234567890")
        manager.wallets["orphan"] = info

        results = manager.batch_send_token(
            token_address="0xusdc",
            recipients=["0xrecipient"],
            amount=100.0,
            delay_between=0,
        )
        skipped = [r for r in results if r.status == "skipped"]
        assert len(skipped) == 1

    def test_batch_send_token_failure(self, manager):
        """Test batch_send_token with failure."""
        manager.create_wallet("w1")
        w = manager.get_wallet("w1")
        w.transfer_token = MagicMock(side_effect=Exception("token not found"))

        results = manager.batch_send_token(
            token_address="0xbad",
            recipients=["0xrecipient"],
            amount=100.0,
            delay_between=0,
        )
        assert len(results) == 1
        assert results[0].status == "failed"
        assert "token not found" in results[0].error

    def test_batch_execute(self, manager):
        """Test batch_execute with custom tx builder."""
        manager.create_wallet("w1")
        manager.create_wallet("w2")

        def tx_builder(wallet):
            return {"hash": "0xcustom", "gas": 30000}

        results = manager.batch_execute(tx_builder=tx_builder, delay_between=0)
        assert len(results) == 2
        assert all(r.status == "success" for r in results)
        assert all(r.tx_hash == "0xcustom" for r in results)

    def test_batch_execute_failure(self, manager):
        """Test batch_execute with failing tx builder."""
        manager.create_wallet("w1")

        def tx_builder(wallet):
            raise Exception("build failed")

        results = manager.batch_execute(tx_builder=tx_builder, delay_between=0)
        assert len(results) == 1
        assert results[0].status == "failed"

    def test_batch_execute_skipped(self, manager):
        """Test batch_execute skips wallets without instance."""
        from src.wallet.multi_wallet import WalletInfo
        info = WalletInfo(label="orphan", address="0xorphan")
        manager.wallets["orphan"] = info

        results = manager.batch_execute(
            tx_builder=lambda w: {"hash": "0x"},
            delay_between=0,
        )
        assert len(results) == 1
        assert results[0].status == "skipped"


class TestConsolidation:
    """Test fund consolidation."""

    def test_consolidate_to_target_not_found(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.consolidate_to(target_label="nonexistent")

    def test_consolidate_to_skips_target(self, manager):
        """consolidate_to should skip the target wallet itself."""
        manager.create_wallet("main")
        manager.create_wallet("sub1")
        manager.create_wallet("sub2")

        main = manager.get_wallet("main")
        main.send = MagicMock()
        main.get_balance = MagicMock(return_value={"native": 10.0})

        sub1 = manager.get_wallet("sub1")
        sub1.get_balance = MagicMock(return_value={"native": 5.0})
        sub1.send = MagicMock(return_value={"hash": "0xsend1", "gas": 21000})

        sub2 = manager.get_wallet("sub2")
        sub2.get_balance = MagicMock(return_value={"native": 3.0})
        sub2.send = MagicMock(return_value={"hash": "0xsend2", "gas": 21000})

        results = manager.consolidate_to(
            target_label="main",
            keep_minimum=0.001,
        )
        # Only sub1 and sub2 should send (main is skipped)
        assert len(results) == 2
        assert all(r.status == "success" for r in results)

    def test_consolidate_to_balance_too_low(self, manager):
        """consolidate_to should skip wallets with balance <= keep_minimum."""
        manager.create_wallet("main")
        manager.create_wallet("poor")

        main = manager.get_wallet("main")
        main.send = MagicMock()
        main.get_balance = MagicMock(return_value={"native": 10.0})

        poor = manager.get_wallet("poor")
        poor.get_balance = MagicMock(return_value={"native": 0.0005})

        results = manager.consolidate_to(
            target_label="main",
            keep_minimum=0.001,
        )
        assert len(results) == 1
        assert results[0].status == "skipped"
        assert "Balance too low" in results[0].error

    def test_consolidate_to_failure(self, manager):
        """consolidate_to handles send failure."""
        manager.create_wallet("main")
        manager.create_wallet("sub")

        main = manager.get_wallet("main")
        sub = manager.get_wallet("sub")
        sub.get_balance = MagicMock(return_value={"native": 5.0})
        sub.send = MagicMock(side_effect=Exception("send failed"))

        main.get_balance = MagicMock(return_value={"native": 10.0})

        results = manager.consolidate_to(
            target_label="main",
            keep_minimum=0.001,
        )
        assert len(results) == 1
        assert results[0].status == "failed"
        assert "send failed" in results[0].error

    def test_consolidate_to_skips_no_instance(self, manager):
        """consolidate_to should skip wallets without instance."""
        manager.create_wallet("main")
        main = manager.get_wallet("main")
        main.get_balance = MagicMock(return_value={"native": 10.0})

        from src.wallet.multi_wallet import WalletInfo
        info = WalletInfo(label="orphan", address="0xorphan")
        manager.wallets["orphan"] = info

        results = manager.consolidate_to(target_label="main", keep_minimum=0.001)
        assert len(results) == 0  # orphan has no instance so it's skipped (continue)


class TestGetConsolidatedBalance:
    """Test get_consolidated_balance."""

    def test_basic(self, manager):
        manager.create_wallet("w1")
        manager.create_wallet("w2")

        w1 = manager.get_wallet("w1")
        w1.get_balance = MagicMock(return_value={
            "native": 1.5,
            "tokens": {"USDC": 500, "WETH": 0.5},
        })
        w2 = manager.get_wallet("w2")
        w2.get_balance = MagicMock(return_value={
            "native": 2.5,
            "tokens": {"USDC": 300, "DAI": 1000},
        })

        balance = manager.get_consolidated_balance()
        assert balance.total_native == 4.0
        assert balance.total_tokens["USDC"] == 800
        assert balance.total_tokens["WETH"] == 0.5
        assert balance.total_tokens["DAI"] == 1000
        assert balance.wallet_count == 2
        assert len(balance.wallets) == 2

    def test_skips_missing_instance(self, manager):
        manager.create_wallet("w1")
        from src.wallet.multi_wallet import WalletInfo
        info = WalletInfo(label="orphan", address="0xorphan")
        manager.wallets["orphan"] = info

        w1 = manager.get_wallet("w1")
        w1.get_balance = MagicMock(return_value={"native": 1.0, "tokens": {}})

        balance = manager.get_consolidated_balance()
        assert balance.wallet_count == 2  # Both wallet infos counted
        assert len(balance.wallets) == 1  # Only w1 has balance data
        assert balance.total_native == 1.0

    def test_handles_balance_failure(self, manager):
        manager.create_wallet("w1")
        w1 = manager.get_wallet("w1")
        w1.get_balance = MagicMock(side_effect=Exception("RPC error"))

        balance = manager.get_consolidated_balance()
        assert len(balance.wallets) == 1
        assert balance.wallets[0].get("error") == "Failed to fetch balance"
        assert balance.wallets[0]["native"] == 0
        assert balance.total_native == 0.0

    def test_filtering(self, manager):
        manager.create_wallet("w1", group="trading")
        manager.create_wallet("w2", group="airdrop")

        w1 = manager.get_wallet("w1")
        w1.get_balance = MagicMock(return_value={"native": 5.0, "tokens": {}})
        w2 = manager.get_wallet("w2")
        w2.get_balance = MagicMock(return_value={"native": 3.0, "tokens": {}})

        balance = manager.get_consolidated_balance(group_filter="trading")
        assert balance.total_native == 5.0
        assert balance.wallet_count == 1


class TestFilterWallets:
    """Test _filter_wallets internal method."""

    def test_active_only(self, manager):
        manager.create_wallet("w1")
        manager.wallets["w1"].is_active = False

        result = manager._filter_wallets()
        assert len(result) == 0

    def test_label_filter(self, manager):
        manager.create_wallet("trading-01")
        manager.create_wallet("trading-02")
        manager.create_wallet("airdrop-01")

        result = manager._filter_wallets(label_filter="trading-*")
        assert len(result) == 2

    def test_group_filter(self, manager):
        manager.create_wallet("w1", group="a")
        manager.create_wallet("w2", group="b")
        manager.create_wallet("w3", group="a")

        result = manager._filter_wallets(group_filter="a")
        assert len(result) == 2

    def test_combined_filters(self, manager):
        manager.create_wallet("trading-01", group="trading", tags=["hot"])
        manager.create_wallet("trading-02", group="trading")
        manager.create_wallet("airdrop-01", group="airdrop")

        result = manager._filter_wallets(label_filter="trading-*", group_filter="trading")
        assert len(result) == 2


class TestWalletInfoProperties:
    def test_short_address_various_lengths(self):
        info = WalletInfo(
            label="test",
            address="0xabcdef1234567890abcdef1234567890abcdef12",
        )
        short = info.short_address
        assert len(short) <= 13  # 0x + 6 + ... + 4 = 13
        assert short.startswith("0x")
        assert short.endswith("ef12")

    def test_short_address_empty(self):
        info = WalletInfo(
            label="test",
            address="0x",
        )
        short = info.short_address
        assert isinstance(short, str)

    def test_default_created_at(self):
        import time
        info = WalletInfo(label="test", address="0xabc")
        assert info.created_at > 0
        assert info.created_at <= time.time() + 1
