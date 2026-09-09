# Capability and Maturity Matrix

This matrix is the canonical feature-status reference. A module's maturity level describes the implementation and test evidence in this repository; it is not a guarantee that an external protocol, RPC provider, or transaction is safe.

## Maturity levels

- **Stable** — read-only or core behavior with strong offline coverage and documented failure modes.
- **Beta** — functional and tested, but interfaces or external integrations can change.
- **Experimental** — useful for research, controlled pilots, testnets, or dry runs; not for unattended mainnet funds.

## Matrix

| Capability | Package surface | Maturity | Evidence / limitation |
|---|---|---:|---|
| Agent planning and LLM adapters | `agent/` | Beta | Core tests exist; provider responses remain untrusted input. |
| Chain and RPC configuration | `chains/` | Stable | Read-only chain abstraction and provider fallback. |
| Robinhood Chain connectivity | `Chain.ROBINHOOD` | Beta | EVM mainnet configuration: chain ID 4663, ETH gas, Robinscan explorer; DEX/bridge protocol adapters are not claimed. |
| Wallet and signing primitives | `wallet/` | Beta | Local signer boundary; requires explicit operational controls. |
| Spend policy and execution intent | `execution/`, `utils/` | Beta | Limits, confirmation, and kill-switch primitives exist. |
| Uniswap V2/V3, Aave V3, Curve, Aerodrome | `defi/` | Beta | Offline protocol tests; live protocol state is external. |
| Portfolio and balance tracking | `portfolio/` | Beta | Read-heavy workflow; token coverage is not universal. |
| Gas and approval analysis | `gas/`, `wallet/approval.py` | Beta | Useful preflight signals; not a complete security verdict. |
| Transaction simulation | `simulator/` | Experimental | `eth_call`, Tenderly, and fork paths need deployment-specific validation. |
| Oracle aggregation | `oracle/` | Experimental | Chainlink, DexScreener, and CoinGecko adapters need source health checks. |
| Event subscriptions and webhooks | `events/` | Experimental | Polling and callback behavior needs production soak testing. |
| REST API and CLI | `api/`, `cli/` | Beta | API key fail-closed behavior exists; deploy behind a trusted network. |
| Plugin registry | `plugins/` | Beta | Extension point is intentional; plugin contracts need versioning. |
| DCA bot | `trading/dca.py` | Beta | Persistence and limits exist; durable idempotency needs more work. |
| Token sniper and risk scan | `trading/sniper.py`, `security/` | Experimental | Risk signals are not proof of safety; add simulation before broadcast. |
| Airdrop discovery and executors | `airdrop/` | Experimental | Browser, social, CAPTCHA, and external platform flows have low integration coverage. |
| Multi-wallet operations | `airdrop/multi_wallet.py`, `wallet/multi_wallet.py` | Experimental | Requires explicit wallet ownership, rate limits, and audit trails. |
| NFT manager, mint, marketplace, whitelist | `nft/` | Experimental | External marketplace and collection behavior is not fully verified. |
| MEV protection and strategies | `mev/` | Experimental | Requires fork/testnet validation and chain-specific relayer testing. |
| Solana client, DEX, LP, NFT | `solana/` | Experimental | Optional dependencies and network-specific behavior apply. |
| Restaking integrations | `plugins/restaking/` | Experimental | Plugin namespace by design; protocol state and slashing risk are external. |
| Account abstraction | `account_abstraction/` | Experimental | ERC-4337 primitives exist; bundler/paymaster compatibility needs live fixtures. |
| Cross-chain messaging | `messaging/` | Experimental | LayerZero, Wormhole, and CCIP adapters need delivery/fee integration tests. |
| Governance tracking and delegation | `governance/` | Experimental | Snapshot/Tally read paths are useful; write paths need additional review. |
| Token security analysis | `security/` | Experimental | Honeypot, tax, liquidity, holder, and contract-pattern analysis; not a general audit framework. |
| Notifications | `notifications/` | Beta | Telegram, Discord, and email adapters exist; legacy duplicate helpers need consolidation. |

## Scope boundaries

The core package does **not** currently provide a general Slither/Echidna exploit-development or on-chain-forensics framework. Those workflows belong in separate security tooling or integrations until implemented and tested here.

The airdrop/browser modules are optional automation surfaces, not prerequisites for the core agent, DeFi, wallet, or API workflows. They should remain isolated from the default production path.
