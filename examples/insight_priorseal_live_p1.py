"""Run the WAK / Insight / PriorSeal P1 leg through the canonical entry point.

This is a thin CLI over ``examples/insight_priorseal_swap.py`` (``run_live_p1``), which
owns the live SignerProtocol / BroadcastFn / ReceiptFn wiring, the GO-to-sheet binding,
session-store GO arrival, live clock, cutoff rechecks, call-event retention, and
counters derived from actual results. Default mode is **dry-run**; broadcast requires
``--allow-broadcast`` AND a validated GO file AND an exact run sheet. ``--rehearsal``
runs the same runner path with inert broadcast/receipt boundaries and no on-chain
effect.

Usage (dry-run):

    python examples/insight_priorseal_live_p1.py \\
        --fixture tests/fixtures/insight_priorseal_spike/v1.1 \\
        --report /tmp/p1-plan.json \\
        --go-file /path/to/go.json \\
        --rpc-url https://sepolia.base.org \\
        --signer-env P1_SIGNER_PRIVATE_KEY \\
        --run-sheet /path/to/run-sheet.json \\
        --session-db /root/.hermes/state.db --go-message-id 4001

GO file schema (``wak-p1.go-file.v1``): ``latestBroadcastAt`` (epoch), ``runSheetSha256``,
``receiverFloorSeconds`` (default 120), ``marginSeconds`` (default 180). Executing runs
read GO arrival from the session store (``--session-db`` + ``--go-message-id``), never
from a ``goArrivalEpoch`` inside the file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from examples.insight_priorseal_swap import run_live_p1
except ModuleNotFoundError:  # running as examples/insight_priorseal_live_p1.py
    from insight_priorseal_swap import run_live_p1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--go-file", required=True, type=Path)
    parser.add_argument("--run-sheet", type=Path, default=None)
    parser.add_argument("--rpc-url", default=None)
    parser.add_argument("--signer-env", default=None)
    parser.add_argument("--session-db", type=Path, default=None)
    parser.add_argument("--go-message-id", type=int, default=None)
    parser.add_argument("--allow-broadcast", action="store_true")
    parser.add_argument("--rehearsal", action="store_true")
    parser.add_argument("--rehearsal-output-dir", type=Path, default=None)
    parser.add_argument("--chain-id", type=int, default=84532)
    parser.add_argument("--cutoff-check-seconds", type=int, default=60)
    parser.add_argument("--confirmations", type=int, default=2)
    parser.add_argument("--receipt-timeout", type=int, default=180)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--wak-commit", default=None)
    parser.add_argument("--call-events", type=Path, default=None)
    args = parser.parse_args()

    evidence = run_live_p1(
        fixture_root=args.fixture,
        report=args.report,
        go_file=args.go_file,
        run_sheet=args.run_sheet,
        session_db=args.session_db,
        go_message_id=args.go_message_id,
        rpc_url=args.rpc_url,
        signer_env=args.signer_env,
        chain_id=args.chain_id,
        allow_broadcast=args.allow_broadcast,
        rehearsal=args.rehearsal,
        rehearsal_output_dir=args.rehearsal_output_dir,
        cutoff_check_seconds=args.cutoff_check_seconds,
        confirmations=args.confirmations,
        receipt_timeout=args.receipt_timeout,
        poll_seconds=args.poll_seconds,
        wak_commit=args.wak_commit,
        call_events=args.call_events,
    )
    print(json.dumps({"report": str(args.report), "outcome": evidence.get("outcome"), "counts": evidence.get("counts")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
