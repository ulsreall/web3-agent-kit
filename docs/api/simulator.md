# Transaction Simulator

`TxSimulator` simulates a transaction with an RPC endpoint using the configured
simulation mode. Simulation does not broadcast the transaction.

```python
from web3_agent_kit.simulator import TxSimulator

simulator = TxSimulator(rpc_url="https://base.example-rpc.com")
result = simulator.simulate(
    from_address="0x...",
    to="0x...",
    data="0x...",
    value=0,
)
print(f"Revert: {not result.success}, Gas: {result.gas_used}")
```

The `value` argument is in wei. `SimResult` provides `success`, `gas_used`,
`error`, `revert_reason`, and warning/event details. The simulator class is
`TxSimulator` and takes `rpc_url`, not a `ChainManager`.
