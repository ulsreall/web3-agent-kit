# 🤖 Web3 Agent Kit

> **Build autonomous AI agents that interact with blockchains — in minutes, not months.**

[![PyPI](https://img.shields.io/pypi/v/web3-agent-kit.svg)](https://pypi.org/project/web3-agent-kit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/ulsreall/web3-agent-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/ulsreall/web3-agent-kit/actions)
[![Coverage](https://img.shields.io/badge/coverage-45%25-yellow.svg)](https://github.com/ulsreall/web3-agent-kit#readme)
[![Twitter](https://img.shields.io/twitter/follow/itseywacc?style=social)](https://twitter.com/itseywacc)

<p align="center">
  <img src="assets/demo.gif" alt="Web3 Agent Kit Demo" width="700"/>
</p>

---

## 🤔 Why Web3 Agent Kit?

Building AI agents that interact with blockchains is **hard**. You need to juggle RPC providers, wallet management, transaction signing, gas estimation, DeFi protocol ABIs, LLM integration, and safety rails — all before writing a single line of business logic.

**Web3 Agent Kit handles all of that for you.**

| Pain Point | Without Web3 Agent Kit | With Web3 Agent Kit |
|------------|------------------------|---------------------|
| **Setup** | Days of boilerplate | `pip install` → 5 lines of code |
| **Multi-chain** | Write adapters per chain | Built-in for 7+ chains |
| **LLM Integration** | Manual prompt engineering | Natural language goals, auto-parsed |
| **Safety** | Build your own guardrails | Spend limits, kill switch, operator confirmation |
| **DeFi** | Read docs, write ABIs | Drop-in Uniswap, Aave, bridges |
| **Error Handling** | Manual retry logic | Auto-fallback across LLM providers & RPCs |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User / Application                          │
│                    "Swap 0.1 ETH to USDC on Base"                  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Agent Framework                            │
│  ┌───────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │ Goal      │→ │ LLM Planner  │→ │ Tool        │→ │ Transaction│ │
│  │ Parser    │  │ (cascade)    │  │ Router      │  │ Executor   │ │
│  └───────────┘  └──────────────┘  └─────────────┘  └─────┬──────┘ │
└───────────────────────────────────────────────────────────┼────────┘
                                                            │
                               ┌────────────────────────────┼────────┐
                               │         Safety Layer       │        │
                               │  ┌─────────────────────────┼──────┐ │
                               │  │ Spend Governor          │      │ │
                               │  │ • Per-tx limits         │      │ │
                               │  │ • Daily caps            │      │ │
                               │  │ • Kill switch           │      │ │
                               │  │ • Operator confirmation │      │ │
                               │  └─────────────────────────┘      │ │
                               └────────────────────────────────────┘
                                                            │
                               ┌────────────────────────────┼────────┐
                               │      Tool Ecosystem        │        │
                               │  ┌─────────┐ ┌──────────┐ │        │
                               │  │ Uniswap │ │ Bridge   │ │        │
                               │  │ V2/V3   │ │ Agg.     │ │        │
                               │  ├─────────┤ ├──────────┤ │        │
                               │  │ Sniper  │ │ Portfolio│ │        │
                               │  │ Module  │ │ Tracker  │ │        │
                               │  └─────────┘ └──────────┘ │        │
                               └────────────────────────────┼────────┘
                                                            │
                               ┌────────────────────────────┼────────┐
                               │    Chain Abstraction Layer  │        │
                               │  ┌──────┐ ┌──────┐ ┌────┐ │        │
                               │  │ ETH  │ │ BASE │ │ARB │ │        │
                               │  ├──────┤ ├──────┤ ├────┤ │        │
                               │  │ OP   │ │ MATIC│ │AVAX│ │        │
                               │  ├──────┤ ├──────┤ ├────┤ │        │
                               │  │ BSC  │ │      │ │    │ │        │
                               │  └──────┘ └──────┘ └────┘ │        │
                               └────────────────────────────────────┘
```

---

## 📊 Comparison vs Alternatives

| Feature | Web3 Agent Kit | LangChain + Web3 | Custom Bot | Goat SDK |
|---------|:--------------:|:----------------:|:----------:|:--------:|
| **Setup Time** | Minutes | Hours | Days | Hours |
| **Multi-chain** | 7+ chains | Manual | Manual | Limited |
| **Built-in LLM** | 6 providers | DIY | ❌ | ❌ |
| **DeFi Tools** | Uniswap, Aave, bridges | ❌ | ❌ | Limited |
| **Token Sniper** | ✅ | ❌ | ❌ | ❌ |
| **Safety Rails** | ✅ Governor | ❌ | ❌ | ❌ |
| **Natural Language** | ✅ | Partial | ❌ | ❌ |
| **Python Native** | ✅ | ✅ | Varies | ❌ (TS) |
| **Type Hints** | ✅ | Partial | Varies | N/A |
| **Active Maintenance** | ✅ | ✅ | Depends | Limited |

---

## 🎯 Quick Start

### 1. Install

```bash
pip install web3-agent-kit
```

### 2. Set Environment Variables

```bash
# Required: Wallet private key
export PRIVATE_KEY="0x..."

# Required: At least one LLM provider key
export OPENAI_API_KEY="sk-..."        # OpenAI
export ANTHROPIC_API_KEY="sk-ant-..."  # Anthropic (best reasoning)
export GROQ_API_KEY="gsk_..."          # Groq (fastest)
export DEEPSEEK_API_KEY="sk-..."       # DeepSeek (cheapest)

# Optional: Custom RPC endpoints (public defaults are provided)
export ETH_RPC="https://..."
export BASE_RPC="https://..."
```

### 3. Write Your First Agent

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

# Natural language swap — that's it!
result = agent.run("Swap 0.1 ETH to USDC on Base")
print(result)
```

### 4. Run It

```bash
python my_agent.py
```

> 💡 **Tip:** Start with a small amount on a testnet or use `dry_run=True` mode to validate behavior before going live.

---

## ✨ Features

### 🤖 Core
- 🔗 **Multi-chain support** — Ethereum, Base, Arbitrum, Optimism, Polygon, Avalanche, BSC
- 🧠 **LLM-powered reasoning** — Multi-provider cascade (OpenAI, Anthropic, Groq, DeepSeek, OpenRouter, Kimi)
- 🎯 **Natural language goals** — Tell the agent what to do in plain English
- 🔐 **Governed signing** — Safety caps, kill-switch, operator confirmation

### 💰 DeFi
- 💱 **Uniswap V2 swaps** — Actual token swaps with quotes, approvals, slippage protection
- 🌉 **Cross-chain bridges** — Li.Fi + Socket aggregators for best routes
- 📊 **Portfolio tracking** — Real-time balances, P&L across all chains

### 🔫 Sniper
- 🎯 **Token sniper** — Monitor new liquidity pools, auto-buy safe tokens
- 🛡️ **Risk assessment** — Honeypot detection, liquidity checks, contract analysis
- ⚡ **Live monitoring** — Background thread with callback alerts

---

## 🎯 Showcase

### Telegram Bot
A full-featured Telegram bot built with web3-agent-kit:

```bash
cd showcase/telegram-bot
pip install -r requirements.txt
python bot.py
```

Features: balance check, token swap, portfolio tracking, token sniper, cross-chain bridge.

[![Telegram Bot Demo](showcase/telegram-bot/demo.gif)](showcase/telegram-bot/)

---

## 📦 Examples

| Example | Description |
|---------|-------------|
| `examples/llm_swap_agent.py` | LLM-powered natural language swapping |
| `examples/direct_swap.py` | Programmatic Uniswap swap without LLM |
| `examples/token_sniper.py` | Monitor new pairs, auto-buy safe tokens |
| `examples/portfolio_dashboard.py` | Real-time portfolio across chains |
| `examples/bridge_agent.py` | Cross-chain transfers via Li.Fi/Socket |
| `examples/swap_agent.py` | Autonomous token swapping |
| `examples/yield_optimizer.py` | Cross-chain yield farming |
| `examples/airdrop_farmer.py` | Multi-chain airdrop farming |
| `examples/sniper_bot.py` | Token launch sniper |
| `examples/portfolio_tracker.py` | Portfolio tracking & reporting |

---

## 🧠 LLM Integration

Multi-provider cascade with automatic fallback:

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

## 🔫 Token Sniper

Monitor new liquidity pools and auto-buy safe tokens:

```python
from web3_agent_kit import TokenSniper, SniperConfig, RiskLevel

config = SniperConfig(
    max_buy=0.005,          # max 0.005 ETH per snipe
    auto_buy=True,          # auto-buy safe tokens
    honeypot_check=True,    # check if token is honeypot
    min_liquidity=0.5,      # min 0.5 ETH liquidity
)

sniper = TokenSniper(chain_manager, wallet, config, uniswap=uniswap)

# Scan recent blocks
pairs = sniper.scan_recent_blocks(num_blocks=100, chain=Chain.BASE)

# Or start live monitoring
sniper.start(chain=Chain.BASE, poll_interval=12)
```

---

## 📊 Portfolio Dashboard

Track balances and P&L across chains:

```python
from web3_agent_kit import PortfolioTracker

tracker = PortfolioTracker(chain_manager, wallet)
summary = tracker.get_summary()

print(summary)
# 📊 Portfolio: 0x1234...
# 💰 Total Value: $12,345.67
#
#   🔗 ETHEREUM: $8,000.00
#      Native: 1.5000 ETH ($5,250.00)
#      USDC: 2750.0000 ($2,750.00)
#
#   🔗 BASE: $4,345.67
#      Native: 1.2000 ETH ($4,200.00)
#      USDC: 145.6700 ($145.67)
```

---

## 🌉 Bridge Agent

Cross-chain transfers via Li.Fi and Socket:

```python
from web3_agent_kit import BridgeAgent

bridge = BridgeAgent(chain_manager, wallet)

# Get best routes
routes = bridge.get_routes("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)

for route in routes:
    print(f"{route.bridge_name}: {route.amount_out:.6f} ETH (fee: ${route.fee_usd:.2f})")

# Execute transfer
result = bridge.transfer("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)
print(f"TX: {result.tx_hash}")
```

---

## 📁 Project Structure

```
web3-agent-kit/
├── src/
│   ├── __init__.py    # Package exports
│   ├── agent.py       # Agent framework + LLM reasoning
│   ├── llm.py         # Multi-provider LLM client
│   ├── wallet.py      # Wallet management + signing
│   ├── chain.py       # Multi-chain RPC + config
│   ├── sniper.py      # Token sniper + monitoring
│   ├── portfolio.py   # Portfolio tracking + P&L
│   ├── bridge.py      # Cross-chain bridge agent
│   └── defi/
│       ├── __init__.py  # Uniswap, Aerodrome, Aave, Curve
├── examples/           # Ready-to-use examples
├── tests/              # Test suite
└── docs/               # Documentation
```

---

## ⚡ Benchmarks

> 📝 *Benchmarks will be published after v1.0 release. Numbers below are preliminary estimates on standard hardware.*

| Metric | Value | Notes |
|--------|-------|-------|
| Swap execution (incl. LLM) | ~3–8s | Depends on LLM provider |
| Swap execution (no LLM) | ~1–3s | Direct RPC interaction |
| Portfolio fetch (7 chains) | ~2–4s | Parallel RPC calls |
| Sniper block scan (100 blocks) | ~5–10s | Per chain |
| Bridge route discovery | ~1–2s | Aggregator API latency |

*Benchmarks run on: Python 3.11, 4-core CPU, SSD, public RPC endpoints.*

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

| Chain | Status | Uniswap | Bridge |
|-------|--------|---------|--------|
| Ethereum | ✅ | ✅ | ✅ |
| Base | ✅ | ✅ | ✅ |
| Arbitrum | ✅ | ✅ | ✅ |
| Optimism | ✅ | ✅ | ✅ |
| Polygon | ✅ | ✅ | ✅ |
| Avalanche | ✅ | — | ✅ |
| BSC | ✅ | — | ✅ |
| Solana | 🔜 | — | — |

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
- [Li.Fi](https://li.fi) / [Socket](https://socket.tech) — Bridge aggregators

---

**Built by [Maulana](https://github.com/ulsreall)** · [Twitter](https://twitter.com/itseywacc)
