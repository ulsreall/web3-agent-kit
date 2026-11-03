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
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)
MCP_PROTOCOL_VERSION = "2024-11-05"

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
                "chain": {
                    "type": "string",
                    "description": "Chain name (e.g. ethereum, base, solana)",
                    "default": "ethereum",
                },
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
                    "description": "Chains to query (default: ethereum and base)",
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
                "confirm": {
                    "type": "boolean",
                    "description": "Set to true to actually execute",
                    "default": False,
                },
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
                "confirm": {
                    "type": "boolean",
                    "description": "Set to true to actually execute",
                    "default": False,
                },
            },
            "required": ["token_address", "spender_address"],
        },
        read_only=False,
    ),
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _get_wallet_from_env(chain_name: str = "ethereum") -> Any | None:
    """Try to create a Wallet from environment config."""
    key = os.environ.get("WALLET_PRIVATE_KEY")
    if not key:
        return None
    from web3_agent_kit.wallet.wallet import Wallet

    _, manager = _chain_and_manager(chain_name)
    return Wallet.from_key(key, chain_manager=manager)


def _get_token_analyzer(chain: str = "ethereum"):
    """Create a TokenAnalyzer instance."""
    from web3_agent_kit.security import SecurityConfig, TokenAnalyzer

    config = SecurityConfig(
        chain=chain,
        etherscan_api_key=os.environ.get("ETHERSCAN_API_KEY", ""),
        goplus_api_key=os.environ.get("GOPLUS_API_KEY", ""),
    )
    return TokenAnalyzer(config)


def _chain_and_manager(chain_name: str):
    """Resolve a supported chain and its configured RPC endpoint."""
    from web3_agent_kit.chains.chain import Chain, ChainManager

    try:
        chain = Chain[chain_name.upper().replace("-", "_")]
    except KeyError as exc:
        raise ValueError(f"Unsupported chain: {chain_name}") from exc
    rpc_url = os.environ.get(f"{chain.name}_RPC_URL") or os.environ.get("RPC_URL")
    if not rpc_url:
        raise ValueError(f"Set {chain.name}_RPC_URL or RPC_URL to query {chain.value}")
    return chain, ChainManager([chain], {chain: rpc_url})


def handle_get_balance(args: dict) -> dict:
    """Get native balance."""
    chain_name = args.get("chain", "ethereum")
    chain, manager = _chain_and_manager(chain_name)
    if chain.value == "solana":
        response = manager.get_solana().get_balance(args["address"])
        balance = response.value / 1e9
    else:
        web3 = manager.get_web3(chain)
        balance = web3.from_wei(web3.eth.get_balance(args["address"]), "ether")
    return {"address": args["address"], "chain": chain.value, "balance": float(balance)}


def handle_check_honeypot(args: dict) -> dict:
    """Check honeypot status."""
    analyzer = _get_token_analyzer(args.get("chain", "ethereum"))
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
    requested = args.get("chains", ["ethereum", "base"])
    portfolio = {}
    for chain_name in requested:
        try:
            chain, manager = _chain_and_manager(chain_name)
            if chain.value == "solana":
                response = manager.get_solana().get_balance(args["address"])
                balance = response.value / 1e9
            else:
                web3 = manager.get_web3(chain)
                balance = web3.from_wei(web3.eth.get_balance(args["address"]), "ether")
            portfolio[chain.value] = {"balance": float(balance)}
        except Exception as exc:
            portfolio[chain_name] = {"error": str(exc)}
    return {"address": args["address"], "portfolio": portfolio, "num_chains": len(portfolio)}


def handle_swap(args: dict) -> dict:
    """Execute or preview a token swap."""
    args = dict(args)
    confirm = args.pop("confirm", False)
    if not confirm:
        _log("swap", args, "preview")
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
    try:
        from web3_agent_kit.chains.chain import Chain
        from web3_agent_kit.defi import UniswapV3

        chain_name = args.get("chain", "ethereum").upper()
        chain = Chain[chain_name.replace("-", "_")]
        wallet = _get_wallet_from_env(chain.value)
        if not wallet:
            return {"error": "WALLET_PRIVATE_KEY not configured", "preview": False}
        if not wallet.is_enforced:
            return {
                "error": (
                    "No pre-sign authorization pipeline is configured; the swap was not submitted"
                ),
                "preview": False,
            }
        dex = UniswapV3(chain_manager=wallet.chain_manager)

        result = dex.swap(
            wallet=wallet,
            token_in=args["token_in"],
            token_out=args["token_out"],
            amount=args["amount"],
        )
        _log("swap", args, "submitted")
        return {"status": "submitted", "result": str(result)}
    except Exception as e:
        _log("swap", args, str(e), status="error")
        return {"error": str(e), "preview": False}


