# Portfolio Tracker

Portfolio dashboard — real-time balance, P&L, positions across chains.

The `PortfolioTracker` tracks wallet balances, token holdings, and calculates
total portfolio value across multiple chains.

---

## Classes

::: src.portfolio.PortfolioTracker
    options:
      members:
        - get_summary
        - get_history
        - get_pnl
      show_root_heading: true
      show_source: true

---

::: src.portfolio.PortfolioSummary
    options:
      members:
        - to_dict
      show_root_heading: true
      show_source: true

---

::: src.portfolio.ChainPortfolio
    options:
      members:
        - to_dict
      show_root_heading: true
      show_source: true

---

::: src.portfolio.TokenBalance
    options:
      members:
        - to_dict
      show_root_heading: true
      show_source: true

---

## Usage

### Get Portfolio Summary

```python
from web3_agent_kit import PortfolioTracker, Wallet, Chain, ChainManager

chain_manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM])
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)

tracker = PortfolioTracker(chain_manager, wallet)
summary = tracker.get_summary()

print(summary)
# 📊 Portfolio: 0x1234...
# 💰 Total Value: $12,345.67
#
#   🔗 ETHEREUM: $8,000.00
#      Native: 1.5000 ETH ($5,250.00)
#      USDC: 2750.0000 ($2,750.00)
```

### Track P&L

```python
# Take initial snapshot
tracker.get_summary()

# ... time passes ...

# Take another snapshot
tracker.get_summary()

# Calculate P&L
pnl = tracker.get_pnl()
print(f"P&L: ${pnl['pnl_absolute']:.2f} ({pnl['pnl_percent']:.1f}%)")
```

### Export as JSON

```python
summary = tracker.get_summary()
data = summary.to_dict()

import json
print(json.dumps(data, indent=2))
```

---

## Known Tokens

The tracker automatically detects these tokens:

| Chain | Tokens |
|-------|--------|
| Ethereum | WETH, USDC, USDT, DAI, WBTC, LINK, UNI |
| Base | WETH, USDC, USDbC, DAI, AERO |
| Arbitrum | WETH, USDC, USDT, ARB, GMX |
