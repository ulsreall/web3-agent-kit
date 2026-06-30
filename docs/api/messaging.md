# Cross-chain Messaging

LayerZero, Wormhole, and CCIP unified API.

## Classes

### `LayerZeroBridge`

### `WormholeBridge`

### `CCIPBridge`

```python
from web3_agent_kit.messaging import LayerZeroBridge

lz = LayerZeroBridge(chain_manager=cm)
quote = lz.estimate_fee(src_chain=1, dst_chain=8453, message=b"hello")
lz.send(src_chain=1, dst_chain=8453, message=b"hello", wallet=wallet)
```
