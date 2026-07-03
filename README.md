# 🤖 Web3 Agent Kit

> **Build autonomous AI agents that interact with blockchains — in minutes, not months.**

[![PyPI](https://img.shields.io/pypi/v/web3-agent-kit.svg)](https://pypi.org/project/web3-agent-kit/)
[![Downloads](https://img.shields.io/pypi/dm/web3-agent-kit.svg)](https://pypi.org/project/web3-agent-kit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/ulsreall/web3-agent-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/ulsreall/web3-agent-kit/actions)
[![Docs](https://img.shields.io/badge/docs-site-blue.svg)](https://web3-agent-kit.vercel.app/)
[![Website](https://img.shields.io/badge/website-live-10b981.svg)](https://web3-agent-kit.vercel.app/)
[![Coverage](https://img.shields.io/badge/coverage-58%25-green.svg)](https://github.com/ulsreall/web3-agent-kit#readme)
[![Twitter](https://img.shields.io/twitter/follow/itseywacc?style=social)](https://twitter.com/itseywacc)

<p align="center">
  <img src="assets/demo.gif" alt="Web3 Agent Kit Demo" width="700"/>
</p>

---

## ⚡ Quick Install

```bash
pip install web3-agent-kit
```

Verify installation:

```bash
wak info        # Show version, modules, chains
wak doctor      # Check dependencies
wak examples    # List 19 example scripts
```

Run your first swap:

```python
from web3_agent_kit import Agent

agent = Agent(private_key="0x...")
result = agent.execute("swap 0.01 ETH to USDC on Base")
print(result.tx_hash)
```

---

## 🤔 Why Web3 Agent Kit?

Building AI agents that interact with blockchains is **hard**. You need to juggle RPC providers, wallet management, transaction signing, gas estimation, DeFi protocol ABIs, LLM integration, and safety rails — all before writing a single line of business logic.

**Web3 Agent Kit handles all of that for you.**

| Pain Point | Without Web3 Agent Kit | With Web3 Agent Kit |
|------------|------------------------|---------------------|
| **Setup** | Days of boilerplate | `pip install` → 5 lines of code |
| **CLI** | Write Python for everything | `wak` — 7 commands, zero code |
| **Multi-chain** | Write adapters per chain | Built-in for 8 chains |
| **LLM Integration** | Manual prompt engineering | Natural language goals, auto-parsed |
| **Safety** | Build your own guardrails | Spend limits, kill switch, operator confirmation |
| **DeFi** | Read docs, write ABIs | Drop-in Uniswap V2, Uniswap V3, Aave V3, Curve, bridges |
| **Airdrops** | Manual quest hunting | Auto-track 7 platforms, multi-wallet farming |
| **Security Audit** | Manual code review | Static analysis, fuzzing, exploit PoC |
| **MEV** | Build from scratch | Arbitrage, liquidation, Flashbot support |
| **NFT** | Write ERC-721 manually | Deploy, batch mint, marketplace listing |
| **Trading** | Manual recurring buys | DCA bot, yield optimizer, token sniper |
| **Multi-wallet** | Manage keys manually | Batch ops, consolidated portfolio |
| **Restaking** | Manual protocol juggling | EigenLayer + Babylon + Solana |
| **Price Oracle** | Hardcode prices | Chainlink + DexScreener + CoinGecko aggregator |
| **TX Simulation** | Hope it works | Tenderly + eth_call pre-flight verification |
| **Account Abstraction** | Build ERC-4337 from scratch | Bundler, paymaster, factory deployment |
| **Cross-chain** | Manual bridge + relay | LayerZero + Wormhole + CCIP unified API |
| **Governance** | Check manually | Snapshot + Tally + on-chain governor tracking |
| **Extensibility** | Hard-coded logic | Plugin system — extend anything |
| **Error Handling** | Manual retry logic | Auto-fallback across LLM providers & RPCs |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User / Application                          │
│              "Swap 0.1 ETH to USDC on Base"  /  `wak agent "..."`  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Agent Framework                            │
│  ┌───────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │ Goal      │→ │ LLM Planner  │→ │ Tool        │→ │ Transaction│ │
│  │ Parser    │  │ (6 providers)│  │ Router      │  │ Executor   │ │
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
       ┌────────────────────────────────────────────────────┼────────┐
       │                    Tool Ecosystem                    │        │
       │                                                     │        │
       │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐│        │
       │  │ DeFi     │ │ Airdrop  │ │ Security │ │ MEV    ││        │
       │  │ •Uniswap │ │ •Galxe   │ │ •Static  │ │ •Arb   ││        │
       │  │ •Aerodrome│ │ •Zealy   │ │ •Fuzzing │ │ •Liq   ││        │
       │  │ •Aave    │ │ •Layer3  │ │ •Exploit │ │ •Flash ││        │
       │  │ •Curve   │ │ •Gleam   │ │ •Audit   │ │  bots  ││        │
       │  ├──────────┤ ├──────────┤ ├──────────┤ ├────────┤│        │
       │  │ Trading  │ │ NFT      │ │ Portfolio│ │ Bridge ││        │
       │  │ •DCA Bot │ │ •Deploy  │ │ •Tracker │ │ •Li.Fi ││        │
       │  │ •Sniper  │ │ •Mint    │ │ •P&L     │ │ •Socket││        │
       │  │ •Yield   │ │ •Market  │ │ •Alerts  │ │        ││        │
       │  └──────────┘ └──────────┘ └──────────┘ └────────┘│        │
       │                                                     │        │
       │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐│        │
       │  │ Gas      │ │ Wallet   │ │ Plugins  │ │Restake ││        │
       │  │ Optimizer│ │ •Multi   │ │ •Custom  │ │•Eigen  ││        │
       │  │          │ │ •Watcher │ │ •Community│ │•Babylon││        │
       │  │          │ │ •Approval│ │          │ │•Solana ││        │
       │  └──────────┘ └──────────┘ └──────────┘ └────────┘│        │
       │                                                     │        │
       │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐│        │
       │  │ Oracle   │ │ Events   │ │Simulator │ │Acct    ││        │
       │  │•Chainlink│ │•Listener │ │•Tenderly │ │Abstract││        │
       │  │•DexScrnr │ │•Webhooks │ │•eth_call │ │•ERC4337││        │
       │  │•CoinGecko│ │•Callbacks│ │•Anvil    │ │•Paymstr││        │
       │  ├──────────┤ ├──────────┤ ├──────────┤ ├────────┤│        │
       │  │Messaging │ │Governance│ │          │ │        ││        │
       │  │•LayerZero│ │•Snapshot │ │          │ │        ││        │
       │  │•Wormhole │ │•Tally    │ │          │ │        ││        │
       │  │•CCIP     │ │•On-chain │ │          │ │        ││        │
       │  └──────────┘ └──────────┘ └──────────┘ └────────┘│        │
       └────────────────────────────────────────────────────┼────────┘
                                                            │
                               ┌────────────────────────────┼────────┐
                               │    Chain Abstraction Layer  │        │
                               │  ┌──────┐ ┌──────┐ ┌────┐ │        │
                               │  │ ETH  │ │ BASE │ │ARB │ │        │
                               │  ├──────┤ ├──────┤ ├────┤ │        │
                               │  │ OP   │ │ MATIC│ │AVAX│ │        │
                               │  ├──────┤ ├──────┤ ├────┤ │        │
                               │  │ BSC  │ │ SOL  │ │    │ │        │
                               │  └──────┘ └──────┘ └────┘ │        │
                               └────────────────────────────────────┘
```

---

## 📊 Comparison vs Alternatives

| Feature | Web3 Agent Kit | LangChain + Web3 | Custom Bot | Goat SDK |
|---------|:--------------:|:----------------:|:----------:|:--------:|
| **Setup Time** | Minutes | Hours | Days | Hours |
| **Multi-chain** | 8 chains | Manual | Manual | Limited |
| **Built-in LLM** | 6 providers | DIY | ❌ | ❌ |
| **CLI Tool** | `wak` (7 cmds) | ❌ | ❌ | ❌ |
| **DeFi Tools** | Uniswap V2, Uniswap V3, Aave V3, Curve | ❌ | ❌ | Limited |
| **Airdrop Suite** | 7 platforms | ❌ | ❌ | ❌ |
| **Security Audit** | Static + Fuzz + Exploit | ❌ | ❌ | ❌ |
| **MEV Bots** | Arbitrage + Liquidation | ❌ | ❌ | ❌ |
| **NFT Tools** | Deploy + Mint + Market | ❌ | ❌ | ❌ |
| **Token Sniper** | ✅ | ❌ | ❌ | ❌ |
| **DCA Bot** | ✅ | ❌ | ❌ | ❌ |
| **Gas Optimizer** | ✅ | ❌ | ❌ | ❌ |
| **Multi-Wallet** | ✅ | ❌ | ❌ | ❌ |
| **Plugin System** | ✅ | ❌ | ❌ | ❌ |
| **Restaking** | EigenLayer + Babylon + Solana | ❌ | ❌ | ❌ |
| **Safety Rails** | ✅ Governor | ❌ | ❌ | ❌ |
| **Natural Language** | ✅ | Partial | ❌ | ❌ |
| **Python Native** | ✅ | ✅ | Varies | ❌ (TS) |
| **Type Hints** | ✅ | Partial | Varies | N/A |

---

## 🎯 Quick Start

**5 lines of code. No ceremony.**

```bash
pip install web3-agent-kit
export PRIVATE_KEY="0x..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

```python
from web3_agent_kit import Agent, Wallet, Chain, ChainManager
from web3_agent_kit.defi import Uniswap

chain = ChainManager(chains=[Chain.BASE])
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain)

agent = Agent(wallet=wallet, chains=[Chain.BASE], tools=[Uniswap(chain_manager=chain)])
result = agent.run("Swap 0.1 ETH to USDC on Base")
```

That's it. One `pip install`, two env vars, five lines of Python, and your AI agent is swapping on-chain.

**CLI?** `wak agent --goal "Swap 0.1 ETH to USDC" --chain base`

**More examples:** `wak examples` or browse [`examples/`](examples/) — 19 working scripts (DCA bot, sniper, airdrop farmer, multi-wallet, yield optimizer, bridge agent, portfolio tracker, and more).

> 💡 **Tip:** Start with `dry_run=True` on testnet to validate before going live.

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
- 📡 **37+ endpoints** — Full HTTP API for all modules
- 🔑 **API key auth** — Secure access control
- 📖 **Swagger UI** — Interactive API documentation
- 🔄 **Auto-fallback** — Multi-provider LLM cascade

### 🔌 Plugin System
- 📦 **Plugin registry** — Discover and load plugins dynamically
- 🛠️ **Custom plugins** — Extend with your own tools
- 🔄 **Hot reload** — Add plugins without restarting

### 🔄 Restaking
- 🏦 **EigenLayer integration** — Restake LSTs, delegate to operators, track rewards
- ₿ **Babylon BTC restaking** — Bitcoin restaking via Babylon protocol
- ☀️ **Solana restaking** — Solayer, Jito, Marinade support
- 📊 **Yield optimizer** — Cross-protocol restaking yield optimization with risk-adjusted scoring
- 🔔 **Slashing monitor** — Position tracking, slashing risk alerts, portfolio snapshots

### 📡 Oracle Aggregator (NEW!)
- 🔗 **Chainlink feeds** — 12+ mainnet price feeds (ETH, BTC, SOL, UNI, AAVE, etc.)
- 📈 **DexScreener** — Real-time DEX price data with liquidity ranking
- 🪙 **CoinGecko** — Free API fallback for 20+ tokens
- ⚖️ **Weighted median** — Multi-source aggregation with deviation detection
- 💾 **Smart cache** — 30s TTL, batch queries, automatic stale detection

### 📡 Event Listener (NEW!)
- 🔔 **On-chain events** — Subscribe to any contract event (Transfer, Approval, custom)
- 🌐 **Webhook support** — HTTP POST to any URL on event trigger
- 🧵 **Background polling** — Multi-subscription threaded listener
- 📦 **Pre-built ABIs** — ERC-20 Transfer/Approval, ERC-721 Transfer
- 📊 **Status tracking** — Per-subscription event count, error rate, last block

### 🧪 Transaction Simulator (NEW!)
- 🔍 **Pre-flight verification** — Simulate before broadcasting to catch reverts
- 🌐 **Tenderly integration** — Full state diff, events, gas profiling
- 🍴 **Local fork mode** — Anvil/Hardhat impersonation testing
- ⚡ **eth_call mode** — Fast simulation with gas estimation + safety margin
- ⚠️ **Smart warnings** — Balance checks, approval analysis, MEV exposure

### 🏦 Account Abstraction (NEW!)
- 📦 **ERC-4337 support** — UserOperations, EntryPoint v0.6
- 🏭 **Factory deployment** — SimpleAccount, Safe v1.4.3, Kernel v3
- 💰 **Paymaster integration** — Pimlico gas sponsorship, token paymaster
- 🔗 **Multi-chain** — Ethereum, Base, Arbitrum, Optimism, Polygon
- 📊 **Counterfactual addresses** — Pre-compute before deployment

### 🌉 Cross-chain Messaging (NEW!)
- 📡 **LayerZero** — 7 chains, endpoint registry, fee estimation
- 🐛 **Wormhole** — Multi-chain message relay, delivery tracking
- ⛓️ **Chainlink CCIP** — Chain selector registry, message verification
- 📊 **Status tracking** — Real-time delivery status via protocol APIs
- 💰 **Fee estimation** — Per-chain cost breakdown

### 🏛️ Governance (NEW!)
- 📊 **Snapshot integration** — GraphQL API, active proposal tracking
- 📈 **On-chain governor** — OpenZeppelin Governor, proposal lifecycle
- 🗳️ **Voting power** — Token-weighted voting, delegation management
- 🔍 **Tally API** — Delegate discovery, voting history
- 🏷️ **Known DAOs** — Uniswap, Aave, Arbitrum, Optimism, ENS pre-configured

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

> 💡 *Full list of endpoints available in [Swagger UI](http://localhost:8000/docs) when the server is running.*

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

[![Telegram Bot Demo](assets/demo.gif)](showcase/telegram-bot/)

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
| `examples/approval_manager.py` | Token approval scanning & management |
| `examples/gas_optimizer.py` | Gas optimization & batch operations |
| `examples/wallet_watcher.py` | Multi-wallet monitoring & alerts |

---

## 🧠 LLM Integration

Multi-provider cascade with automatic fallback:

```python
from web3_agent_kit.agent import LLM, LLMConfig

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
    OnChainConfig,
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

## 🔄 Restaking

Optimize yields across restaking protocols:

```python
from web3_agent_kit.restaking import (
    EigenLayer,
    EigenLayerConfig,
    RestakingOptimizer,
    RestakingMonitor,
    BabylonBtcRestaking,
    SolanaRestaking,
)

# EigenLayer restaking
el = EigenLayer(EigenLayerConfig(chain="ethereum"))
result = el.restake("stETH", 10.0)
print(f"Restaked: {result.tx_hash}")

# Find best restaking yield
optimizer = RestakingOptimizer()
best = optimizer.find_best_opportunity(min_apy=3.0)
print(f"Best: {best.protocol} — {best.apy}% APY")

# Monitor positions
monitor = RestakingMonitor()
snapshot = monitor.get_portfolio_snapshot()
print(f"Total staked: ${snapshot.total_value_usd:,.2f}")
print(f"Slashing risk: {snapshot.total_risk_score}")
```

---

## 📊 Project Stats

- **Version:** 1.9.0
- **Modules:** 23
- **Source Files:** 115
- **Lines of Code:** 32,743
- **Tests:** 991
- **Examples:** 19
- **Chains:** 8
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
