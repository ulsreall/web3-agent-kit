"""Approval manager API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/scan")
async def scan_approvals(chain: str = "ethereum"):
    """Scan all token approvals for an address."""
    from ...approval_manager import ApprovalManager

    try:
        manager = ApprovalManager(chain)
        approvals = manager.scan()
        return {"approvals": approvals, "total": len(approvals)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/risk")
async def get_risk_report(chain: str = "ethereum"):
    """Get risk report for all approvals."""
    from ...approval_manager import ApprovalManager

    try:
        manager = ApprovalManager(chain)
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
    from ...approval_manager import ApprovalManager

    try:
        manager = ApprovalManager(chain)
        result = manager.revoke(token, spender)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/revoke-all-unlimited")
async def revoke_all_unlimited(chain: str = "ethereum"):
    """Revoke all unlimited approvals."""
    from ...approval_manager import ApprovalManager

    try:
        manager = ApprovalManager(chain)
        result = manager.revoke_all_unlimited()
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/known-protocols")
async def list_known_protocols():
    """List known protocol addresses for risk assessment."""
    from ...approval_manager import KNOWN_SPENDERS

    try:
        return {"protocols": KNOWN_SPENDERS}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
