# Examples

Ready-to-use code examples for common Web3 Agent Kit use cases.

---

## 🔄 LLM-Powered Swap Agent

Natural language token swapping with LLM reasoning.

**File:** `examples/llm_swap_agent.py`

```python
"""LLM-powered natural language swapping agent."""

from web3_agent_kit import Agent, Wallet, Chain, ChainManager
from web3_agent_kit.defi import Uniswap

def main():
    # Setup
    chain_manager = ChainManager(chains=[Chain.BASE])
    wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
    uniswap = Uniswap(chain_manager=chain_manager)

    # Create agent
    agent = Agent(
        wallet=wallet,
        chains=[Chain.BASE],
        tools=[uniswap],
        verbose=True,
    )

    # Run with natural language goal
    result = agent.run("Swap 0.01 ETH to USDC on Base")
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
```

---

## 💱 Direct Swap

Programmatic Uniswap swap without LLM.

**File:** `examples/direct_swap.py`

```python
"""Programmatic Uniswap swap without LLM."""

from web3_agent_kit import Wallet, Chain, ChainManager
from web3_agent_kit.defi import Uniswap

def main():
    chain_manager = ChainManager(chains=[Chain.BASE])
    wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
    uniswap = Uniswap(chain_manager=chain_manager)

    # Get quote first
    quote = uniswap.get_quote(
        token_in="ETH",
        token_out="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
        amount=0.01,
        chain=Chain.BASE,
    )
    print(f"Quote: 0.01 ETH = {quote['amount_out']:.2f} USDC")

    # Execute swap
    result = uniswap.execute(
        wallet=wallet,
        token_in="ETH",
        token_out="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        amount=0.01,
        chain=Chain.BASE,
    )
    print(f"TX: {result.tx_hash}")
    print(f"Swapped {result.amount_in} → {result.amount_out} USDC")

if __name__ == "__main__":
    main()
```

---

## 🔫 Token Sniper

Monitor new pairs and auto-buy safe tokens.

**File:** `examples/token_sniper.py`

```python
"""Monitor new liquidity pools and auto-buy safe tokens."""

from web3_agent_kit import TokenSniper, SniperConfig, Chain, ChainManager, Wallet
from web3_agent_kit.defi import Uniswap

def on_new_pair(pair):
    """Callback for new pair detection."""
    print(f"🚨 New pair detected!")
    print(f"   Token: {pair.token_symbol} ({pair.token_name})")
    print(f"   Risk: {pair.risk_level.value}")
    print(f"   Liquidity: {pair.liquidity_eth:.2f} ETH")
    print(f"   Score: {pair.score:.1f}/100")

def main():
    chain_manager = ChainManager(chains=[Chain.BASE])
    wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
    uniswap = Uniswap(chain_manager=chain_manager)

    config = SniperConfig(
        max_buy=0.005,
        auto_buy=True,
        honeypot_check=True,
        min_liquidity=0.5,
        callback=on_new_pair,
    )

    sniper = TokenSniper(chain_manager, wallet, config, uniswap=uniswap)

    # Option 1: Scan recent blocks
    print("Scanning recent blocks...")
    pairs = sniper.scan_recent_blocks(num_blocks=100, chain=Chain.BASE)
    print(f"Found {len(pairs)} new pairs")

    # Option 2: Start live monitoring
    # print("Starting live monitor...")
    # sniper.start(chain=Chain.BASE, poll_interval=12)

if __name__ == "__main__":
    main()
```

---

## 📊 Portfolio Dashboard

Real-time portfolio tracking across chains.

**File:** `examples/portfolio_dashboard.py`

```python
"""Real-time portfolio across chains."""

from web3_agent_kit import PortfolioTracker, Wallet, Chain, ChainManager

def main():
    chain_manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM])
    wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)

    tracker = PortfolioTracker(chain_manager, wallet)

    # Get full portfolio
    summary = tracker.get_summary()
    print(summary)
    print()

    # Get P&L over time
    pnl = tracker.get_pnl()
    if pnl["pnl_absolute"] != 0:
        print(f"P&L: ${pnl['pnl_absolute']:.2f} ({pnl['pnl_percent']:.1f}%)")

if __name__ == "__main__":
    main()
```

---

## 🌉 Bridge Agent

Cross-chain transfers via Li.Fi and Socket.

**File:** `examples/bridge_agent.py`

```python
"""Cross-chain transfers via Li.Fi/Socket."""

from web3_agent_kit import BridgeAgent, Wallet, Chain, ChainManager

def main():
    chain_manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE])
    wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)

    bridge = BridgeAgent(chain_manager, wallet)

    # Get available routes
    print("Finding bridge routes...")
    routes = bridge.get_routes("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)

    for route in routes:
        print(f"  {route.bridge_name}:")
        print(f"    Amount out: {route.amount_out:.6f} ETH")
        print(f"    Fee: ${route.fee_usd:.2f}")
        print(f"    Time: ~{route.time_estimate // 60} min")
        print()

    # Execute best route
    if routes:
        print(f"Using best route: {routes[0].bridge_name}")
        result = bridge.transfer("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)
        print(f"TX: {result.tx_hash}")

if __name__ == "__main__":
    main()
```

