# Changelog

All notable changes to Web3 Agent Kit are documented here.

---

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
- 163 source files (was 115)
- 1,033 tests passing (was 991)
- 60% coverage (was 31%)
- 8 chains supported

---

## [1.9.1] - 2026-07-01

### Fixed
- Coverage badge: 58% → 31% (actual)
- Version bump to 1.9.1

### Stats
- 23 modules
- 115 source files
- 991 tests passing
- 31% coverage
- 8 chains supported

---

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
- 31% coverage
- 8 chains supported (was 7)

---

## [1.8.0] - 2026-06-29

### Added
- Aave V3 integration — supply, borrow, repay, liquidation
- Curve Finance — swaps across all pool types, gauge deposits
- Uniswap V3 — pool queries, multi-hop quotes, position NFTs

### Changed
- CI workflow fixed (`httpx2` typo removed)
- README stats updated

---

## [1.7.0] - 2026-06-28

### Added
- Restaking module — EigenLayer, Babylon BTC, Solana restaking
- Notifications module — Telegram, Discord, email alerts
- Plugin system — custom tool registration
- MEV protection — Flashbots, private mempool

---

## [1.6.0] - 2026-06-06

### Added
- **CLI tool `wak`** — 7 commands for terminal usage (info, doctor, wallet, gas, token, examples, agent)
- ASCII art banner on CLI startup
- click + rich CLI dependencies

### Changed
- Updated README with CLI tool usage
- Version bump to 1.6.0

---

## [1.5.0] - 2026-06-05

### Added
- Gas optimizer with historical analysis
- Portfolio tracker with P&L
- Cross-chain bridge via Li.Fi + Socket
