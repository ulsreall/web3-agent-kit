# Oracle Module

Multi-source price aggregation with automatic fallback.

## Classes

### `OracleAggregator`

Aggregates prices from multiple oracle sources.

```python
from web3_agent_kit.oracle import OracleAggregator

oracle = OracleAggregator()
price = oracle.get_price("ETH")
print(f"ETH: ${price.usd:.2f}")
```

### `AggregatedPrice`

Contains `usd`, `sources`, `timestamp`, and `confidence` fields.

### `PricePoint`

Single source price data: `source`, `price`, `timestamp`.

### `OracleSource`

Enum: `CHAINLINK`, `DEXSCREENER`, `COINGECKO`.
