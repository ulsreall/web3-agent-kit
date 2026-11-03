# CLI Tool — `wak`

The `wak` command provides read-only wallet, token-safety, and gas queries plus
an AI-agent entry point. RPC-backed commands require an RPC URL; they do not
silently print placeholder results.

## Installation

```bash
pip install web3-agent-kit
```

## Commands

### `wak info` and `wak doctor`

`wak info` shows package details. `wak doctor` checks the Python environment,
core dependencies, `.env` file, and configured environment-variable presence.

### `wak wallet balance`

Read a public address's native-token balance without a private key:

```bash
wak wallet balance --address 0x... --chain base
```

Set `BASE_RPC_URL` or the fallback `RPC_URL` to query Base. The output reports
the address, chain, and balance; it does not fetch token balances or USD prices.

### `wak gas`

Query the configured chain's gas price and show the selected priority fee and
an estimated 21,000-gas transfer cost:

```bash
wak gas --chain ethereum --priority medium
```

Supported priorities are `low`, `medium`, `high`, and `urgent`.

### `wak token check`

Run the GoPlus quick honeypot/tax lookup:

```bash
wak token check --address 0x... --chain base
```

This is not a full contract audit or a token-balance/price query. If the
provider has no result, the CLI reports the check as `unknown`.

### `wak examples`

List the Python example files included in the repository.

### `wak agent`

The command accepts `--goal`, `--wallet`, and `--chain`; the wallet address
must match the account from `PRIVATE_KEY`. `--yes` skips the interactive
transaction prompt only. The CLI currently has no configuration surface for
the required pre-sign authorization provider, so it fails closed rather than
running an agent that could attempt to submit a transaction. Use the Python API
to construct and bind an authorized `PreSignInterceptor` before running an
agent.

## Environment

Use chain-specific RPC variables when possible; each takes precedence over
`RPC_URL`:

```text
BASE_RPC_URL=https://...
ETHEREUM_RPC_URL=https://...
RPC_URL=https://...
```

`PRIVATE_KEY` is required only by `wak agent`, and `OPENAI_API_KEY` or
`ANTHROPIC_API_KEY` is needed by the LLM client. Do not put keys in command-line
arguments or commit them to the repository.

## Help

```bash
wak --help
wak --version
wak wallet --help
```
