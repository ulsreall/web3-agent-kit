# Token Sniper

Token sniper — monitor new liquidity pools and auto-buy.

The `TokenSniper` monitors DEX factory contracts for new pair creation,
analyzes contract safety, and executes buys if tokens are deemed safe.

---

## Classes

::: src.sniper.TokenSniper
    options:
      members:
        - scan_recent_blocks
        - buy
        - start
        - stop
      show_root_heading: true
      show_source: true

---

::: src.sniper.SniperConfig
    options:
      show_root_heading: true
      show_source: true

---

::: src.sniper.NewPair
    options:
      members:
        - is_weth_pair
        - non_weth_token
        - to_dict
      show_root_heading: true
      show_source: true

---

::: src.sniper.RiskLevel
    options:
      show_root_heading: true
      show_source: true

---

## Usage

### Scan Recent Blocks

```python
from web3_agent_kit import TokenSniper, SniperConfig, Chain, ChainManager, Wallet
from web3_agent_kit.defi import Uniswap

chain_manager = ChainManager(chains=[Chain.BASE])
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
uniswap = Uniswap(chain_manager=chain_manager)

sniper = TokenSniper(chain_manager, wallet, uniswap=uniswap)

# Scan last 100 blocks
pairs = sniper.scan_recent_blocks(num_blocks=100, chain=Chain.BASE)

for pair in pairs:
    print(f"{pair.token_symbol}: risk={pair.risk_level.value}, liq={pair.liquidity_eth:.2f} ETH")
```

### Live Monitoring

```python
config = SniperConfig(
    max_buy=0.005,
    auto_buy=True,
    honeypot_check=True,
    min_liquidity=0.5,
    callback=lambda pair: print(f"New pair: {pair.token_symbol}"),
)

sniper = TokenSniper(chain_manager, wallet, config, uniswap=uniswap)

# Start monitoring (non-blocking)
sniper.start(chain=Chain.BASE, poll_interval=12)

# Stop monitoring
sniper.stop()
```

### Manual Buy

```python
pairs = sniper.scan_recent_blocks(num_blocks=50, chain=Chain.BASE)

for pair in pairs:
    if pair.risk_level == RiskLevel.LOW:
        tx_hash = sniper.buy(pair)
        print(f"Bought {pair.token_symbol}: {tx_hash}")
```

---

## Risk Assessment

Each token is scored 0-100 (higher = safer):

| Score | Risk Level | Action |
|-------|------------|--------|
| 70+ | `RiskLevel.LOW` | Safe to auto-buy |
| 40-69 | `RiskLevel.MEDIUM` | Review before buying |
| 20-39 | `RiskLevel.HIGH` | Avoid unless confident |
| <20 | `RiskLevel.SCAM` | Never buy |

### Scoring Factors

- **Liquidity** — +15 if above minimum, -30 if below
- **Contract code size** — +10 if reasonable, -40 if too small
- **Honeypot check** — +5 if passes
