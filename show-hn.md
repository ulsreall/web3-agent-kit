# Show HN: Web3 Agent Kit – Build AI Agents That Trade, Bridge, and Snipe on Blockchain

I built an open-source Python framework for creating autonomous AI agents that interact with DeFi protocols across multiple blockchains.

## What it does

Web3 Agent Kit lets you build AI agents that can:
- **Swap tokens** on Uniswap with LLM reasoning
- **Bridge assets** across chains (Ethereum, Base, Arbitrum, Optimism, Polygon)
- **Snipe new tokens** with safety checks (honeypot detection, liquidity analysis)
- **Track portfolios** with real-time P&L
- **Execute natural language goals** like "Swap 0.1 ETH to USDC on Base"

## How I built it

- **Python** with web3.py for blockchain interactions
- **Multi-LLM cascade** (Anthropic → OpenAI → Groq → DeepSeek → OpenRouter → Kimi) for reasoning
- **Li.Fi + Socket** aggregators for cross-chain bridges
- **Uniswap V2** for DEX swaps
- **Safety-first** design with spend governors and kill switches

## Key features

- 🔗 Multi-chain: Ethereum, Base, Arbitrum, Optimism, Polygon, Avalanche, BSC
- 🧠 LLM-powered reasoning with automatic provider fallback
- 🎯 Natural language goals
- 🔫 Token sniper with honeypot detection
- 🌉 Cross-chain bridge via Li.Fi/Socket
- 📊 Portfolio tracking with P&L
- 🔐 Spend governor with per-tx and daily limits

## Quick start

```bash
pip install web3-agent-kit

# Set your keys
export PRIVATE_KEY="0x..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Run
python -c "
from web3_agent_kit import Agent, Wallet, Chain
agent = Agent(wallet=Wallet.from_env('PRIVATE_KEY'), chains=[Chain.BASE])
result = agent.run('Swap 0.1 ETH to USDC')
print(result)
"
```

## Showcase: Telegram Bot

I also built a Telegram bot that demonstrates all features:
- /balance – Check wallet balance
- /swap 0.1 ETH USDC – Swap tokens
- /portfolio – View holdings
- /snipe <address> – Analyze new tokens
- /bridge 100 USDC arbitrum – Cross-chain transfer

## Links

- **GitHub:** https://github.com/ulsreall/web3-agent-kit
- **PyPI:** https://pypi.org/project/web3-agent-kit/
- **Examples:** 10 working examples in /examples

Built by [Maulana](https://github.com/ulsreall) · [@itseywacc](https://twitter.com/itseywacc)