---

## 🤖 Swap Agent

Autonomous token swapping agent.

**File:** `examples/swap_agent.py`

```python
"""Autonomous token swapping agent."""

from web3_agent_kit import Agent, Wallet, Chain, ChainManager
from web3_agent_kit.defi import Uniswap

def main():
    chain_manager = ChainManager(chains=[Chain.BASE, Chain.ETHEREUM])
    wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)

    # Register multiple tools
    uniswap_base = Uniswap(chain_manager=chain_manager)
    uniswap_eth = Uniswap(chain_manager=chain_manager)

    agent = Agent(
        wallet=wallet,
        chains=[Chain.BASE, Chain.ETHEREUM],
        tools=[uniswap_base, uniswap_eth],
        max_steps=10,
        verbose=True,
    )

    # Complex multi-step goal
    result = agent.run(
        "Check my balances on Base and Ethereum. "
        "If I have more than 0.1 ETH on Base, swap 0.05 ETH to USDC."
    )
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
```

---

## 🌾 Yield Optimizer

Cross-chain yield farming optimizer (coming soon).

**File:** `examples/yield_optimizer.py`

```python
"""Cross-chain yield farming optimizer."""

from web3_agent_kit import Agent, Wallet, Chain, ChainManager
from web3_agent_kit.defi import Uniswap, Aave

def main():
    chain_manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM])
    wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)

    # Note: Aave integration is coming soon
    agent = Agent(
        wallet=wallet,
        chains=[Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM],
        tools=[Uniswap(chain_manager=chain_manager)],
        verbose=True,
    )

    result = agent.run(
        "Find the best yield opportunity across Ethereum, Base, and Arbitrum. "
        "Compare APYs and suggest where to deposit."
    )
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
```

---

## 🪂 Airdrop Farmer

Multi-chain airdrop farming strategy (coming soon).

**File:** `examples/airdrop_farmer.py`

```python
"""Multi-chain airdrop farming agent."""

from web3_agent_kit import Agent, Wallet, Chain, ChainManager
from web3_agent_kit.defi import Uniswap

def main():
    chain_manager = ChainManager(chains=[Chain.BASE, Chain.ARBITRUM, Chain.OPTIMISM])
    wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)

    agent = Agent(
        wallet=wallet,
        chains=[Chain.BASE, Chain.ARBITRUM, Chain.OPTIMISM],
        tools=[Uniswap(chain_manager=chain_manager)],
        verbose=True,
    )

    result = agent.run(
        "Perform a small swap on each chain (Base, Arbitrum, Optimism) "
        "to generate on-chain activity for potential airdrops. "
        "Use 0.001 ETH per swap."
    )
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
```

---

## 📈 Portfolio Tracker

Portfolio tracking and reporting.

**File:** `examples/portfolio_tracker.py`

```python
"""Portfolio tracking and reporting."""

import time
from web3_agent_kit import PortfolioTracker, Wallet, Chain, ChainManager

def main():
    chain_manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE])
    wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)

    tracker = PortfolioTracker(chain_manager, wallet)

    # Take snapshots over time
    for i in range(3):
        summary = tracker.get_summary()
        print(f"\n--- Snapshot {i + 1} ---")
        print(summary)
        print(f"Total: ${summary.total_value_usd:,.2f}")

        if i < 2:
            print("Waiting 60 seconds...")
            time.sleep(60)

    # Calculate P&L
    pnl = tracker.get_pnl()
    print(f"\n--- P&L Report ---")
    print(f"Initial: ${pnl['initial_value']:,.2f}")
    print(f"Current: ${pnl['current_value']:,.2f}")
    print(f"P&L: ${pnl['pnl_absolute']:,.2f} ({pnl['pnl_percent']:.1f}%)")

if __name__ == "__main__":
    main()
```

---

## 🎯 Telegram Bot

A full-featured Telegram bot built with Web3 Agent Kit.

See the `showcase/telegram-bot/` directory for a complete implementation with:

- Balance checking
- Token swapping
- Portfolio tracking
- Token sniper
- Cross-chain bridge

```bash
cd showcase/telegram-bot
pip install -r requirements.txt
python bot.py
```

---

## 📁 Example Files

All examples are available in the `examples/` directory:

| File | Description |
|------|-------------|
| `llm_swap_agent.py` | LLM-powered natural language swapping |
| `direct_swap.py` | Programmatic Uniswap swap without LLM |
| `token_sniper.py` | Monitor new pairs, auto-buy safe tokens |
| `portfolio_dashboard.py` | Real-time portfolio across chains |
| `bridge_agent.py` | Cross-chain transfers via Li.Fi/Socket |
| `swap_agent.py` | Autonomous token swapping |
| `yield_optimizer.py` | Cross-chain yield farming |
| `airdrop_farmer.py` | Multi-chain airdrop farming |
| `sniper_bot.py` | Token launch sniper |
| `portfolio_tracker.py` | Portfolio tracking & reporting |
