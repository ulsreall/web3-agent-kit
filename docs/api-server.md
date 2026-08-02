# REST API Server

Web3 Agent Kit ships an optional REST API (FastAPI) that exposes wallet,
swap, portfolio, gas, watcher, approval, DCA, yield, and bridge tools over
HTTP — useful for driving the toolkit from a dashboard, bot, or any
non-Python client.

!!! danger "This API can sign and broadcast real on-chain transactions"
    Treat `WEB3_API_KEY` like a wallet-level secret. Anyone holding a valid
    key can execute swaps, bridges, DCA orders, and approval revocations
    against the configured wallet.

## Quick Start

```bash
# 1. Generate a strong API key
python -c "import secrets; print(secrets.token_hex(32))"

# 2. Export it — the server refuses to start without this
export WEB3_API_KEY="<your-generated-key>"

# 3. Run the server (binds to 127.0.0.1:8000 by default)
python -m web3_agent_kit.api
# or
uvicorn web3_agent_kit.api:app --host 127.0.0.1 --port 8000
```

Interactive docs are available once it's running: `http://127.0.0.1:8000/docs`
(Swagger UI) and `/redoc`.

## Authentication

Every endpoint **except `/health`** requires an `X-API-Key` header that
matches `WEB3_API_KEY`:

```bash
curl -H "X-API-Key: $WEB3_API_KEY" http://127.0.0.1:8000/wallet/info
```

Missing or incorrect key → `401 Unauthorized`. Since v1.14.0 the server is
**fail-closed**: if `WEB3_API_KEY` isn't set, the process refuses to start
at all rather than silently running with open access.

## Network Exposure

| Env var | Default | Notes |
|---|---|---|
| `API_HOST` | `127.0.0.1` | Set `0.0.0.0` only if you understand the risk of exposing wallet-signing endpoints to your network — a warning is logged when you do |
| `API_PORT` | `8000` | |
| `CORS_ALLOWED_ORIGINS` | *(empty)* | Comma-separated list of trusted origins for browser clients. `*` is rejected at startup since credentials are always allowed — an explicit allowlist is required for any cross-origin access |

## Endpoints

All routes below require `X-API-Key` unless noted.

### `/wallet`

| Method | Path | Description |
|---|---|---|
| GET | `/wallet/info` | Current wallet address + balance for a chain |
| POST | `/wallet/create` | Generate a new wallet — **disabled by default**, see below |
| GET | `/wallet/balance/{address}` | Read-only balance lookup for any address |

!!! warning "`/wallet/create` is disabled by default"
    This endpoint returns a freshly generated private key **once**, in the
    HTTP response body. It's gated behind `ENABLE_WALLET_CREATE_ENDPOINT`
    (default `false`). Only enable it if you fully understand the risk of
    transmitting a raw private key over HTTP, and always serve it over
    HTTPS:
    ```bash
    export ENABLE_WALLET_CREATE_ENDPOINT=true
    ```

### `/swap`

| Method | Path | Description |
|---|---|---|
| GET | `/swap/quote` | Get a swap quote without executing |
| POST | `/swap/execute` | Execute a token swap |
| GET | `/swap/tokens` | List supported tokens |

### `/portfolio`

| Method | Path | Description |
|---|---|---|
| GET | `/portfolio/` | Full portfolio snapshot |
| GET | `/portfolio/value` | Total portfolio value |

### `/gas`

| Method | Path | Description |
|---|---|---|
| GET | `/gas/estimate` | Estimate gas for a transaction |
| GET | `/gas/recommendation` | Recommended gas price/priority fee |
| GET | `/gas/batch` | Batch gas estimates |

### `/watcher`

| Method | Path | Description |
|---|---|---|
| GET | `/watcher/list` | List watched wallets |
| POST | `/watcher/add` | Add a wallet to watch |
| DELETE | `/watcher/remove` | Remove a watched wallet |
| GET | `/watcher/alerts` | Recent alerts |
| POST | `/watcher/check` | Force a check cycle |
| GET | `/watcher/summary` | Watcher status summary |

### `/approval`

| Method | Path | Description |
|---|---|---|
| GET | `/approval/scan` | Scan token approvals for a wallet |
| GET | `/approval/risk` | Risk-score existing approvals |
| POST | `/approval/revoke` | Revoke a specific approval |
| POST | `/approval/revoke-all-unlimited` | Revoke all unlimited approvals |
| GET | `/approval/known-protocols` | List known protocol addresses |

### `/dca`

| Method | Path | Description |
|---|---|---|
| GET | `/dca/orders` | List DCA orders |
| POST | `/dca/orders` | Create a DCA order |
| GET | `/dca/orders/{order_id}` | Get a specific order |
| DELETE | `/dca/orders/{order_id}` | Cancel an order |
| POST | `/dca/orders/{order_id}/pause` | Pause an order |
| POST | `/dca/orders/{order_id}/resume` | Resume a paused order |
| GET | `/dca/stats` | DCA statistics |

### `/yield`

| Method | Path | Description |
|---|---|---|
| GET | `/yield/opportunities` | List yield opportunities |
| GET | `/yield/best` | Best current opportunity |
| GET | `/yield/compare` | Compare opportunities |
| GET | `/yield/portfolio` | Yield-bearing portfolio positions |
| POST | `/yield/compound` | Trigger compounding |

### `/bridge`

| Method | Path | Description |
|---|---|---|
| GET | `/bridge/quote` | Get a cross-chain bridge quote |
| POST | `/bridge/execute` | Execute a bridge transfer |
| GET | `/bridge/chains` | Supported bridge routes/chains |

### `/health` *(no auth required)*

```bash
curl http://127.0.0.1:8000/health
# {"status": "ok", "version": "1.0.0"}
```

Intentionally unauthenticated so infra/load-balancer health checks work
without a key.

## Version History

Security hardening shipped in **v1.14.0**:

- Authentication (`X-API-Key`/`WEB3_API_KEY`) enforced on every router — previously only defined, never wired in
- Fail-closed startup — server refuses to boot without `WEB3_API_KEY`
- Default bind host changed `0.0.0.0` → `127.0.0.1`
- CORS hardened via `CORS_ALLOWED_ORIGINS`, unsafe `*` + credentials combo rejected at startup
- `/wallet/create` gated behind `ENABLE_WALLET_CREATE_ENDPOINT` (default `false`)
- `/wallet/balance/{address}` fixed to query the requested address instead of the configured env wallet

See the [changelog](changelog.md) for full details.
