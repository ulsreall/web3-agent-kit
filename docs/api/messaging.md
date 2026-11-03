# Cross-chain Messaging

`CrossChainMessenger` provides cross-chain message helpers. Submission is
implemented only for LayerZero and requires a configured private key and
authorization gate. Wormhole and CCIP send methods raise
`NotImplementedError`; their chain metadata, status, and fee helpers do not
submit messages.

```python
from web3_agent_kit.messaging import CrossChainMessenger

messenger = CrossChainMessenger(
    bridge="layerzero",
    rpc_url="https://arb.example-rpc.com",
    src_chain="arbitrum",
)
estimate = messenger.estimate_fee(dst_chain="optimism", payload_size=16)
print(estimate)
```

`estimate_fee` currently returns rough protocol defaults, not a live quote.
`send_message(dst_chain, dst_address, payload="0x", value=0, gas_limit=300000,
refund_address=None)` submits a LayerZero transaction and requires a configured
signing authorization pipeline. `track_status(tx_hash)` checks delivery
status. The implemented class is `CrossChainMessenger`; `LayerZeroBridge`,
`WormholeBridge`, and `CCIPBridge` are not exposed by this module.
