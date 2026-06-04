# 🤖 Web3 Agent Kit

> Open-source framework for building autonomous AI agents that interact with blockchain networks.

[![PyPI](https://img.shields.io/pypi/v/web3-agent-kit.svg)](https://pypi.org/project/web3-agent-kit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/ulsreall/web3-agent-kit/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## What is Web3 Agent Kit?

Web3 Agent Kit is a Python framework for building **AI agents that can autonomously interact with DeFi protocols**, manage wallets, execute trades, and perform complex on-chain operations across multiple blockchains.

```python
from web3_agent_kit import Agent, Wallet, Chain
from web3_agent_kit.defi import Uniswap

agent = Agent(
    wallet=Wallet.from_env("PRIVATE_KEY"),
    chains=[Chain.BASE],
    tools=[Uniswap()],
)

# Agent uses LLM reasoning to execute natural language goals
result = agent.run("Swap 0.1 ETH to USDC on Base")
```

---

## ✨ Key Features

### 🤖 Core

- **Multi-chain support** — Ethereum, Base, Arbitrum, Optimism, Polygon, Avalanche, BSC
- **LLM-powered reasoning** — Multi-provider cascade (OpenAI, Anthropic, Groq, DeepSeek, OpenRouter, Kimi)
- **Natural language goals** — Tell the agent what to do in plain English
- **Governed signing** — Safety caps, kill-switch, operator confirmation

### 💰 DeFi

- **Uniswap V2 swaps** — Actual token swaps with quotes, approvals, slippage protection
- **Cross-chain bridges** — Li.Fi + Socket aggregators for best routes
- **Portfolio tracking** — Real-time balances, P&L across all chains

### 🔫 Sniper

- **Token sniper** — Monitor new liquidity pools, auto-buy safe tokens
- **Risk assessment** — Honeypot detection, liquidity checks, contract analysis
- **Live monitoring** — Background thread with callback alerts

---

## 🚀 Quick Start

### Install

```bash
pip install web3-agent-kit
```

### Environment Variables

```bash
# Required: Wallet
export PRIVATE_KEY="0x..."

# Required: At least one LLM provider
export OPENAI_API_KEY="sk-..."        # OpenAI
export ANTHROPIC_API_KEY="sk-ant-..."  # Anthropic (best reasoning)
export GROQ_API_KEY="gsk_..."          # Groq (fastest)
export DEEPSEEK_API_KEY="sk-..."       # DeepSeek (cheapest)
```

### Basic Usage

```python
from web3_agent_kit import Agent, Wallet, Chain, ChainManager
from web3_agent_kit.defi import Uniswap

# Setup
chain_manager = ChainManager(chains=[Chain.BASE])
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
uniswap = Uniswap(chain_manager=chain_manager)

# Create agent with LLM reasoning
agent = Agent(
    wallet=wallet,
    chains=[Chain.BASE],
    tools=[uniswap],
)

# Natural language swap
result = agent.run("Swap 0.1 ETH to USDC on Base")
print(result)
```

---

## 📖 Documentation

- [Getting Started](getting-started.md) — Installation, configuration, first steps
- [Features](features.md) — Detailed feature overview
- [Examples](examples.md) — Ready-to-use code examples
- [API Reference](api/agent.md) — Full API documentation

---

## 🤝 Contributing

We welcome contributions! See the [Contributing Guide](contributing.md) for guidelines.

---

## 📄 License

MIT License — see [LICENSE](https://github.com/ulsreall/web3-agent-kit/blob/main/LICENSE) for details.

---

**Built by [Maulana](https://github.com/ulsreall)** · [Twitter](https://twitter.com/itseywacc)
