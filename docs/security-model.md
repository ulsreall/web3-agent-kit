# Security Model

> **Last updated:** v1.15.0 (2026-07-23)
> **Scope:** Wallet safety, transaction governance, API security, and known limitations.

---

## Overview

Web3 Agent Kit executes real financial transactions on behalf of its users. This document explains the security architecture — what is protected, how, and what **is not yet** fully secure.

**Core principle:** Fail closed, not open. When in doubt (API down, unknown value, unverified state), block the action and require explicit operator approval.

---

## 1. SpendGovernor — Transaction Caps & Confirmation Gate

The `SpendGovernor` (in `web3_agent_kit/utils/__init__.py`) enforces spending limits on every agent action that touches funds.

### Limits enforced

| Limit | Default | Configurable |
|-------|---------|-------------|
| Per-transaction max | 0.05 ETH-equivalent | `SpendLimits(max_per_tx=...)` |
| Daily spend cap | 0.5 ETH-equivalent | `SpendLimits(daily_limit=...)` |
| Session spend cap | 1.0 ETH-equivalent | `SpendLimits(session_limit=...)` |
| Kill switch | Off by default | `governor.kill()` / `governor.unkill()` |

### Confirmation gate

When `require_confirm=True` (off by default for the default governor), the operator must provide a `confirm_fn` callable:

```python
def my_confirm(payload: dict) -> bool:
    print(f"Approve {payload['action']} for {payload['value']} ETH?")
    return input("y/n: ").lower() == "y"

governor = SpendGovernor(
    SpendLimits(max_per_tx=0.1),
    require_confirm=True,
    confirm_fn=my_confirm,
)
```

**Important:** If `require_confirm=True` is set without a `confirm_fn`, `SpendGovernor` raises a `ValueError` at construction time. Silent pass was removed in v1.15.0.

**Default behaviour:** The built-in `_default_governor()` uses `require_confirm=False` (caps-only protection) to avoid requiring a `confirm_fn` out of the box. For production deployments handling significant value, explicitly configure `require_confirm=True` with a proper `confirm_fn`.

### Wiring from AgentConfig

`AgentConfig.confirm_fn` is automatically wired to `SpendGovernor.confirm_fn` in `Agent.__init__`:

```python
config = AgentConfig(
    wallet=wallet,
    confirm_fn=my_confirm,  # This is now piped to the governor
)
```

### Kill switch

Emergency stop that blocks all transactions regardless of limits:

```python
agent.config.governor.kill()    # Stop all transactions
agent.config.governor.unkill()  # Re-enable
```

---

## 2. Transaction Value Estimation

`Agent._estimate_tx_value()` extracts the native-token value from tool arguments before sending them to the governor.

### Known argument keys

Recognised keys: `value`, `amount`, `amount_in`, `eth_amount`, `tx_value`.

### Unknown keys

If none of the recognised keys are found in the arguments, the method returns `None` instead of `0.0`. When `None` is returned, `Agent._act()` **blocks the action** with a message requiring explicit approval or a properly set value (v1.15.0 behaviour).

**Trade-off:** Read-only actions (e.g., `get_balance`) that don't move funds must include one of the recognised keys to pass through. If your tool doesn't have a value field, use `amount: 0` explicitly. Otherwise the governor will block it.

---

## 3. Token Security (Honeypot & Tax Checks)

The `TokenAnalyzer` (in `web3_agent_kit/security/__init__.py`) queries third-party APIs to detect honeypot tokens and excessive fees.

### How it works

1. Calls GoPlus Labs API (`api.gopluslabs.io`) for token security data
2. Falls back to DexScreener for liquidity information
3. Computes a safety score (0-100) and risk level

### 3-state honeypot detection (v1.15.0+)

`TaxInfo.is_honeypot` uses `Optional[bool]` with three states:

| Value | Meaning |
|-------|---------|
| `True` | Confirmed honeypot (API returned `is_honeypot: "1"`) |
| `False` | Confirmed safe (API returned `is_honeypot: "0"`) |
| `None` | **Unknown** — API call failed, timed out, or returned no data |

**Behaviour when unknown:** `SecurityReport.is_safe` returns `False` when `is_honeypot` is `None`. Unknown is treated as unsafe.

