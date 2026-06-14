"""NFT shared types, enums, and dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


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


def calculate_rarity(nfts: list[NFTItem]) -> list[NFTItem]:
    """Calculate rarity scores for a list of NFTs.

    Args:
        nfts: List of NFTItem objects.

    Returns:
        NFTs sorted by rarity with ``rarity_score`` and ``rarity_rank``
        populated.
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