def handle_revoke_approval(args: dict) -> dict:
    """Revoke a token approval."""
    args = dict(args)
    confirm = args.pop("confirm", False)
    if not confirm:
        _log("revoke_approval", args, "preview")
        return {
            "preview": True,
            "message": f"Preview: Revoke approval for {args['token_address']} spender {args['spender_address']}",
            "token_address": args["token_address"],
            "spender_address": args["spender_address"],
            "chain": args.get("chain", "ethereum"),
            "note": "Pass confirm=true to execute",
        }

    try:
        wallet = _get_wallet_from_env(args.get("chain", "ethereum"))
        if not wallet:
            return {"error": "WALLET_PRIVATE_KEY not configured"}
        if not wallet.is_enforced:
            return {
                "error": (
                    "No pre-sign authorization pipeline is configured; the approval was not revoked"
                )
            }
        from web3_agent_kit.wallet.approval import ApprovalManager

        chain, _ = _chain_and_manager(args.get("chain", "ethereum"))
        manager = ApprovalManager(wallet, wallet.chain_manager)
        result = manager.revoke(
            args["token_address"],
            args["spender_address"],
            chain,
        )
        if not result.success:
            return {"error": result.error or "Approval revocation failed"}
        _log("revoke_approval", args, "submitted")
        return {"status": "submitted", "tx_hash": result.tx_hash}
    except Exception as e:
        _log("revoke_approval", args, str(e), status="error")
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
            "annotations": {"readOnlyHint": t.read_only},
        }
        for t in TOOLS
    ]


def _rpc_error(request_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def handle_request(request: dict) -> dict | None:
    """Handle one MCP JSON-RPC request or notification."""
    if not isinstance(request, dict):
        return _rpc_error(None, -32600, "Invalid Request")
    request_id = request.get("id")
    method = request.get("method")
    if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return _rpc_error(request_id, -32600, "Invalid Request")

    is_notification = "id" not in request
    params = request.get("params") or {}
    if not isinstance(params, dict):
        return _rpc_error(request_id, -32600, "Invalid Request")

    if method == "notifications/initialized":
        return None
    if is_notification:
        return None
    if method == "initialize":
        protocol_version = params.get("protocolVersion")
        if protocol_version != MCP_PROTOCOL_VERSION:
            protocol_version = MCP_PROTOCOL_VERSION
        from web3_agent_kit import __version__

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "web3-agent-kit",
                    "version": __version__,
                },
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": list_tools()}}
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or name not in HANDLERS:
            response = {
                "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                "isError": True,
            }
        elif not isinstance(arguments, dict):
            response = {
                "content": [{"type": "text", "text": "Tool arguments must be an object"}],
                "isError": True,
            }
        else:
            try:
                result = HANDLERS[name](arguments)
                failed = isinstance(result, dict) and result.get("error") is not None
                _log(name, arguments, json.dumps(result), status="error" if failed else "ok")
                response = {
                    "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                    **({"isError": True} if failed else {}),
                }
            except Exception as exc:
                _log(name, arguments, str(exc), status="error")
                response = {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                }
        return {"jsonrpc": "2.0", "id": request_id, "result": response}

    return _rpc_error(request_id, -32601, f"Method not found: {method}")


# ---------------------------------------------------------------------------
# MCP server entry point
# ---------------------------------------------------------------------------


def main():
    """Entry point for MCP server.

    Supports:
        --list          List available tools as JSON
        <tool> --args   Call a tool directly (utility mode)
        (no args)       Start the MCP JSON-RPC stdio server
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
        result = HANDLERS[tool_name](args)
        print(json.dumps(result, indent=2))
        return

    for line in sys.stdin:
        try:
            response = handle_request(json.loads(line))
        except json.JSONDecodeError:
            response = _rpc_error(None, -32700, "Parse error")
        if response is not None:
            print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
