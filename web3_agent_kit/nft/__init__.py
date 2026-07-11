"""NFT Module — mint, track, flip, and analyze NFTs.

Provides NFT operations: minting, floor price tracking,
rarity checking, and trading.

Usage::

    from web3_agent_kit.nft import NFTManager, NFTConfig

    nft = NFTManager(NFTConfig(chain="ethereum"))
    collection = nft.get_collection("0x...")
    nfts = nft.get_wallet_nfts("0x...")
"""

from .manager import NFTManager
from .marketplace import NFTMarketplace
from .mint import NFTMinter
from .utils import (
    MintResult,
    NFTCollection,
    NFTConfig,
    NFTItem,
    NFTListing,
    NFTStandard,
    calculate_rarity,
)
from .whitelist import WhitelistEntry, WhitelistManager, WhitelistResult

__all__ = [
    "NFTStandard",
    "NFTConfig",
    "NFTCollection",
    "NFTItem",
    "NFTListing",
    "MintResult",
    "NFTManager",
    "NFTMarketplace",
    "NFTMinter",
    "WhitelistManager",
    "WhitelistEntry",
    "WhitelistResult",
    "calculate_rarity",
]
