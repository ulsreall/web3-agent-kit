# Chain

Multi-chain support — chain definitions and RPC management.

The `Chain` enum and `ChainManager` class handle connections to multiple
blockchain networks.

---

## Classes

::: src.chain.Chain
    options:
      show_root_heading: true
      show_source: true

---

::: src.chain.ChainManager
    options:
      members:
        - get_config
        - get_web3
        - get_solana
        - list_chains
      show_root_heading: true
      show_source: true

---

::: src.chain.ChainConfig
    options:
      members:
        - is_evm
        - explorer
      show_root_heading: true
      show_source: true

---

## Usage

### Initialize Chain Manager

```python
from web3_agent_kit import ChainManager, Chain

# Use default public RPCs
chain_manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM])

# Use custom RPCs
chain_manager = ChainManager(
    chains=[Chain.ETHEREUM, Chain.BASE],
    rpcs={
        Chain.ETHEREUM: "https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY",
        Chain.BASE: "https://base-mainnet.g.alchemy.com/v2/YOUR_KEY",
    },
)
```

### Get Web3 Instance

```python
w3 = chain_manager.get_web3(Chain.BASE)
block_number = w3.eth.block_number
```

### List Configured Chains

```python
chains = chain_manager.list_chains()
print(chains)  # [Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM]
```

---

## Supported Chains

| Chain | Chain ID | Default RPC |
|-------|----------|-------------|
| `Chain.ETHEREUM` | 1 | `https://eth.llamarpc.com` |
| `Chain.BASE` | 8453 | `https://mainnet.base.org` |
| `Chain.ARBITRUM` | 42161 | `https://arb1.arbitrum.io/rpc` |
| `Chain.OPTIMISM` | 10 | `https://mainnet.optimism.io` |
| `Chain.POLYGON` | 137 | `https://polygon-rpc.com` |
| `Chain.AVALANCHE` | 43114 | `https://api.avax.network/ext/bc/C/rpc` |
| `Chain.BSC` | 56 | `https://bsc-dataseed1.binance.org` |
| `Chain.SOLANA` | — | `https://api.mainnet-beta.solana.com` |

---

## Block Explorers

Each chain has a default block explorer URL:

```python
config = chain_manager.get_config(Chain.BASE)
print(config.explorer)  # https://basescan.org
```
