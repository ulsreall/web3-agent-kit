"""Solana module — wallet, RPC client, DEX aggregator, and NFT operations."""

from .client import SolanaClient, SolanaClientConfig
from .dex import JupiterDEX, JupiterDEXConfig
from .lp import DEXProtocol, LPConfig, PoolInfo, SolanaLPManager
from .nft import SolanaNFT, SolanaNFTConfig
from .wallet import SolanaWallet, SolanaWalletConfig

__all__ = [
    "SolanaClient",
    "SolanaClientConfig",
    "SolanaWallet",
    "SolanaWalletConfig",
    "JupiterDEX",
    "JupiterDEXConfig",
    "SolanaNFT",
    "SolanaNFTConfig",
    "SolanaLPManager",
    "LPConfig",
    "DEXProtocol",
    "PoolInfo",
]
