# DeFi Tools
DeFi protocol integrations — Uniswap, Aerodrome, Aave, Curve.
---
## Base Class

      members:
        - execute
      show_root_heading: true
      show_source: true
---
## Uniswap V2

      members:
        - execute
        - get_quote
        - resolve_token
      show_root_heading: true
      show_source: true
### Supported Chains
- Ethereum
- Base
- Arbitrum
- Optimism
- Polygon
### Usage
```python
from web3_agent_kit import Chain, ChainManager, Wallet
from web3_agent_kit.defi import Uniswap
chain_manager = ChainManager(chains=[Chain.BASE])
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
uniswap = Uniswap(chain_manager=chain_manager, slippage=0.5)
# Get quote
quote = uniswap.get_quote("ETH", "USDC", 0.1, chain=Chain.BASE)
print(f"0.1 ETH = {quote['amount_out']:.2f} USDC")
# Execute swap
result = uniswap.execute(
    wallet=wallet,
    token_in="ETH",
    token_out="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    amount=0.1,
    chain=Chain.BASE,
)
print(f"TX: {result.tx_hash}")
```
---
## Aerodrome

      show_root_heading: true
      show_source: true
Aerodrome is a DEX on Base that uses a Uniswap V2-compatible router.
```python
from web3_agent_kit.defi import Aerodrome
aerodrome = Aerodrome(chain_manager=chain_manager)
result = aerodrome.execute(wallet, "ETH", "USDC", 0.1)
```
---
## Aave

      show_root_heading: true
      show_source: true

Aave V3 lending/borrowing integration — deposit, withdraw, borrow, repay, and liquidation.

```python
from web3_agent_kit.defi import Aave

aave = Aave(chain_manager=chain_manager)

# Deposit tokens
result = aave.execute(
    wallet=wallet,
    action="deposit",
    token="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    amount=1000,
)

# Get user data
data = aave.get_user_data(wallet.address)
print(f"Health factor: {data.health_factor}")
```
---
## Curve

      show_root_heading: true
      show_source: true

Curve Finance stableswap integration — swap stablecoins across all pool types, gauge deposits.

```python
from web3_agent_kit.defi import Curve

curve = Curve(chain_manager=chain_manager)
swap_result = curve.execute(
    wallet=wallet,
    pool="0x...",
    token_in="USDC",
    token_out="USDT",
    amount=1000,
)
print(f"Swapped: {swap_result.amount_in} → {swap_result.amount_out}")
```
---
## Data Classes

      show_root_heading: true
      show_source: true
---

      show_root_heading: true
      show_source: true
