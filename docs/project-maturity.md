# Project Maturity

Web3 Agent Kit is currently **beta software**. Its modules do not all have the
same production-readiness level. A feature being available does not mean it has
been validated for unattended use with real funds.

## Maturity levels

| Level | Stability promise | Intended use |
|---|---|---|
| **Stable** | Backward-compatible within a major version, with offline tests and documented failure modes | Production use with appropriate operational controls |
| **Beta** | Functional and tested, but APIs or behavior may change between minor versions | Controlled pilots and testnet-first deployments |
| **Experimental** | Best-effort implementation with limited compatibility guarantees | Research, evaluation, and testnets only |

No maturity level eliminates blockchain, smart-contract, key-management, or
market risk. Always review the [risk disclosure](https://github.com/ulsreall/web3-agent-kit/blob/master/RISKS.md) and
[security model](security-model.md).

## Current classification

| Area | Level | Notes |
|---|---|---|
| Chain configuration and read-only RPC access | Stable | Validate provider availability and chain identity in deployments |
| Wallet primitives and transaction signing | Beta | Local keys remain sensitive in process memory |
| Spend governor and approval analysis | Beta | Configure explicit limits and confirmation callbacks |
| Agent planning and LLM integrations | Beta | LLM output must be treated as untrusted input |
| REST API and CLI | Beta | The API must remain authenticated and should be exposed only over a trusted network |
| DeFi, bridge, trading, and yield execution | Experimental | Protocol behavior and external APIs can change without notice |
| Solana, NFT, MEV, airdrop, governance, messaging, and account abstraction | Experimental | Testnet and evaluation use only |

The classification is intentionally conservative. A module moves to a higher
level only after satisfying the release criteria below.

## Promotion criteria

### Experimental to Beta

- Public interfaces and supported networks are documented.
- Inputs, addresses, amounts, slippage, and deadlines are validated.
- Unit tests do not require live network access.
- Integration behavior and failure paths are covered with deterministic tests.
- A runnable testnet or dry-run example exists.
- Known financial and operational risks are documented.

### Beta to Stable

- The public API has a documented compatibility commitment.
- Transaction-building and signing boundaries have been security reviewed.
- Write operations support policy enforcement and pre-flight simulation.
- Operational telemetry is available without exposing secrets.
- At least one release cycle has completed without unresolved critical defects.
- A named maintainer owns the module.

## Safe adoption path

1. Start with read-only calls.
2. Use a testnet or local fork.
3. Configure the spend governor and a human confirmation callback.
4. Restrict allowed chains, contracts, tokens, and transaction values.
5. Simulate every write operation before signing.
6. Use a dedicated wallet containing only the minimum required funds.
7. Monitor transactions and keep an emergency shutdown procedure.

Production readiness is a property of the complete deployment—not only the
library. RPC providers, signers, policies, monitoring, network exposure, and
upstream protocols must all be assessed together.
