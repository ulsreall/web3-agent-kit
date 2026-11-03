"""Tests for the MCP JSON-RPC stdio server."""

import io
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import mcp_server
from web3_agent_kit.chains.chain import Chain


def test_initialize_returns_standard_mcp_capabilities():
    response = mcp_server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 7
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert response["result"]["capabilities"] == {"tools": {}}


def test_tools_list_uses_mcp_tool_shape():
    response = mcp_server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )

    tool = response["result"]["tools"][0]
    assert tool["name"] == "get_balance"
    assert "inputSchema" in tool
    assert tool["annotations"]["readOnlyHint"] is True


def test_tools_call_uses_mcp_arguments_and_content():
    with patch.dict(
        mcp_server.HANDLERS,
        {"get_balance": lambda arguments: {"address": arguments["address"], "balance": 2}},
    ):
        response = mcp_server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {
                    "name": "get_balance",
                    "arguments": {"address": "0xabc"},
                },
            }
        )

    assert response["id"] == "call-1"
    assert json.loads(response["result"]["content"][0]["text"]) == {
        "address": "0xabc",
        "balance": 2,
    }


def test_notification_has_no_response():
    assert (
        mcp_server.handle_request(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        is None
    )


def test_custom_tool_args_envelope_is_not_accepted():
    response = mcp_server.handle_request({"tool": "get_balance", "args": {}})

    assert response["error"]["code"] == -32600


def test_balance_queries_supplied_address_without_private_key():
    web3 = SimpleNamespace(
        eth=SimpleNamespace(get_balance=lambda address: 12),
        from_wei=lambda amount, unit: 1.2,
    )
    manager = SimpleNamespace(get_web3=lambda chain: web3)
    with patch.object(mcp_server, "_chain_and_manager", return_value=(Chain.ETHEREUM, manager)):
        result = mcp_server.handle_get_balance(
            {"address": "0xabc", "chain": "ethereum"}
        )

    assert result == {"address": "0xabc", "chain": "ethereum", "balance": 1.2}


def test_confirmed_swap_refuses_without_authorization_gate():
    wallet = SimpleNamespace(is_enforced=False)
    with patch.object(mcp_server, "_get_wallet_from_env", return_value=wallet):
        result = mcp_server.handle_swap(
            {
                "confirm": True,
                "token_in": "ETH",
                "token_out": "USDC",
                "amount": 0.1,
                "chain": "base",
            }
        )

    assert "authorization pipeline" in result["error"]
    assert result["preview"] is False


def test_confirmed_approval_uses_approval_manager(monkeypatch):
    wallet = SimpleNamespace(is_enforced=True, chain_manager=object())
    manager = MagicMock()
    manager.revoke.return_value = SimpleNamespace(success=True, tx_hash="0xsent")
    monkeypatch.setenv("BASE_RPC_URL", "https://rpc.example")
    with (
        patch.object(mcp_server, "_get_wallet_from_env", return_value=wallet),
        patch(
            "web3_agent_kit.wallet.approval.ApprovalManager",
            return_value=manager,
        ),
    ):
        result = mcp_server.handle_revoke_approval(
            {
                "confirm": True,
                "chain": "base",
                "token_address": "0xtoken",
                "spender_address": "0xspender",
            }
        )

    assert result == {"status": "submitted", "tx_hash": "0xsent"}
    manager.revoke.assert_called_once_with(
        "0xtoken", "0xspender", Chain.BASE
    )


def test_stdio_main_reads_jsonrpc_requests(monkeypatch):
    requests = "\n".join(
        [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"},
                }
            ),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                }
            ),
        ]
    )
    output = io.StringIO()
    monkeypatch.setattr(sys, "argv", ["mcp_server"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(requests))
    monkeypatch.setattr(sys, "stdout", output)

    mcp_server.main()

    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [response["id"] for response in responses] == [1, 2]
    assert all(response["jsonrpc"] == "2.0" for response in responses)
