"""NFT whitelist management — check and manage mint whitelists."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class WhitelistEntry:
    """A single whitelist entry."""
    address: str
    max_mint: int = 1
    added_at: float = field(default_factory=time.time)
    used: bool = False
    tier: str = "standard"


@dataclass
class WhitelistResult:
    """Result of a whitelist check."""
    address: str
    is_whitelisted: bool
    max_mint: int = 0
    tier: str = ""
    message: str = ""


class WhitelistManager:
    """Manage NFT mint whitelists.

    Tracks which addresses are allowed to mint and enforces limits.

    Example::

        wl = WhitelistManager()
        wl.add("0xABC", max_mint=3, tier="og")
        result = wl.check("0xABC")
    """

    def __init__(self) -> None:
        self._entries: dict[str, WhitelistEntry] = {}

    def add(
        self,
        address: str,
        max_mint: int = 1,
        tier: str = "standard",
    ) -> bool:
        """Add an address to the whitelist.

        Args:
            address: Wallet address.
            max_mint: Maximum number of mints allowed.
            tier: Whitelist tier (e.g. ``"og"``, ``"standard"``).

        Returns:
            True if added, False if already present.
        """
        address = address.lower()
        if address in self._entries:
            logger.debug("Address %s already whitelisted", address)
            return False

        self._entries[address] = WhitelistEntry(
            address=address,
            max_mint=max_mint,
            tier=tier,
        )
        logger.info("Added %s to whitelist (tier=%s, max_mint=%d)", address, tier, max_mint)
        return True

    def remove(self, address: str) -> bool:
        """Remove an address from the whitelist.

        Args:
            address: Wallet address.

        Returns:
            True if removed, False if not found.
        """
        address = address.lower()
        if address not in self._entries:
            return False
        del self._entries[address]
        logger.info("Removed %s from whitelist", address)
        return True

    def check(self, address: str) -> WhitelistResult:
        """Check if an address is whitelisted.

        Args:
            address: Wallet address.

        Returns:
            WhitelistResult with status details.
        """
        address = address.lower()
        entry = self._entries.get(address)

        if entry is None:
            return WhitelistResult(
                address=address,
                is_whitelisted=False,
                message="Address not on whitelist",
            )

        if entry.used:
            return WhitelistResult(
                address=address,
                is_whitelisted=False,
                max_mint=entry.max_mint,
                tier=entry.tier,
                message="Whitelist spot already used",
            )

        return WhitelistResult(
            address=address,
            is_whitelisted=True,
            max_mint=entry.max_mint,
            tier=entry.tier,
            message=f"Whitelisted (tier={entry.tier}, max_mint={entry.max_mint})",
        )

    def mark_used(self, address: str) -> bool:
        """Mark an address's whitelist spot as used.

        Args:
            address: Wallet address.

        Returns:
            True if marked, False if not found.
        """
        address = address.lower()
        entry = self._entries.get(address)
        if entry is None:
            return False
        entry.used = True
        return True

    def bulk_add(self, addresses: list[str], max_mint: int = 1, tier: str = "standard") -> int:
        """Add multiple addresses to the whitelist.

        Args:
            addresses: List of wallet addresses.
            max_mint: Maximum mints per address.
            tier: Whitelist tier.

        Returns:
            Number of addresses actually added.
        """
        count = 0
        for addr in addresses:
            if self.add(addr, max_mint=max_mint, tier=tier):
                count += 1
        return count

    def get_all(self) -> list[WhitelistEntry]:
        """Get all whitelist entries.

        Returns:
            List of WhitelistEntry objects.
        """
        return list(self._entries.values())

    def clear(self) -> int:
        """Clear the entire whitelist.

        Returns:
            Number of entries cleared.
        """
        count = len(self._entries)
        self._entries.clear()
        return count
