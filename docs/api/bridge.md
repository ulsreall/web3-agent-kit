# Bridge Agent

Cross-chain bridge agent — find best routes and execute transfers.

The `BridgeAgent` supports Li.Fi and Socket bridge aggregators for
finding the best cross-chain transfer routes.

---

## Classes

::: src.bridge.BridgeAgent
    options:
      members:
        - get_routes
        - transfer
      show_root_heading: true
      show_source: true

---

::: src.bridge.BridgeRoute
    options:
      members:
        - to_dict
      show_root_heading: true
      show_source: true

---

::: src.bridge.BridgeResult
    options:
      members:
        - to_dict
      show_root_heading: true
      show_source: true

---

## Usage

### Get Bridge Routes

```python
from web3_agent_kit import BridgeAgent, Wallet, Chain, ChainManager

chain_manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE])
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)

bridge = BridgeAgent(chain_manager, wallet)

# Get available routes
routes = bridge.get_routes("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)

for route in routes:
    print(f"{route.bridge_name}:")
    print(f"  Amount out: {route.amount_out:.6f} ETH")
    print(f"  Fee: ${route.fee_usd:.2f}")
    print(f"  Time: ~{route.time_estimate // 60} min")
```

### Execute Transfer

```python
# Use best route automatically
result = bridge.transfer("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)
print(f"TX: {result.tx_hash}")

# Or specify a route
routes = bridge.get_routes("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)
result = bridge.transfer("ETH", 0.1, Chain.ETHEREUM, Chain.BASE, route=routes[0])
```

### Export Results

```python
result = bridge.transfer("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)
data = result.to_dict()

import json
print(json.dumps(data, indent=2))
```

---

## Supported Bridges

| Bridge | Type | Chains |
|--------|------|--------|
| **Li.Fi** | Aggregator | Ethereum, Base, Arbitrum, Optimism, Polygon, Avalanche, BSC |
| **Socket** | Aggregator | Ethereum, Base, Arbitrum, Optimism, Polygon, Avalanche, BSC |

---

## Token Resolution

The bridge agent automatically resolves token symbols:

- `"ETH"` / `"NATIVE"` → Native token (0xEeee...eEEeE)
- `"WETH"` → Wrapped ETH on the chain
- `"USDC"`, `"USDT"`, etc. → Known token addresses
- `"0x..."` → Treated as contract address
