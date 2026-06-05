# 🤖 Web3 Agent Kit

> **Build autonomous AI agents that interact with blockchains — in minutes, not months.**

[![PyPI](https://img.shields.io/pypi/v/web3-agent-kit.svg)](https://pypi.org/project/web3-agent-kit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/ulsreall/web3-agent-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/ulsreall/web3-agent-kit/actions)
| [![Coverage](https://img.shields.io/badge/coverage-66%25-green.svg)](https://github.com/ulsreall/web3-agent-kit#readme) |
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
| **Yield** | Manual research, claim, compound | Auto-compound, cross-protocol APY comparison |
| **DCA** | Manual recurring buys | Automated DCA with intervals, limits, callbacks |
| **Gas** | Guess gas prices | Smart estimation, timing, batching |
| **Security** | Manual approval checks | Auto-scan & revoke risky approvals |
| **Alerts** | Manual whale tracking | Auto-monitor wallets, instant alerts |
| **Multi-wallet** | Manage keys manually | Batch ops, consolidated portfolio, wallet groups |
| **Airdrops** | Manual quest hunting | Auto-track campaigns, multi-wallet farming, Sybil-safe |
| **Token Security** | Manual research | Honeypot detection, rug pull check, contract audit |
| **Extensibility** | Hard-coded logic | Plugin system — community can extend anything |
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
| **DCA Bot** | ✅ | ❌ | ❌ | ❌ |
| **Gas Optimizer** | ✅ | ❌ | ❌ | ❌ |
| **Approval Manager** | ✅ | ❌ | ❌ | ❌ |
| **Wallet Watcher** | ✅ | ❌ | ❌ | ❌ |
| **Yield Optimizer** | ✅ | ❌ | ❌ | ❌ |
| **Multi-Wallet** | ✅ | ❌ | ❌ | ❌ |
| **Airdrops** | ✅ | ❌ | ❌ | ❌ |
| **Token Security** | ✅ | ❌ | ❌ | ❌ |
| **Plugin System** | ✅ | ❌ | ❌ | ❌ |
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

### 📈 DCA Bot
- 🔄 **Recurring buys** — Dollar-cost average into any token automatically
- ⏰ **Flexible intervals** — Hourly, daily, weekly, biweekly, monthly
- 🛑 **Spending limits** — Max buys, max total spend, auto-stop
- 📊 **Cost average analysis** — Track avg price, min/max, P&L
- 💾 **Persistent orders** — Survives restarts, stored on disk
- 🔔 **Callbacks** — Hook into execution events for notifications

### 🔒 Security Module (NEW!)
- 🍯 **Honeypot detection** — Check if token can be sold before buying
- 🧶 **Rug pull checker** — Assess rug pull risk factors
- 📝 **Contract audit** — Detect hidden mint, blacklist, pause, proxy patterns
- 💰 **Tax checker** — Buy/sell tax analysis
- 💧 **Liquidity analysis** — Locked %, lock duration
- 👥 **Holder analysis** — Concentration, whale detection
- 📊 **Safety score** — 0-100 score with risk levels
- 🌐 **GoPlus API** — Real-time token security data
- 📈 **DexScreener** — Liquidity data integration

### 🪂 Airdrop Automation (NEW!)
- 🔍 **Campaign Discovery** — Auto-scan 7 platforms (Galxe, Zealy, Layer3, QuestN, TaskOn, Intract, Port3)
- ⛓️ **On-chain Farming** — DeFi interactions for airdrops (Base, Ethereum, Arbitrum, Optimism, Scroll, Linea, zkSync)
- ⏰ **Daily Scheduler** — Automate recurring tasks with retry logic
- 📊 **Points Dashboard** — Track points across all platforms with history
- 🔗 **Referral Manager** — Generate, track, and optimize referral links
- 🚰 **Faucet Claimer** — Auto-claim testnet tokens from 12+ faucets
- 🤖 **Multi-wallet** — Sybil avoidance, wallet rotation
- 🔌 **Plugin System** — Extend with custom platform executors

### 🌐 REST API
- 📡 **18 endpoints** — Full HTTP API for all modules
- 🔑 **API key auth** — Secure access control
- 📖 **Swagger UI** — Interactive API documentation
- 🔄 **Auto-fallback** — Multi-provider LLM cascade

### 🔌 Plugin System
- 📦 **Plugin registry** — Discover and load plugins dynamically
- 🛠️ **Custom plugins** — Extend with your own tools
- 🔄 **Hot reload** — Add plugins without restarting

---

## 🌐 REST API

Full HTTP API for all modules — use from any language (JavaScript, curl, etc):

```bash
# Start the API server
python -m src.api

# Or with API key
WEB3_API_KEY=your-secret python -m src.api
```

**Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/wallet/info` | GET | Wallet info + balance |
| `/swap/quote` | GET | Get swap quote |
| `/swap/execute` | POST | Execute token swap |
| `/portfolio/` | GET | Portfolio dashboard |
| `/gas/estimate` | GET | Gas estimates (EIP-1559) |
| `/gas/recommendation` | GET | Gas timing recommendation |
| `/watcher/list` | GET | List watched wallets |
| `/watcher/add` | POST | Add wallet to watch |
| `/approval/scan` | GET | Scan token approvals |
| `/approval/risk` | GET | Risk report |
| `/dca/orders` | GET/POST | List/create DCA orders |
| `/yield/opportunities` | GET | Scan yield opportunities |
| `/yield/best` | GET | Find best yield |
| `/bridge/quote` | GET | Get bridge quote |
| `/bridge/execute` | POST | Execute bridge |
| `/health` | GET | Health check |
| `/docs` | GET | Swagger UI |
| `/redoc` | GET | ReDoc documentation |

**Example:**
```bash
# Get gas estimate
curl http://localhost:8000/gas/estimate?chain=ethereum

# Get swap quote
curl "http://localhost:8000/swap/quote?token_in=ETH&token_out=USDC&amount_in=1.0"

# Scan approvals
curl http://localhost:8000/approval/scan?chain=ethereum
```

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
| `examples/yield_optimizer.py` | Cross-protocol yield farming + auto-compound |
| `examples/multi_wallet.py` | Multi-wallet management + batch ops |
| `examples/plugin_system.py` | Plugin system usage + custom plugins |
| `examples/dca_bot.py` | Dollar-cost averaging bot with intervals & limits |
| `examples/api_server.py` | REST API server with Swagger docs |
| `examples/airdrop_farmer.py` | Multi-chain airdrop farming |
| `examples/sniper_bot.py` | Token launch sniper |
| `examples/portfolio_tracker.py` | Portfolio tracking & reporting |
| `examples/airdrop_suite.py` | Full airdrop automation suite |
| `examples/security_analysis.py` | Token security analysis |

---

## 🧠 LLM Integration

Multi-provider cascade with automatic fallback:

```python
from web3_agent_kit.llm import LLM, LLMConfig

# Use any LLM provider with automatic fallback
llm = LLM(LLMConfig(
    providers=["anthropic", "openai", "groq", "deepseek"],
    model="claude-3-5-sonnet-20241022",
))

# Natural language → structured action
action = llm.parse("Swap 0.1 ETH to USDC on Base")
# → {"tool": "uniswap", "action": "swap", "params": {...}}
```

---

## 🔒 Security Module

Analyze tokens before interacting:

```python
from web3_agent_kit.security import TokenAnalyzer, SecurityConfig

analyzer = TokenAnalyzer(SecurityConfig(chain="base"))

# Quick check
result = analyzer.quick_check("0x...")
print(f"Is Honeypot: {result['is_honeypot']}")

# Full analysis
report = analyzer.analyze_token("0x...")
print(f"Safety Score: {report.safety_score}/100")
print(f"Risk Level: {report.risk_level.value}")

if report.is_honeypot:
    print("🚨 HONEYPOT DETECTED!")
elif report.safety_score < 50:
    print("⚠️ HIGH RISK TOKEN")
else:
    print("✓ Safe to trade")
```

---

## 🪂 Airdrop Automation

Automate airdrop farming across multiple platforms:

```python
from web3_agent_kit.airdrop import (
    CampaignDiscovery,
    OnChainAirdropFarmer,
    AirdropScheduler,
    PointsDashboard,
    ReferralManager,
    FaucetClaimer,
)

# Discover new campaigns
discovery = CampaignDiscovery()
campaigns = discovery.discover_all()

# On-chain farming (dry run)
farmer = OnChainAirdropFarmer(OnChainConfig(chain="base", dry_run=True))
farmer.farm_plan("base_activity")

# Schedule daily tasks
scheduler = AirdropScheduler()
scheduler.add_daily("galxe_checkin", "09:00", galxe_checkin_fn)

# Track points
dashboard = PointsDashboard(DashboardConfig(wallet="0x..."))
dashboard.sync_all()

# Generate referrals
manager = ReferralManager()
manager.generate_links(count=10)

# Claim testnet tokens
claimer = FaucetClaimer()
claimer.claim_all(wallet="0x...")
```

---

## 📊 Project Stats

- **Version:** 1.2.0
- **Modules:** 20+
- **Tests:** 565+
- **Examples:** 18
- **Chains:** 7+
- **License:** MIT

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [Uniswap](https://uniswap.org/) — DEX protocol
- [Li.Fi](https://li.fi/) — Bridge aggregator
- [Socket](https://socket.tech/) — Bridge aggregator
- [GoPlus](https://gopluslabs.io/) — Token security API
- [DexScreener](https://dexscreener.com/) — DEX data

---

<p align="center">
  Made with ❤️ by <a href="https://twitter.com/itseywacc">@itseywacc</a>
</p>
