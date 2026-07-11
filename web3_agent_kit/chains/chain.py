"""Multi-chain support — chain definitions and RPC management."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Chain(Enum):
    """Supported blockchain networks."""

    ETHEREUM = "ethereum"
    BASE = "base"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    POLYGON = "polygon"
    AVALANCHE = "avalanche"
    BSC = "bsc"
    SOLANA = "solana"


# Default RPC endpoints
DEFAULT_RPCS = {
    Chain.ETHEREUM: "https://eth.llamarpc.com",
    Chain.BASE: "https://mainnet.base.org",
    Chain.ARBITRUM: "https://arb1.arbitrum.io/rpc",
    Chain.OPTIMISM: "https://mainnet.optimism.io",
    Chain.POLYGON: "https://polygon-rpc.com",
    Chain.AVALANCHE: "https://api.avax.network/ext/bc/C/rpc",
    Chain.BSC: "https://bsc-dataseed1.binance.org",
    Chain.SOLANA: "https://api.mainnet-beta.solana.com",
}

# Chain IDs for EVM chains
CHAIN_IDS = {
    Chain.ETHEREUM: 1,
    Chain.BASE: 8453,
    Chain.ARBITRUM: 42161,
    Chain.OPTIMISM: 10,
    Chain.POLYGON: 137,
    Chain.AVALANCHE: 43114,
    Chain.BSC: 56,
}


@dataclass
class ChainConfig:
    """Configuration for a blockchain connection."""

    chain: Chain
    rpc_url: Optional[str] = None
    chain_id: Optional[int] = None
    explorer_url: Optional[str] = None

    def __post_init__(self):
        if self.rpc_url is None:
            self.rpc_url = DEFAULT_RPCS.get(self.chain)
        if self.chain_id is None:
            self.chain_id = CHAIN_IDS.get(self.chain)

    @property
    def is_evm(self) -> bool:
        """Check if chain is EVM-compatible."""
        return self.chain != Chain.SOLANA

    @property
    def explorer(self) -> str:
        """Get block explorer URL."""
        explorers = {
            Chain.ETHEREUM: "https://etherscan.io",
            Chain.BASE: "https://basescan.org",
            Chain.ARBITRUM: "https://arbiscan.io",
            Chain.OPTIMISM: "https://optimistic.etherscan.io",
            Chain.POLYGON: "https://polygonscan.com",
            Chain.AVALANCHE: "https://snowtrace.io",
            Chain.BSC: "https://bscscan.com",
            Chain.SOLANA: "https://solscan.io",
        }
        return self.explorer_url or explorers.get(self.chain, "")


class ChainManager:
    """Manage connections to multiple blockchain networks."""

    def __init__(self, chains: list[Chain], rpcs: Optional[dict[Chain, str]] = None):
        self.configs = {}
        for chain in chains:
            rpc = (rpcs or {}).get(chain)
            self.configs[chain] = ChainConfig(chain=chain, rpc_url=rpc)

    def get_config(self, chain: Chain) -> ChainConfig:
        """Get configuration for a chain."""
        if chain not in self.configs:
            raise ValueError(f"Chain {chain.value} not configured")
        return self.configs[chain]

    def get_web3(self, chain: Chain):
        """Get Web3 instance for a chain."""
        config = self.get_config(chain)
        if not config.is_evm:
            raise ValueError(f"Chain {chain.value} is not EVM — use get_solana() instead")

        from web3 import Web3
        return Web3(Web3.HTTPProvider(config.rpc_url))

    def get_solana(self):
        """Get Solana client."""
        from solana.rpc.api import Client
        config = self.get_config(Chain.SOLANA)
        return Client(config.rpc_url)

    def list_chains(self) -> list[Chain]:
        """List configured chains."""
        return list(self.configs.keys())
