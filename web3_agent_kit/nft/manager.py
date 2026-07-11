"""NFT Manager — facade combining marketplace, minting, and analysis."""

from __future__ import annotations

import logging
from typing import Optional

import requests

from .marketplace import NFTMarketplace
from .mint import NFTMinter
from .utils import (
    MintResult,
    NFTCollection,
    NFTConfig,
    NFTItem,
    NFTListing,
    calculate_rarity,
)
from .whitelist import WhitelistManager

logger = logging.getLogger(__name__)


class NFTManager:
    """Manage NFT operations.

    Provides minting, tracking, listing, and analysis by composing
    :class:`NFTMarketplace`, :class:`NFTMinter`, and
    :class:`WhitelistManager`.

    Example::

        nft = NFTManager(NFTConfig(chain="ethereum"))

        # Get collection info
        collection = nft.get_collection("0x...")

        # Get NFTs in wallet
        nfts = nft.get_wallet_nfts("0x...")

        # Mint NFT
        result = nft.mint("0x...", quantity=1)
    """

    def __init__(self, config: Optional[NFTConfig] = None) -> None:
        """Initialize NFT manager.

        Args:
            config: NFT configuration.
        """
        self.config = config or NFTConfig()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "web3-agent-kit/1.6.0"})
        if self.config.opensea_api_key:
            self.session.headers["X-API-KEY"] = self.config.opensea_api_key
        if self.config.proxy:
            self.session.proxies = {"http": self.config.proxy, "https": self.config.proxy}

        self.marketplace = NFTMarketplace(self.config)
        self.minter = NFTMinter(self.config)
        self.whitelist = WhitelistManager()
        logger.info("NFTManager initialized")

    # ─── Delegated Marketplace Methods ────────────────────────────

    def get_collection(self, address: str) -> Optional[NFTCollection]:
        """Get collection information.

        Args:
            address: Collection contract address.

        Returns:
            NFTCollection object, or None if not found.
        """
        return self.marketplace.get_collection(address)

    def get_wallet_nfts(self, wallet: str, limit: int = 100) -> list[NFTItem]:
        """Get NFTs owned by a wallet.

        Args:
            wallet: Wallet address.
            limit: Max NFTs to return.

        Returns:
            List of NFTItem objects.
        """
        return self.marketplace.get_wallet_nfts(wallet, limit)

    def get_floor_price(self, address: str) -> float:
        """Get collection floor price.

        Args:
            address: Collection contract address.

        Returns:
            Floor price in ETH.
        """
        return self.marketplace.get_floor_price(address)

    def get_listings(self, address: str, limit: int = 20) -> list[NFTListing]:
        """Get active listings for a collection.

        Args:
            address: Collection contract address.
            limit: Max listings to return.

        Returns:
            List of NFTListing objects.
        """
        return self.marketplace.get_listings(address, limit)

    def get_trending(self, limit: int = 10) -> list[NFTCollection]:
        """Get trending collections.

        Args:
            limit: Max collections to return.

        Returns:
            List of trending NFTCollection objects.
        """
        return self.marketplace.get_trending(limit)

    def search_collections(self, query: str, limit: int = 10) -> list[NFTCollection]:
        """Search for collections.

        Args:
            query: Search query.
            limit: Max results.

        Returns:
            List of matching NFTCollection objects.
        """
        return self.marketplace.search_collections(query, limit)

    # ─── Delegated Minting Methods ────────────────────────────────

    def mint(
        self,
        contract: str,
        quantity: int = 1,
        value_eth: float = 0.0,
    ) -> MintResult:
        """Mint NFTs (placeholder — requires web3).

        Args:
            contract: NFT contract address.
            quantity: Number to mint.
            value_eth: ETH value to send.

        Returns:
            MintResult with details.
        """
        return self.minter.mint(contract, quantity, value_eth)

    # ─── Analysis Methods ─────────────────────────────────────────

    def calculate_rarity(self, nfts: list[NFTItem]) -> list[NFTItem]:
        """Calculate rarity scores for NFTs.

        Args:
            nfts: List of NFTItem objects.

        Returns:
            NFTs with rarity scores populated.
        """
        return calculate_rarity(nfts)