### Known limitations

- **Third-party dependency:** All token security data comes from GoPlus Labs and DexScreener. If these APIs are down, rate-limited, or return stale data, the analysis is degraded.
- **Not a replacement for manual audit:** Automated checks can miss sophisticated honeypots, tax evasion mechanisms, or newly deployed scam patterns.
- **ERC-20 focused:** Token analysis is optimised for standard ERC-20 tokens on EVM chains. SPL tokens on Solana have partial coverage.
- **No simulation:** The kit does not execute a real buy/sell transaction to verify honeypot status — it relies entirely on API data.

---

## 4. API Server Security

The REST API (in `web3_agent_kit/api/`) follows a fail-closed model.

### Authentication

- All sensitive endpoints require `X-API-Key` header matching the `WEB3_API_KEY` environment variable.
- The server **refuses to start** if `WEB3_API_KEY` is not set.
- `GET /wallet/create` is disabled by default (`ENABLE_WALLET_CREATE_ENDPOINT=false`).

### Network binding

- Default bind address: `127.0.0.1` (localhost only). Explicitly setting `0.0.0.0` logs a clear network-exposure warning.
- CORS is restricted to origins in `CORS_ALLOWED_ORIGINS` (empty by default).
- The `allow_origins=["*"]` + `allow_credentials=True` combination is **rejected at startup**.

### Rate limiting

- No built-in rate limiting yet. For production deployments, place the API behind a reverse proxy (nginx, Cloudflare) with rate limiting.

---

## 5. Approval & Token Allowance Management

`web3_agent_kit/wallet/approval.py` provides token approval and revocation utilities.

### Current state

- `approve()` with unlimited allowance (`2**256-1`) remains the default for compatibility with major DEXs. Use `revoke_approval()` to clean up after use.
- `revoke_approval()` is supported for ERC-20 tokens on EVM chains.
- `approve_exact(amount)` is available for use cases that prefer finite allowances.

### Recommendation

For production use, prefer `approve_exact()` over unlimited approval, and call `revoke_approval()` after operations complete.

---

## 6. Private Key Storage

### In-memory

- Private keys are stored as **plaintext in memory** (not encrypted, not persisted to disk by default) when loaded via `Wallet.from_key()` or `MultiWalletManager.add_wallet()`.
- The `MultiWalletManager.clear()` method removes all keys from memory.

### Known limitation (v1.15.0)

- Keys are **not** wrapped in a zero-on-destroy container. After `clear()` or object destruction, the memory may persist until the Python runtime reuses it.
- For high-security environments, consider using hardware wallets or external signing services.

---

## 7. What Is NOT Yet Secure

These are acknowledged gaps tracked for future releases:

| Gap | Impact | Planned fix |
|-----|--------|-------------|
| No built-in rate limiting on API | DOS / brute force | Reverse proxy recommendation for now |
| Unlimited approval default | Post-swap cleanup required | `approve_exact()` exists as alternative |
| No transaction simulation before broadcast | User must verify themselves | `Simulator` module exists but not wired to Agent |
| `swap_exact_output()` not production-ready | Potential fund loss from slippage | Marked with warning docstring |
| No hardware wallet support | Keys in memory | Post-2.0 feature |
| No webhook notifications for governor blocks | User may miss blocked tx | Post-2.0 feature |

---

## 8. Reporting Vulnerabilities

See `SECURITY.md` for the full disclosure process.

**Key contact:** khasbimln@gmail.com (PGP on request)
**Response target:** Acknowledgment within 48 hours, assessment within 1 week.

---

## Appendices

### A. Future security roadmap

- [ ] Hardware wallet / Ledger support
- [ ] Transaction simulation integration with Agent
- [ ] Built-in rate limiting
- [ ] Webhook notifications for governor blocks
- [ ] Zeroisation of private keys in memory
- [ ] On-chain incident monitoring
- [ ] External security audit by a third-party firm

### B. Dependency security

- Dependencies are automatically updated via Dependabot (weekly, pip + GitHub Actions)
- `pip-audit` runs in CI as a non-blocking check
- See `.github/dependabot.yml` and `.github/workflows/ci.yml` for details