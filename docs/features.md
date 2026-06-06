# Features

Web3 Agent Kit provides a comprehensive set of features for building autonomous Web3 AI agents.

---

## 🤖 Core Agent Framework

The core agent framework enables goal-driven autonomous operations powered by LLM reasoning.

### Goal-Driven Execution

Tell the agent what to accomplish in natural language — it figures out the steps:

```python
from web3_agent_kit import Agent, Wallet, Chain, ChainManager
from web3_agent_kit.defi import Uniswap

agent = Agent(
    wallet=wallet,
    chains=[Chain.BASE],
    tools=[Uniswap(chain_manager=chain_manager)],
)

# The agent reasons about the goal and executes the right sequence of actions
result = agent.run("Check my ETH balance, then swap 0.1 ETH to USDC if I have enough")
```

### Multi-Step Reasoning

The agent uses an observe-decide-act loop:

1. **Observe** — Gathers current blockchain state (balances, prices)
2. **Decide** — Uses LLM to reason about the next action
3. **Act** — Executes the action using available tools
4. **Repeat** — Until the goal is achieved or max steps reached

### Configurable Behavior

```python
from web3_agent_kit import AgentConfig

config = AgentConfig(
    wallet=wallet,
    chains=[Chain.BASE, Chain.ETHEREUM],
    llm="auto",           # Auto-detect best available LLM
    max_steps=20,         # Maximum reasoning steps
    tools=[uniswap, aave],
    governor=governor,    # Safety governor
    verbose=True,         # Log reasoning steps
)

agent = Agent(config=config)
```

---

## 🔗 Multi-Chain Support

Web3 Agent Kit supports 7+ blockchain networks out of the box.

### Supported Chains

- **Ethereum** — The original smart contract platform
- **Base** — Coinbase's L2, low fees, fast finality
- **Arbitrum** — Leading Ethereum L2 by TVL
- **Optimism** — Ethereum L2 with OP Stack
- **Polygon** — Ethereum sidechain with low fees
- **Avalanche** — High-throughput L1
- **BSC** — Binance Smart Chain

### Custom RPC Endpoints

```python
from web3_agent_kit import ChainManager, Chain

chain_manager = ChainManager(
    chains=[Chain.ETHEREUM, Chain.BASE],
    rpcs={
        Chain.ETHEREUM: "https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY",
        Chain.BASE: "https://base-mainnet.g.alchemy.com/v2/YOUR_KEY",
    },
)
```

### Automatic Fallback

Each chain has default public RPC endpoints. If you don't provide custom RPCs, the framework uses these defaults automatically.

---

## 🧠 LLM Integration

Multi-provider LLM client with automatic cascade fallback.

### Provider Cascade

The LLM client tries providers in order. On 429 (rate limit), 5xx (server error), or timeout, it moves to the next provider:

```
Anthropic → Kimi → OpenRouter → DeepSeek → Groq → OpenAI
```

### Chat Interface

```python
from web3_agent_kit.llm import LLM

llm = LLM()

# Simple chat
response = llm.chat("What is the current gas price on Ethereum?")

# Chat with system prompt
response = llm.chat(
    "Analyze this swap opportunity",
    system="You are a DeFi expert. Be concise.",
)

# JSON response (parsed automatically)
data = llm.chat_json("Give me a swap analysis as JSON")
```

### Custom Configuration

```python
from web3_agent_kit.llm import LLM, LLMConfig

config = LLMConfig(
    providers=[
        {"name": "anthropic", "api_key": "...", "model": "claude-sonnet-4-20250514"},
        {"name": "openai", "api_key": "...", "model": "gpt-4o"},
    ],
    temperature=0.1,
    max_tokens=2048,
    timeout=30,
)

llm = LLM(config=config)
```

---

## 💱 Token Swaps

Execute real token swaps on Uniswap V2-compatible DEXes.

### Uniswap V2

```python
from web3_agent_kit.defi import Uniswap

uniswap = Uniswap(chain_manager=chain_manager, slippage=0.5)

# Execute swap
result = uniswap.execute(
    wallet=wallet,
    token_in="ETH",
    token_out="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC on Base
    amount=0.1,
    chain=Chain.BASE,
)

print(f"TX: {result.tx_hash}")
print(f"Swapped {result.amount_in} {result.token_in} → {result.amount_out} {result.token_out}")
```

### Get Quote (No Execution)

```python
quote = uniswap.get_quote(
    token_in="ETH",
    token_out="USDC",
    amount=0.1,
    chain=Chain.BASE,
)

print(f"0.1 ETH = {quote['amount_out']:.2f} USDC")
```

### Supported DEXes

- **Uniswap V2** — Ethereum, Base, Arbitrum, Optimism, Polygon
- **Aerodrome** — Base (V2-compatible router)
- **Aave** — Lending/borrowing
- **Curve** — Stableswap

---

## 🎯 Airdrop Suite

Full airdrop farming automation — discover, track, and claim airdrops across multiple platforms.

### Platform Integrations

- **Galxe** — Quest completion, credential claiming
- **Zealy** — Quest automation
- **Layer3** — Task completion
- **QuestN** — Quest participation
- **Intract** — Campaign automation
- **Gleam** — Giveaway entry

### Multi-Wallet Farming

Manage multiple wallets for airdrop farming with a single interface.

```python
from web3_agent_kit.airdrop import MultiWalletManager

manager = MultiWalletManager.from_csv("wallets.csv")
manager.execute_on_all("swap", token_in="ETH", token_out="USDC", amount=0.01)
```

---

## 🔐 Security Tools

Smart contract security auditing — static analysis, fuzzing, exploit development, and forensics.

