# Roadmap

> **Current version:** v1.15.0  
> **Updated:** 2026-07-23  
> **Modules:** 25  
> **Tests:** 1,248+ (62% coverage)  
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
| Coverage gate 60% | ✅ |
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
| GitHub Discussions | ⬜ | [`has_discussions`=false] — buka Settings → Features → Discussions
| **Supply-chain security** | ⬜ ***Next up*** |
| **Governance documentation** | ⬜ ***Next up*** |

## Phase 5 — Supply-Chain Security (planned)

| Feature | Priority | Notes |
|---------|----------|-------|
| PyPI Trusted Publishing (OIDC) | High | Replace static API token |
| Pin GH Actions to commit SHA | High | Supply-chain attack protection |
| SBOM generation per release | Medium | `cyclonedx-py` |
| Sigstore/cosign signing | Medium | Keyless via OIDC |
| Hash-pinned lockfile | Medium | `pip-compile --generate-hashes` |
| OpenSSF Scorecard | Medium | Public trust badge |
| 2FA for PyPI + GitHub org | Low | Manual setup required |

## Phase 6 — Governance (planned)

| Feature | Priority | Notes |
|---------|----------|-------|
| `GOVERNANCE.md` | High | Maintainer roles, decision process, bus factor |
| `CODEOWNERS` | High | Mandatory review for wallet/security/agent paths |
| DCO (Signed-off-by) check | Medium | Lighter than CLA |
| `SECURITY.md` upgrade | Medium | GHSA workflow, safe-harbor statement |
| `RISKS.md` | Medium | Specific disclaimer for fund-loss risk |
| `versioning-policy.md` | Medium | SemVer commitment, deprecation process |
| Fuzz testing (`hypothesis`) | Low | Slippage, gas, approval edge cases |
| External security audit | Low | Post-2.0, fundable via ecosystem grants |

## Beyond

| Idea | Status |
|------|--------|
| Hardware wallet support | Exploring |
| Transaction simulation in Agent | Exploring |
| Webhook notifications | Exploring |
| Zeroisation of private keys | Researching |
| On-chain incident monitoring | Researching |

---

*This roadmap is a living document. Priority may shift based on user feedback and ecosystem changes.*