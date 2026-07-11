"""NFT marketplace operations — collections, listings, trending, search."""

from __future__ import annotations

import logging
from typing import Optional

import requests

from .utils import NFTCollection, NFTConfig, NFTItem, NFTListing

logger = logging.getLogger(__name__)


class NFTMarketplace:
    """NFT marketplace client for querying collections, listings, and trends.

    Example::

        marketplace = NFTMarketplace(NFTConfig(chain="ethereum"))
        collection = marketplace.get_collection("0x...")
        listings = marketplace.get_listings("0x...")
    """

    OPENSEA_API: str = "https://api.opensea.io/api/v2"
    ALCHEMY_API: str = "https://eth-mainnet.g.alchemy.com/nft/v3"

    def __init__(self, config: Optional[NFTConfig] = None) -> None:
        self.config = config or NFTConfig()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "web3-agent-kit/1.6.0"})
        if self.config.opensea_api_key:
            self.session.headers["X-API-KEY"] = self.config.opensea_api_key
        if self.config.proxy:
            self.session.proxies = {"http": self.config.proxy, "https": self.config.proxy}

    def get_collection(self, address: str) -> Optional[NFTCollection]:
        """Get collection information.

        Args:
            address: Collection contract address.

        Returns:
            NFTCollection object, or None if not found.
        """
        try:
            resp = self.session.get(
                f"{self.OPENSEA_API}/collections/{address}",
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                return NFTCollection(
                    address=address,
                    name=data.get("name", ""),
                    symbol=data.get("symbol", ""),
                    total_supply=data.get("total_supply", 0),
                    floor_price_eth=data.get("floor_price", {}).get("value", 0) / 1e18,
                    description=data.get("description", ""),
                    image_url=data.get("image_url", ""),
                    chain=self.config.chain,
                    verified=data.get("safelist_request_status") == "verified",
                )
        except (requests.RequestException, ConnectionError, TimeoutError, KeyError, ValueError) as exc:
            logger.error("Failed to get collection: %s", exc)

        return None

    def get_wallet_nfts(self, wallet: str, limit: int = 100) -> list[NFTItem]:
        """Get NFTs owned by a wallet.

        Args:
            wallet: Wallet address.
            limit: Max NFTs to return.

        Returns:
            List of NFTItem objects.
        """
        nfts: list[NFTItem] = []
        try:
            if self.config.alchemy_api_key:
                resp = self.session.get(
                    f"{self.ALCHEMY_API}/{self.config.alchemy_api_key}/getNFTs",
                    params={"owner": wallet, "pageSize": limit},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("ownedNfts", []):
                        metadata = item.get("metadata", {})
                        nfts.append(NFTItem(
                            contract=item.get("contract", {}).get("address", ""),
                            token_id=item.get("tokenId", ""),
                            name=metadata.get("name", ""),
                            description=metadata.get("description", ""),
                            image_url=metadata.get("image", ""),
                            attributes=metadata.get("attributes", []),
                            owner=wallet,
                        ))
        except (requests.RequestException, ConnectionError, TimeoutError, KeyError, ValueError) as exc:
            logger.error("Failed to get wallet NFTs: %s", exc)

        return nfts

    def get_floor_price(self, address: str) -> float:
        """Get collection floor price.

        Args:
            address: Collection contract address.

        Returns:
            Floor price in ETH.
        """
        collection = self.get_collection(address)
        return collection.floor_price_eth if collection else 0.0

    def get_listings(self, address: str, limit: int = 20) -> list[NFTListing]:
        """Get active listings for a collection.

        Args:
            address: Collection contract address.
            limit: Max listings to return.

        Returns:
            List of NFTListing objects.
        """
        listings: list[NFTListing] = []
        try:
            resp = self.session.get(
                f"{self.OPENSEA_API}/listings/collection/{address}",
                params={"limit": limit},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("listings", []):
                    listings.append(NFTListing(
                        contract=address,
                        token_id=item.get("token_id", ""),
                        marketplace="opensea",
                        price=float(item.get("price", {}).get("value", 0)) / 1e18,
                        currency=item.get("price", {}).get("currency", "ETH"),
                        seller=item.get("seller", ""),
                        url=item.get("url", ""),
                    ))
        except (requests.RequestException, ConnectionError, TimeoutError, KeyError, ValueError) as exc:
            logger.error("Failed to get listings: %s", exc)

        return listings

    def get_trending(self, limit: int = 10) -> list[NFTCollection]:
        """Get trending collections.

        Args:
            limit: Max collections to return.

        Returns:
            List of trending NFTCollection objects.
        """
        collections: list[NFTCollection] = []
        try:
            resp = self.session.get(
                f"{self.OPENSEA_API}/collections/trending",
                params={"limit": limit},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("collections", []):
                    collections.append(NFTCollection(
                        address=item.get("address", ""),
                        name=item.get("name", ""),
                        floor_price_eth=item.get("floor_price", {}).get("value", 0) / 1e18,
                        volume_24h=item.get("volume", 0),
                        chain=self.config.chain,
                    ))
        except (requests.RequestException, ConnectionError, TimeoutError, KeyError, ValueError) as exc:
            logger.error("Failed to get trending: %s", exc)

        return collections

    def search_collections(self, query: str, limit: int = 10) -> list[NFTCollection]:
        """Search for collections.

        Args:
            query: Search query.
            limit: Max results.

        Returns:
            List of matching NFTCollection objects.
        """
        collections: list[NFTCollection] = []
        try:
            resp = self.session.get(
                f"{self.OPENSEA_API}/collections/search",
                params={"q": query, "limit": limit},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("results", []):
                    collections.append(NFTCollection(
                        address=item.get("address", ""),
                        name=item.get("name", ""),
                        floor_price_eth=item.get("floor_price", {}).get("value", 0) / 1e18,
                        chain=self.config.chain,
                    ))
        except (requests.RequestException, ConnectionError, TimeoutError, KeyError, ValueError) as exc:
            logger.error("Failed to search: %s", exc)

        return collections
