"""
REST API for Web3 Agent Kit.

Provides HTTP endpoints for all framework modules:
- Wallet management
- Token swaps (Uniswap V2)
- Portfolio dashboard
- Gas optimizer
- Wallet watcher
- Approval manager
- DCA bot
- Yield optimizer
- Bridge
- Token sniper

SECURITY:
    This API can sign and broadcast real on-chain transactions. It requires
    the WEB3_API_KEY environment variable to be set before it will start —
    the server refuses to boot without it (fail-closed by design). Every
    endpoint except /health requires the `X-API-Key` header to match
    WEB3_API_KEY.

    Generate a strong key, e.g.:
        python -c "import secrets; print(secrets.token_hex(32))"

Usage:
    export WEB3_API_KEY="<your-generated-key>"
    uvicorn web3_agent_kit.api:app --host 127.0.0.1 --port 8000
    python -m web3_agent_kit.api

    By default the server binds to 127.0.0.1 (localhost only). Only set
    API_HOST=0.0.0.0 if you understand the risk of exposing wallet-signing
    endpoints to your network — the server will log a warning if you do.
"""

from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from .routes import (
    approval,
    bridge,
    dca,
    gas,
    portfolio,
    swap,
    wallet,
    watcher,
    yield_opt,
)

logger = logging.getLogger(__name__)

# API key auth
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
    """Validate the X-API-Key header against the WEB3_API_KEY env var.

    Fails closed: if WEB3_API_KEY is not configured, access is always
    denied (401) — "no key configured" must never mean "open access".
    In normal operation this branch should be unreachable because
    `lifespan()` refuses to start the server at all when WEB3_API_KEY is
    unset; this check is defense-in-depth for callers that construct/use
    the `app` object without going through the normal startup path.
    """
    expected = os.environ.get("WEB3_API_KEY", "")
    if not expected:
        raise HTTPException(
            status_code=401,
            detail="Server has no WEB3_API_KEY configured; access denied.",
        )
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key


def _build_cors_config() -> tuple[list[str], bool]:
    """Build CORS origin allowlist from env, validating for unsafe combos.

    CORS_ALLOWED_ORIGINS is a comma-separated list of trusted origins.
    Defaults to an empty list (no cross-origin access) if unset. Credentials
    are allowed, but allow_origins may never be "*" while allow_credentials
    is True — that combination is invalid/unsafe for a wallet-handling API
    and is rejected at startup.
    """
    origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    allow_origins = [o.strip() for o in origins_env.split(",") if o.strip()]
    allow_credentials = True

    if allow_credentials and "*" in allow_origins:
        raise RuntimeError(
            "Invalid CORS configuration: CORS_ALLOWED_ORIGINS cannot contain "
            "'*' while credentials are allowed. Set CORS_ALLOWED_ORIGINS to "
            "an explicit comma-separated list of trusted origins instead."
        )

    return allow_origins, allow_credentials


# Lifespan for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle.

    Fail-closed startup guard: refuses to start the API server at all if
    WEB3_API_KEY is not set, since every wallet-signing endpoint depends on
    it for authentication. "No key configured" must never silently mean
    "open access".
    """
    if not os.environ.get("WEB3_API_KEY"):
        raise RuntimeError(
            "WEB3_API_KEY must be set before starting the API server. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\" "
            "and export it as WEB3_API_KEY before launching the server."
        )
    yield


# Create app
app = FastAPI(
    title="Web3 Agent Kit API",
    description="REST API for autonomous Web3 AI agents. "
    "Manage wallets, swap tokens, monitor portfolios, "
    "optimize gas, track approvals, and more. "
    "Requires the X-API-Key header (see WEB3_API_KEY) on all endpoints except /health.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — env-driven allowlist, validated against the allow_origins="*" +
# allow_credentials=True anti-pattern.
_cors_allow_origins, _cors_allow_credentials = _build_cors_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/health", tags=["system"])
async def health():
    """Health check endpoint. Intentionally unauthenticated for infra checks."""
    return {"status": "ok", "version": "1.0.0"}


@app.get("/", tags=["system"])
async def root():
    """API root with available endpoints."""
    return {
        "name": "Web3 Agent Kit API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "wallet": "/wallet",
            "swap": "/swap",
            "portfolio": "/portfolio",
            "gas": "/gas",
            "watcher": "/watcher",
            "approval": "/approval",
            "dca": "/dca",
            "yield": "/yield",
            "bridge": "/bridge",
        },
    }


# Include routers — every one requires a valid X-API-Key (see get_api_key).
app.include_router(
    wallet.router, prefix="/wallet", tags=["wallet"], dependencies=[Depends(get_api_key)]
)
app.include_router(
    swap.router, prefix="/swap", tags=["swap"], dependencies=[Depends(get_api_key)]
)
app.include_router(
    portfolio.router,
    prefix="/portfolio",
    tags=["portfolio"],
    dependencies=[Depends(get_api_key)],
)
app.include_router(
    gas.router, prefix="/gas", tags=["gas"], dependencies=[Depends(get_api_key)]
)
app.include_router(
    watcher.router, prefix="/watcher", tags=["watcher"], dependencies=[Depends(get_api_key)]
)
app.include_router(
    approval.router,
    prefix="/approval",
    tags=["approval"],
    dependencies=[Depends(get_api_key)],
)
app.include_router(
    dca.router, prefix="/dca", tags=["dca"], dependencies=[Depends(get_api_key)]
)
app.include_router(
    yield_opt.router, prefix="/yield", tags=["yield"], dependencies=[Depends(get_api_key)]
)
app.include_router(
    bridge.router, prefix="/bridge", tags=["bridge"], dependencies=[Depends(get_api_key)]
)


def main():
    """Run the API server.

    Binds to 127.0.0.1 by default. Set API_HOST=0.0.0.0 to expose the
    server to the network — this is logged as a warning since it exposes
    wallet-signing endpoints beyond localhost.
    """
    import uvicorn

    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", "8000"))

    if host == "0.0.0.0":
        logger.warning(
            "⚠️ API server is binding to 0.0.0.0 — this exposes wallet-signing "
            "endpoints to your network. Make sure WEB3_API_KEY is set and you "
            "understand the risk."
        )

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

__all__ = [
    "app",
    "main",
    "get_api_key",
    "lifespan",
]
