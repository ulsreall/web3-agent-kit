# DeFi Tools

DeFi protocol integrations — Uniswap, Aerodrome, Aave, Curve.

---

## Base Class

::: src.defi.DeFiTool
    options:
      members:
        - execute
      show_root_heading: true
      show_source: true

---

## Uniswap V2

::: src.defi.Uniswap
    options:
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

::: src.defi.Aerodrome
    options:
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

::: src.defi.Aave
    options:
      show_root_heading: true
      show_source: true

!!! note "Coming Soon"
    Aave lending/borrowing integration is not yet implemented.

---

## Curve

::: src.defi.Curve
    options:
      show_root_heading: true
      show_source: true

!!! note "Coming Soon"
    Curve stableswap integration is not yet implemented.

---

## Data Classes

::: src.defi.SwapResult
    options:
      show_root_heading: true
      show_source: true

---

::: src.defi.YieldOpportunity
    options:
      show_root_heading: true
      show_source: true
