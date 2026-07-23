# MCP Server — Web3 Agent Kit

[Model Context Protocol](https://modelcontextprotocol.io) server that exposes Web3 Agent Kit tools for use with AI agents (Claude, Cursor, etc.).

## Tools

### Read-only (auto-approved)

| Tool | Description |
|------|-------------|
| `get_balance` | Get native balance for a wallet address on a chain |
| `check_honeypot` | Check if a token is a honeypot (uses GoPlus API) |
| `get_portfolio` | Get portfolio overview across multiple wallets/chains |

### State-changing (dry-run by default)

| Tool | Description |
|------|-------------|
| `swap` | Execute a token swap (returns preview first, confirm to execute) |
| `revoke_approval` | Revoke a token approval (returns preview first) |

All state-changing tools default to **simulation mode** — they return a transaction preview without broadcasting. Pass `confirm=true` to execute.

## Usage

### With Claude Desktop

```json
{
  "mcpServers": {
    "web3-agent-kit": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "env": {
        "WEB3_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### Direct

```bash
# List tools
python -m mcp_server --list

# Call a read-only tool
python -m mcp_server get_balance --args '{"address": "0x...", "chain": "base"}'

# Call a state-changing tool (dry-run)
python -m mcp_server swap --args '{"token_in": "ETH", "token_out": "USDC", "amount": 0.1}'

# Call with confirmation
python -m mcp_server swap --args '{"token_in": "ETH", "token_out": "USDC", "amount": 0.1, "confirm": true}'
```

## Security

- **Read-only tools** are safe to expose directly — they never modify state.
- **State-changing tools** require explicit `confirm: true` — without it, they return a preview only.
- All tool calls are logged to stdout with timestamp, tool name, args, and result.
- The server does **not** hold private keys itself; users must configure wallet access separately.
- For production, run behind a local-only socket and set `WEB3_API_KEY`.

## Audit Log

Every state-changing call is logged in structured JSON format:

```
{"timestamp": "...", "tool": "swap", "args": {...}, "result": "preview|executed|error"}
```