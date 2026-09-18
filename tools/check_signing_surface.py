#!/usr/bin/env python3
"""Reject unapproved direct transaction signing anywhere in the package.

Thin wrapper. The check itself lives in
``web3_agent_kit/execution/check_signing_surface.py`` so that it ships inside
the package and is reachable from an installed wheel.

Prefer the packaged entry points:
    python -m web3_agent_kit.execution.check_signing_surface
    wak-signing-surface

Usage (source checkout):
    python tools/check_signing_surface.py
    python tools/check_signing_surface.py --root web3_agent_kit

Exit codes
----------
0  no unapproved signer calls found
1  unapproved signer calls found (fails CI)
2  the scan could not run
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web3_agent_kit.execution.check_signing_surface import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
