"""Events Module — On-chain event listener and webhook system.

Subscribe to smart contract events and trigger callbacks, webhooks,
or custom actions. Supports real-time monitoring with configurable
polling or WebSocket-based subscription.

Usage::
    from web3_agent_kit.events import EventListener, EventConfig
    
    listener = EventListener(rpc_url="https://eth.llamarpc.com")
    listener.subscribe(
        address="0x...",
        abi=erc20_abi,
        event="Transfer",
        callback=lambda event: print(f"Transfer: {event['args']}"),
    )
    listener.start()
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class EventConfig:
    """Configuration for an event listener."""
    address: str
    abi: list[dict]
    event_name: str
    callback: Callable[[dict], Any]
    from_block: int = 0  # 0 = latest
    poll_interval: float = 2.0  # seconds
    max_blocks_per_poll: int = 2000
    webhook_url: Optional[str] = None
    webhook_headers: dict = field(default_factory=dict)


@dataclass
class Subscription:
    """A single event subscription."""
    id: str
    config: EventConfig
    last_block: int = 0
    active: bool = True
    events_processed: int = 0
    errors: int = 0


class EventListener:
    """On-chain event listener with webhook support.

    Monitors blockchain events and triggers callbacks or webhooks.
    Runs in a background thread with configurable polling.

    Example::
        listener = EventListener(rpc_url="https://eth.llamarpc.com")
        
        # Subscribe to USDC Transfer events
        listener.subscribe(
            address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            abi=erc20_abi,
            event="Transfer",
            callback=lambda e: print(f"{e['args']['from']} → {e['args']['to']}: {e['args']['value']}"),
        )
        listener.start()
    """

    def __init__(self, rpc_url: str, max_subscriptions: int = 50):
        self.rpc_url = rpc_url
        self.max_subscriptions = max_subscriptions
        self._subscriptions: dict[str, Subscription] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._counter = 0

    def subscribe(
        self,
        address: str,
        abi: list[dict],
        event: str,
        callback: Optional[Callable[[dict], Any]] = None,
        webhook_url: Optional[str] = None,
        webhook_headers: Optional[dict] = None,
        from_block: int = 0,
        poll_interval: float = 2.0,
    ) -> str:
        """Subscribe to a contract event.

        Args:
            address: Contract address
            abi: Contract ABI
            event: Event name (e.g. "Transfer", "Approval")
            callback: Python callback function
            webhook_url: Optional webhook URL for HTTP POST
            webhook_headers: Custom headers for webhook
            from_block: Start block (0 = latest)
            poll_interval: Polling interval in seconds

        Returns:
            Subscription ID
        """
        if len(self._subscriptions) >= self.max_subscriptions:
            raise ValueError(f"Max subscriptions ({self.max_subscriptions}) reached")

        if not callback and not webhook_url:
            raise ValueError("Either callback or webhook_url must be provided")

        sub_id = f"sub_{int(time.time())}_{self._counter}"
        self._counter += 1

        config = EventConfig(
            address=address,
            abi=abi,
            event_name=event,
            callback=callback or (lambda e: None),
            from_block=from_block,
            poll_interval=poll_interval,
            webhook_url=webhook_url,
            webhook_headers=webhook_headers or {},
        )

        sub = Subscription(id=sub_id, config=config)
        with self._lock:
            self._subscriptions[sub_id] = sub

        logger.info(f"Subscribed to {event} on {address[:10]}... (id={sub_id})")
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """Remove a subscription."""
        with self._lock:
            if sub_id in self._subscriptions:
                self._subscriptions[sub_id].active = False
                del self._subscriptions[sub_id]
                return True
        return False

    def start(self, background: bool = True):
        """Start the event listener.

        Args:
            background: If True, run in background thread
        """
        if self._running:
            return

        self._running = True
        if background:
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
            logger.info("Event listener started in background")
        else:
            self._poll_loop()

    def stop(self):
        """Stop the event listener."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Event listener stopped")

    def _poll_loop(self):
        """Main polling loop."""
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        current_block = w3.eth.block_number

        while self._running:
            try:
                with self._lock:
                    subs = list(self._subscriptions.values())

                for sub in subs:
                    if not sub.active:
                        continue
                    try:
                        self._poll_subscription(w3, sub, current_block)
                    except Exception as e:
                        sub.errors += 1
                        logger.error(f"Poll error for {sub.id}: {e}")

                current_block = w3.eth.block_number
                time.sleep(min(s.config.poll_interval for s in subs) if subs else 2.0)
            except Exception as e:
                logger.error(f"Poll loop error: {e}")
                time.sleep(5)

    def _poll_subscription(self, w3, sub: Subscription, current_block: int):
        """Poll a single subscription for new events."""
        config = sub.config
        contract = w3.eth.contract(
            address=w3.to_checksum_address(config.address),
            abi=config.abi,
        )

        from_block = max(sub.last_block or config.from_block, current_block - config.max_blocks_per_poll)
        to_block = min(current_block, from_block + config.max_blocks_per_poll)

        if from_block >= to_block:
            return

        event_filter = getattr(contract.events, config.event_name)
        events = event_filter.get_logs(fromBlock=from_block, toBlock=to_block)

        for event in events:
            event_data = {
                "event": config.event_name,
                "address": config.address,
                "block": event.blockNumber,
                "tx_hash": event.transactionHash.hex(),
                "args": dict(event.args),
                "log_index": event.logIndex,
            }

            # Trigger callback
            try:
                config.callback(event_data)
            except Exception as e:
                logger.error(f"Callback error for {sub.id}: {e}")

            # Trigger webhook
            if config.webhook_url:
                self._send_webhook(event_data, config)

            sub.events_processed += 1

        sub.last_block = to_block

    def _send_webhook(self, event_data: dict, config: EventConfig):
        """Send event data to webhook URL."""
        import json
        import requests
        try:
            requests.post(
                config.webhook_url,
                json=event_data,
                headers={"Content-Type": "application/json", **config.webhook_headers},
                timeout=10,
            )
        except Exception as e:
            logger.error(f"Webhook error: {e}")

    def get_status(self) -> dict:
        """Get status of all subscriptions."""
        return {
            "running": self._running,
            "subscriptions": [
                {
                    "id": s.id,
                    "address": s.config.address[:10] + "...",
                    "event": s.config.event_name,
                    "active": s.active,
                    "events_processed": s.events_processed,
                    "errors": s.errors,
                    "last_block": s.last_block,
                }
                for s in self._subscriptions.values()
            ],
        }


# Pre-built common ABIs
ERC20_TRANSFER_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "owner", "type": "address"},
            {"indexed": True, "name": "spender", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Approval",
        "type": "event",
    },
]

ERC721_TRANSFER_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": True, "name": "tokenId", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
]


__all__ = [
    "EventListener",
    "EventConfig",
    "Subscription",
    "ERC20_TRANSFER_ABI",
    "ERC721_TRANSFER_ABI",
]