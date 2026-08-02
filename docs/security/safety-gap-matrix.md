# Transaction Safety Gap Matrix

This document prioritizes gaps discovered by the transaction execution-path
audit. It describes current code behavior and the controls required before a
module can be promoted. It does not claim that unlisted risks are absent.

## Rating model

| Priority | Meaning |
|---|---|
| **P0** | A cross-cutting gap that can permit unintended signing, broadcast, or fund movement |
| **P1** | A material correctness or loss-amplification risk on a supported write path |
| **P2** | A defense-in-depth, operability, or maintainability gap |

## Cross-cutting gaps

| Priority | Gap | Evidence | Required control | Completion signal |
|---|---|---|---|---|
| P0 | No mandatory execution gateway | Broadcasts occur directly in wallet, DeFi, bridge, governance, messaging, restaking, airdrop, and Solana modules | Route all supported writes through typed intent, policy, simulation, signer, and receipt stages | A CI check and tests demonstrate that supported writes cannot bypass the gateway |
| P0 | SpendGovernor is agent-scoped | `Agent._act()` authorizes tool calls, while direct SDK and REST calls execute outside that path | Introduce a library-level `ExecutionPolicy`; retain SpendGovernor through a compatibility adapter | Direct SDK, agent, CLI, and API calls produce the same policy decision |
| P0 | Simulation is optional and disconnected | `TxSimulator` is standalone and direct broadcast sites do not require it | Add `require_simulation`, fail closed when required simulation is unavailable, and attach results to confirmation | Every supported broadcast test asserts successful prior simulation |
| P0 | Signing boundaries are fragmented | Governance, messaging, and airdrop sign directly; EVM Wallet and Solana Wallet use separate local secret models | Introduce signer protocols and prohibit execution modules from accepting raw keys | Raw-key parameters are confined to signer construction |
| P0 | Externally supplied bridge calldata is broadcast without a shared allowlist policy | Li.Fi and Socket responses supply destination, calldata, value, and gas fields | Verify chain, provider, destination contract, value, calldata selector, and route expiry before signing | Mutated provider responses are rejected in adversarial tests |
| P1 | Receipt success is not consistently validated | Several paths wait for a receipt but return success without a shared `status == 1` check | Centralize receipt validation and typed failure results | Reverted-receipt tests never report success |
| P1 | Chain IDs can fall back to Ethereum | Several transaction builders use `CHAIN_IDS.get(chain, 1)` | Reject unsupported or absent chain IDs instead of defaulting | Unknown-chain tests fail before signing |
| P1 | Financial values frequently use `float` | Swap, bridge, DCA, and Solana public methods accept decimal floats | Use integer base units and `Decimal` at external display boundaries | Property tests cover exact conversion and boundary values |
| P1 | Read-only messaging returns a zero transaction hash | Messaging can return a fabricated zero hash when no private key is configured | Return a typed unsigned proposal or explicit read-only error | No dry-run path can be mistaken for a broadcast transaction |
| P1 | Slippage guarantees vary by protocol path | Some swaps calculate minimum output, while liquidity code includes permissive minimums | Validate basis-point limits centrally and reject zero minimums unless explicitly approved | Policy tests cover every supported swap/liquidity action |
| P1 | API authentication grants broad execution authority | A valid API key can reach transaction endpoints without per-request authorization policy | Add scoped credentials, idempotency keys, policy evaluation, and optional human approval | API tests verify scope, replay rejection, and policy parity |
| P2 | Audit records are unstructured | Execution methods return different dictionaries, dataclasses, hashes, or strings | Emit a common redacted record for intent, policy, simulation, signing, and receipt | Operators can correlate every attempt by intent ID |
| P2 | Error handling is inconsistent | Some paths raise, some return `None`, and agent paths stringify exceptions | Define typed execution errors and preserve safe diagnostic context | Callers can distinguish validation, policy, simulation, signing, broadcast, and receipt failures |
| P2 | Secret redaction is not enforced centrally | Multiple objects hold plaintext private keys or keypairs in memory | Add redaction tests and signer-owned secret lifecycle rules | Keys never appear in repr, logs, exceptions, or audit records |

## Area readiness matrix

