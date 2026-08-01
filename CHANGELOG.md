# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.15.0] - 2026-07-23

### BREAKING CHANGE

- **`TaxInfo.is_honeypot` and `TaxInfo.can_sell` types changed from `bool` to `Optional[bool]`.**
  Previously, both fields defaulted to `False` / `True`, which meant a failed API
  call was silently treated as "safe" (fail-open). The new default is `None`
  (unverified/unknown). `SecurityReport.is_safe` now returns `False` when the
  honeypot status is `None`. All internal callers have been updated to use
  explicit 3-state comparisons (`is True` / `is None` / `is False`). External
  code using truthy checks (`if tax.is_honeypot:`) will still work syntactically
  but will treat `None` as falsy — upgrade your callers to use
  `tax.is_honeypot is True` for the old behaviour.

### Security

- **`SpendGovernor` now raises `ValueError` at construction time** when
  `require_confirm=True` is set without a `confirm_fn` callable. Previously it
  silently skipped the confirmation gate.
- **`AgentConfig.confirm_fn` is now wired to `SpendGovernor.confirm_fn`**
  automatically in `Agent.__init__`. Previously setting a `confirm_fn` on the
  config had no effect — the governor never called it.
- **`_estimate_tx_value` returns `None`** (instead of `0.0`) for unrecognised
  argument keys. The governor now blocks execution when the transaction value
  is unknown, requiring explicit operator approval.
- **`swap_exact_output()` hardened**: `amount_in_max` and `recipient` are now
  required parameters. The previous defaults (`2**256-1` and `0x0`) exposed
  callers to unlimited token spend and fund loss. A warning docstring marks the
  method as not production-ready.

### Fixed

- **Honeypot/tax check no longer fail-open.** When GoPlus API calls fail
  (timeout, network error, rate limit), `is_honeypot` and `can_sell` now remain
  `None` (unknown) instead of defaulting to safe. The error message is saved in
  `TaxInfo.error` for debugging.
- **`quick_check()` returns `is_honeypot=None`** on API failure, with the error
  stored in a new `error` key in the result dict.
- **Corrected misleading comment** in `MultiWalletManager._private_keys`:
  private keys are stored as plaintext in memory (not encrypted).

### Changed

- **Coverage gate raised from 40% to 60%** (`pyproject.toml` `fail_under`).
  Current coverage: 62.26%.

## [1.14.0] - 2026-07-21

### Security
- REST API now requires authentication (`X-API-Key` / `WEB3_API_KEY`) on all sensitive endpoints; server fails closed and refuses to start if `WEB3_API_KEY` is unset
- Default API bind host changed from `0.0.0.0` to `127.0.0.1`; explicit `0.0.0.0` now logs a clear network-exposure warning
- CORS configuration hardened — origins are now driven by `CORS_ALLOWED_ORIGINS` (empty by default) and the unsafe `allow_origins=["*"]` + `allow_credentials=True` combination is rejected at startup
- `/wallet/create` is now disabled by default (`ENABLE_WALLET_CREATE_ENDPOINT=false`) and returns a clearer one-time-secret warning

### Fixed
- Spend governor is now enforced by default on every `Agent` (conservative limits) and no longer crashes when wired into `Agent._act()` — it now receives the correct `tx_value`/`action` arguments instead of a raw dict
- `GET /wallet/balance/{address}` now queries the requested address instead of always returning the configured env wallet's balance

### Added
- `Wallet.from_keystore(path, password)` — load and decrypt a standard Ethereum JSON keystore file

### Removed
- Unused `httpx2` dependency

### BREAKING CHANGES
- `WEB3_API_KEY` is now mandatory to start the REST API server
- `AgentConfig.governor` is active by default with conservative spend limits — pass a custom governor or explicitly set `governor=None` to opt out

## [1.13.0] - 2026-07-14

### Changed
- Version bump to 1.13.0 across package metadata (`__init__.py`, `pyproject.toml`)

## [1.12.0] - 2026-07-12

### Fixed
- **CRITICAL DX:** package import path is now `web3_agent_kit` (was incorrectly installed as `src`)
- README/docs/examples import paths aligned with real package name
- CLI version string synced to release version
- Notification module duplication: `notifications/` is canonical; `utils/notif_*` are thin shims
- Runtime `__version__` and packaging metadata kept in sync

### Added
- `Agent(private_key=...)` convenience constructor
- `Agent.execute()` alias for `Agent.run()`
- CI import smoke test for public package path

### Changed
- Source tree renamed: `src/` → `web3_agent_kit/`
- Pytest/coverage config now tracks `web3_agent_kit`

