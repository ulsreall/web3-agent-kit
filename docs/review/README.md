# Core-change review artifact — 1.18.5

This directory exists so the WAK owner and YuTao can review the **core** delta in isolation,
exactly as the v1 conformance fixture requires:

> *"The WAK owner and YuTao must align on the necessary file split before any WAK core change
> or P1 attempt."* — `tests/fixtures/insight_priorseal_spike/v1/README.md`

## Why this exists

The v1.18.4 tag's `web3_agent_kit/chains/chain.py` has no Base Sepolia member. PR #90
(`3ee16156b31c6a6201f98254079cf58415a7f9c9`) added one — `Chain.BASE_SEPOLIA = "base-sepolia"`,
default RPC `https://sepolia.base.org`, chain ID `84532`, BaseScan Sepolia explorer — plus a
runtime dependency (`cryptography>=41.0.0`). That change shipped inside a PR titled
`feat(examples)` with no version bump and no changelog entry, so the tree silently diverged
from the released tag while still reporting `__version__ = "1.18.4"`.

Version is now bumped to 1.18.5 and the divergence is documented in `CHANGELOG.md`. The patch
below is the isolated core delta from PR #90 for review:

- `docs/review/1.18.5-core-change-base-sepolia.patch`

## The v1 fixture contradiction around P1

The bundled verifier (`verify.mjs`) hardcodes `wakVersion === "1.18.4"` for every case row,
**including P1**, and prints a fixed `compatibilityNote` claiming v1.18.4 lacks Base Sepolia.
But P1 requires a **live Base Sepolia (84532) execution**, which is impossible on the released
1.18.4 tree (the gate rejects chainId 84532). Consequences:

1. P1 as written in the v1 fixture is **unsatisfiable on the released 1.18.4 tree**.
2. Any tree that can execute P1 carries an unreleased core change, so its report will carry
   `wakVersion: "1.18.4"` while running different code — exactly the ambiguity this artifact
   exists to remove.

Resolution to agree with YuTao before any P1 attempt: either re-pin the fixture's P1 identity
(e.g. `wakVersion: "1.18.5"` in a v1.1 fixture) or explicitly bless running P1 on the 1.18.5
tree whose core delta is reviewed above. No transaction is authorized by this document.
