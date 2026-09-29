# Web3 Agent Kit / Insight / PriorSeal conformance bundle v1.1

This is a new, separately versioned synthetic conformance fixture for the proposed WAK runtime P1 on Base Sepolia. It corrects the executable version identity: **all N1–N5b and conditional P1 rows pin WAK 1.18.5**. The v1 and v1.0.1 bundles remain immutable historical artifacts. Re-run N1–N5b on the reviewed 1.18.5 tree before reporting a new P1; do not copy their earlier 1.18.4 outcomes into a new runtime report.

The synthetic baseline, case inputs, expected outcomes, digests, namespaces, signatures and trust roots are unchanged from v1.0.1. Only the case version pins, bundle identity, verifier checks and this explanation change. The fixture contains no funded key, API credential or real broadcast. Insight's synthetic source assessment is labeled Base mainnet (8453); proposed execution is Base Sepolia (84532).

## Files and ownership

- `fixture/baseline.json`: synthetic exact call, signed Insight and PriorSeal inputs, WAK envelope and policy digests, and public synthetic trust material. It contains no execution receipt.
- `fixture/cases.json`: N1–N5b and conditional P1 inputs and expected outcomes, all with `wakVersion: "1.18.5"`.
- `fixture/trust-roots.json`: synthetic public pins, not production trust roots.
- `fixture/manifest.json`: SHA-256 of each other bundled file.
- `verify.mjs`: standalone Node.js verifier. No repository checkout or npm install is needed to run the extracted bundle.

The authoritative source is in PriorSeal. WAK may vendor the exact archive and pin its SHA-256. Changing the copy requires another version and review; neither repository imports the other's package.

## Verification

Run `node verify.mjs` from a fresh extraction. A PASS validates only the fixture's files, synthetic signatures, commitments and expected-case consistency; it reports `wakAcceptance: NOT_RUN` until a WAK report is supplied.

Run `node verify.mjs --report /path/to/report.json` for an N1–N5b report. The report must use `wak-insight-priorseal.acceptance-report.v1`, `fixtureVersion: "v1.1"`, and the established ordered cases, boundary counts, adapter `newFieldTypes: 0`, and durable N5b reconstruction fields. The verifier checks these reported fields; source review is still needed to establish that the actual WAK boundaries generated them.

For P1, also pass `--trust-key-sha256` with a fingerprint obtained independently of the bundle and `--wak-commit` with the full independently reviewed WAK commit SHA. The P1 row must identify WAK 1.18.5 and a fresh raw run-sheet SHA-256. `runtime.packageVersion` must be `1.18.5`, `runtime.commit` must match `--wak-commit`, `runtime.treeClean` must be true, and `versionAlignment` must be true for 1.18.5. The receipt must verify against the pinned key and exact commitments. A report PASS alone does **not** prove that the reviewed commit ran, that a real session-store GO arrived, that both cutoff checks occurred, that call events were retained, or that the transaction is canonical. Review the execution log and exact source, then independently recheck the chain before countersigning.

The new P1 requires a fresh frozen run sheet, fresh signed inputs, a new package-specific GO and a validated GO file. Attempt 9 stays closed. Never use the synthetic fixture authorization or the attempt-9 receipt as authorization or proof for a new transaction. Nothing in this bundle authorizes signing or broadcast.

## Rebuild from PriorSeal source

```sh
npm run core:build
node scripts/build-web3-agent-kit-integration-spike-v1.1.mjs
node examples/web3-agent-kit-integration-spike-v1.1/verify.mjs
node scripts/package-web3-agent-kit-integration-spike-v1.mjs --version v1.1 --output /tmp/wak-conformance-v1.1.zip
```