## [1.11.0] - 2026-07-11

### Added
- **Solana module** — client, wallet, Jupiter DEX, NFT helpers
- **DEX Aggregator** — 1inch + Paraswap + 0x + Jupiter unified quote/swap interface
- Expanded test coverage for Solana + aggregator paths

### Stats
- 24+ modules
- 1100+ tests
- 8 chains supported

## [1.10.0] - 2026-07-06

### Added
- **Async airdrop module** — 31 `time.sleep()` calls converted to `asyncio.sleep()` / `page.wait_for_timeout()`
  - `scheduler.py`, `discovery.py`, `faucet.py`, `onchain.py`, `multi_wallet.py`, `wl_grinder.py`, `form_filler.py`, `base.py`
- **Simulator test suite** — 29 new tests for TransactionSimulator
- **PyPI trusted publisher** — OIDC-based auto-publish on GitHub Release (no API token needed)

### Changed
- `AirdropScheduler.start()` now uses async event loop in background thread
- `AirdropScheduler.run_task_now()` is now async (`await`)
- `FaucetClaimer.claim_chain()` is now async (`await`)
- `AirdropFarmer.farm_campaign()` is now async (`await`)
- CI: added `pytest-asyncio` dependency for async test support

### Stats
- 27 modules (was 23)
- 1,033 tests passing (was 991)
- 60% coverage (was 58%)
- 8 chains supported

## [1.9.1] - 2026-07-01

### Fixed
- Coverage badge: 58% → 31% (actual)
- Docs: updated version to v1.9.1, coverage stats, chain table (Berachain → Solana)
- CLI version: `wak --version` now shows 1.9.1

### Stats
- 23 modules
- 115 source files
- 991 tests passing
- 31% coverage
- 8 chains supported

## [1.9.0] - 2026-06-30

### Added
- **Oracle Aggregator** — Multi-source price feeds (Chainlink, DexScreener, CoinGecko) with weighted median, cache, and auto-fallback
- **Event Listener** — On-chain event subscription with webhooks, callbacks, and background polling
- **Transaction Simulator** — Pre-flight TX verification via eth_call, Tenderly API, and local fork
- **Account Abstraction** — ERC-4337 bundler, paymaster integration (Pimlico), smart account factory (SimpleAccount, Safe, Kernel)
- **Cross-chain Messaging** — LayerZero + Wormhole + CCIP unified API with status tracking and fee estimation
- **Governance** — Snapshot + Tally + on-chain governor, proposal tracking, voting power, delegation
- `.env.example` with all module configurations
- Integration test suite (`tests/test_integration.py`)
- PyPI auto-publish workflow via GitHub Actions
- Aave V3, Curve, Uniswap V3 DeFi integrations

### Changed
- `restaking/` moved to `plugins/restaking/` — now a plugin, not a core module
- `notifications/` merged into `utils/` — backward-compatible re-exports maintained
- README updated with 6 new module sections, architecture diagram, and stats
- PyPI keywords updated with oracle, erc4337, governance, cross-chain, layerzero, simulation
- Version bump to 1.9.0

### Stats
- 23 modules (was 18)
- 115 source files (was 104)
- 32,743 lines of code
- 991 tests passing (was 986)
- 58% coverage (later corrected to 31%)
- 8 chains supported (was 7)

## [1.8.0] - 2026-06-17

### Added
- **Aave V3 Integration** — Full lending/borrowing protocol support
  - `supply()` — Deposit tokens into Aave
  - `withdraw()` — Withdraw deposited tokens
  - `borrow()` — Borrow with variable/stable rate
  - `repay()` — Repay borrowed tokens
  - `get_user_data()` — Health factor, deposits, borrows
  - `get_reserve_data()` — APY, LTV, liquidation threshold
  - Multi-chain support (Ethereum, Base, Arbitrum, Optimism, Polygon)
- **Curve Finance Integration** — DEX + liquidity pool support
  - `swap()` — Swap via Curve pools
  - `get_swap_estimate()` — Get price quotes
  - `get_pool_info()` — Pool tokens, balances, APY
  - `add_liquidity()` / `remove_liquidity()` — LP management
- **Uniswap V3** — Concentrated liquidity support
  - `swap()` / `swap_exact_output()` — Exact input/output swaps
  - `get_quote()` — Price quotes via QuoterV2
  - `mint_position()` — Create liquidity positions (NFT)
  - `increase_liquidity()` / `decrease_liquidity()` — Manage positions
  - `collect_fees()` — Collect accumulated fees
  - Tick math helpers (tick ↔ sqrtPriceX96 conversion)
  - Fee tiers: 0.01%, 0.05%, 0.3%, 1%
