"""Wallet API routes."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/info")
async def get_wallet_info(chain: str = "ethereum"):
    """Get current wallet info and balance."""
    from ...wallet.wallet import Wallet

    try:
        wallet = Wallet.from_env(chain)
        balance = wallet.get_balance()
        return {
            "address": wallet.address,
            "chain": chain,
            "balance": str(balance),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/create")
async def create_wallet(chain: str = "ethereum"):
    """Create a new wallet.

    SECURITY NOTE:
        This endpoint generates a brand new private key server-side and
        returns it once, in the response body. It requires a valid
        X-API-Key (see api/__init__.py router wiring). The key is never
        stored server-side or logged.

        Because returning a raw private key over HTTP is inherently
        risky, this endpoint should ideally be disabled entirely in
        production deployments. It can be toggled via the
        ENABLE_WALLET_CREATE_ENDPOINT env flag, which defaults to "false".
        To enable it explicitly:

            export ENABLE_WALLET_CREATE_ENDPOINT=true

        Even when enabled, only call this over HTTPS and never log the
        response.
    """
    if os.environ.get("ENABLE_WALLET_CREATE_ENDPOINT", "false").lower() not in (
        "1",
        "true",
        "yes",
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "The /wallet/create endpoint is disabled by default. "
                "Set ENABLE_WALLET_CREATE_ENDPOINT=true to enable it "
                "(not recommended in production)."
            ),
        )

    from eth_account import Account

    try:
        account = Account.create()
        # eth_account's LocalAccount exposes the raw key as `.key` in
        # modern versions; older versions used the private `._key`
        # attribute. Support both to avoid depending on library internals.
        raw_key = getattr(account, "key", None)
        if raw_key is None:
            raw_key = account._key
        private_key_hex = raw_key.hex() if not isinstance(raw_key, str) else raw_key
        if not private_key_hex.startswith("0x"):
            private_key_hex = "0x" + private_key_hex
        return {
            "address": account.address,
            "private_key": private_key_hex,
            "chain": chain,
            "warning": (
                "This private key is shown ONLY ONCE and is never stored "
                "or logged server-side. Save it securely immediately. "
                "Transmit this response over HTTPS only, and never log it "
                "(including in proxies, load balancers, or client apps)."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/balance/{address}")
async def get_balance(address: str, chain: str = "ethereum"):
    """Get ETH/native balance for the given on-chain address (read-only)."""
    from ...chains.chain import Chain, ChainManager

    try:
        chain_enum = Chain(chain)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")

    try:
        manager = ChainManager([chain_enum])

        if chain_enum == Chain.SOLANA:
            sol = manager.get_solana()
            resp = sol.get_balance(address)
            balance = resp.value / 1e9
        else:
            w3 = manager.get_web3(chain_enum)
            balance_wei = w3.eth.get_balance(w3.to_checksum_address(address))
            balance = w3.from_wei(balance_wei, "ether")

        return {"address": address, "balance": str(balance), "chain": chain}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
