"""Wallet API routes."""

from __future__ import annotations

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
    """Create a new wallet."""
    from eth_account import Account

    try:
        account = Account.create()
        return {
            "address": account.address,
            "private_key": account._key.hex(),
            "chain": chain,
            "warning": "Save the private key securely. It won't be shown again.",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/balance/{address}")
async def get_balance(address: str, chain: str = "ethereum"):
    """Get ETH/native balance for an address."""
    from ...wallet.wallet import Wallet

    try:
        wallet = Wallet.from_env(chain)
        balance = wallet.get_balance()
        return {"address": address, "balance": str(balance), "chain": chain}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
