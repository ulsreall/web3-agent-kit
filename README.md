# 🤖 Web3 Agent Kit

> Open-source framework for building autonomous AI agents that interact with blockchain networks.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/ulsreall/web3-agent-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/ulsreall/web3-agent-kit/actions)
[![Twitter](https://img.shields.io/twitter/follow/itseywacc?style=social)](https://twitter.com/itseywacc)

---

## What is this?

Web3 Agent Kit is a Python framework for building **AI agents that can autonomously interact with DeFi protocols**, manage wallets, execute trades, and perform complex on-chain operations across multiple blockchains.

```python
from web3_agent_kit import Agent, Wallet, Chain

# Create an autonomous DeFi agent
agent = Agent(
    wallet=Wallet.from_key("0x..."),
    chains=[Chain.ETHEREUM, Chain.BASE],
)

# Agent autonomously finds and executes yield opportunities
agent.run("Find the best yield farming opportunities on Base and optimize my portfolio")
```

---

## ✨ Features

- 🔗 **Multi-chain support** — Ethereum, Base, Arbitrum, Optimism, Polygon, Solana
- 🤖 **Agent framework** — Goal-driven autonomous agents with LLM reasoning
- 💰 **DeFi integrations** — Uniswap, Aave, Curve, Aerodrome, and more
- 🔐 **Governed signing** — Safety caps, kill-switch, operator confirmation
- 📊 **Portfolio management** — Track balances, positions, P&L across chains
- 🦊 **Browser automation** — Interact with dApps via stealth browser
- 📡 **Real-time monitoring** — Mempool, whale tracking, price alerts

---

## 🚀 Quick Start

### Install

```bash
pip install web3-agent-kit
```

### Basic Usage

```python
from web3_agent_kit import Agent, Wallet, Chain
from web3_agent_kit.defi import Uniswap, Aave

# Setup wallet
wallet = Wallet.from_env("PRIVATE_KEY")

# Create agent with DeFi capabilities
agent = Agent(
    wallet=wallet,
    chains=[Chain.BASE],
    tools=[Uniswap(), Aave()],
    llm="gpt-4",
)

# Run a task
result = agent.run("Swap 0.1 ETH to USDC on Base")
print(result)  # → Transaction hash, gas used, etc.
```

---

## 📦 Examples

| Example | Description |
|---------|-------------|
| `examples/swap_agent.py` | Autonomous token swapping |
| `examples/yield_optimizer.py` | Cross-chain yield farming |
| `examples/airdrop_farmer.py` | Multi-chain airdrop farming |
| `examples/sniper_bot.py` | Token launch sniper |
| `examples/portfolio_tracker.py` | Portfolio tracking & reporting |

### Airdrop Farmer

```python
from web3_agent_kit import Agent, Wallet, Chain
from web3_agent_kit.defi import Uniswap, Aerodrome

wallet = Wallet.from_env("PRIVATE_KEY")

agent = Agent(
    wallet=wallet,
    chains=[Chain.BASE, Chain.ARBITRUM, Chain.OPTIMISM],
    tools=[Uniswap(), Aerodrome()],
)

# Farm airdrops across multiple chains
agent.run("Complete daily quests and track eligibility across all chains")
```

### Token Sniper

```python
from web3_agent_kit import Agent, Wallet, Chain
from web3_agent_kit.defi import Uniswap

agent = Agent(
    wallet=Wallet.from_env("PRIVATE_KEY"),
    chains=[Chain.BASE],
    tools=[Uniswap()],
)

# Snipe new token launches
agent.run("Monitor for new liquidity adds, analyze contracts, and buy if safe")
```

### Portfolio Tracker

```python
from web3_agent_kit import Agent, Wallet, Chain

agent = Agent(
    wallet=Wallet.from_env("PRIVATE_KEY"),
    chains=[Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM],
)

# Track portfolio across chains
agent.run("Get all balances, calculate total value, identify opportunities")
```

---

## 🏗️ Architecture

```
web3-agent-kit/
├── src/
│   ├── agents/          # Agent framework & LLM integration
│   ├── chains/          # Multi-chain RPC & transaction handling
│   ├── defi/            # DeFi protocol integrations
│   └── utils/           # Wallet, signing, monitoring
├── examples/            # Ready-to-use agent examples
├── tests/               # Test suite
└── docs/                # Documentation
```

---

## 🔐 Safety

Web3 Agent Kit includes built-in safety features:

```python
from web3_agent_kit.safety import SpendGovernor, SpendLimits

governor = SpendGovernor(
    limits=SpendLimits(
        max_per_tx=0.1,      # max 0.1 ETH per transaction
        daily_limit=1.0,     # max 1 ETH per day
    ),
    require_confirm=True,    # operator must confirm
)

# Kill switch for emergencies
governor.kill()   # blocks all transactions
governor.unkill() # resume
```

---

## 🛠️ Supported Chains

| Chain | Status |
|-------|--------|
| Ethereum | ✅ |
| Base | ✅ |
| Arbitrum | ✅ |
| Optimism | ✅ |
| Polygon | ✅ |
| Avalanche | ✅ |
| BSC | ✅ |
| Solana | 🔜 |

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

Built with:
- [web3.py](https://github.com/ethereum/web3.py) — Ethereum interactions
- [LangChain](https://github.com/langchain-ai/langchain) — LLM framework
- [Foundry](https://github.com/foundry-rs/foundry) — Smart contract toolkit

---

**Built by [Maulana](https://github.com/ulsreall)** · [Twitter](https://twitter.com/itseywacc)
