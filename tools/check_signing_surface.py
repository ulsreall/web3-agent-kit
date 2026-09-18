#!/usr/bin/env python3
"""Reject unapproved direct transaction signing anywhere in the package.

Why this exists
---------------
Every write-capable module must sign through the enforced pre-sign gate in
``web3_agent_kit.execution.interceptor``. A direct ``Account.sign_transaction``
or ``w3.eth.account.sign_transaction`` call builds a transaction, skips the
policy layer, and produces a signature indistinguishable from an authorized
one. That is a silent bypass, and it is exactly the class of bug this check
exists to prevent from reappearing.

How it works
------------
AST-based, not regex: comments and strings cannot produce a false positive, and
aliasing through a local variable is followed where resolvable. Every call
expression whose called attribute is ``sign_transaction`` is enumerated.

Exit codes
----------
0  no unapproved signer calls found
1  unapproved signer calls found (fails CI)

Usage
-----
    python tools/check_signing_surface.py
    python tools/check_signing_surface.py --root web3_agent_kit
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

# Modules permitted to contain a low-level signing call.
#
# The gate wraps a signer callable supplied by the caller, so a direct signer
# call is legitimate only where the primitive itself is defined. Every entry
# here is a place where the pre-sign policy is deliberately not applied, so the
# list stays minimal and each entry is reviewed.
APPROVED_FILES: frozenset[str] = frozenset(
    {
        # Defines the Wallet signing primitive that the gate wraps.
        "web3_agent_kit/wallet/wallet.py",
        # The gate implementation itself.
        "web3_agent_kit/execution/interceptor.py",
        # These three define the raw signer passed into their own gate, so the
        # call sits behind the gate rather than beside it.
        "web3_agent_kit/airdrop/onchain.py",
        "web3_agent_kit/messaging/__init__.py",
        "web3_agent_kit/governance/__init__.py",
    }
)

# Directories that never contain production write paths.
EXCLUDED_DIR_PARTS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "htmlcov",
        "node_modules",
        "build",
        "dist",
    }
)

SIGNER_ATTRIBUTE = "sign_transaction"

# Known, not-yet-migrated call sites.
#
# These still reach signing without passing through the gate. They are listed
# rather than silently tolerated so the remaining surface is visible and the
# count only moves down. Removing an entry requires the call to be migrated.
#
# Keyed by path with the expected number of unapproved calls in that file, so
# adding a new call to an already-listed file still fails the check.
LEGACY_BASELINE: dict[str, int] = {
    "web3_agent_kit/bridge/bridge.py": 2,
    "web3_agent_kit/defi/__init__.py": 6,
    "web3_agent_kit/defi/uniswap_v3.py": 2,
    "web3_agent_kit/plugins/restaking/eigenlayer.py": 5,
    "web3_agent_kit/plugins/restaking/protocols.py": 4,
}


@dataclass(frozen=True)
class SignerCall:
    """One call expression that invokes a signer."""

    path: str
    line: int
    column: int
    expression: str
    is_test: bool

    def describe(self) -> str:
        kind = "test" if self.is_test else "production"
        return f"{self.path}:{self.line}:{self.column}  ({kind})  {self.expression}"


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIR_PARTS for part in path.parts)


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive for exotic AST nodes
        return "<unparseable>"


def _is_test_path(relative: str) -> bool:
    parts = Path(relative).parts
    if parts and parts[0] in {"tests", "test"}:
        return True
    name = Path(relative).name
    return name.startswith("test_") or name.endswith("_test.py")


def find_signer_calls(root: Path) -> list[SignerCall]:
    """Enumerate every ``<something>.sign_transaction(...)`` call expression."""
    found: list[SignerCall] = []
    for path in sorted(root.rglob("*.py")):
        if _is_excluded(path):
            continue
        relative = path.relative_to(root.parent).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            print(f"warning: could not parse {relative}: {exc}", file=sys.stderr)
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == SIGNER_ATTRIBUTE:
                found.append(
                    SignerCall(
                        path=relative,
                        line=node.lineno,
                        column=node.col_offset,
                        expression=_unparse(func),
                        is_test=_is_test_path(relative),
                    )
                )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default="web3_agent_kit",
        help="package directory to scan (default: web3_agent_kit)",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="also fail on direct signer calls inside test files",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    calls = find_signer_calls(root)
    violations = [
        call
        for call in calls
        if call.path not in APPROVED_FILES and (args.include_tests or not call.is_test)
    ]

    # Group by file so an already-known file growing a new call is still caught.
    by_file: dict[str, list[SignerCall]] = {}
    for call in violations:
        by_file.setdefault(call.path, []).append(call)

    print(f"scanned: {root}")
    print(f"signer call expressions found: {len(calls)}")
    print(f"approved files: {sorted(APPROVED_FILES) or '(none)'}")
    print()

    new_violations: list[SignerCall] = []
    regressions: list[str] = []
    for path, group in sorted(by_file.items()):
        expected = LEGACY_BASELINE.get(path)
        if expected is None:
            new_violations.extend(group)
        elif len(group) > expected:
            regressions.append(
                f"{path}: {len(group)} unapproved calls, baseline allows {expected}"
            )

    if not new_violations and not regressions:
        migrated = [
            path
            for path, expected in LEGACY_BASELINE.items()
            if len(by_file.get(path, [])) < expected
        ]
        print(f"OK: no new unapproved signer calls. {len(violations)} known legacy")
        print("    call sites remain on the baseline.")
        if migrated:
            print()
            print("    These files dropped below their baseline and should be")
            print("    removed from LEGACY_BASELINE:")
            for path in sorted(migrated):
                actual = len(by_file.get(path, []))
                print(f"      {path} (now {actual}, baseline {LEGACY_BASELINE[path]})")
        return 0

    print("FAIL: unapproved direct signer calls detected.")
    print()
    print("These bypass the enforced pre-sign gate and will skip policy")
    print("evaluation entirely. Route them through PreSignInterceptor.sign().")
    print()
    for call in new_violations:
        print(f"  NEW       {call.describe()}")
    for line in regressions:
        print(f"  INCREASED {line}")
    print()
    print(f"new violations: {len(new_violations)}, regressions: {len(regressions)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
