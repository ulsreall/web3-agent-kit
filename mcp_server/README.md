# MCP Server — Web3 Agent Kit

The server exposes Web3 Agent Kit tools over the standard MCP JSON-RPC stdio
transport. Start it with `python -m mcp_server` from an environment where this
repository is installed or on `PYTHONPATH`.

The stdio transport accepts newline-delimited JSON-RPC requests, including
`initialize`, `notifications/initialized`, `tools/list`, and `tools/call`.
Tool calls use MCP's `params.name` and `params.arguments` shape; the server does
not use a custom `{ "tool": ..., "args": ... }` envelope on stdio.

## Client configuration

For Claude Desktop or another MCP client, configure the command using the
client's normal stdio server settings:

```json
{
  "mcpServers": {
    "web3-agent-kit": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "env": {
        "RPC_URL": "https://your-rpc-provider.example"
      }
    }
  }
}
```

Set `BASE_RPC_URL`, `ETHEREUM_RPC_URL`, or another `<CHAIN>_RPC_URL` to use a
different endpoint for a supported chain; the chain-specific variable takes
precedence over `RPC_URL`. Read-only balance calls use the supplied wallet
address and do not require a private key. The token check uses the GoPlus API.

## Tools and safety

`tools/list` advertises `get_balance`, `check_honeypot`, `get_portfolio`,
`swap`, and `revoke_approval`. Balance and portfolio calls query the configured
RPC. State-changing tools return a preview unless called with
`confirm: true`. This server does not configure an application-specific
pre-sign authorization provider, so confirmed state-changing calls return an
explicit error instead of signing or submitting a transaction. No credentials
or external operations are used by this documentation example.

For local inspection only, `python -m mcp_server --list` prints the tool
definitions. The legacy direct utility form
`python -m mcp_server <tool> --args '<json>'` is not the MCP stdio protocol.
