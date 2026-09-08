# Safety and Transaction Pipeline

The project has safety primitives, but the long-term goal is one consistent write path for every module that can move funds or change on-chain state.

## Target pipeline

1. **Validate input** — addresses, chain, token, amount, slippage, deadline, and destination.
2. **Apply capability and allowlist policy** — reject unsupported chains, contracts, tokens, and actions.
3. **Run risk checks** — approval exposure, token security signals, liquidity, oracle freshness, and MEV exposure where relevant.
4. **Simulate** — use `eth_call`, Tenderly, or a local fork before signing.
5. **Apply spend policy** — per-transaction, daily, session, and strategy limits.
6. **Request explicit confirmation** — unless an application-specific policy explicitly permits unattended execution.
7. **Sign locally** — keep private key material inside the caller's signer boundary.
8. **Broadcast and track** — persist transaction state, receipt, revert reason, and provider response.
9. **Verify outcome** — confirm expected balance, event, or position change; mark ambiguous transactions for review.

## Current state

The repository already contains spend-governor, approval-analysis, simulation, security-analysis, and transaction-intent primitives. They are not yet enforced through one shared pipeline across every write-capable module. This is a Phase 5 stabilization item, not a reason to add more protocol integrations now.

## Implementation order

- Add a shared `PreflightContext` and result type without changing existing public APIs.
- Integrate it first with swaps, bridges, Aave operations, DCA execution, and sniper buys.
- Add deterministic local-fork fixtures for success, revert, slippage, stale quote, and allowance cases.
- Add transaction lifecycle persistence and idempotency before enabling unattended schedules.
- Expose structured audit events without logging private keys, seed phrases, or API secrets.

## Definition of done

A write-capable feature is ready for Beta only when it has input validation, policy enforcement, simulation or an explicit documented exception, deterministic failure-path tests, receipt verification, and a runbook for pause/retry/recovery.
