# Review — web3-agent-kit @ 55c6a0a (v1.19.1)

> **Status:** P1, P2 and the P3 commitment check are fixed on branch `fix/api-write-paths`
> (see `docs/changelog.md` → Unreleased). Remaining: cross-process replay store (P3),
> `_consumed` pruning (P3). PoCs below now print OK/GAP against the branch.

Scope: full read of `web3_agent_kit/execution/*`, `wallet/wallet.py`, `api/*`, the Nov 3 security commits (#117, #118), plus the Solana ATA/instruction rewrite. Everything below was reproduced locally on Python 3.11 with the project's own venv, not inferred from reading.

Baseline: `pytest` → 2047 passed, 7 skipped, **1 failed** (`tests/test_integration.py::test_wallet_sign_transaction`).

---

## P1 — The API write surface is dead code

All three write endpoints are broken by signature drift against the library they call. None of it is caught by CI because the route tests replace the collaborator with a `Mock` and only assert the mock was called.

### 1. `POST /swap/execute` — `web3_agent_kit/api/routes/swap.py:42-44`

```python
wallet = Wallet.from_env("PRIVATE_KEY")
uni = Uniswap(chain)  # (a)
result = uni.execute(wallet, token_in, token_out, amount_in, slippage)  # (b)(c)
```

| # | Reality | Result |
|---|---------|--------|
| a | `Uniswap.__init__(self, chain_manager=None, slippage=0.5)` (`defi/__init__.py:203`) | `"base"` lands in `chain_manager` → `AttributeError: 'str' object has no attribute 'get_web3'` |
| b | `execute(self, wallet, token_in, token_out, amount, chain=Chain.ETHEREUM, **kwargs)` (`defi/__init__.py:207`) | 5th positional is `chain`; the route passes `slippage` (float) → `AttributeError: 'float' object has no attribute 'value'` |
| c | Defaults are `token_out="USDC"`, but `execute` only resolves `ETH`/`NATIVE`/WETH or a raw address (`defi/__init__.py:242-253`) | `ValueError: when sending a str, it must be a hex string. Got: 'USDC'` |
| d | `Wallet.from_env(...)` is never bound to a gate | `EnforcementDenied: wallet has no bound pre-sign gate` |

Reproduced:

```
POST /swap/execute?chain=base&token_in=ETH&token_out=USDC
→ 400 {"detail":"'float' object has no attribute 'value'"}
```

With `token_out` set to a real address and the constructor fixed, it still ends at (d) — the endpoint can never produce a signature.

### 2. `POST /bridge/execute` — `api/routes/bridge.py:40-42`

```python
agent = BridgeAgent(from_chain)  # __init__(self, chain_manager, wallet, ...)
result = agent.transfer(wallet, to_chain, token, amount)
# real signature: transfer(self, token, amount, from_chain, to_chain, route=None)
```

`BridgeAgent('ethereum')` → `TypeError: missing 1 required positional argument: 'wallet'`. Argument order is also fully rotated.

### 3. `POST /dca/create` — `api/routes/dca.py:36-43`

```python
bot = DCABot(chain)  # __init__(self, wallet, chain_manager, uniswap=None)
order = bot.create_order(
    token_in=..., token_out=..., amount_per_buy=..., frequency=..., total_buys=...
)
# real: create_order(from_token, to_token, amount, chain, interval, max_buys=None, ...)
```

Constructor is missing `chain_manager`; all five keyword names are wrong.

### Fix

Bind one shared gate at app startup and inject it; pass real objects, not names. Then add one contract test per route that does **not** mock the collaborator (or that asserts against `inspect.signature`). The current tests (`tests/test_api_routes.py:165`, `:722`) would pass even if the methods were renamed.

---

## P2 — Contract creation cannot pass the gate

`docs/changelog.md:163` says the unbound-wallet creation hole was fixed. It was fixed by *refusing* creation, not by *enforcing* it: with a gate bound, creation still fails.

`AuthorizationRequest.__post_init__` (`execution/interceptor.py:126`) requires `to`:

```python
_REQUIRED_TX_FIELDS = ("to", "from", "nonce", "chainId")
```

Reproduced:

```
AuthorizationRequest(chain=BASE, action=CONTRACT_CALL, transaction={to: None, data: "0x60806052", ...})
→ InvalidIntentError: transaction must be fully constructed before signing; missing: to
```

Even if that check is relaxed, `TransactionIntent` requires `contract` for `CONTRACT_CALL` (`execution/intent.py:128-140`), so the second stage denies too. `CallEnvelopeV1/V2` already model creation correctly (`execution_profile == "create"`, `tests/test_p0_hardening.py:486`) — the envelope is simply unreachable through the request object.

Impact: `wallet.sign_transaction(tx_with_to_None)` can never succeed, so the deploy path is unusable behind the gate. `p0_probe.py` only probes the *unbound* case, which is why this was missed.

### Fix

- Drop `to` from `_REQUIRED_TX_FIELDS` (the envelope already validates the creation profile).
- In `TransactionIntent.from_evm_transaction`, allow `contract=None` when `to is None` and calldata is non-empty; carry an explicit `execution_profile`.
- Add a gate-level test: bound wallet + policy + provider + `to=None` → signature produced, envelope profile `create`.

---

## P2 — `input` is ignored; the envelope can authorize the wrong calldata

`_canonical_calldata` reads only `transaction.get("data")` (`execution/envelope.py:277`), and `TransactionIntent` does the same (`execution/intent.py:188`).

- A tx carrying `input` only → envelope hashes `keccak256(b"")` = `0xc5d24601…` while the transaction carries real calldata.
- `eth_account.sign_transaction` rejects the key outright: `TypeError: Unknown kwargs: ['input']`.

So today it fails loudly at the signer. The dangerous variant is a custom `SignerFn` (KMS, viem bridge, hardware signer) that *does* accept `input`: the principal would authorize an empty-calldata envelope and the signer would sign the real call. `covers()` would still return true because the digest matches the (wrong) envelope.

### Fix

Resolve `data`/`input` once, with conflict detection like `_optional_transaction_int` already does for `gas`/`gasLimit`:

```python
raw = transaction.get("data")
alt = transaction.get("input")
if raw is not None and alt is not None and _canonical_calldata(raw) != _canonical_calldata(alt):
    raise CallEnvelopeError("conflicting data and input")
calldata = _canonical_calldata(raw if raw is not None else alt)
```

Mirror it in `TransactionIntent`, and normalize to `data` before handing the mapping to the signer.

---

## P2 — The integration test fails whenever it is actually run

`tests/test_integration.py` skips the whole module unless `PRIVATE_KEY` is set — which is exactly how its docstring tells you to run it. With a key present:

```
tests/test_integration.py::test_wallet_sign_transaction FAILED
EnforcementDenied: wallet has no bound pre-sign gate
```

CI never sees it because CI sets no `PRIVATE_KEY`, so the module silently skips. The test still signs through an unbound wallet (`test_integration.py:74`).

### Fix

Bind a gate in the test (or use the `enforced_signing.py` helper), and add one CI job that runs the integration module with a throwaway key so the fail-closed contract stays covered.

---

## P3 — Authorization replay protection is per-process only

`_consumed` (`execution/interceptor.py:270`) is an instance set. A second gate instance — a second uvicorn worker, a restarted process, a second agent — accepts the same authorization again. Reproduced with a fresh gate on the same tx: accepted.

The docstring is honest about it ("process-local"), but the API server is the deployment where it matters, and nothing in `api/` shares a gate.

Also unbounded: `_consumed` never prunes, so a long-running worker grows one tuple per signed transaction forever.

### Fix

- Share a single gate per process *and* persist consumed `(authorization_id, nonce)` to a small SQLite/Redis store with a TTL equal to the authorization validity window.
- Prune by `valid_until` on insert.

---

## P3 — The evidence's policy commitment is never checked

`AuthorizationEvidence.policy_commitment_digest` is stored and logged (`interceptor.py:448`) but never compared to `commitment.digest()`. A provider returning `0xdeadbeef` is accepted:

```
accepted with bogus policy_commitment_digest: 0xdeadbeef
real commitment digest:                       0xa5de88c6…
```

The commitment is therefore decorative on the verification path — it only reaches the audit log.

### Fix

Add a fifth check next to the envelope/executor/freshness checks:

```python
if evidence.policy_commitment_digest != commitment.digest():
    → _DenialReason.AUTHORIZATION_POLICY_MISMATCH
```

---

## P3 — Solana: the sender's ATA is never created

`web3_agent_kit/solana/wallet.py:189` builds a `CreateIdempotent` (discriminator `0x01`) for the **destination** ATA only. `from_ata` is derived and used as the transfer source but never created. A wallet that has never held the mint fails the transfer with `AccountNotInitialized`. The instruction encoding itself is correct (accounts and `TransferChecked` layout match the SPL program).

Also: `TOKEN_PROGRAM_ID` is hardcoded, so Token-2022 mints derive the wrong ATA.

### Fix

Prepend a `CreateIdempotent` for `from_ata` (payer = owner), and resolve the token program from the mint account owner instead of hardcoding it.

---

## P3 — Every example except one is stale

`examples/enforced_signing.py` is the only file that binds a gate. `swap_agent.py`, `sniper_bot.py`, `dca_bot.py`, `airdrop_farmer.py`, `direct_swap.py`, `multi_wallet.py`, `bridge_agent.py` all construct a bare `Wallet` and will now raise `EnforcementDenied` on their first write. The README documents the fail-closed rule, so this is documentation drift rather than a hole — but the examples are the first thing a new user runs.

### Fix

Add a `build_enforced_wallet()` helper to `examples/support/` and use it in every write example.

---

## P4 — `tests/test_solana_lp.py` fixture ignores the optional extra

The `lp_manager_with_wallet` fixture instantiates `SolanaWallet()` unconditionally (`tests/test_solana_lp.py:18`), so the suite errors instead of skipping when `solders` is absent:

```
ModuleNotFoundError: No module named 'solders'
```

CI installs `.[dev,solana]`, so it only bites contributors who install `.[dev]`. Guard with `pytest.importorskip("solders")`.

---

## What is genuinely good

Worth saying because it is the part that should not regress:

- **Envelope canonicalization** (`execution/envelope.py`) is the strongest code in the repo: domain-separated hashing, schema label inside the payload, bool-vs-int rejection, hex/decimal normalization, alias conflict detection, address lowercasing, creation as a distinct profile, and a chain-ID equality check that fails before the signer is reachable.
- **Gate ordering** is correct and fail-closed at every stage: policy → confirmation → authorization → sign, with the raw signer unreachable until evidence exists.
- **Independent re-verification of provider evidence** (digest, executor, freshness, replay) instead of trusting the provider's return value.
- **API key handling**: `secrets.compare_digest`, 401 when unconfigured, startup refusal, CORS `*`+credentials rejection.
- **`tools/check_signing_surface.py` in CI** — a real structural guard against new bypasses, with an explicit legacy baseline.

## Suggested order

1. API routes (P1) + a non-mocked contract test — the endpoints are the product's front door.
2. Creation through the gate (P2) — unblocks deploys and makes the changelog claim true.
3. `data`/`input` normalization (P2) — closes the wrong-calldata authorization path.
4. Integration test in CI (P2).
5. Replay store + commitment check (P3).
6. Solana ATA/program resolution (P3).
7. Examples + fixture guards (P3/P4).

## Reproduction

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,solana]"
.venv/bin/python poc_gate.py     # creation, input, replay, commitment
.venv/bin/python poc_api.py      # POST /swap/execute
.venv/bin/python -m pytest tests/test_integration.py -q   # with PRIVATE_KEY set
```
