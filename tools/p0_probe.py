#!/usr/bin/env python3
"""Reproduce the three P0 findings against a given revision.

Thin wrapper. The probe itself lives in
``web3_agent_kit/execution/p0_probe.py`` so that it ships inside the package
and is reachable from an installed wheel. This file exists for the
source-checkout workflow, where ``tools/`` is on hand and the probe may need to
run against a revision whose installed package differs.

Prefer the packaged entry points:
    python -m web3_agent_kit.execution.p0_probe
    wak-p0-probe

Run it on the pre-fix revision to see the gaps open, and on the fixed revision
to see them closed.

Usage:
    python tools/p0_probe.py                 # probe the working tree
    python tools/p0_probe.py --json          # machine-readable output

Exit code is 0 when every gap is closed, 1 when at least one is still open, and
2 when a probe could not be evaluated. An unknown result is never a pass: a
missing checker or an import failure must not read as a closed gap.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web3_agent_kit.execution.p0_probe import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
