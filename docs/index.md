---
title: Web3 Agent Kit
description: Build autonomous AI agents that interact with blockchains — in minutes, not months.
hide:
  - navigation
  - toc
  - title
---

<!-- Hero Section -->
<div class="tx-hero tx-hero-gradient" markdown>

# Web3 Agent Kit

<div class="tx-hero-sub" markdown>

Build autonomous AI agents that interact with blockchains — **in minutes, not months.**

</div>

<div class="tx-hero-code" markdown>

```bash
pip install web3-agent-kit
```

</div>

<div class="tx-hero-buttons" markdown>
[Get Started](getting-started.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/ulsreall/web3-agent-kit){ .md-button }
</div>

</div>

<!-- Stats Bar -->
<div class="tx-stats" markdown>
<div class="stat" markdown>
<div class="stat-num">v1.6.0</div>
<div class="stat-label">Version</div>
</div>
<div class="stat" markdown>
<div class="stat-num">19</div>
<div class="stat-label">Modules</div>
</div>
<div class="stat" markdown>
<div class="stat-num">565+</div>
<div class="stat-label">Tests</div>
</div>
<div class="stat" markdown>
<div class="stat-num">7+</div>
<div class="stat-label">Chains</div>
</div>
<div class="stat" markdown>
<div class="stat-num">MIT</div>
<div class="stat-label">License</div>
</div>
</div>

<!-- One-liner Demo -->
<div class="tx-divider"></div>

## 🚀 From Zero to Agent in 5 Lines

```python
from web3_agent_kit import Agent, Wallet, Chain
from web3_agent_kit.defi import Uniswap

agent = Agent(wallet=Wallet.from_env("PRIVATE_KEY"), chains=[Chain.BASE], tools=[Uniswap()])
result = agent.run("Swap 0.1 ETH to USDC on Base")
print(result)
```

Or use the **CLI** — no Python needed:

```bash
wak agent "Swap 0.1 ETH to USDC on Base"
```

<div class="tx-divider"></div>

## ✨ Everything You Need

<div class="tx-features" markdown>

<div class="tx-feature" markdown>
<span class="tx-feature-icon">🤖</span>
### Agent Framework
Goal-driven autonomous agents with LLM reasoning. Natural language in, on-chain actions out.
</div>

<div class="tx-feature" markdown>
<span class="tx-feature-icon">💰</span>
### DeFi Tools
Uniswap V2, Aerodrome, Aave, Curve. Real swaps, quotes, approvals, slippage protection.
</div>

<div class="tx-feature" markdown>
<span class="tx-feature-icon">🎯</span>
### Airdrop Suite
Galxe, Zealy, Layer3, Gleam, QuestN, Intract. Multi-wallet farming, auto-discovery.
</div>

<div class="tx-feature" markdown>
<span class="tx-feature-icon">🔐</span>
### Security Audit
Static analysis, fuzzing, exploit PoC, forensics. 10 specialized audit skills built-in.
</div>

<div class="tx-feature" markdown>
<span class="tx-feature-icon">⚡</span>
### MEV Bots
Cross-DEX arbitrage, liquidation bot, Flashbot support. Extract value from mempool.
</div>

<div class="tx-feature" markdown>
<span class="tx-feature-icon">🖼️</span>
### NFT Tools
Deploy collections, batch mint, marketplace listing. ERC-721A optimized.
</div>

<div class="tx-feature" markdown>
<span class="tx-feature-icon">📈</span>
### Trading Bots
DCA with price triggers, yield optimizer, token sniper. Automated strategies.
</div>

<div class="tx-feature" markdown>
<span class="tx-feature-icon">🌉</span>
### Cross-Chain Bridge
Li.Fi + Socket aggregators. Best routes, lowest fees, 7+ chains.
</div>

<div class="tx-feature" markdown>
<span class="tx-feature-icon">🛠️</span>
### CLI Tool
`wak` — 7 commands for terminal usage. Check balances, gas, run agents, zero Python.
</div>

</div>

<div class="tx-divider"></div>

## 🏗️ Architecture

```
User / Application
        │
        ▼
┌───────────────────────────┐
│     Agent Framework       │
│  Goal → LLM → Tool → TX  │
└─────────────┬─────────────┘
              │
   ┌──────────┼──────────┐
   │   Safety Layer      │
   │  Governor + Kill SW │
   └──────────┼──────────┘
              │
   ┌──────────┼──────────────────────────────────┐
   │          Tool Ecosystem                      │
   │  DeFi · Airdrop · Security · MEV · NFT      │
   │  Trading · Portfolio · Bridge · Gas · Wallet │
   └──────────┼──────────────────────────────────┘
              │
   ┌──────────┼──────────┐
   │  Chain Abstraction   │
   │  ETH · BASE · ARB   │
   │  OP · MATIC · BSC   │
   └─────────────────────┘
```

<div class="tx-divider"></div>

## ⚡ Quick Start

=== "Python"

    ```python
    from web3_agent_kit import Agent, Wallet, Chain, ChainManager
    from web3_agent_kit.defi import Uniswap

    chain_manager = ChainManager(chains=[Chain.BASE])
    wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
    uniswap = Uniswap(chain_manager=chain_manager)

    agent = Agent(wallet=wallet, chains=[Chain.BASE], tools=[uniswap])
    result = agent.run("Swap 0.1 ETH to USDC on Base")
    ```

=== "CLI"

    ```bash
    # Check your wallet
    wak wallet

    # Check gas prices
    wak gas

    # Run an agent
    wak agent "Swap 0.1 ETH to USDC on Base"
    ```

=== "Airdrop Farming"

    ```python
    from web3_agent_kit.airdrop import MultiWalletManager

    manager = MultiWalletManager.from_csv("wallets.csv")
    manager.execute_on_all("swap", token_in="ETH", token_out="USDC", amount=0.01)
    ```

=== "Security Audit"

    ```python
    from web3_agent_kit.security import StaticAnalyzer

    analyzer = StaticAnalyzer()
    results = analyzer.analyze("contracts/Token.sol")
    for vuln in results.vulnerabilities:
        print(f"[{vuln.severity}] {vuln.name}")
    ```

<div class="tx-divider"></div>

## 📦 Supported Chains

| Chain | Status | DeFi | Bridge |
|-------|:------:|:----:|:------:|
| Ethereum | ✅ | ✅ | ✅ |
| Base | ✅ | ✅ | ✅ |
| Arbitrum | ✅ | ✅ | ✅ |
| Optimism | ✅ | ✅ | ✅ |
| Polygon | ✅ | ✅ | ✅ |
| Avalanche | ✅ | — | ✅ |
| BSC | ✅ | — | ✅ |

<div class="tx-divider"></div>

## 🤝 Contributing

We welcome contributions! Whether it's bug reports, feature requests, documentation improvements, or code contributions.

[Contributing Guide](contributing.md){ .md-button .md-button--primary }

<div class="tx-divider"></div>

<div style="text-align: center; opacity: 0.6; font-size: 0.85rem;">

Built by [Maulana](https://github.com/ulsreall) · [Twitter](https://twitter.com/itseywacc) · [PyPI](https://pypi.org/project/web3-agent-kit/)

</div>
