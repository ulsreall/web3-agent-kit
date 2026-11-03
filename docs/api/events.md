# Events Module

`EventListener` polls contract events and can deliver them to a callback or
webhook.

```python
from web3_agent_kit.events import EventListener

listener = EventListener(rpc_url="https://eth.example-rpc.com")
subscription_id = listener.subscribe(
    address="0x...",
    abi=erc20_abi,
    event="Transfer",
    callback=lambda event: print(event["args"]),
)
listener.start()
```

`subscribe` requires the contract address, ABI, and event name, plus either a
callback or `webhook_url`. Optional arguments include `webhook_headers`,
`from_block`, and `poll_interval`. Call `stop()` when monitoring should end.
Webhook settings are subscription arguments; there is no `WebhookConfig` class.
