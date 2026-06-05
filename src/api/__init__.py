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

Usage:
    uvicorn src.api:app --host 0.0.0.0 --port 8000
    python -m src.api
"""

from __future__ import annotations

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


# API key auth
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
    """Validate API key from header."""
    expected = os.environ.get("WEB3_API_KEY", "")
    if not expected:
        return "open"  # No key configured = open access
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key


# Lifespan for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    yield


# Create app
app = FastAPI(
    title="Web3 Agent Kit API",
    description="REST API for autonomous Web3 AI agents. "
    "Manage wallets, swap tokens, monitor portfolios, "
    "optimize gas, track approvals, and more.",
    version="0.9.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/health", tags=["system"])
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.9.0"}


@app.get("/", tags=["system"])
async def root():
    """API root with available endpoints."""
    return {
        "name": "Web3 Agent Kit API",
        "version": "0.9.0",
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


# Include routers
app.include_router(wallet.router, prefix="/wallet", tags=["wallet"])
app.include_router(swap.router, prefix="/swap", tags=["swap"])
app.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
app.include_router(gas.router, prefix="/gas", tags=["gas"])
app.include_router(watcher.router, prefix="/watcher", tags=["watcher"])
app.include_router(approval.router, prefix="/approval", tags=["approval"])
app.include_router(dca.router, prefix="/dca", tags=["dca"])
app.include_router(yield_opt.router, prefix="/yield", tags=["yield"])
app.include_router(bridge.router, prefix="/bridge", tags=["bridge"])


def main():
    """Run the API server."""
    import uvicorn

    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
