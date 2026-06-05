"""NFT Module — mint, track, flip, and analyze NFTs.

Provides NFT operations: minting, floor price tracking,
rarity checking, and trading.

Usage::

    from web3_agent_kit.nft import NFTManager, NFTConfig

    nft = NFTManager(NFTConfig(chain="ethereum"))
    collection = nft.get_collection("0x...")
    nfts = nft.get_wallet_nfts("0x...")
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class NFTStandard(Enum):
    """NFT token standard."""
    ERC721 = "ERC721"
    ERC1155 = "ERC1155"


@dataclass
class NFTConfig:
    """Configuration for NFT operations."""
    chain: str = "ethereum"
    # API keys
    opensea_api_key: str = ""
    alchemy_api_key: str = ""
    # Settings
    max_gas_gwei: int = 100
    slippage_percent: float = 5.0
    # Proxy
    proxy: Optional[str] = None


@dataclass
class NFTCollection:
    """NFT collection information."""
    address: str
    name: str = ""
    symbol: str = ""
    standard: NFTStandard = NFTStandard.ERC721
    total_supply: int = 0
    floor_price_eth: float = 0.0
    floor_price_usd: float = 0.0
    volume_24h: float = 0.0
    owners: int = 0
    description: str = ""
    image_url: str = ""
    external_url: str = ""
    chain: str = "ethereum"
    verified: bool = False

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "name": self.name,
            "symbol": self.symbol,
            "standard": self.standard.value,
            "total_supply": self.total_supply,
            "floor_price_eth": self.floor_price_eth,
            "floor_price_usd": self.floor_price_usd,
            "volume_24h": self.volume_24h,
            "owners": self.owners,
        }


@dataclass
class NFTItem:
    """Individual NFT item."""
    contract: str
    token_id: str
    name: str = ""
    description: str = ""
    image_url: str = ""
    attributes: list[dict] = field(default_factory=list)
    owner: str = ""
    standard: NFTStandard = NFTStandard.ERC721
    rarity_rank: int = 0
    rarity_score: float = 0.0
    last_sale_price: float = 0.0
    last_sale_currency: str = "ETH"
    estimated_value: float = 0.0

    @property
    def opensea_url(self) -> str:
        return f"https://opensea.io/assets/ethereum/{self.contract}/{self.token_id}"

    def to_dict(self) -> dict:
        return {
            "contract": self.contract,
            "token_id": self.token_id,
            "name": self.name,
            "image_url": self.image_url,
            "rarity_rank": self.rarity_rank,
            "rarity_score": self.rarity_score,
            "last_sale_price": self.last_sale_price,
        }


@dataclass
class NFTListing:
    """NFT listing on marketplace."""
    contract: str
    token_id: str
    marketplace: str = "opensea"
    price: float = 0.0
    currency: str = "ETH"
    seller: str = ""
    listing_time: float = 0.0
    expiration_time: float = 0.0
    url: str = ""

    def to_dict(self) -> dict:
        return {
            "contract": self.contract,
            "token_id": self.token_id,
            "marketplace": self.marketplace,
            "price": self.price,
            "currency": self.currency,
            "url": self.url,
        }


@dataclass
class MintResult:
    """Result of NFT minting."""
    contract: str
    token_id: str = ""
    tx_hash: str = ""
    success: bool = False
    gas_used: int = 0
    error: str = ""
    chain: str = ""

    def to_dict(self) -> dict:
        return {
            "contract": self.contract,
            "token_id": self.token_id,
            "tx_hash": self.tx_hash,
            "success": self.success,
        }


class NFTManager:
    """Manage NFT operations.

    Provides minting, tracking, listing, and analysis.

    Example::

        nft = NFTManager(NFTConfig(chain="ethereum"))

        # Get collection info
        collection = nft.get_collection("0x...")

        # Get NFTs in wallet
        nfts = nft.get_wallet_nfts("0x...")

        # Mint NFT
        result = nft.mint("0x...", quantity=1)
    """

    # API endpoints
    OPENSEA_API = "https://api.opensea.io/api/v2"
    ALCHEMY_API = "https://eth-mainnet.g.alchemy.com/nft/v3"

    def __init__(self, config: Optional[NFTConfig] = None):
        """Initialize NFT manager.

        Args:
            config: NFT configuration.
        """
        self.config = config or NFTConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "web3-agent-kit/1.3.1",
        })
        if self.config.opensea_api_key:
            self.session.headers["X-API-KEY"] = self.config.opensea_api_key
        if self.config.proxy:
            self.session.proxies = {"http": self.config.proxy, "https": self.config.proxy}
        logger.info("NFTManager initialized")

    def get_collection(self, address: str) -> Optional[NFTCollection]:
        """Get collection information.

        Args:
            address: Collection contract address.

        Returns:
            NFTCollection object, or None if not found.
        """
        try:
            # Try OpenSea API
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
        except Exception as e:
            logger.error(f"Failed to get collection: {e}")

        return None

    def get_wallet_nfts(self, wallet: str, limit: int = 100) -> list[NFTItem]:
        """Get NFTs owned by a wallet.

        Args:
            wallet: Wallet address.
            limit: Max NFTs to return.

        Returns:
            List of NFTItem objects.
        """
        nfts = []
        try:
            # Try Alchemy API
            if self.config.alchemy_api_key:
                resp = self.session.get(
                    f"{self.ALCHEMY_API}/{self.config.alchemy_api_key}/getNFTs",
                    params={
                        "owner": wallet,
                        "pageSize": limit,
                    },
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
        except Exception as e:
            logger.error(f"Failed to get wallet NFTs: {e}")

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
        listings = []
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
        except Exception as e:
            logger.error(f"Failed to get listings: {e}")

        return listings

    def calculate_rarity(self, nfts: list[NFTItem]) -> list[NFTItem]:
        """Calculate rarity scores for NFTs.

        Args:
            nfts: List of NFTItem objects.

        Returns:
            NFTs with rarity scores populated.
        """
        if not nfts:
            return nfts

        # Count attribute frequencies
        attr_counts: dict[str, dict[str, int]] = {}
        for nft in nfts:
            for attr in nft.attributes:
                trait_type = attr.get("trait_type", "")
                value = attr.get("value", "")
                if trait_type not in attr_counts:
                    attr_counts[trait_type] = {}
                attr_counts[trait_type][value] = attr_counts[trait_type].get(value, 0) + 1

        # Calculate rarity scores
        total = len(nfts)
        for nft in nfts:
            score = 0.0
            for attr in nft.attributes:
                trait_type = attr.get("trait_type", "")
                value = attr.get("value", "")
                count = attr_counts.get(trait_type, {}).get(value, 1)
                score += total / count  # Rarer = higher score
            nft.rarity_score = round(score, 2)

        # Sort by rarity and assign ranks
        sorted_nfts = sorted(nfts, key=lambda x: x.rarity_score, reverse=True)
        for i, nft in enumerate(sorted_nfts):
            nft.rarity_rank = i + 1

        return sorted_nfts

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
        result = MintResult(contract=contract, chain=self.config.chain)

        # This would use web3 to interact with the contract
        # For now, return placeholder
        result.error = "Minting requires web3 integration"
        logger.warning("Minting not yet implemented — requires web3")

        return result

    def get_trending(self, limit: int = 10) -> list[NFTCollection]:
        """Get trending collections.

        Args:
            limit: Max collections to return.

        Returns:
            List of trending NFTCollection objects.
        """
        collections = []
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
        except Exception as e:
            logger.error(f"Failed to get trending: {e}")

        return collections

    def search_collections(self, query: str, limit: int = 10) -> list[NFTCollection]:
        """Search for collections.

        Args:
            query: Search query.
            limit: Max results.

        Returns:
            List of matching NFTCollection objects.
        """
        collections = []
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
        except Exception as e:
            logger.error(f"Failed to search: {e}")

        return collections

__all__ = [
    "NFTStandard",
    "NFTConfig",
    "NFTCollection",
    "NFTItem",
    "NFTListing",
    "MintResult",
    "NFTManager",
]
