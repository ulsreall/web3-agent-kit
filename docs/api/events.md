# Events Module

On-chain event listener with webhook support.

## Classes

### `EventListener`

Subscribe to smart contract events.

```python
from web3_agent_kit.events import EventListener

listener = EventListener(chain_manager=cm)
listener.subscribe(
    contract="0x...",
    event="Transfer",
    callback=lambda event: print(event)
)
listener.start()
```

### `WebhookConfig`

Configure webhook delivery: `url`, `headers`, `secret`.