Legend: **Yes** means the control is enforced on the path, **Partial** means it
exists only on some methods or outside the execution boundary, and **No** means
the audit found no mandatory control.

| Area | Central policy | Simulation required | Typed intent | Shared signer | Receipt validation | Idempotency | Priority |
|---|---:|---:|---:|---:|---:|---:|---|
| Agent tool execution | Partial | No | No | Partial | Tool-dependent | No | P0 |
| EVM Wallet | No | No | No | Yes | No | No | P0 |
| DeFi / Uniswap | No | No | No | Yes | Partial | No | P0 |
| Bridge | No | No | No | Yes | Partial | No | P0 |
| REST write endpoints | No | No | No | Partial | Downstream-dependent | No | P0 |
| Governance | No | No | No | No | No | No | P0 |
| Messaging | No | No | No | No | No | No | P0 |
| Restaking | No | No | No | Yes | Partial | No | P0 |
| Airdrop on-chain | Partial | No | No | No | Partial | No | P0 |
| Solana wallet | No | No | No | Separate implementation | No | No | P0 |

## Recommended implementation order

### Milestone 1 — Establish the boundary

1. Add immutable `TransactionIntent` and normalized amount/address types.
2. Add `ExecutionPolicy` with explicit allowlists and value/slippage limits.
3. Add a local EVM `Signer` adapter around the existing Wallet behavior.
4. Migrate `Wallet.send_transaction()` without breaking existing callers.
5. Add typed execution and receipt results.

### Milestone 2 — Make simulation mandatory

1. Connect `TxSimulator` to the execution gateway.
2. Add fail-closed `require_simulation` behavior.
3. Decode reverts and record gas estimates.
4. Compare intended and simulated native/token/approval deltas.
5. Add confirmation payloads based on simulation results.

### Milestone 3 — Close high-risk bypasses

1. Migrate REST swap and bridge execution.
2. Validate external bridge transactions against provider and contract allowlists.
3. Migrate Uniswap approvals and swaps.
4. Replace governance and messaging raw-key parameters with signers.
5. Return explicit unsigned proposals for read-only flows.

### Milestone 4 — Expand coverage

1. Migrate restaking.
2. Migrate airdrop execution.
3. Define and implement the Solana signer/policy equivalent.
4. Add idempotency and structured audit storage.
5. Promote modules only after satisfying the maturity criteria.

## Proposed issue backlog

| Order | Issue | Acceptance summary |
|---:|---|---|
| 1 | `feat: introduce immutable TransactionIntent` | Typed chain, sender, destination, value, calldata, action, and metadata; validation tests |
| 2 | `feat: add centralized ExecutionPolicy` | Chain/contract/token allowlists, amount/slippage/approval limits, fail-closed decisions |
| 3 | `feat: define EVM Signer protocol` | Local-key adapter, read-only signer, secret-redaction tests |
| 4 | `refactor: route Wallet.send_transaction through execution gateway` | Compatibility preserved; policy cannot be bypassed on the new path |
| 5 | `feat: require pre-flight simulation before configured broadcasts` | Simulation result attached; unavailable simulator blocks execution |
| 6 | `fix: reject unknown chain IDs instead of defaulting to Ethereum` | No `CHAIN_IDS.get(..., 1)` on migrated write paths |
| 7 | `fix: validate receipt status consistently` | Reverted receipts produce typed failures |
| 8 | `security: validate bridge provider transaction payloads` | Destination/value/selector/expiry mutation tests |
| 9 | `security: add REST execution scopes and idempotency` | Scoped keys and replay tests |
| 10 | `refactor: replace raw-key execution parameters with Signer` | Governance and messaging accept signer/proposal flows |

## Definition of done for a migrated path

- The request becomes a validated immutable intent.
- Amounts use base units; slippage uses basis points.
- Unknown chains, values, destinations, and actions fail closed.
- Policy evaluation happens before simulation or signing.
- Required simulation cannot be bypassed by simulator failure.
- Confirmation receives normalized intent and simulation data.
- Only a signer owns secret material.
- Receipt status is checked before success is returned.
- An idempotent, redacted audit record is emitted.
- Unit and adversarial tests require no live network.
