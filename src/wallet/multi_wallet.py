"""Multi-Wallet Manager — Manage multiple wallets, batch transactions, consolidated views."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from eth_account import Account
from web3 import Web3

from .wallet import Wallet, WalletConfig
from ..chains.chain import Chain, ChainManager


@dataclass
class WalletInfo:
    """Metadata for a managed wallet."""
    label: str                    # Human-readable label (e.g. "main", "airdrop-01")
    address: str                  # EVM address
    group: str = "default"        # Wallet group name
    tags: list[str] = field(default_factory=list)  # Tags for filtering
    created_at: float = field(default_factory=time.time)
    is_active: bool = True

    @property
    def short_address(self) -> str:
        return f"{self.address[:6]}...{self.address[-4:]}"


@dataclass
class BatchTxResult:
    """Result of a batch transaction execution."""
    wallet_label: str
    wallet_address: str
    tx_hash: Optional[str]
    status: str                   # "success", "failed", "skipped"
    error: Optional[str] = None
    gas_used: Optional[int] = None


@dataclass
class ConsolidatedBalance:
    """Consolidated balance across all wallets."""
    total_native: float           # Total native token (ETH, BNB, etc.)
    total_tokens: dict[str, float]  # Token symbol -> total balance
    wallet_count: int
    wallets: list[dict]           # Per-wallet breakdown


class MultiWalletManager:
    """Manage multiple wallets with batch operations and consolidated views.

    Example::

        manager = MultiWalletManager(chain)

        # Create wallets
        manager.create_wallet("trading-01", group="trading")
        manager.create_wallet("airdrop-01", group="airdrop")
        manager.import_wallet("main", private_key="0x...", group="main")

        # Batch send
        results = manager.batch_send(
            recipients=["0xAddr1", "0xAddr2"],
            amount=0.01,
            label_filter="airdrop-*",
        )

        # Consolidated view
        summary = manager.get_consolidated_balance()
    """

    def __init__(
        self,
        chain: Chain,
        storage_path: Optional[str] = None,
    ):
        self.chain = chain
        self.wallets: dict[str, WalletInfo] = {}
        self._wallet_instances: dict[str, Wallet] = {}  # label -> Wallet
        self._private_keys: dict[str, str] = {}  # label -> encrypted PK (in memory only)

        # Storage for wallet metadata (NOT private keys)
        self.storage_path = storage_path or os.path.expanduser("~/.web3-agent-kit/wallets.json")
        self._load_metadata()

    def create_wallet(
        self,
        label: str,
        group: str = "default",
        tags: Optional[list[str]] = None,
    ) -> WalletInfo:
        """Create a new random wallet.

        Args:
            label: Unique label for the wallet.
            group: Wallet group name.
            tags: Optional tags for filtering.

        Returns:
            WalletInfo with the new wallet details.
        """
        if label in self.wallets:
            raise ValueError(f"Wallet '{label}' already exists")

        acct = Account.create()
        info = WalletInfo(
            label=label,
            address=acct.address,
            group=group,
            tags=tags or [],
        )

        self.wallets[label] = info
        self._private_keys[label] = acct.key.hex()
        self._wallet_instances[label] = Wallet(
            config=WalletConfig(private_key=acct.key.hex()),
            chain_manager=ChainManager(chains=[self.chain]),
        )
        self._save_metadata()

        return info

    def import_wallet(
        self,
        label: str,
        private_key: str,
        group: str = "default",
        tags: Optional[list[str]] = None,
    ) -> WalletInfo:
        """Import an existing wallet from private key.

        Args:
            label: Unique label for the wallet.
            private_key: Hex private key (with or without 0x prefix).
            group: Wallet group name.
            tags: Optional tags.

        Returns:
            WalletInfo with the wallet details.
        """
        if label in self.wallets:
            raise ValueError(f"Wallet '{label}' already exists")

        if not private_key.startswith("0x"):
            private_key = "0x" + private_key

        acct = Account.from_key(private_key)
        info = WalletInfo(
            label=label,
            address=acct.address,
            group=group,
            tags=tags or [],
        )

        self.wallets[label] = info
        self._private_keys[label] = private_key
        self._wallet_instances[label] = Wallet(
            config=WalletConfig(private_key=private_key),
            chain_manager=ChainManager(chains=[self.chain]),
        )
        self._save_metadata()

        return info

    def remove_wallet(self, label: str) -> bool:
        """Remove a wallet from management.

        Args:
            label: Wallet label to remove.

        Returns:
            True if removed, False if not found.
        """
        if label not in self.wallets:
            return False

        del self.wallets[label]
        self._private_keys.pop(label, None)
        self._wallet_instances.pop(label, None)
        self._save_metadata()
        return True

    def get_wallet(self, label: str) -> Optional[Wallet]:
        """Get Wallet instance by label."""
        return self._wallet_instances.get(label)

    def list_wallets(
        self,
        group: Optional[str] = None,
        tag: Optional[str] = None,
        active_only: bool = True,
    ) -> list[WalletInfo]:
        """List wallets with optional filters.

        Args:
            group: Filter by group name.
            tag: Filter by tag.
            active_only: Only return active wallets.

        Returns:
            List of matching WalletInfo.
        """
        result = []
        for info in self.wallets.values():
            if active_only and not info.is_active:
                continue
            if group and info.group != group:
                continue
            if tag and tag not in info.tags:
                continue
            result.append(info)
        return result

    def get_groups(self) -> dict[str, list[str]]:
        """Get wallets grouped by group name.

        Returns:
            Dict of group_name -> list of wallet labels.
        """
        groups: dict[str, list[str]] = {}
        for label, info in self.wallets.items():
            groups.setdefault(info.group, []).append(label)
        return groups

    # === Batch Operations ===

    def batch_send(
        self,
        recipients: list[str],
        amount: float,
        label_filter: Optional[str] = None,
        group_filter: Optional[str] = None,
        delay_between: float = 1.0,
    ) -> list[BatchTxResult]:
        """Send native token from multiple wallets to recipients.

        Args:
            recipients: List of recipient addresses.
            amount: Amount to send per wallet (in native token).
            label_filter: Filter wallets by label (supports * wildcard).
            group_filter: Filter wallets by group.
            delay_between: Delay between transactions in seconds.

        Returns:
            List of BatchTxResult.
        """
        wallets = self._filter_wallets(label_filter, group_filter)
        results = []

        for wallet_info in wallets:
            wallet = self._wallet_instances.get(wallet_info.label)
            if not wallet:
                results.append(BatchTxResult(
                    wallet_label=wallet_info.label,
                    wallet_address=wallet_info.address,
                    tx_hash=None,
                    status="skipped",
                    error="No private key loaded",
                ))
                continue

            for recipient in recipients:
                try:
                    tx = wallet.send(
                        to=recipient,
                        amount=amount,
                    )
                    results.append(BatchTxResult(
                        wallet_label=wallet_info.label,
                        wallet_address=wallet_info.address,
                        tx_hash=tx.get("hash"),
                        status="success",
                        gas_used=tx.get("gas"),
                    ))
                except Exception as e:
                    results.append(BatchTxResult(
                        wallet_label=wallet_info.label,
                        wallet_address=wallet_info.address,
                        tx_hash=None,
                        status="failed",
                        error=str(e),
                    ))

                if delay_between > 0:
                    time.sleep(delay_between)

        return results

    def batch_send_token(
        self,
        token_address: str,
        recipients: list[str],
        amount: float,
        label_filter: Optional[str] = None,
        group_filter: Optional[str] = None,
        delay_between: float = 1.0,
    ) -> list[BatchTxResult]:
        """Send ERC20 tokens from multiple wallets.

        Args:
            token_address: ERC20 token contract address.
            recipients: List of recipient addresses.
            amount: Amount per wallet.
            label_filter: Filter wallets by label.
            group_filter: Filter wallets by group.
            delay_between: Delay between txs.

        Returns:
            List of BatchTxResult.
        """
        wallets = self._filter_wallets(label_filter, group_filter)
        results = []

        for wallet_info in wallets:
            wallet = self._wallet_instances.get(wallet_info.label)
            if not wallet:
                results.append(BatchTxResult(
                    wallet_label=wallet_info.label,
                    wallet_address=wallet_info.address,
                    tx_hash=None,
                    status="skipped",
                    error="No private key loaded",
                ))
                continue

            for recipient in recipients:
                try:
                    tx = wallet.transfer_token(
                        token=token_address,
                        to=recipient,
                        amount=amount,
                    )
                    results.append(BatchTxResult(
                        wallet_label=wallet_info.label,
                        wallet_address=wallet_info.address,
                        tx_hash=tx.get("hash"),
                        status="success",
                        gas_used=tx.get("gas"),
                    ))
                except Exception as e:
                    results.append(BatchTxResult(
                        wallet_label=wallet_info.label,
                        wallet_address=wallet_info.address,
                        tx_hash=None,
                        status="failed",
                        error=str(e),
                    ))

                if delay_between > 0:
                    time.sleep(delay_between)

        return results

    def batch_execute(
        self,
        tx_builder,  # Callable[[Wallet], dict]
        label_filter: Optional[str] = None,
        group_filter: Optional[str] = None,
        delay_between: float = 1.0,
    ) -> list[BatchTxResult]:
        """Execute a custom transaction from multiple wallets.

        Args:
            tx_builder: Function that takes a Wallet and returns tx dict.
            label_filter: Filter wallets by label.
            group_filter: Filter wallets by group.
            delay_between: Delay between txs.

        Returns:
            List of BatchTxResult.
        """
        wallets = self._filter_wallets(label_filter, group_filter)
        results = []

        for wallet_info in wallets:
            wallet = self._wallet_instances.get(wallet_info.label)
            if not wallet:
                results.append(BatchTxResult(
                    wallet_label=wallet_info.label,
                    wallet_address=wallet_info.address,
                    tx_hash=None,
                    status="skipped",
                    error="No private key loaded",
                ))
                continue

            try:
                tx = tx_builder(wallet)
                results.append(BatchTxResult(
                    wallet_label=wallet_info.label,
                    wallet_address=wallet_info.address,
                    tx_hash=tx.get("hash"),
                    status="success",
                    gas_used=tx.get("gas"),
                ))
            except Exception as e:
                results.append(BatchTxResult(
                    wallet_label=wallet_info.label,
                    wallet_address=wallet_info.address,
                    tx_hash=None,
                    status="failed",
                    error=str(e),
                ))

            if delay_between > 0:
                time.sleep(delay_between)

        return results

    # === Balance & Portfolio ===

    def get_consolidated_balance(
        self,
        label_filter: Optional[str] = None,
        group_filter: Optional[str] = None,
    ) -> ConsolidatedBalance:
        """Get consolidated balance across all wallets.

        Returns:
            ConsolidatedBalance with totals and per-wallet breakdown.
        """
        wallets = self._filter_wallets(label_filter, group_filter)
        total_native = 0.0
        total_tokens: dict[str, float] = {}
        wallet_breakdown = []

        for wallet_info in wallets:
            wallet = self._wallet_instances.get(wallet_info.label)
            if not wallet:
                continue

            try:
                balance = wallet.get_balance()
                native = balance.get("native", 0)
                total_native += native

                tokens = {}
                for token_symbol, token_balance in balance.get("tokens", {}).items():
                    tokens[token_symbol] = token_balance
                    total_tokens[token_symbol] = total_tokens.get(token_symbol, 0) + token_balance

                wallet_breakdown.append({
                    "label": wallet_info.label,
                    "address": wallet_info.address,
                    "group": wallet_info.group,
                    "native": native,
                    "tokens": tokens,
                })
            except Exception:
                wallet_breakdown.append({
                    "label": wallet_info.label,
                    "address": wallet_info.address,
                    "group": wallet_info.group,
                    "native": 0,
                    "tokens": {},
                    "error": "Failed to fetch balance",
                })

        return ConsolidatedBalance(
            total_native=total_native,
            total_tokens=total_tokens,
            wallet_count=len(wallets),
            wallets=wallet_breakdown,
        )

    # === Consolidation ===

    def consolidate_to(
        self,
        target_label: str,
        label_filter: Optional[str] = None,
        group_filter: Optional[str] = None,
        keep_minimum: float = 0.001,
    ) -> list[BatchTxResult]:
        """Consolidate funds from multiple wallets to a target wallet.

        Args:
            target_label: Label of the target wallet to receive funds.
            label_filter: Filter source wallets by label.
            group_filter: Filter source wallets by group.
            keep_minimum: Minimum balance to keep in source wallets (for gas).

        Returns:
            List of BatchTxResult.
        """
        target = self.wallets.get(target_label)
        if not target:
            raise ValueError(f"Target wallet '{target_label}' not found")

        wallets = self._filter_wallets(label_filter, group_filter)
        results = []

        for wallet_info in wallets:
            if wallet_info.label == target_label:
                continue

            wallet = self._wallet_instances.get(wallet_info.label)
            if not wallet:
                continue

            try:
                balance = wallet.get_balance().get("native", 0)
                send_amount = balance - keep_minimum

                if send_amount <= 0:
                    results.append(BatchTxResult(
                        wallet_label=wallet_info.label,
                        wallet_address=wallet_info.address,
                        tx_hash=None,
                        status="skipped",
                        error=f"Balance too low ({balance})",
                    ))
                    continue

                tx = wallet.send(to=target.address, amount=send_amount)
                results.append(BatchTxResult(
                    wallet_label=wallet_info.label,
                    wallet_address=wallet_info.address,
                    tx_hash=tx.get("hash"),
                    status="success",
                    gas_used=tx.get("gas"),
                ))
            except Exception as e:
                results.append(BatchTxResult(
                    wallet_label=wallet_info.label,
                    wallet_address=wallet_info.address,
                    tx_hash=None,
                    status="failed",
                    error=str(e),
                ))

            time.sleep(1)

        return results

    # === Export ===

    def export_addresses(self, format: str = "json") -> str:
        """Export all wallet addresses.

        Args:
            format: "json" or "csv"

        Returns:
            Formatted string of addresses.
        """
        if format == "csv":
            lines = ["label,address,group"]
            for label, info in self.wallets.items():
                lines.append(f"{label},{info.address},{info.group}")
            return "\n".join(lines)
        else:
            return json.dumps(
                {label: info.address for label, info in self.wallets.items()},
                indent=2,
            )

    # === Internal ===

    def _filter_wallets(
        self,
        label_filter: Optional[str] = None,
        group_filter: Optional[str] = None,
    ) -> list[WalletInfo]:
        """Filter wallets by label pattern and group."""
        import fnmatch

        result = []
        for label, info in self.wallets.items():
            if not info.is_active:
                continue
            if label_filter and not fnmatch.fnmatch(label, label_filter):
                continue
            if group_filter and info.group != group_filter:
                continue
            result.append(info)
        return result

    def _save_metadata(self) -> None:
        """Save wallet metadata to disk (addresses only, NOT keys)."""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        data = {}
        for label, info in self.wallets.items():
            data[label] = {
                "address": info.address,
                "group": info.group,
                "tags": info.tags,
                "created_at": info.created_at,
                "is_active": info.is_active,
            }
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load_metadata(self) -> None:
        """Load wallet metadata from disk."""
        if not os.path.exists(self.storage_path):
            return

        try:
            with open(self.storage_path) as f:
                data = json.load(f)

            for label, meta in data.items():
                self.wallets[label] = WalletInfo(
                    label=label,
                    address=meta["address"],
                    group=meta.get("group", "default"),
                    tags=meta.get("tags", []),
                    created_at=meta.get("created_at", 0),
                    is_active=meta.get("is_active", True),
                )
        except Exception:
            pass
