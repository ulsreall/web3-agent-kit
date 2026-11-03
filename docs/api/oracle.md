# Oracle Module

`OracleAggregator` combines available price sources. It requires an RPC URL;
price-source availability depends on the pair and configured sources.

```python
from web3_agent_kit.oracle import OracleAggregator

oracle = OracleAggregator(rpc_url="https://eth.example-rpc.com")
price = oracle.get_price("ETH", "USD")
print(f"{price.pair}: ${price.price:.2f} from {price.num_sources} sources")
```

`AggregatedPrice` contains `pair`, `price`, `sources`, `num_sources`,
`deviation`, `timestamp`, and `stale`. Each `PricePoint` contains a source,
price, timestamp, and confidence. The supported enum members are defined by
`OracleSource` (including `CHAINLINK`, `PYTH`, `REDSTONE`, `DEX_SCREENER`, and
`COINGECKO`).
