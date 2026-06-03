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

## ✨ Features

- 🔗 **Multi-chain support** — Ethereum, Base, Arbitrum, Optimism, Polygon, Avalanche, BSC, Solana
- 🤖 **LLM-powered reasoning** — Multi-provider cascade (OpenAI, Anthropic, Groq, DeepSeek, OpenRouter, Kimi)
- 💰 **Uniswap V2 swaps** — Actual token swaps with quotes, approvals, slippage protection
- 🔐 **Governed signing** — Safety caps, kill-switch, operator confirmation
- 📊 **Portfolio management** — Track balances, positions, P&L across chains
- 🎯 **Natural language goals** — Tell the agent what to do in plain English

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

# Optional: Custom RPC endpoints
export ETH_RPC="https://..."
export BASE_RPC="https://..."
```

### Basic Usage

```python
from web3_agent_kit import Agent, Wallet, Chain
from web3_agent_kit.defi import Uniswap

# Setup
wallet = Wallet.from_env("PRIVATE_KEY")
uniswap = Uniswap(chain_manager=wallet.chain_manager, slippage=0.5)

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

### Direct Swap (No LLM)

```python
from web3_agent_kit import Wallet, Chain, ChainManager
from web3_agent_kit.defi import Uniswap

chain_manager = ChainManager(chains=[Chain.BASE])
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
uniswap = Uniswap(chain_manager=chain_manager)

# Get quote
quote = uniswap.get_quote("ETH", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", 0.1, Chain.BASE)
print(f"0.1 ETH → {quote['amount_out']:.2f} USDC")

# Execute swap
result = uniswap.execute(wallet, "ETH", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", 0.1, Chain.BASE)
print(f"TX: {result.tx_hash}")
```

---

## 📦 Examples

| Example | Description |
|---------|-------------|
| `examples/llm_swap_agent.py` | LLM-powered natural language swapping |
| `examples/direct_swap.py` | Programmatic Uniswap swap without LLM |
| `examples/swap_agent.py` | Autonomous token swapping |
| `examples/yield_optimizer.py` | Cross-chain yield farming |
| `examples/airdrop_farmer.py` | Multi-chain airdrop farming |
| `examples/sniper_bot.py` | Token launch sniper |
| `examples/portfolio_tracker.py` | Portfolio tracking & reporting |

---

## 🧠 LLM Integration

Web3 Agent Kit supports multiple LLM providers with automatic cascade fallback:

```python
from web3_agent_kit.llm import LLM

# Auto-detect from environment variables
llm = LLM()

# Cascade order: Anthropic → Kimi → OpenRouter → DeepSeek → Groq → OpenAI

# Simple chat
response = llm.chat("What is the best yield on Base?")

# JSON response
data = llm.chat_json("Analyze this swap: 0.1 ETH to USDC")
```

**Supported providers:**
- **Anthropic** (Claude) — Best reasoning
- **OpenAI** (GPT-4) — General purpose
- **Groq** (Llama) — Fastest inference
- **DeepSeek** — Cheapest
- **OpenRouter** — Multi-model fallback
- **Kimi** — Long context

---

## 🏗️ Architecture

```
web3-agent-kit/
├── src/
│   ├── agent.py      # Agent framework + LLM reasoning
│   ├── llm.py        # Multi-provider LLM client
│   ├── wallet.py     # Wallet management + signing
│   ├── chain.py      # Multi-chain RPC + config
│   └── defi/
│       ├── __init__.py  # Uniswap, Aerodrome, Aave, Curve
├── examples/          # Ready-to-use examples
├── tests/             # Test suite
└── docs/              # Documentation
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

| Chain | Status | Uniswap |
|-------|--------|---------|
| Ethereum | ✅ | ✅ |
| Base | ✅ | ✅ |
| Arbitrum | ✅ | ✅ |
| Optimism | ✅ | ✅ |
| Polygon | ✅ | ✅ |
| Avalanche | ✅ | — |
| BSC | ✅ | — |
| Solana | 🔜 | — |

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
- [OpenAI](https://openai.com) / [Anthropic](https://anthropic.com) / [Groq](https://groq.com) — LLM providers
- [Uniswap](https://uniswap.org) — DEX protocol

---

**Built by [Maulana](https://github.com/ulsreall)** · [Twitter](https://twitter.com/itseywacc)
