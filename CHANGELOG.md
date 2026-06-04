# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-06-04

### Added
- **Yield Optimizer** (`src/yield_optimizer.py`) — Cross-protocol yield farming + auto-compound
  - DeFiLlama API integration for real-time APY/TVL data
  - 6 supported protocols: Aave V3, Compound V3, Morpho, Lido, Rocket Pool, Fluid
  - Auto-compound with configurable threshold and interval
  - Risk assessment (LOW/MEDIUM/HIGH)
  - Portfolio summary with P&L tracking
  - Protocol comparison for any asset
- **Multi-Wallet Manager** (`src/multi_wallet.py`) — Manage multiple wallets with batch operations
  - Create/import wallets with labels, groups, and tags
  - Batch send native tokens and ERC20s across wallet groups
  - Consolidated portfolio view across all wallets
  - Fund consolidation to single target wallet
  - Export addresses (JSON/CSV)
  - Persistent metadata storage (no private keys on disk)
- **Plugin System** (`src/plugins/`) — Extend with community plugins
  - Abstract `Plugin` base class with lifecycle hooks
  - `PluginRegistry` for discovery and management
  - `PluginManager` with agent lifecycle integration
  - Hooks: `on_transaction`, `on_block`, `on_price_update`, `on_startup`, `on_shutdown`
  - Discovery: local directories, Python entry points, manual registration
  - Example plugin: `GasTrackerPlugin`

### Changed
- Version bumped from 0.3.0 to 0.4.0
- Added `httpx` as dependency (for DeFiLlama API)
- Updated README with Yield Optimizer, Multi-Wallet, and Plugin System docs
- Updated comparison table and architecture

## [0.3.0] - 2025-06-04

### Added
- **Token Sniper** (`src/sniper.py`) — Monitor new liquidity pools and auto-buy safe tokens
  - Uniswap V2 factory PairCreated event monitoring
  - Risk assessment (honeypot, liquidity, contract size)
  - Auto-buy safe tokens with configurable slippage
  - Background monitoring thread with callbacks
- **Portfolio Dashboard** (`src/portfolio.py`) — Real-time balances across chains
  - Token balance tracking (WETH, USDC, USDT, DAI, WBTC, LINK, UNI, ARB, GMX, AERO)
  - USD value calculation
  - P&L tracking with snapshots
- **Bridge Agent** (`src/bridge.py`) — Cross-chain transfers
  - Li.Fi aggregator integration
  - Socket aggregator integration
  - Best route finding (sorted by output amount)
  - Execute transfers with tx confirmation
- **Examples**: `token_sniper.py`, `portfolio_dashboard.py`, `bridge_agent.py`
- **Tests**: 50 tests covering LLM, portfolio, bridge, sniper modules

### Changed
- Version bumped from 0.2.0 to 0.3.0

## [0.2.0] - 2025-06-04

### Added
- **LLM Integration** (`src/llm.py`) — Multi-provider cascade with fallback
  - Support: OpenAI, Anthropic, Groq, DeepSeek, OpenRouter, Kimi
  - Auto-detect from environment variables
  - JSON response mode
  - Graceful fallback on 429/5xx/timeout
- **Uniswap V2 Swaps** — Actual token swap execution
  - swapExactETHForTokens, swapExactTokensForETH, swapExactTokensForTokens
  - getAmountsOut for quotes
  - ERC20 approve handling
  - Token symbol resolution (ETH, USDC, USDT, WETH)
  - Multi-chain support (Ethereum, Base, Arbitrum, Optimism, Polygon)
- **Agent LLM Reasoning** — Natural language goal execution
  - System prompt with tool descriptions
  - Conversation context with history
  - JSON output parsing
- **Examples**: `llm_swap_agent.py`, `direct_swap.py`

### Changed
- Version bumped from 0.1.0 to 0.2.0

## [0.1.0] - 2025-06-03

### Added
- Initial release
- Core agent framework (`src/agent.py`)
- Wallet management (`src/wallet.py`)
- Multi-chain support (`src/chain.py`)
- DeFi tools base (`src/defi/__init__.py`)
- Spend governor (`src/utils/__init__.py`)
- Examples: `swap_agent.py`, `yield_optimizer.py`, `airdrop_farmer.py`, `sniper_bot.py`, `portfolio_tracker.py`
- CI/CD pipeline
- MIT License
