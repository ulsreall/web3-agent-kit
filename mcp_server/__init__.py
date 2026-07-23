"""MCP Server — Web3 Agent Kit Tools for AI Agents.

Exposes Web3 Agent Kit functionality via the Model Context Protocol (MCP).
Read-only tools are auto-approved; state-changing tools default to dry-run.

Usage:
    python -m mcp_server                # Start MCP server
    python -m mcp_server --list         # List available tools
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

AUDIT_LOG: list[dict] = []


def _log(tool: str, args: dict, result: str, status: str = "ok") -> None:
    entry = {
        "timestamp": time.time(),
        "tool": tool,
        "args": args,
        "result": result,
        "status": status,
    }
    AUDIT_LOG.append(entry)
    logger.info("AUDIT: %s", json.dumps(entry))


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


@dataclass
class ToolSpec:
    """MCP tool specification."""

    name: str
    description: str
    input_schema: dict
    read_only: bool = True


TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="get_balance",
        description="Get native balance for a wallet address on a chain.",
        input_schema={
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Wallet address"},
                "chain": {"type": "string", "description": "Chain name (e.g. ethereum, base, solana)", "default": "ethereum"},
            },
            "required": ["address"],
        },
        read_only=True,
    ),
    ToolSpec(
        name="check_honeypot",
        description="Check if a token contract address is a honeypot.",
        input_schema={
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Token contract address"},
                "chain": {"type": "string", "description": "Chain name", "default": "ethereum"},
            },
            "required": ["address"],
        },
        read_only=True,
    ),
    ToolSpec(
        name="get_portfolio",
        description="Get portfolio overview for a wallet across supported chains.",
        input_schema={
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Wallet address"},
                "chains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Chains to query (default: all supported)",
                },
            },
            "required": ["address"],
        },
        read_only=True,
    ),
    ToolSpec(
        name="swap",
        description="Execute a token swap. Returns a preview by default; pass confirm=true to execute.",
        input_schema={
            "type": "object",
            "properties": {
                "token_in": {"type": "string", "description": "Input token symbol or address"},
                "token_out": {"type": "string", "description": "Output token symbol or address"},
                "amount": {"type": "number", "description": "Amount to swap"},
                "chain": {"type": "string", "description": "Chain name", "default": "ethereum"},
                "confirm": {"type": "boolean", "description": "Set to true to actually execute", "default": False},
            },
            "required": ["token_in", "token_out", "amount"],
        },
        read_only=False,
    ),
    ToolSpec(
        name="revoke_approval",
        description="Revoke a token approval. Returns a preview by default; pass confirm=true to execute.",
        input_schema={
            "type": "object",
            "properties": {
                "token_address": {"type": "string", "description": "Token contract address"},
                "spender_address": {"type": "string", "description": "Spender address to revoke"},
                "chain": {"type": "string", "description": "Chain name", "default": "ethereum"},
                "confirm": {"type": "boolean", "description": "Set to true to actually execute", "default": False},
            },
            "required": ["token_address", "spender_address"],
        },
        read_only=False,
    ),
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _get_wallet_from_env() -> Any | None:
    """Try to create a Wallet from environment config."""
    key = os.environ.get("WALLET_PRIVATE_KEY")
    if key:
        try:
            from web3_agent_kit.wallet.wallet import Wallet
            return Wallet.from_key(key)
        except Exception as e:
            logger.warning("Failed to create wallet from env: %s", e)
    return None


def _get_token_analyzer():
    """Create a TokenAnalyzer instance."""
    from web3_agent_kit.security import SecurityConfig, TokenAnalyzer
    config = SecurityConfig(chain=os.environ.get("MCP_CHAIN", "ethereum"))
    return TokenAnalyzer(config)


def handle_get_balance(args: dict) -> dict:
    """Get native balance."""
    wallet = _get_wallet_from_env()
    if wallet:
        from web3_agent_kit.chains.chain import Chain
        chain_name = args.get("chain", "ethereum").upper()
        try:
            chain = Chain[chain_name]
            balance = wallet.get_balance(chain)
            return {"address": args["address"], "chain": chain_name.lower(), "balance": balance}
        except Exception as e:
            return {"error": str(e), "address": args["address"]}
    return {"address": args["address"], "note": "Configure WALLET_PRIVATE_KEY for real balance checks"}


def handle_check_honeypot(args: dict) -> dict:
    """Check honeypot status."""
    analyzer = _get_token_analyzer()
    result = analyzer.quick_check(args["address"])
    return {
        "address": args["address"],
        "is_honeypot": result["is_honeypot"],
        "buy_tax": result["buy_tax"],
        "sell_tax": result["sell_tax"],
        "risk_level": result["risk_level"],
        "error": result.get("error"),
    }


def handle_get_portfolio(args: dict) -> dict:
    """Get portfolio overview."""
    wallet = _get_wallet_from_env()
    if wallet:
        from web3_agent_kit.chains.chain import Chain
        requested = args.get("chains", ["ethereum", "base"])
        portfolio = {}
        for c_name in requested:
            try:
                chain = Chain[c_name.upper()]
                balance = wallet.get_balance(chain)
                portfolio[c_name] = {"balance": balance}
            except Exception as e:
                portfolio[c_name] = {"error": str(e)}
        return {"address": args["address"], "portfolio": portfolio, "num_chains": len(portfolio)}
    return {"address": args["address"], "note": "Configure WALLET_PRIVATE_KEY for real portfolio data"}


def handle_swap(args: dict) -> dict:
    """Execute or preview a token swap."""
    confirm = args.pop("confirm", False)
    _log("swap", args, "preview" if not confirm else "executed")

    if not confirm:
        return {
            "preview": True,
            "message": f"Preview: Swap {args['amount']} {args['token_in']} → {args['token_out']} on {args.get('chain', 'ethereum')}",
            "token_in": args["token_in"],
            "token_out": args["token_out"],
            "amount": args["amount"],
            "chain": args.get("chain", "ethereum"),
            "note": "Pass confirm=true to execute this swap",
        }

    # Actual execution
    wallet = _get_wallet_from_env()
    if not wallet:
        return {"error": "WALLET_PRIVATE_KEY not configured", "preview": False}

    try:
        from web3_agent_kit.chains.chain import Chain
        from web3_agent_kit.defi import UniswapV3
        from web3_agent_kit import ChainManager

        chain_name = args.get("chain", "ethereum").upper()
        chain = Chain[chain_name]
        cm = ChainManager(chain)
        dex = UniswapV3(chain_manager=cm)

        result = dex.swap(
            wallet=wallet,
            token_in=args["token_in"],
            token_out=args["token_out"],
            amount=args["amount"],
        )
        return {"status": "executed", "result": str(result)}
    except Exception as e:
        return {"error": str(e), "preview": False}


def handle_revoke_approval(args: dict) -> dict:
    """Revoke a token approval."""
    confirm = args.pop("confirm", False)
    _log("revoke_approval", args, "preview" if not confirm else "executed")

    if not confirm:
        return {
            "preview": True,
            "message": f"Preview: Revoke approval for {args['token_address']} spender {args['spender_address']}",
            "token_address": args["token_address"],
            "spender_address": args["spender_address"],
            "chain": args.get("chain", "ethereum"),
            "note": "Pass confirm=true to execute",
        }

    wallet = _get_wallet_from_env()
    if not wallet:
        return {"error": "WALLET_PRIVATE_KEY not configured"}

    try:
        from web3_agent_kit.wallet.approval import revoke_approval
        tx_hash = revoke_approval(
            wallet=wallet,
            token_address=args["token_address"],
            spender_address=args["spender_address"],
        )
        return {"status": "executed", "tx_hash": tx_hash}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Handler dispatch
# ---------------------------------------------------------------------------

HANDLERS = {
    "get_balance": handle_get_balance,
    "check_honeypot": handle_check_honeypot,
    "get_portfolio": handle_get_portfolio,
    "swap": handle_swap,
    "revoke_approval": handle_revoke_approval,
}


def list_tools() -> list[dict]:
    """Return tool list in MCP format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.input_schema,
            "readOnly": t.read_only,
        }
        for t in TOOLS
    ]


