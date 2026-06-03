# 🤖 Web3 Agent Kit

> Open-source framework for building autonomous AI agents that interact with blockchain networks.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Twitter](https://img.shields.io/twitter/follow/web3agentkit?style=social)](https://twitter.com/web3agentkit)

## What is this?

Web3 Agent Kit is a Python framework for building AI agents that can autonomously interact with DeFi protocols, manage wallets, execute trades, and perform complex on-chain operations across multiple blockchains.

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

## Features

- 🔗 **Multi-chain support** — Ethereum, Base, Arbitrum, Optimism, Polygon, Solana
- 🤖 **Agent framework** — Goal-driven autonomous agents with LLM reasoning
- 💰 **DeFi integrations** — Uniswap, Aave, Curve, Aerodrome, and more
- 🔐 **Governed signing** — Safety caps, kill-switch, operator confirmation
- 📊 **Portfolio management** — Track balances, positions, P&L across chains
- 🦊 **Browser automation** — Interact with dApps via stealth browser
- 📡 **Real-time monitoring** — Mempool, whale tracking, price alerts

## Quick Start

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
    llm="gpt-4",  # or claude, llama, etc.
)

# Run a task
result = agent.run("Swap 0.1 ETH to USDC on Base")
print(result)  # → Transaction hash, gas used, etc.
```

### Yield Optimizer

```python
from web3_agent_kit import Agent
from web3_agent_kit.strategies import YieldOptimizer

optimizer = YieldOptimizer(
    wallet=wallet,
    chains=[Chain.ETHEREUM, Chain.BASE],
    min_apy=5.0,  # minimum 5% APY
    max_risk=0.3,  # low-medium risk
)

# Auto-optimize yield across chains
optimizer.run(interval="1h")  # check every hour
```

### Airdrop Farmer

```python
from web3_agent_kit import Agent
from web3_agent_kit.tools import AirdropFarmer

farmer = AirdropFarmer(
    wallet=wallet,
    targets=["scroll", "zksync", "linea"],
)

# Farm airdrops across multiple chains
farmer.run("Complete daily quests and track eligibility")
```

## Architecture

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

## Examples

| Example | Description |
|---------|-------------|
| `examples/swap_agent.py` | Autonomous token swapping |
| `examples/yield_optimizer.py` | Cross-chain yield farming |
| `examples/airdrop_farmer.py` | Multi-chain airdrop farming |
| `examples/sniper_bot.py` | Token launch sniper |
| `examples/portfolio_manager.py` | Portfolio rebalancing |

## Safety

Web3 Agent Kit includes built-in safety features:

- **Spend Governor** — Per-transaction caps, daily limits, kill-switch
- **Confirm Gate** — Operator approval for high-value transactions
- **Simulation** — Dry-run transactions before execution
- **Audit Log** — Complete history of all agent actions

```python
from web3_agent_kit.safety import SpendGovernor

governor = SpendGovernor(
    max_per_tx=0.1,      # max 0.1 ETH per transaction
    daily_limit=1.0,     # max 1 ETH per day
    require_confirm=True, # operator must confirm
)
```

## Roadmap

- [ ] Core framework (wallet, chains, agents)
- [ ] DeFi integrations (Uniswap, Aave, Curve)
- [ ] LLM integration (GPT-4, Claude, Llama)
- [ ] Browser automation for dApp interaction
- [ ] Solana support
- [ ] Telegram/Discord bot interface
- [ ] Web dashboard
- [ ] Token-gated features

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

Built with:
- [web3.py](https://github.com/ethereum/web3.py) — Ethereum interactions
- [LangChain](https://github.com/langchain-ai/langchain) — LLM framework
- [Foundry](https://github.com/foundry-rs/foundry) — Smart contract toolkit

---

**Built by [Maulana](https://github.com/ulsreall)** · [Twitter](https://twitter.com/itseywacc)
