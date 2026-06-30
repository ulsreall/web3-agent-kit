# Transaction Simulator

Simulate transactions before broadcasting.

## Classes

### `TransactionSimulator`

```python
from web3_agent_kit.simulator import TransactionSimulator

sim = TransactionSimulator(chain_manager=cm)
result = sim.simulate(
    to=router_addr,
    data=calldata,
    from_addr=wallet.address
)
print(f"Revert: {result.would_revert}, Gas: {result.gas_used}")
```

Supports: `eth_call`, Tenderly API, local fork.