def handle_request(request: dict) -> dict:
    """Handle a single MCP tool call request."""
    tool_name = request.get("tool", "")
    args = request.get("args", {})

    if tool_name not in HANDLERS:
        return {"error": f"Unknown tool: {tool_name}. Available: {list(HANDLERS.keys())}"}

    try:
        result = HANDLERS[tool_name](args)
        _log(tool_name, args, "success")
        return {"success": True, "result": result}
    except Exception as e:
        _log(tool_name, args, str(e), status="error")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# MCP server entry point
# ---------------------------------------------------------------------------


def main():
    """Entry point for MCP server.

    Supports:
        --list          List available tools as JSON
        <tool> --args   Call a specific tool
        (no args)       Start MCP STDIO server
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if "--list" in sys.argv:
        print(json.dumps(list_tools(), indent=2))
        return

    if len(sys.argv) >= 2 and sys.argv[1] in HANDLERS:
        tool_name = sys.argv[1]
        args = {}
        if "--args" in sys.argv:
            idx = sys.argv.index("--args")
            if idx + 1 < len(sys.argv):
                args = json.loads(sys.argv[idx + 1])
        result = handle_request({"tool": tool_name, "args": args})
        print(json.dumps(result, indent=2))
        return

    # STDIO MCP mode — read JSON requests line by line
    import select

    logger.info("MCP Server ready — waiting for requests on stdin")
    while True:
        if select.select([sys.stdin], [], [], 0.5)[0]:
            line = sys.stdin.readline()
            if not line:
                break
            request = json.loads(line.strip())
            response = handle_request(request)
            print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()