- **122 new DeFi tests** — Full coverage for Aave, Curve, UniswapV3

### Changed
- **Airdrop module cleanup** — 27 `time.sleep()` annotated with async TODOs
- Replaced bare `except Exception:` in airdrop form_filler and faucet
- Replaced `print()` with `logging` in airdrop faucet
- Updated README: Aave/Curve now marked as implemented (not "coming soon")
- Total tests: 986 (up from 817)

## [1.7.0] - 2026-06-14

### Added
- **Restaking Module** (`src/restaking/`) — EigenLayer, Babylon BTC, Solana restaking
  - `EigenLayer` class — restake LSTs, delegate to operators, track rewards, estimate yields
  - `BabylonBtcRestaking` — Bitcoin restaking via Babylon protocol
  - `SolanaRestaking` — Solana restaking (Solayer, Jito, Marinade)
  - `RestakingOptimizer` — Cross-protocol yield optimization with risk-adjusted scoring
  - `RestakingMonitor` — Position tracking, slashing alerts, portfolio snapshots
  - Real contract addresses for EigenLayer mainnet (StrategyManager, DelegationManager, Slasher)
- **Price Utility** (`src/utils/prices.py`) — Real-time price fetching
  - CoinGecko API integration with 60-second cache
  - `get_price_usd()` for any asset, `get_eth_price_usd()` convenience function
  - Stablecoin detection, graceful fallback on API failure
- **252 new tests** — Full coverage for mev, nft, gas, notifications, restaking modules
  - `tests/test_mev.py` — 43 tests (sandwich protection, frontrun detection, strategies)
  - `tests/test_nft.py` — 50 tests (minting, marketplace, whitelist, rarity)
  - `tests/test_gas.py` — 28 tests (optimizer, batch operations, recommendations)
  - `tests/test_notifications.py` — 40 tests (Telegram, Discord, email delivery)
  - `tests/test_restaking.py` — 91 tests (EigenLayer, Babylon, Solana, optimizer, monitor)

### Changed
- **Refactored monolithic modules** — Split 4 single-file modules into proper submodules:
  - `mev/` → `sandwich_protection.py`, `frontrun_detection.py`, `mev_strategy.py`, `utils.py`
  - `nft/` → `mint.py`, `marketplace.py`, `whitelist.py`, `manager.py`, `utils.py`
  - `notifications/` → `telegram.py`, `discord.py`, `email_notifier.py`, `notifier.py`, `utils.py`
  - `gas/` → cleaned up `optimizer.py` with proper structure
- **Replaced 31 bare `except Exception:`** with specific exceptions (ConnectionError, ValueError, etc.)
- **Replaced `print()` with `logging`** across 15+ files
- **Fixed hardcoded ETH price** — `$3,500` → real CoinGecko price fetch with fallback
- **Fixed hardcoded USD values** in yield optimizer — now uses real price data
- **All `__init__.py` re-exports** preserved for backward compatibility

### Fixed
- `wallet/watcher.py` — ETH price no longer hardcoded at $3,500
- `defi/yield_optimizer.py` — USD value calculation now uses real prices
- Silent error swallowing in mev, bridge, notifications, gas modules

## [1.5.0] - 2026-06-05

### Changed — Major Repo Reorganization
- **Reorganized `src/` structure** — grouped flat files into logical subdirectories:
  - `src/agent/` — Agent core + LLM integration
  - `src/wallet/` — Wallet, multi-wallet, watcher, approval manager
  - `src/bridge/` — Cross-chain bridge agent
  - `src/chains/` — Chain definitions and RPC management
  - `src/portfolio/` — Portfolio tracker
  - `src/trading/` — Token sniper + DCA bot
  - `src/gas/` — Gas optimizer
  - `src/defi/` — DeFi protocols + yield optimizer (merged)
- **Added `__all__` exports** to every `__init__.py` for explicit public API
- **Added `py.typed` marker** for PEP 561 type checking support
- **Moved content files** to proper directories:
  - `blog-post.md` → `blog/post.md`
  - `show-hn.md` → `blog/show-hn.md`
  - `CONTRIBUTING_PLATFORMS.md` → `docs/contributing-platforms.md`
  - `research/` → `docs/research/`
- **Cleaned up root directory** — only config/docs remain
- **Updated all imports** in tests, examples, and API routes
- **Backward compatible** — all `from web3_agent_kit import ...` paths still work

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
