"""Run the WAK / Insight / PriorSeal P1 leg with live execution boundaries.

Default mode is **dry-run**: GO and cutoff checks plus a read-only RPC preflight are
performed and a plan report is written; nothing is signed and nothing is broadcast.
Broadcast mode requires ``--allow-broadcast`` AND a validated GO file, and even then it
signs once, broadcasts once, and waits for confirmations. No transaction is authorized by
running this script.

Usage (dry-run):

    python examples/insight_priorseal_live_p1.py \\
        --fixture tests/fixtures/insight_priorseal_spike/v1 \\
        --report /tmp/p1-plan.json \\
        --go-file /path/to/go.json \\
        --rpc-url https://sepolia.base.org \\
        --signer-env P1_SIGNER_PRIVATE_KEY \\
        --run-sheet /path/to/run-sheet.json

GO file schema (``wak-p1.go-file.v1``): ``latestBroadcastAt`` (epoch), ``runSheetSha256``,
``receiverFloorSeconds`` (default 120), and either ``goArrivalEpoch`` directly or
``sessionDb`` + ``goMessageId`` to read the real delivery timestamp from the session store.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping

try:
    from examples.insight_priorseal_swap import (
        BoundaryError,
        FixtureBundle,
        _run_gate_attempt,
    )
except ModuleNotFoundError:  # running as examples/insight_priorseal_live_p1.py
    from insight_priorseal_swap import (
        BoundaryError,
        FixtureBundle,
        _run_gate_attempt,
    )
from web3_agent_kit.execution import EnforcementDenied

try:
    from examples.support.go_arrival import (
        query_go_messages,
        resolve_go_arrival,
    )
    from examples.support.insight_priorseal_live import (
        CallEventRecorder,
        EvmSigner,
        LiveRunConfig,
        RpcBroadcast,
        RpcReceipt,
        check_cutoff,
        check_go_arrival,
        live_execution_boundaries,
        runtime_provenance,
        version_alignment,
    )
except ModuleNotFoundError:  # running from a different cwd
    from support.go_arrival import (
        query_go_messages,
        resolve_go_arrival,
    )
    from support.insight_priorseal_live import (
        CallEventRecorder,
        EvmSigner,
        LiveRunConfig,
        RpcBroadcast,
        RpcReceipt,
        check_cutoff,
        check_go_arrival,
        live_execution_boundaries,
        runtime_provenance,
        version_alignment,
    )


def _jsonrpc(rpc_url: str, method: str, params: list[Any], *, timeout: float) -> Any:
    import httpx

    resp = httpx.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"{method} RPC error: {body['error']}")
    return body["result"]


def load_go_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise BoundaryError("GO file must be a JSON object")
    for field in ("latestBroadcastAt", "runSheetSha256"):
        if field not in data:
            raise BoundaryError(f"GO file is missing '{field}'")
    return dict(data)


def preflight(config: LiveRunConfig, signer: EvmSigner) -> dict[str, Any]:
    chain_id = int(str(_jsonrpc(config.rpc_url, "eth_chainId", [], timeout=20)), 16)
    if chain_id != config.chain_id:
        raise RuntimeError(f"RPC chainId {chain_id} != configured {config.chain_id}")
    block = int(str(_jsonrpc(config.rpc_url, "eth_blockNumber", [], timeout=20)), 16)
    nonce = int(str(_jsonrpc(config.rpc_url, "eth_getTransactionCount", [signer.address(), "pending"], timeout=20)), 16)
    balance = int(str(_jsonrpc(config.rpc_url, "eth_getBalance", [signer.address(), "latest"], timeout=20)), 16)
    return {"chainId": chain_id, "headBlock": block, "pendingNonce": nonce, "balanceWei": balance}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--go-file", required=True, type=Path)
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--signer-env", required=True)
    parser.add_argument("--run-sheet", type=Path, default=None)
    parser.add_argument("--session-db", type=Path, default=None)
    parser.add_argument("--go-message-id", type=int, default=None)
    parser.add_argument("--allow-broadcast", action="store_true")
    parser.add_argument("--chain-id", type=int, default=84532)
    parser.add_argument("--cutoff-check-seconds", type=int, default=60)
    parser.add_argument("--confirmations", type=int, default=2)
    parser.add_argument("--receipt-timeout", type=int, default=180)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()

    go = load_go_file(args.go_file)
    go_arrival_epoch: int | None = go.get("goArrivalEpoch")
    arrival_metadata: dict[str, Any] | None = None
    if args.session_db is not None and args.go_message_id is not None:
        rows = query_go_messages(args.session_db, message_id=args.go_message_id, role="user")
        arrival_metadata = dict(resolve_go_arrival(rows))
        go_arrival_epoch = int(arrival_metadata.get("deliveryTimestampEpoch", 0))
    if go_arrival_epoch is None:
        raise BoundaryError("GO file must carry goArrivalEpoch or session-db/go-message-id must be provided")

    config = LiveRunConfig(
        rpc_url=args.rpc_url,
        chain_id=args.chain_id,
        latest_broadcast_at=int(go["latestBroadcastAt"]),
        run_sheet_sha256=str(go["runSheetSha256"]),
        go_arrival_epoch=go_arrival_epoch,
        receiver_floor_seconds=int(go.get("receiverFloorSeconds", 120)),
        margin_seconds=int(go.get("marginSeconds", 180)),
        confirmations=args.confirmations,
        receipt_timeout_seconds=args.receipt_timeout,
        broadcast_poll_seconds=args.poll_seconds,
    )

    go_runway = check_go_arrival(config)
    now_runway = check_cutoff(
        now_epoch=int(time.time()),
        latest_broadcast_at=config.latest_broadcast_at,
        minimum_seconds=args.cutoff_check_seconds,
    )

    key = os.environ.get(args.signer_env)
    if not key:
        raise BoundaryError(f"signer key environment {args.signer_env} is not set")
    import eth_account

    account = eth_account.Account.from_key(key)
    signer = EvmSigner(account)
    plan = preflight(config, signer)

    recorder = CallEventRecorder()
    boundaries = live_execution_boundaries(
        recorder=recorder,
        signer=signer,
        broadcast=RpcBroadcast(config.rpc_url),
        receipt=RpcReceipt(
            config.rpc_url,
            confirmations=config.confirmations,
            timeout=config.receipt_timeout_seconds,
            poll_seconds=config.broadcast_poll_seconds,
        ),
        config=config,
        cutoff_check_seconds=args.cutoff_check_seconds,
    )

    bundle = FixtureBundle.load(args.fixture)
    transaction = dict(bundle.baseline["transaction"])
    transaction["chainId"] = int(transaction["chainId"])
    transaction["from"] = signer.address()

    run_sheet_hash: str | None = None
    if args.run_sheet is not None:
        sheet = json.loads(args.run_sheet.read_text(encoding="utf-8"))
        import hashlib

        raw = args.run_sheet.read_bytes()
        run_sheet_hash = hashlib.sha256(raw).hexdigest()
        if run_sheet_hash != config.run_sheet_sha256:
            raise BoundaryError("run sheet SHA-256 does not match the GO file pin")
        sheet_tx = sheet.get("transaction") if isinstance(sheet, Mapping) else None
        if isinstance(sheet_tx, Mapping):
            transaction = dict(sheet_tx)
            transaction["chainId"] = int(transaction["chainId"])
            transaction["from"] = signer.address()

    from web3_agent_kit import __version__

    evidence: dict[str, Any] = {
        "schema": "wak-p1.execution-evidence.v1",
        "goArrival": arrival_metadata or {
            "schema": "wak-p1.go-arrival-metadata.v1",
            "source": "go-file (explicit goArrivalEpoch)",
            "goArrivalEpoch": go_arrival_epoch,
        },
        "goArrivalRunwaySeconds": go_runway,
        "runwayAtCheckSeconds": now_runway,
        "receiverFloorSeconds": config.receiver_floor_seconds,
        "cutoffCheckSeconds": args.cutoff_check_seconds,
        "preflight": plan,
        "signerAddress": signer.address(),
        "runSheetSha256": run_sheet_hash,
        "transaction": {k: v for k, v in transaction.items() if k != "from"},
        "runtime": runtime_provenance(package_version=__version__, commit=None, tree_clean=None),
        "versionAlignment": version_alignment(
            fixture_wak_version="1.18.4",
            runtime_package_version=__version__,
        ),
        "callEvents": recorder.as_report(),
        "signed": False,
        "broadcast": False,
    }

    if args.allow_broadcast:
        try:
            _ = _run_gate_attempt(
                transaction=transaction,
                response=bundle.baseline["priorSeal"]["response"],
                trust_roots=bundle.trust_roots,
                counters=recorder.counts(),  # type: ignore[arg-type]
                now=int(time.time()),
                acceptance_store=None,
                boundaries=boundaries,
            )
        except EnforcementDenied as exc:
            evidence["outcome"] = f"ENFORCEMENT_DENIED: {exc}"
        evidence["signed"] = True
        evidence["broadcast"] = True
        evidence["outcome"] = "LIVE_LEG_COMPLETED"
    else:
        evidence["outcome"] = "DRY_RUN_NO_TRANSACTION"
        evidence["note"] = "GO and cutoff checks passed; no transaction signed or broadcast (dry-run)."

    destination = args.report
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(destination)
    return 0


if __name__ == "__main__":
    sys.exit(main())
