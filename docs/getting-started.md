# Getting Started

This guide walks you through installing Web3 Agent Kit and running your first autonomous agent.

---

## 📦 Installation

### From PyPI (recommended)

```bash
pip install web3-agent-kit
```

### From Source

```bash
git clone https://github.com/ulsreall/web3-agent-kit.git
cd web3-agent-kit
pip install -e .
```

---

## 🔧 Prerequisites

- **Python 3.10+**
- **A wallet private key** (for on-chain transactions)
- **At least one LLM API key** (for agent reasoning)

---

## 🔑 Environment Variables

Web3 Agent Kit uses environment variables for configuration. Create a `.env` file or export them directly:

### Required

```bash
# Wallet private key (NEVER share this!)
export PRIVATE_KEY="0x..."

# At least one LLM provider
export OPENAI_API_KEY="sk-..."
# OR
export ANTHROPIC_API_KEY="sk-ant-..."
# OR
export GROQ_API_KEY="gsk_..."
# OR
export DEEPSEEK_API_KEY="sk-..."
```

### Optional

```bash
# Custom RPC endpoints (uses public defaults if not set)
export ETH_RPC="https://..."
export BASE_RPC="https://..."
export ARBITRUM_RPC="https://..."

# Additional LLM providers (used as fallback cascade)
export OPENROUTER_API_KEY="sk-..."
export KIMI_API_KEY="sk-..."

# LLM model overrides
export ANTHROPIC_MODEL="claude-sonnet-4-20250514"
export OPENAI_MODEL="gpt-4o-mini"
export GROQ_MODEL="llama-3.3-70b-versatile"
```

---

## 🏃 Quick Start

### 1. Basic Agent

Create an agent that can swap tokens using natural language:

```python
from web3_agent_kit import Agent, Wallet, Chain, ChainManager
from web3_agent_kit.defi import Uniswap

# Initialize chain manager
chain_manager = ChainManager(chains=[Chain.BASE])

# Create wallet from environment variable
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)

# Initialize Uniswap tool
uniswap = Uniswap(chain_manager=chain_manager)

# Create the agent
agent = Agent(
    wallet=wallet,
    chains=[Chain.BASE],
    tools=[uniswap],
    verbose=True,
)

# Run with a natural language goal
result = agent.run("Swap 0.01 ETH to USDC on Base")
print(result)
```

### 2. Portfolio Tracking

Check your portfolio across multiple chains:

```python
from web3_agent_kit import PortfolioTracker, Wallet, Chain, ChainManager

chain_manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM])
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)

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

### 3. Cross-Chain Bridging

Bridge tokens between chains:

```python
from web3_agent_kit import BridgeAgent, Wallet, Chain, ChainManager

chain_manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE])
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)

bridge = BridgeAgent(chain_manager, wallet)

# Get best routes
routes = bridge.get_routes("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)

for route in routes:
    print(f"{route.bridge_name}: {route.amount_out:.6f} ETH (fee: ${route.fee_usd:.2f})")

# Execute transfer
result = bridge.transfer("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)
print(f"TX: {result.tx_hash}")
```

### 4. Token Sniper

Monitor new liquidity pools and auto-buy safe tokens:

```python
from web3_agent_kit import TokenSniper, SniperConfig, Chain, ChainManager, Wallet
from web3_agent_kit.defi import Uniswap

chain_manager = ChainManager(chains=[Chain.BASE])
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
uniswap = Uniswap(chain_manager=chain_manager)

config = SniperConfig(
    max_buy=0.005,          # max 0.005 ETH per snipe
    auto_buy=True,          # auto-buy safe tokens
    honeypot_check=True,    # check if token is honeypot
    min_liquidity=0.5,      # min 0.5 ETH liquidity
    callback=lambda pair: print(f"🚨 New pair: {pair.token_symbol}"),
)

sniper = TokenSniper(chain_manager, wallet, config, uniswap=uniswap)

# Scan recent blocks
pairs = sniper.scan_recent_blocks(num_blocks=100, chain=Chain.BASE)

# Or start live monitoring
sniper.start(chain=Chain.BASE, poll_interval=12)
```

---

## 🧠 LLM Integration

The LLM client automatically detects available providers from environment variables and cascades through them on failure:

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

### Supported Providers

| Provider | Best For | Env Variable |
|----------|----------|--------------|
| **Anthropic** (Claude) | Best reasoning | `ANTHROPIC_API_KEY` |
| **OpenAI** (GPT-4) | General purpose | `OPENAI_API_KEY` |
| **Groq** (Llama) | Fastest inference | `GROQ_API_KEY` |
| **DeepSeek** | Cheapest | `DEEPSEEK_API_KEY` |
| **OpenRouter** | Multi-model fallback | `OPENROUTER_API_KEY` |
| **Kimi** | Long context | `KIMI_API_KEY` |

---

## 🔐 Safety Features

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

## 📚 Next Steps

- [Features](features.md) — Detailed feature overview
- [Examples](examples.md) — Ready-to-use code examples
- [API Reference](api/agent.md) — Full API documentation
