# CLI Tool — `wak`

Web3 Agent Kit ships with a terminal CLI tool called `wak` for quick blockchain operations without writing Python.

---

## Installation

```bash
pip install web3-agent-kit
```

The `wak` command is automatically available after installation.

---

## Commands

### `wak info`

Display package information and version.

```bash
$ wak info
╔══════════════════════════════════════════════╗
║         🤖 Web3 Agent Kit v1.14.0             ║
║    Open-source AI agent framework for Web3   ║
╚══════════════════════════════════════════════╝

📦 Version: 1.14.0
🔗 GitHub: https://github.com/ulsreall/web3-agent-kit
📦 PyPI: https://pypi.org/project/web3-agent-kit/
```

### `wak doctor`

Check environment health — validates API keys, RPC endpoints, and dependencies.

```bash
$ wak doctor
🔍 Environment Check
✅ PRIVATE_KEY: set
✅ ANTHROPIC_API_KEY: set
✅ BASE_RPC: set
⚠️ OPENAI_API_KEY: not set (optional)
✅ All core dependencies installed
```

### `wak wallet`

Check wallet balance across chains.

```bash
$ wak wallet
💰 Wallet: 0x721e...A522

🔗 ETHEREUM: 0.5 ETH ($1,750.00)
🔗 BASE: 1.2 ETH ($4,200.00)
🔗 ARBITRUM: 0.05 ETH ($175.00)

Total: $6,125.00
```

### `wak gas`

Check current gas prices across chains.

```bash
$ wak gas
⛽ Gas Prices

🔗 ETHEREUM: 12 gwei (Low: 8 / Avg: 12 / High: 18)
🔗 BASE: 0.001 gwei
🔗 ARBITRUM: 0.1 gwei
🔗 OPTIMISM: 0.005 gwei
```

### `wak token <address>`

Check token info and balance.

```bash
$ wak token 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
🪙 USDC (USD Coin)
📍 Base: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
💰 Balance: 1,456.78 USDC
💵 Price: $1.00
```

### `wak examples`

List all available code examples.

```bash
$ wak examples
📚 Available Examples

  1. basic_agent.py        — Create your first agent
  2. swap_tokens.py        — Swap tokens on Uniswap
  3. portfolio.py          — Track portfolio across chains
  4. bridge.py             — Cross-chain bridging
  5. sniper.py             — Token sniper bot
  6. airdrop_hunter.py     — Hunt airdrops automatically
  7. security_audit.py     — Audit smart contracts
  8. mev_bot.py            — MEV extraction
  9. dca_bot.py            — Dollar-cost averaging
  10. multi_wallet.py      — Multi-wallet management
```

### `wak agent --goal <goal> --wallet <address>`

Run an agent with a natural language goal directly from terminal.

```bash
$ wak agent --goal "Check my ETH balance on Base" --wallet 0x721e...A522
🤖 Agent running...
📊 Goal: Check my ETH balance on Base

🔗 Base: 1.2000 ETH ($4,200.00)

✅ Goal completed in 2.3s
```

---

## Environment Variables

The CLI reads the same env vars as the Python library:

```bash
# Required
export PRIVATE_KEY="0x..."

# At least one LLM provider (for `wak agent`)
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."

# Optional: custom RPCs
export BASE_RPC="https://..."
export ETH_RPC="https://..."
```

---

## Global Options

```bash
wak --help          # Show help
wak --version       # Show version
wak --verbose       # Enable verbose output
```
