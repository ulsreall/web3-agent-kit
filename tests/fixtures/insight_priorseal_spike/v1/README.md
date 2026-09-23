# Web3 Agent Kit / Insight / PriorSeal integration spike conformance bundle v1

This is the YuTao-owned, separately versioned **synthetic input and expected-outcome bundle** from the 2026-09-21 bounded spike specification. It is not a runtime dependency and contains no funded key, API key, production credential, or real broadcast. Its signed Insight attestations and principal authorization use fixed public synthetic keys. The source assessment is labeled Base mainnet (8453); the proposed execution is Base Sepolia (84532), so this is explicitly cross-network advisory evidence.

## Files and ownership

- `fixture/baseline.json`: one synthetic Base Sepolia call, the exact WAK v1.18.4 envelope and policy payloads/digests, three signed Insight attestations (PASS/PASS and signed BLOCK), the positive and BLOCK pair commitments, a signed PriorSeal exact-call authorization, a signed pre-execution acceptance, a versioned PriorSeal response with verification result, and the nine existing WAK `AuthorizationEvidence` fields including `raw`. There is **no execution receipt** in this fixture: no transaction was signed or broadcast.
- `fixture/cases.json`: N1, N2, N3, N4, N5a, N5b and conditional P1 inputs, input artifact SHA-256 values, WAK version, terminal outcomes, stable reason codes, and four expected call counts per case. These are expected values, not observed WAK results.
- `fixture/trust-roots.json`: synthetic public trust pins. Production trust roots must be obtained independently.
- `fixture/manifest.json`: SHA-256 of every other bundled file, including the standalone verifier.
- `verify.mjs`: single-file Node.js verifier bundled with its runtime libraries; no `npm install` or repository checkout is required to run it.

The authoritative source files live in PriorSeal. WAK may vendor an exact copy and pin the **archive SHA-256**. Updating the copy requires a version change and review on both sides. Neither repository imports the other's package.

## Run from a fresh extraction

```sh
node verify.mjs
```

A passing result means the portable files match their manifest, the fixed synthetic Insight signatures and pair commitments verify, the WAK payloads hash to the supplied domain-separated digests, the PriorSeal authorization and acceptance signatures verify, exact-call fields and validity windows match, and each case vector is internally consistent. It reports `wakAcceptance: NOT_RUN` until a separate WAK report is provided. **It does not prove WAK enforcement, durable replay prevention, receipt generation, or P1.**

To check a WAK-generated report, run:

```sh
node verify.mjs --report /path/to/wak-acceptance-report.json
```

The report must use `wak-insight-priorseal.acceptance-report.v1` and include `fixtureVersion: "v1"`, the baseline envelope/policy digests, `instrumentation.explicitSignerProtocol = true`, `instrumentation.explicitBroadcastFn = true`, `adapter.newFieldTypes = 0`, a separate `adapterAcceptance` row with `expectedNewFieldTypes = 0`, `actualNewFieldTypes = 0`, `terminal = "PASS"`, and ordered `cases` for N1-N5b. Each case must record `id`, `wakVersion`, `inputArtifactHashes`, `expectedTerminal`, `actualTerminal`, `reason`, and `counts` (`authorizationProvider`, `signer`, `broadcast`, `receipt`). For N1-N5b, the input hashes must equal the per-case fixture values and the terminal outcomes and counters must match their expected values. N5b also needs `reconstruction.differentProviderInstance = true` and `reconstruction.samePersistedAcceptanceId = true`. This validates reported evidence fields; source review of the WAK-owned example/tests is still required to prove that the counters actually sit at the boundaries.

P1 is conditional on all negative cases. Its report row must include a fresh `inputArtifactHashes.liveInputSha256`; a report that includes P1 must also include `p1.receipt`, `p1.trustedKey`, `p1.wak.envelopeDigest`, `p1.wak.policyCommitmentDigest`, and `p1.insightPairCommitment`, and the verifier must be invoked with an independently obtained `--trust-key-sha256` fingerprint. The verifier checks the PriorSeal receipt signature, exact commitments, Base Sepolia chain and compliance status. Independent RPC verification of the public transaction is still a separate acceptance step.

## Known WAK v1.18.4 compatibility finding

In the reviewed WAK v1.18.4 source, `Chain` has `BASE` (8453) but no Base Sepolia member. `AuthorizationRequest.envelope()` calls `CallEnvelopeV1.from_transaction()`, which rejects a transaction whose `chainId` differs from the selected `Chain` mapping. Therefore the current WAK gate cannot pass a Base Sepolia (84532) transaction as this specification requires. The fixture uses 84532 to preserve the agreed testnet scope and reports this gap; it does **not** bypass or patch the WAK gate. The WAK owner and YuTao must align on the necessary file split before any WAK core change or P1 attempt.

## Rebuild from PriorSeal source

```sh
node scripts/generate-web3-agent-kit-integration-spike-v1.mjs
node scripts/build-web3-agent-kit-integration-spike-v1.mjs
node examples/web3-agent-kit-integration-spike-v1/verify.mjs
python3 scripts/package-web3-agent-kit-integration-spike-v1.py
```

The two confirmed amendments are represented directly: structural `SignerProtocol`/`BroadcastFn` observability and `adapter.newFieldTypes = 0`. The original v1 PDF remains untouched; this fixture does not claim that WAK has implemented those changes.
