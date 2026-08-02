"""Bridge API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/quote")
async def get_bridge_quote(
    from_chain: str = "ethereum",
    to_chain: str = "arbitrum",
    token: str = "USDC",
    amount: str = "100",
):
    """Get bridge quote with estimated fees and time."""
    from ...bridge.bridge import BridgeAgent

    try:
        agent = BridgeAgent(from_chain)
        routes = agent.get_routes(to_chain, token, amount)
        return routes
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/execute")
async def execute_bridge(
    from_chain: str = "ethereum",
    to_chain: str = "arbitrum",
    token: str = "USDC",
    amount: str = "100",
):
    """Execute a cross-chain bridge."""
    from ...bridge.bridge import BridgeAgent
    from ...wallet.wallet import Wallet

    try:
        wallet = Wallet.from_env(from_chain)
        agent = BridgeAgent(from_chain)
        result = agent.transfer(wallet, to_chain, token, amount)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/chains")
async def list_chains():
    """List supported chains for bridging."""
    from ...bridge.bridge import LIFI_CHAIN_IDS, SOCKET_CHAIN_IDS

    try:
        return {
            "lifi_chains": list(LIFI_CHAIN_IDS.keys()),
            "socket_chains": list(SOCKET_CHAIN_IDS.keys()),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
