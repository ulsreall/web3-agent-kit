# Transaction Execution Paths

This inventory maps the code paths that can sign or broadcast transactions. It
is a static audit of the v1.15 codebase, not a security certification. Line
numbers are intentionally omitted because the inventory should remain useful as
implementations move; paths and symbols are the stable references.

## Scope and method

The audit searched the package for transaction construction, signing, receipt
waiting, and EVM/Solana broadcast primitives. Read-only quote, balance, and
simulation operations are excluded unless they can lead directly to a write.

At the time of the audit, direct broadcast primitives occur at **24 call sites
across 10 files**. Several higher-level entry points eventually converge on
those sites, but there is no single mandatory execution gateway.

## Entry-point inventory

| Area | Public or high-level entry point | Signing boundary | Broadcast boundary | Current safeguards | Maturity |
|---|---|---|---|---|---|
| Agent tools | `Agent._act()` → `tool.execute()` | Tool-dependent | Tool-dependent | SpendGovernor checks an estimated native value; unknown values fail closed | Beta |
| EVM wallet | `Wallet.send_transaction()` | `Wallet.sign_transaction()` | `w3.eth.send_raw_transaction()` | Requires configured chain manager and key | Beta |
| Uniswap V2-style swaps | `Uniswap.execute()` | `Wallet.sign_transaction()` | Direct Web3 broadcast | Quote-derived minimum output and 20-minute deadline; exact-amount approvals | Experimental |
| Uniswap V3 swaps | `UniswapV3.swap()` and related execution helpers | `Wallet.sign_transaction()` | Direct Web3 broadcast | Minimum output, deadline, and exact-amount approvals on covered paths | Experimental |
| Other DeFi protocols | Aave/Curve and liquidity execution helpers in `defi/__init__.py` | `Wallet.sign_transaction()` | Direct Web3 broadcast | Per-method slippage behavior; no shared policy gateway | Experimental |
| Bridge | `BridgeAgent.transfer()` | `Wallet.sign_transaction()` | Direct Web3 broadcast | Route selection and receipt wait | Experimental |
| Governance | `GovernanceTracker.delegate()` | Direct Web3 account signing with a raw key | Direct Web3 broadcast | Address checksum conversion | Experimental |
| Cross-chain messaging | `CrossChainMessenger.send_message()` | Direct Web3 account signing with stored raw key | Direct Web3 broadcast | Protocol fee/gas construction | Experimental |
| Restaking | EigenLayer and protocol adapter stake/unstake/delegate helpers | `Wallet.sign_transaction()` | Direct Web3 broadcast | Protocol-specific transaction construction and receipt wait | Experimental |
| Airdrop on-chain executor | `OnchainExecutor._send_transaction()` | Direct local-account signing | Direct Web3 broadcast | Daily transaction count in the orchestration layer; exceptions logged | Experimental |
| Solana wallet | `SolanaWallet.send_sol()` / `send_token()` | In-process keypair signing | `SolanaClient.send_transaction()` | Recent blockhash requirement and checked token transfer | Experimental |

## Direct broadcast sites

### Core wallet

- `web3_agent_kit/wallet/wallet.py`
  - `Wallet.send_transaction()` signs and broadcasts an arbitrary transaction
    dictionary.

### DeFi

- `web3_agent_kit/defi/__init__.py`
  - Swap execution and token approvals.
  - Shared protocol transaction execution.
  - Curve and liquidity operations.
- `web3_agent_kit/defi/uniswap_v3.py`
  - Approval execution.
  - Exact-input swap execution.

### Cross-chain and governance

- `web3_agent_kit/bridge/bridge.py`
  - Li.Fi transaction execution.
  - Socket transaction execution.
- `web3_agent_kit/governance/__init__.py`
  - Delegation transaction execution.
- `web3_agent_kit/messaging/__init__.py`
  - LayerZero message transaction execution.

### Restaking plugins

- `web3_agent_kit/plugins/restaking/eigenlayer.py`
  - Deposit, delegate, undelegate, withdrawal, and approval execution.
- `web3_agent_kit/plugins/restaking/protocols.py`
  - Protocol-specific stake, delegate, unstake, and withdrawal execution.

### Other autonomous execution

- `web3_agent_kit/airdrop/onchain.py`
  - Generic local-account transaction signing and broadcast.
- `web3_agent_kit/solana/client.py`
  - Base64 transaction submission through the Solana RPC
    `sendTransaction` method.

## Control flow observations

### Agent execution is only one of several gateways

`Agent._act()` applies SpendGovernor before calling a registered tool. Direct
library calls, REST endpoints, bridge execution, governance, messaging,
restaking, airdrop, and Solana wallet methods do not necessarily pass through
the agent. SpendGovernor therefore cannot currently be treated as a global
transaction policy.

### Simulation is available but not mandatory

`TxSimulator` exists as a standalone module. None of the direct broadcast sites
are forced through it, and write methods do not share a `require_simulation`
contract.

### Signing is fragmented

The EVM wallet abstraction is used by much of DeFi, bridge, and restaking.
Governance, messaging, and airdrop code sign directly with private keys or local
accounts. Solana has a separate in-process keypair boundary. This fragmentation
prevents one policy, secret-redaction, or hardware-signer implementation from
covering every execution path.

### API authentication is not transaction authorization

REST API authentication controls who may call an endpoint. Once authenticated,
swap and bridge handlers invoke execution methods directly. Authentication must
not be considered a substitute for per-transaction value, asset, contract, and
simulation policies.

## Target execution lifecycle

All supported write paths should converge on the following lifecycle:

```text
request / agent plan
        ↓
typed TransactionIntent
        ↓
deterministic validation
        ↓
ExecutionPolicy decision
        ↓
pre-flight simulation
        ↓
human confirmation (when required)
        ↓
Signer
        ↓
broadcast + receipt validation
        ↓
structured audit record
```

## First migration slice

The first implementation slice should be `Wallet.send_transaction()` because it
is small, already reused by callers, and exposes the core sign/broadcast
boundary. The slice should introduce:

1. A typed `TransactionIntent` separate from the Web3 transaction dictionary.
2. An `ExecutionPolicy` decision before signing.
3. Optional but fail-closed required simulation.
4. A `Signer` interface implemented by the current local-key wallet.
5. Receipt-status validation and a structured execution result.
6. An explicit compatibility adapter for existing callers.

After that slice is stable, migrate Uniswap, bridge, and REST execution before
expanding to the remaining experimental modules.
