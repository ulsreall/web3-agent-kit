# Roadmap

> **Current version:** v1.15.0  
> **Updated:** 2026-07-23  
> **Modules:** 25  
> **Tests:** 1,248+ (70% coverage gate)
> **Chains:** 8 (Ethereum, Base, Polygon, Arbitrum, Optimism, BSC, Avalanche, Solana)

---

## Phase 1 — Foundation ✅ (v1.0 - v1.9)

| Feature | Status |
|---------|--------|
| Core agent framework | ✅ |
| Wallet management | ✅ |
| Multi-chain support | ✅ |
| DeFi protocols (Uniswap V3, Aave, Curve) | ✅ |
| Airdrop automation | ✅ |
| DCA bot, token sniper | ✅ |
| REST API server | ✅ |
| CLI tool | ✅ |
| GitHub Pages docs | ✅ |

## Phase 2 — Solana & DEX Expansion ✅ (v1.10 - v1.14)

| Feature | Status |
|---------|--------|
| Async airdrop module | ✅ |
| PyPI trusted publisher | ✅ |
| Solana module (client, wallet, Jupiter DEX, NFT, LP) | ✅ |
| DEX Aggregator (1inch, Paraswap, 0x, Jupiter) | ✅ |
| Package import path fix (`src` → `web3_agent_kit`) | ✅ |
| REST API auth + fail-closed | ✅ |
| SpendGovernor enforcement | ✅ |

## Phase 3 — Security Hardening ✅ (v1.15)

| Feature | Status |
|---------|--------|
| SpendGovernor + confirm_fn wiring | ✅ |
| Honeypot fail-open fix (3-state) | ✅ |
| `swap_exact_output` protections | ✅ |
| Coverage gate 70% | ✅ |
| Dependabot + pip-audit CI | ✅ |
| Release-please draft workflow | ✅ |
| MCP server scaffold | ✅ |
| Security model documentation | ✅ |
| Architecture Decision Records (3) | ✅ |
| Good-first-issue labels (3) | ✅ |

## Phase 4 — Community & Process 🚧 (current)

| Feature | Status |
|---------|--------|
| CONTRIBUTING.md updated | ✅ |
| ROADMAP.md | ✅ | *[this file]* |
| GitHub Discussions | ✅ | Enabled |
| **Supply-chain security** | ✅ | Scorecard, SBOM, lockfile, pinned actions |
| **Governance documentation** | ✅ | DCO, versioning-policy, SECURITY.md, fuzz tests |

## Phase 5 — Stabilization & Trust (current)

New integrations are lower priority until the execution path is safe,
observable, and consistently tested.

| Outcome | Priority | Exit criterion |
|---------|----------|----------------|
| Module maturity policy | High | Every capability is classified as stable, beta, or experimental |
| Unified transaction policy | High | Every write path uses limits, allowlists, and explicit confirmation rules |
| Pre-flight simulation | High | Every supported write path can be simulated before signing |
| Signer abstraction | High | Core execution does not require direct access to a raw private key |
| Typed public API | Medium | Public interfaces pass static type checking in CI |
| Test isolation | Medium | Unit, integration, network, and security suites are independently runnable |
| Documentation consistency | Medium | Version, support, coverage, and readiness claims have one source of truth |
| External security review | Medium | Critical execution paths reviewed before a v2.0 stable release |

## Phase 6 — Production Proof (planned)

| Outcome | Priority | Exit criterion |
|---------|----------|----------------|
| Safe portfolio reference agent | High | Read-only by default, simulated writes, human approval |
| Policy-controlled DCA agent | High | Allowlisted assets, bounded value/slippage, complete audit trail |
| Testnet soak testing | High | Continuous multi-day runs without unresolved critical failures |
| Design partners | Medium | At least three external projects validate real workflows |
| Maintainer ownership | Medium | Named owners and support expectations for stable modules |
| v2.0 release candidate | Medium | Migration guide, compatibility policy, and security review complete |

## Beyond

| Idea | Status |
|------|--------|
| Hardware wallet support | Exploring |
| Transaction simulation in Agent | Phase 5 priority |
| Webhook notifications | Exploring |
| Zeroisation of private keys | Researching |
| On-chain incident monitoring | Researching |

---

*This roadmap is a living document. Priority may shift based on user feedback and ecosystem changes.*
