---
title: "I Built a Python Framework for Autonomous Web3 AI Agents — Here's What I Learned"
published: true
description: "Web3 Agent Kit: Open-source framework for building AI agents that interact with DeFi protocols. Multi-chain, LLM-powered, 5 lines to get started."
tags: web3, python, ai, defi
canonical_url: https://github.com/ulsreall/web3-agent-kit
---

# I Built a Python Framework for Autonomous Web3 AI Agents — Here's What I Learned

After months of building bots, scripts, and automation tools for DeFi, I realized I kept rewriting the same boilerplate: wallet management, RPC connections, swap execution, gas estimation, error handling...

So I built **[Web3 Agent Kit](https://github.com/ulsreall/web3-agent-kit)** — an open-source Python framework that lets you spin up autonomous blockchain agents in 5 lines of code.

```bash
pip install web3-agent-kit
```

## The Problem

Most Web3 automation tools suffer from one or more of these issues:

- **Closed-source** — you don't know what's happening under the hood
- **Chain-specific** — built for Ethereum only, or Solana only
- **Low-level** — requires deep Solidity/smart contract knowledge
- **No AI reasoning** — pure rule-based automation, no adaptability

I wanted something that combines the power of LLMs with on-chain execution, across multiple chains, in Python.

## What It Does

### 1. DeFi Operations (Uniswap V2 Swaps)

```python
from web3_agent_kit import Agent, UniswapSwap, SpendGovernor

agent = Agent(
    name="AlphaSeeker",
    private_key="0x...",
    rpc_url="https://eth.llamarpc.com",
    tools=[
        SpendGovernor(per_tx_cap="0.01 ETH", daily_cap="0.1 ETH"),
        UniswapSwap()
    ]
)

result = await agent.chat("Swap 0.01 ETH to USDC")
```

The spend governor is crucial — it's a hard cap that prevents your agent from going rogue and draining your wallet. Every transaction is checked against per-tx and daily limits before execution.

### 2. Token Sniping with Risk Assessment

The token sniper monitors Uniswap V2 `PairCreated` events in real-time and evaluates each new token:

```python
from web3_agent_kit.sniper import TokenSniper

sniper = TokenSniper(
    w3=w3,
    private_key="0x...",
    buy_amount=0.005,
    min_liquidity=10000,
    callback=my_alert_function
)

# Automatically detects new pairs, assesses risk, buys if safe
sniper.start()
```

Risk assessment includes:
- **Honeypot detection** — can you actually sell?
- **Liquidity analysis** — is there enough depth?
- **Contract verification** — is the source code published?
- **Owner analysis** — is there a renounced ownership?

### 3. Cross-Chain Bridging

Instead of manually comparing routes across bridges, the agent finds the best path:

```python
from web3_agent_kit.bridge import BridgeAgent

bridge = BridgeAgent(private_key="0x...")

# Finds cheapest route from ETH to Base
result = bridge.bridge(
    from_chain="ethereum",
    to_chain="base",
    token="ETH",
    amount=1.0
)
```

It queries both **Li.Fi** and **Socket** aggregators and picks the route with the lowest fees.

### 4. LLM-Powered Reasoning

This is where it gets interesting. The agent doesn't just execute — it *thinks*:

```python
from web3_agent_kit.llm import LLMClient

llm = LLMClient()  # Auto-detects API keys from env

response = llm.chat(
    system="You are a DeFi expert. Analyze market conditions.",
    prompt="Should I swap ETH to USDC now? Gas is 18 gwei.",
    json_mode=True
)
```

The LLM client supports 6 providers with automatic cascade:
1. **Anthropic** (Claude) — best reasoning
2. **Kimi** (Moonshot) — long context
3. **OpenRouter** — multi-model fallback
4. **DeepSeek** — cheap
5. **Groq** — fast inference
6. **OpenAI** — fallback

If one provider hits rate limits or errors, it automatically falls back to the next.

### 5. Portfolio Tracking

Real-time portfolio dashboard across multiple tokens:

```python
from web3_agent_kit.portfolio import Portfolio

portfolio = Portfolio(w3=w3, address="0x...")
dashboard = portfolio.get_dashboard()

# Returns:
# - Token balances with USD values
# - 24h P&L
# - Asset allocation
```

## Architecture Decisions

### Why Python?

Most DeFi tooling is in JavaScript/TypeScript (ethers.js, viem). I chose Python because:
- Better AI/ML ecosystem (LangChain, transformers, etc.)
- Cleaner async patterns for monitoring loops
- The audience I'm targeting (AI engineers) primarily uses Python

### Why Multi-Provider LLM Cascade?

LLM APIs are unreliable. Rate limits, outages, pricing changes. A single-provider setup is a single point of failure. The cascade pattern means your agent never stops thinking.

### Why Spend Governor?

This is non-negotiable for autonomous agents. Without hard caps, a bug or adversarial prompt could drain your wallet. The governor is enforced at the tool level — not the LLM level — so it can't be bypassed by prompt injection.

## What I Learned

1. **Security is everything** — One bug in an autonomous agent can cost real money. The spend governor saved me multiple times during development.

2. **Gas estimation is an art** — Not all transactions estimate gas correctly. You need fallbacks and overestimation buffers.

3. **LLMs are bad at math** — Never let your LLM calculate token amounts. Always use on-chain `getAmountsOut()` for quotes.

4. **Multi-chain is messy** — Every chain has different RPC quirks, gas models, and contract addresses. Abstract early.

5. **Testing with real money is terrifying** — Use testnets, but also test on mainnet with tiny amounts ($0.01) because testnets don't behave the same.

## Try It

```bash
pip install web3-agent-kit
```

**GitHub:** [github.com/ulsreall/web3-agent-kit](https://github.com/ulsreall/web3-agent-kit)

**PyPI:** [pypi.org/project/web3-agent-kit](https://pypi.org/project/web3-agent-kit/)

The repo has 10 ready-to-use examples covering swaps, sniping, portfolio tracking, bridging, and LLM integration. MIT licensed — use it however you want.

Contributions, issues, and feature requests are welcome. If you build something cool with it, I'd love to hear about it.

---

*If you found this useful, consider starring the repo on GitHub. It helps with visibility and motivates me to keep building.*