- **Static Analysis** — Slither-based vulnerability detection
- **Fuzzing** — Property-based testing with Echidna/Foundry
- **Exploit Development** — PoC builder for discovered vulnerabilities
- **Forensics** — On-chain transaction tracing
- **Protocol Audit** — Full DeFi protocol security audit

---

## ⚡ MEV Bots

Maximal Extractable Value extraction tools.

- **Arbitrage** — Cross-DEX arbitrage with Flashbot support
- **Liquidation** — Monitor and liquidate undercollateralized positions
- **Flashbots** — Private mempool submission to avoid frontrunning

---

## 🖼️ NFT Tools

NFT collection creation, minting, and marketplace integration.

- **Collection Deploy** — Deploy ERC-721A contracts
- **Batch Minting** — Mint to multiple recipients
- **Marketplace** — OpenSea-compatible listing

---

## 📈 Trading Bots

Automated trading strategies.

- **DCA Bot** — Dollar-cost averaging with price triggers
- **Yield Optimizer** — Find and auto-compound best yields
- **Token Sniper** — Monitor new pools, auto-buy safe tokens

---

## 🌉 Cross-Chain Bridges

Transfer tokens between chains using bridge aggregators.

### Bridge Aggregators

- **Li.Fi** — Multi-bridge aggregator with best route selection
- **Socket** — Cross-chain liquidity aggregator

### Usage

```python
from web3_agent_kit import BridgeAgent

bridge = BridgeAgent(chain_manager, wallet)

# Get all available routes
routes = bridge.get_routes("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)

for route in routes:
    print(f"{route.bridge_name}: {route.amount_out:.6f} ETH")
    print(f"  Fee: ${route.fee_usd:.2f}")
    print(f"  Time: {route.time_estimate // 60} minutes")

# Execute best route
result = bridge.transfer("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)
print(f"TX: {result.tx_hash}")
```

---

## 📊 Portfolio Tracking

Track wallet balances and P&L across multiple chains.

### Real-Time Portfolio

```python
from web3_agent_kit import PortfolioTracker

tracker = PortfolioTracker(chain_manager, wallet)

# Get current portfolio
summary = tracker.get_summary()
print(summary)

# Get specific chains only
summary = tracker.get_summary(chains=[Chain.ETHEREUM, Chain.BASE])
```

### P&L Tracking

```python
# Take initial snapshot
tracker.get_summary()

# ... time passes, prices change ...

# Take another snapshot
tracker.get_summary()

# Calculate P&L
pnl = tracker.get_pnl()
print(f"P&L: ${pnl['pnl_absolute']:.2f} ({pnl['pnl_percent']:.1f}%)")
```

### Known Tokens

The portfolio tracker automatically detects these tokens:

- **Ethereum**: WETH, USDC, USDT, DAI, WBTC, LINK, UNI
- **Base**: WETH, USDC, USDbC, DAI, AERO
- **Arbitrum**: WETH, USDC, USDT, ARB, GMX

---

## 🔫 Token Sniper

Monitor new liquidity pools and auto-buy safe tokens.

### Risk Assessment

Each new pair is analyzed for safety:

- **Liquidity check** — Minimum ETH in pool
- **Contract code analysis** — Detect suspicious patterns
- **Honeypot detection** — Check if token can be sold
- **Risk scoring** — LOW / MEDIUM / HIGH / SCAM

### Configuration

```python
from web3_agent_kit import SniperConfig

config = SniperConfig(
    max_buy=0.005,          # Max 0.005 ETH per snipe
    auto_buy=True,          # Auto-buy safe tokens
    honeypot_check=True,    # Enable honeypot detection
    min_liquidity=0.5,      # Min 0.5 ETH liquidity
    max_buy_tax=10.0,       # Max 10% buy tax
    max_sell_tax=10.0,      # Max 10% sell tax
    blacklisted_tokens=[],  # Tokens to ignore
    whitelisted_tokens=[],  # Tokens to always consider
    callback=my_callback,   # Function to call on new pair
)
```

### Scanning vs Monitoring

```python
# One-time scan of recent blocks
pairs = sniper.scan_recent_blocks(num_blocks=100, chain=Chain.BASE)

# Live monitoring (background thread)
sniper.start(chain=Chain.BASE, poll_interval=12)

# Stop monitoring
sniper.stop()
```

---

## 🔐 Safety & Governance

Built-in safety features to protect your wallet.

### Spend Governor

```python
from web3_agent_kit.safety import SpendGovernor, SpendLimits

governor = SpendGovernor(
    limits=SpendLimits(
        max_per_tx=0.1,      # Max 0.1 ETH per transaction
        daily_limit=1.0,     # Max 1 ETH per day
    ),
    require_confirm=True,    # Operator must confirm
)

# Use with agent
agent = Agent(
    wallet=wallet,
    chains=[Chain.BASE],
    tools=[uniswap],
    governor=governor,
)
```

### Kill Switch

```python
# Emergency stop — blocks all transactions
governor.kill()

# Resume operations
governor.unkill()
```

---

## 📦 Package Exports

All core classes are available from the top-level package:

```python
from web3_agent_kit import (
    # Core
    Agent,
    AgentConfig,
    Wallet,
    Chain,
    ChainManager,
    LLM,
    LLMConfig,

    # Features
    PortfolioTracker,
    PortfolioSummary,
    BridgeAgent,
    BridgeRoute,
    BridgeResult,
    TokenSniper,
    SniperConfig,
    NewPair,
    RiskLevel,
)

# DeFi tools
from web3_agent_kit.defi import (
    Uniswap,
    Aerodrome,
    Aave,
    Curve,
    SwapResult,
    YieldOpportunity,
)
```
