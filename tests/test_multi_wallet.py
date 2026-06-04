"""Tests for Multi-Wallet Manager."""

import json
import os
import tempfile

import pytest

from src.multi_wallet import (
    MultiWalletManager,
    WalletInfo,
    BatchTxResult,
    ConsolidatedBalance,
)
from src.chain import Chain


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
