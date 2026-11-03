"""Approval manager API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


def _approval_manager(chain_name: str):
    from ...chains.chain import Chain, ChainManager
    from ...wallet.approval import ApprovalManager
    from ...wallet.wallet import Wallet

    chain = Chain(chain_name)
    chain_manager = ChainManager([chain])
    wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
    return ApprovalManager(wallet, chain_manager), chain


@router.get("/scan")
async def scan_approvals(chain: str = "ethereum"):
    """Scan all token approvals for an address."""
    try:
        manager, chain_enum = _approval_manager(chain)
        approvals = manager.scan(chain_enum)
        return {"approvals": approvals, "total": len(approvals)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/risk")
async def get_risk_report(chain: str = "ethereum"):
    """Get risk report for all approvals."""
    try:
        manager, chain_enum = _approval_manager(chain)
        manager.scan(chain_enum)
        summary = manager.get_summary()
        risky = manager.get_risky()
        unlimited = manager.get_unlimited()
        return {
            "summary": summary,
            "risky_approvals": risky,
            "unlimited_approvals": unlimited,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/revoke")
async def revoke_approval(
    chain: str = "ethereum",
    token: str = "",
    spender: str = "",
):
    """Revoke a token approval."""
    try:
        manager, chain_enum = _approval_manager(chain)
        result = manager.revoke(token, spender, chain_enum)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/revoke-all-unlimited")
async def revoke_all_unlimited(chain: str = "ethereum"):
    """Revoke all unlimited approvals."""
    try:
        manager, chain_enum = _approval_manager(chain)
        manager.scan(chain_enum)
        result = manager.revoke_all_unlimited(chain_enum)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/known-protocols")
async def list_known_protocols():
    """List known protocol addresses for risk assessment."""
    from ...wallet.approval import KNOWN_SPENDERS

    try:
        return {"protocols": KNOWN_SPENDERS}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
