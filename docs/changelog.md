# Changelog

All notable changes to Web3 Agent Kit are documented here.

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

### Changed
- **Major repo reorganization** — 13 flat files → 7 subdirectories (agent, airdrop, chains, defi, security, trading, utils)
- Backward compatible imports maintained
- Updated CI to handle new structure

---

## [1.4.0] - 2026-06-05

### Added
- MEV module — arbitrage bot, liquidation bot, Flashbot support
- NFT module — collection deploy, batch minting, marketplace
- Notifications module — Telegram, Discord, webhook alerts

---

## [1.3.0] - 2026-06-05

### Added
- **Real execution layer** — actual on-chain transactions
- Airdrop suite — Galxe, Zealy, Layer3, QuestN, Intract, Gleam integrations
- Multi-wallet management
- Form filler for whitelist applications
- Whitelist grinder for X/Twitter automation

---

## [1.2.0] - 2026-06-05

### Added
- Security module — static analysis, fuzzing, exploit development, forensics
- Protocol audit capabilities
- 10 specialized security skills

---

## [1.1.0] - 2026-06-04

### Added
- Trading bots — DCA bot, yield optimizer
- Plugin system for extensibility
- Enhanced portfolio tracking

---

## [1.0.0] - 2026-06-04

### Added
- First stable release
- Full agent framework with LLM reasoning
- Multi-chain support (7 chains)
- Uniswap V2 swaps, bridge agent, token sniper
- Spend governor and kill switch safety features
- PyPI package publication

---

## [0.3.0] - 2025-01-XX

### Added
- Multi-provider LLM cascade with automatic fallback
- Token sniper with risk assessment
- Cross-chain bridge agent (Li.Fi + Socket)
- Portfolio tracker with P&L calculation
- Aerodrome DEX integration (Base)
- Telegram bot showcase

### Changed
- Improved agent reasoning loop
- Better error handling across all modules
- Updated default RPC endpoints

### Fixed
- Transaction nonce management
- Token approval race conditions

---

## [0.2.0] - 2024-12-XX

### Added
- Multi-chain support (Ethereum, Base, Arbitrum, Optimism, Polygon)
- Uniswap V2 swap execution
- Wallet management (private key, seed phrase, keystore)
- Chain manager with custom RPC support

### Changed
- Migrated from single-chain to multi-chain architecture

---

## [0.1.0] - 2024-11-XX

### Added
- Initial release
- Basic agent framework
- LLM integration (OpenAI)
- Simple swap functionality
