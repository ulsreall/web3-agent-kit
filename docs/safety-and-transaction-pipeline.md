# Safety and Transaction Pipeline

The repository contains transaction-safety primitives, including a fail-closed wallet pre-sign gate. They are not yet enforced through one configured write path across every module; the built-in REST API's write routes currently construct unbound wallets and therefore fail closed at signing.

## Intended write lifecycle

Where a module and application have the required controls configured, a write should follow this lifecycle. Coverage is not uniform across all write-capable modules.

1. **Validate input** — addresses, chain, token, amount, slippage, deadline, and destination.
2. **Apply capability and allowlist policy** — reject unsupported chains, contracts, tokens, and actions.
3. **Run risk checks** — approval exposure, token security signals, liquidity, oracle freshness, and MEV exposure where relevant.
4. **Simulate** — use `eth_call`, Tenderly, or a local fork before signing.
5. **Apply spend policy and authorization** — enforce transaction limits, then verify the application's fresh, single-use authorization through the configured pre-sign gate. The current authorization fingerprint omits gas-limit and fee fields.
6. **Request explicit confirmation** — where required by the application's policy; confirmation is not a substitute for authorization.
7. **Sign locally** — only through a bound pre-sign gate; keep private key material inside the caller's signer boundary.
8. **Broadcast and track** — persist transaction state, receipt, revert reason, and provider response.
9. **Verify outcome** — confirm expected balance, event, or position change; mark ambiguous transactions for review.

## Current state

`SpendGovernor`, approval analysis, simulation, security analysis, and transaction-intent primitives exist. `Wallet.sign_transaction()` requires a bound pre-sign gate; that gate requires both policy and an application-supplied authorization provider. The gate's call fingerprint currently omits gas-limit and fee fields, so authorization does not commit to maximum execution cost. Some write-capable integrations and built-in API routes have not been wired to a configured shared gate; the API's unbound wallet paths therefore fail closed instead of executing writes.

## Implementation order

- Add a shared `PreflightContext` and result type without changing existing public APIs.
- Integrate it first with swaps, bridges, Aave operations, DCA execution, and sniper buys.
- Add deterministic local-fork fixtures for success, revert, slippage, stale quote, and allowance cases.
- Add transaction lifecycle persistence and idempotency before enabling unattended schedules.
- Expose structured audit events without logging private keys, seed phrases, or API secrets.

## Definition of done

A write-capable feature is ready for Beta only when it has input validation, policy enforcement, simulation or an explicit documented exception, deterministic failure-path tests, receipt verification, and a runbook for pause/retry/recovery.
