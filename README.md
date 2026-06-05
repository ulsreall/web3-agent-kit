     1|# 🤖 Web3 Agent Kit
     2|
     3|> **Build autonomous AI agents that interact with blockchains — in minutes, not months.**
     4|
     5|[![PyPI](https://img.shields.io/pypi/v/web3-agent-kit.svg)](https://pypi.org/project/web3-agent-kit/)
     6|[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
     7|[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
     8|[![CI](https://github.com/ulsreall/web3-agent-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/ulsreall/web3-agent-kit/actions)
     9|| [![Coverage](https://img.shields.io/badge/coverage-66%25-green.svg)](https://github.com/ulsreall/web3-agent-kit#readme) |
    10|[![Twitter](https://img.shields.io/twitter/follow/itseywacc?style=social)](https://twitter.com/itseywacc)
    11|
    12|<p align="center">
    13|  <img src="assets/demo.gif" alt="Web3 Agent Kit Demo" width="700"/>
    14|</p>
    15|
    16|---
    17|
    18|## 🤔 Why Web3 Agent Kit?
    19|
    20|Building AI agents that interact with blockchains is **hard**. You need to juggle RPC providers, wallet management, transaction signing, gas estimation, DeFi protocol ABIs, LLM integration, and safety rails — all before writing a single line of business logic.
    21|
    22|**Web3 Agent Kit handles all of that for you.**
    23|
    24|| Pain Point | Without Web3 Agent Kit | With Web3 Agent Kit |
    25||------------|------------------------|---------------------|
    26|| **Setup** | Days of boilerplate | `pip install` → 5 lines of code |
    27|| **Multi-chain** | Write adapters per chain | Built-in for 7+ chains |
    28|| **LLM Integration** | Manual prompt engineering | Natural language goals, auto-parsed |
    29|| **Safety** | Build your own guardrails | Spend limits, kill switch, operator confirmation |
    30|| **DeFi** | Read docs, write ABIs | Drop-in Uniswap, Aave, bridges |
    31|| **Yield** | Manual research, claim, compound | Auto-compound, cross-protocol APY comparison |
    32|| **DCA** | Manual recurring buys | Automated DCA with intervals, limits, callbacks |
    33|| **Gas** | Guess gas prices | Smart estimation, timing, batching |
    34|| **Security** | Manual approval checks | Auto-scan & revoke risky approvals |
    35|| **Alerts** | Manual whale tracking | Auto-monitor wallets, instant alerts |
    36|| **Multi-wallet** | Manage keys manually | Batch ops, consolidated portfolio, wallet groups |
    37|| **Airdrops** | Manual quest hunting | Auto-track campaigns, multi-wallet farming, Sybil-safe |
    38|| **Token Security** | Manual research | Honeypot detection, rug pull check, contract audit |
    39|| **Extensibility** | Hard-coded logic | Plugin system — community can extend anything |
    40|| **Error Handling** | Manual retry logic | Auto-fallback across LLM providers & RPCs |
    41|
    42|---
    43|
    44|## 🏗️ Architecture
    45|
    46|```
    47|┌─────────────────────────────────────────────────────────────────────┐
    48|│                        User / Application                          │
    49|│                    "Swap 0.1 ETH to USDC on Base"                  │
    50|└──────────────────────────────┬──────────────────────────────────────┘
    51|                               │
    52|                               ▼
    53|┌─────────────────────────────────────────────────────────────────────┐
    54|│                          Agent Framework                            │
    55|│  ┌───────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐ │
    56|│  │ Goal      │→ │ LLM Planner  │→ │ Tool        │→ │ Transaction│ │
    57|│  │ Parser    │  │ (cascade)    │  │ Router      │  │ Executor   │ │
    58|│  └───────────┘  └──────────────┘  └─────────────┘  └─────┬──────┘ │
    59|└───────────────────────────────────────────────────────────┼────────┘
    60|                                                            │
    61|                               ┌────────────────────────────┼────────┐
    62|                               │         Safety Layer       │        │
    63|                               │  ┌─────────────────────────┼──────┐ │
    64|                               │  │ Spend Governor          │      │ │
    65|                               │  │ • Per-tx limits         │      │ │
    66|                               │  │ • Daily caps            │      │ │
    67|                               │  │ • Kill switch           │      │ │
    68|                               │  │ • Operator confirmation │      │ │
    69|                               │  └─────────────────────────┘      │ │
    70|                               └────────────────────────────────────┘
    71|                                                            │
    72|                               ┌────────────────────────────┼────────┐
    73|                               │      Tool Ecosystem        │        │
    74|                               │  ┌─────────┐ ┌──────────┐ │        │
    75|                               │  │ Uniswap │ │ Bridge   │ │        │
    76|                               │  │ V2/V3   │ │ Agg.     │ │        │
    77|                               │  ├─────────┤ ├──────────┤ │        │
    78|                               │  │ Sniper  │ │ Portfolio│ │        │
    79|                               │  │ Module  │ │ Tracker  │ │        │
    80|                               │  └─────────┘ └──────────┘ │        │
    81|                               └────────────────────────────┼────────┘
    82|                                                            │
    83|                               ┌────────────────────────────┼────────┐
    84|                               │    Chain Abstraction Layer  │        │
    85|                               │  ┌──────┐ ┌──────┐ ┌────┐ │        │
    86|                               │  │ ETH  │ │ BASE │ │ARB │ │        │
    87|                               │  ├──────┤ ├──────┤ ├────┤ │        │
    88|                               │  │ OP   │ │ MATIC│ │AVAX│ │        │
    89|                               │  ├──────┤ ├──────┤ ├────┤ │        │
    90|                               │  │ BSC  │ │      │ │    │ │        │
    91|                               │  └──────┘ └──────┘ └────┘ │        │
    92|                               └────────────────────────────────────┘
    93|```
    94|
    95|---
    96|
    97|## 📊 Comparison vs Alternatives
    98|
    99|| Feature | Web3 Agent Kit | LangChain + Web3 | Custom Bot | Goat SDK |
   100||---------|:--------------:|:----------------:|:----------:|:--------:|
   101|| **Setup Time** | Minutes | Hours | Days | Hours |
   102|| **Multi-chain** | 7+ chains | Manual | Manual | Limited |
   103|| **Built-in LLM** | 6 providers | DIY | ❌ | ❌ |
   104|| **DeFi Tools** | Uniswap, Aave, bridges | ❌ | ❌ | Limited |
   105|| **Token Sniper** | ✅ | ❌ | ❌ | ❌ |
   106|| **DCA Bot** | ✅ | ❌ | ❌ | ❌ |
   107|| **Gas Optimizer** | ✅ | ❌ | ❌ | ❌ |
   108|| **Approval Manager** | ✅ | ❌ | ❌ | ❌ |
   109|| **Wallet Watcher** | ✅ | ❌ | ❌ | ❌ |
   110|| **Yield Optimizer** | ✅ | ❌ | ❌ | ❌ |
   111|| **Multi-Wallet** | ✅ | ❌ | ❌ | ❌ |
   112|| **Airdrops** | ✅ | ❌ | ❌ | ❌ |
   113|| **Token Security** | ✅ | ❌ | ❌ | ❌ |
   114|| **Plugin System** | ✅ | ❌ | ❌ | ❌ |
   115|| **Safety Rails** | ✅ Governor | ❌ | ❌ | ❌ |
   116|| **Natural Language** | ✅ | Partial | ❌ | ❌ |
   117|| **Python Native** | ✅ | ✅ | Varies | ❌ (TS) |
   118|| **Type Hints** | ✅ | Partial | Varies | N/A |
   119|| **Active Maintenance** | ✅ | ✅ | Depends | Limited |
   120|
   121|---
   122|
   123|## 🎯 Quick Start
   124|
   125|### 1. Install
   126|
   127|```bash
   128|pip install web3-agent-kit
   129|```
   130|
   131|### 2. Set Environment Variables
   132|
   133|```bash
   134|# Required: Wallet private key
   135|export PRIVATE_KEY="0x..."
   136|
   137|# Required: At least one LLM provider key
   138|export OPENAI_API_KEY="sk-..."        # OpenAI
   139|export ANTHROPIC_API_KEY="sk-ant-..."  # Anthropic (best reasoning)
   140|export GROQ_API_KEY="gsk_..."          # Groq (fastest)
   141|export DEEPSEEK_API_KEY="sk-..."       # DeepSeek (cheapest)
   142|
   143|# Optional: Custom RPC endpoints (public defaults are provided)
   144|export ETH_RPC="https://..."
   145|export BASE_RPC="https://..."
   146|```
   147|
   148|### 3. Write Your First Agent
   149|
   150|```python
   151|from web3_agent_kit import Agent, Wallet, Chain, ChainManager
   152|from web3_agent_kit.defi import Uniswap
   153|
   154|# Setup
   155|chain_manager = ChainManager(chains=[Chain.BASE])
   156|wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
   157|uniswap = Uniswap(chain_manager=chain_manager)
   158|
   159|# Create agent with LLM reasoning
   160|agent = Agent(
   161|    wallet=wallet,
   162|    chains=[Chain.BASE],
   163|    tools=[uniswap],
   164|)
   165|
   166|# Natural language swap — that's it!
   167|result = agent.run("Swap 0.1 ETH to USDC on Base")
   168|print(result)
   169|```
   170|
   171|### 4. Run It
   172|
   173|```bash
   174|python my_agent.py
   175|```
   176|
   177|> 💡 **Tip:** Start with a small amount on a testnet or use `dry_run=True` mode to validate behavior before going live.
   178|
   179|---
   180|
   181|## ✨ Features
   182|
   183|### 🤖 Core
   184|- 🔗 **Multi-chain support** — Ethereum, Base, Arbitrum, Optimism, Polygon, Avalanche, BSC
   185|- 🧠 **LLM-powered reasoning** — Multi-provider cascade (OpenAI, Anthropic, Groq, DeepSeek, OpenRouter, Kimi)
   186|- 🎯 **Natural language goals** — Tell the agent what to do in plain English
   187|- 🔐 **Governed signing** — Safety caps, kill-switch, operator confirmation
   188|
   189|### 💰 DeFi
   190|- 💱 **Uniswap V2 swaps** — Actual token swaps with quotes, approvals, slippage protection
   191|- 🌉 **Cross-chain bridges** — Li.Fi + Socket aggregators for best routes
   192|- 📊 **Portfolio tracking** — Real-time balances, P&L across all chains
   193|
   194|### 🔫 Sniper
   195|- 🎯 **Token sniper** — Monitor new liquidity pools, auto-buy safe tokens
   196|- 🛡️ **Risk assessment** — Honeypot detection, liquidity checks, contract analysis
   197|- ⚡ **Live monitoring** — Background thread with callback alerts
   198|
   199|### 📈 DCA Bot
   200|- 🔄 **Recurring buys** — Dollar-cost average into any token automatically
   201|- ⏰ **Flexible intervals** — Hourly, daily, weekly, biweekly, monthly
   202|- 🛑 **Spending limits** — Max buys, max total spend, auto-stop
   203|- 📊 **Cost average analysis** — Track avg price, min/max, P&L
   204|- 💾 **Persistent orders** — Survives restarts, stored on disk
   205|- 🔔 **Callbacks** — Hook into execution events for notifications
   206|
   207|### 🔒 Security Module (NEW!)
   208|- 🍯 **Honeypot detection** — Check if token can be sold before buying
   209|- 🧶 **Rug pull checker** — Assess rug pull risk factors
   210|- 📝 **Contract audit** — Detect hidden mint, blacklist, pause, proxy patterns
   211|- 💰 **Tax checker** — Buy/sell tax analysis
   212|- 💧 **Liquidity analysis** — Locked %, lock duration
   213|- 👥 **Holder analysis** — Concentration, whale detection
   214|- 📊 **Safety score** — 0-100 score with risk levels
   215|- 🌐 **GoPlus API** — Real-time token security data
   216|- 📈 **DexScreener** — Liquidity data integration
   217|
   218|### 🪂 Airdrop Automation (NEW!)
   219|- 🔍 **Campaign Discovery** — Auto-scan 7 platforms (Galxe, Zealy, Layer3, QuestN, TaskOn, Intract, Port3)
   220|- ⛓️ **On-chain Farming** — DeFi interactions for airdrops (Base, Ethereum, Arbitrum, Optimism, Scroll, Linea, zkSync)
   221|- ⏰ **Daily Scheduler** — Automate recurring tasks with retry logic
   222|- 📊 **Points Dashboard** — Track points across all platforms with history
   223|- 🔗 **Referral Manager** — Generate, track, and optimize referral links
   224|- 🚰 **Faucet Claimer** — Auto-claim testnet tokens from 12+ faucets
   225|- 🤖 **Multi-wallet** — Sybil avoidance, wallet rotation
   226|- 🔌 **Plugin System** — Extend with custom platform executors
   227|
   228|### 🌐 REST API
   229|- 📡 **18 endpoints** — Full HTTP API for all modules
   230|- 🔑 **API key auth** — Secure access control
   231|- 📖 **Swagger UI** — Interactive API documentation
   232|- 🔄 **Auto-fallback** — Multi-provider LLM cascade
   233|
   234|### 🔌 Plugin System
   235|- 📦 **Plugin registry** — Discover and load plugins dynamically
   236|- 🛠️ **Custom plugins** — Extend with your own tools
   237|- 🔄 **Hot reload** — Add plugins without restarting
   238|
   239|---
   240|
   241|## 🌐 REST API
   242|
   243|Full HTTP API for all modules — use from any language (JavaScript, curl, etc):
   244|
   245|```bash
   246|# Start the API server
   247|python -m src.api
   248|
   249|# Or with API key
   250|WEB3_API_KEY=your-secret python -m src.api
   251|```
   252|
   253|**Endpoints:**
   254|
   255|| Endpoint | Method | Description |
   256||----------|--------|-------------|
   257|| `/wallet/info` | GET | Wallet info + balance |
   258|| `/swap/quote` | GET | Get swap quote |
   259|| `/swap/execute` | POST | Execute token swap |
   260|| `/portfolio/` | GET | Portfolio dashboard |
   261|| `/gas/estimate` | GET | Gas estimates (EIP-1559) |
   262|| `/gas/recommendation` | GET | Gas timing recommendation |
   263|| `/watcher/list` | GET | List watched wallets |
   264|| `/watcher/add` | POST | Add wallet to watch |
   265|| `/approval/scan` | GET | Scan token approvals |
   266|| `/approval/risk` | GET | Risk report |
   267|| `/dca/orders` | GET/POST | List/create DCA orders |
   268|| `/yield/opportunities` | GET | Scan yield opportunities |
   269|| `/yield/best` | GET | Find best yield |
   270|| `/bridge/quote` | GET | Get bridge quote |
   271|| `/bridge/execute` | POST | Execute bridge |
   272|| `/health` | GET | Health check |
   273|| `/docs` | GET | Swagger UI |
   274|| `/redoc` | GET | ReDoc documentation |
   275|
   276|**Example:**
   277|```bash
   278|# Get gas estimate
   279|curl http://localhost:8000/gas/estimate?chain=ethereum
   280|
   281|# Get swap quote
   282|curl "http://localhost:8000/swap/quote?token_in=ETH&token_out=USDC&amount_in=1.0"
   283|
   284|# Scan approvals
   285|curl http://localhost:8000/approval/scan?chain=ethereum
   286|```
   287|
   288|---
   289|
   290|## 🎯 Showcase
   291|
   292|### Telegram Bot
   293|A full-featured Telegram bot built with web3-agent-kit:
   294|
   295|```bash
   296|cd showcase/telegram-bot
   297|pip install -r requirements.txt
   298|python bot.py
   299|```
   300|
   301|Features: balance check, token swap, portfolio tracking, token sniper, cross-chain bridge.
   302|
   303|[![Telegram Bot Demo](showcase/telegram-bot/demo.gif)](showcase/telegram-bot/)
   304|
   305|---
   306|
   307|## 📦 Examples
   308|
   309|| Example | Description |
   310||---------|-------------|
   311|| `examples/llm_swap_agent.py` | LLM-powered natural language swapping |
   312|| `examples/direct_swap.py` | Programmatic Uniswap swap without LLM |
   313|| `examples/token_sniper.py` | Monitor new pairs, auto-buy safe tokens |
   314|| `examples/portfolio_dashboard.py` | Real-time portfolio across chains |
   315|| `examples/bridge_agent.py` | Cross-chain transfers via Li.Fi/Socket |
   316|| `examples/swap_agent.py` | Autonomous token swapping |
   317|| `examples/yield_optimizer.py` | Cross-protocol yield farming + auto-compound |
   318|| `examples/multi_wallet.py` | Multi-wallet management + batch ops |
   319|| `examples/plugin_system.py` | Plugin system usage + custom plugins |
   320|| `examples/dca_bot.py` | Dollar-cost averaging bot with intervals & limits |
   321|| `examples/api_server.py` | REST API server with Swagger docs |
   322|| `examples/airdrop_farmer.py` | Multi-chain airdrop farming |
   323|| `examples/sniper_bot.py` | Token launch sniper |
   324|| `examples/portfolio_tracker.py` | Portfolio tracking & reporting |
   325|| `examples/airdrop_suite.py` | Full airdrop automation suite |
   326|| `examples/security_analysis.py` | Token security analysis |
   327|
   328|---
   329|
   330|## 🧠 LLM Integration
   331|
   332|Multi-provider cascade with automatic fallback:
   333|
   334|```python
   335|from web3_agent_kit.agent import LLM, LLMConfig
   336|
   337|# Use any LLM provider with automatic fallback
   338|llm = LLM(LLMConfig(
   339|    providers=["anthropic", "openai", "groq", "deepseek"],
   340|    model="claude-3-5-sonnet-20241022",
   341|))
   342|
   343|# Natural language → structured action
   344|action = llm.parse("Swap 0.1 ETH to USDC on Base")
   345|# → {"tool": "uniswap", "action": "swap", "params": {...}}
   346|```
   347|
   348|---
   349|
   350|## 🔒 Security Module
   351|
   352|Analyze tokens before interacting:
   353|
   354|```python
   355|from web3_agent_kit.security import TokenAnalyzer, SecurityConfig
   356|
   357|analyzer = TokenAnalyzer(SecurityConfig(chain="base"))
   358|
   359|# Quick check
   360|result = analyzer.quick_check("0x...")
   361|print(f"Is Honeypot: {result['is_honeypot']}")
   362|
   363|# Full analysis
   364|report = analyzer.analyze_token("0x...")
   365|print(f"Safety Score: {report.safety_score}/100")
   366|print(f"Risk Level: {report.risk_level.value}")
   367|
   368|if report.is_honeypot:
   369|    print("🚨 HONEYPOT DETECTED!")
   370|elif report.safety_score < 50:
   371|    print("⚠️ HIGH RISK TOKEN")
   372|else:
   373|    print("✓ Safe to trade")
   374|```
   375|
   376|---
   377|
   378|## 🪂 Airdrop Automation
   379|
   380|Automate airdrop farming across multiple platforms:
   381|
   382|```python
   383|from web3_agent_kit.airdrop import (
   384|    CampaignDiscovery,
   385|    OnChainAirdropFarmer,
   386|    AirdropScheduler,
   387|    PointsDashboard,
   388|    ReferralManager,
   389|    FaucetClaimer,
   390|)
   391|
   392|# Discover new campaigns
   393|discovery = CampaignDiscovery()
   394|campaigns = discovery.discover_all()
   395|
   396|# On-chain farming (dry run)
   397|farmer = OnChainAirdropFarmer(OnChainConfig(chain="base", dry_run=True))
   398|farmer.farm_plan("base_activity")
   399|
   400|# Schedule daily tasks
   401|scheduler = AirdropScheduler()
   402|scheduler.add_daily("galxe_checkin", "09:00", galxe_checkin_fn)
   403|
   404|# Track points
   405|dashboard = PointsDashboard(DashboardConfig(wallet="0x..."))
   406|dashboard.sync_all()
   407|
   408|# Generate referrals
   409|manager = ReferralManager()
   410|manager.generate_links(count=10)
   411|
   412|# Claim testnet tokens
   413|claimer = FaucetClaimer()
   414|claimer.claim_all(wallet="0x...")
   415|```
   416|
   417|---
   418|
   419|## 📊 Project Stats
   420|
   421|- **Version:** 1.2.0
   422|- **Modules:** 20+
   423|- **Tests:** 565+
   424|- **Examples:** 18
   425|- **Chains:** 7+
   426|- **License:** MIT
   427|
   428|---
   429|
   430|## 🤝 Contributing
   431|
   432|We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
   433|
   434|---
   435|
   436|## 📄 License
   437|
   438|MIT License — see [LICENSE](LICENSE) for details.
   439|
   440|---
   441|
   442|## 🙏 Acknowledgments
   443|
   444|- [Uniswap](https://uniswap.org/) — DEX protocol
   445|- [Li.Fi](https://li.fi/) — Bridge aggregator
   446|- [Socket](https://socket.tech/) — Bridge aggregator
   447|- [GoPlus](https://gopluslabs.io/) — Token security API
   448|- [DexScreener](https://dexscreener.com/) — DEX data
   449|
   450|---
   451|
   452|<p align="center">
   453|  Made with ❤️ by <a href="https://twitter.com/itseywacc">@itseywacc</a>
   454|</p>
   455|