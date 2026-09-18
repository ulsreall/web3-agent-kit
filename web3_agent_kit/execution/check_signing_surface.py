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

Why it lives inside the package
------------------------------
An earlier attempt shipped this as ``tools/check_signing_surface.py`` and
referenced it from a verification bundle. ``tools/`` is not packaged, so the
check was unreachable from an installed wheel. It lives here now, with a thin
wrapper left in ``tools/`` for the source-checkout workflow and a console entry
point for installed use.

Usage
-----
    python -m web3_agent_kit.execution.check_signing_surface
    wak-signing-surface
    python tools/check_signing_surface.py          # source checkout
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

# Modules permitted to contain a low-level signing call.
#
# Being on this list means "the check should not flag calls here", which covers
# two different situations. Both are listed explicitly, because an approval with
# no stated reason is indistinguishable from an oversight:
#
#   DEFINES  -- the module owns the signing primitive the gate wraps.
#   EXERCISES -- the module calls the signing API deliberately, to test that it
#                refuses. These are not sign sites; flagging them would train
#                reviewers to add exemptions without reading them.
APPROVED_FILES: frozenset[str] = frozenset(
    {
        # DEFINES: the Wallet signing primitive that the gate wraps.
        "web3_agent_kit/wallet/wallet.py",
        # DEFINES: the gate implementation itself.
        "web3_agent_kit/execution/interceptor.py",
        # DEFINES: these three build the raw signer passed into their own gate,
        # so the call sits behind the gate rather than beside it.
        "web3_agent_kit/airdrop/onchain.py",
        "web3_agent_kit/messaging/__init__.py",
        "web3_agent_kit/governance/__init__.py",
        # EXERCISES: the P0 probe asserts that an unbound wallet refuses to
        # sign. Its call is the test, not a signature. The probe resolves the
        # attribute dynamically for the same reason.
        "web3_agent_kit/execution/p0_probe.py",
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


def _report_path(path: Path, root: Path) -> str:
    """Return the path as it should appear in the report.

    Relative to the scanned root's parent when that is a repository, so the
    output matches the paths in APPROVED_FILES and LEGACY_BASELINE. Falls back
    to the path relative to the root when the parent is unrelated, which is what
    happens with an installed package -- ``site-packages/web3_agent_kit`` has no
    meaningful parent name to strip.
    """
    try:
        return path.relative_to(root.parent).as_posix()
    except ValueError:
        return f"{root.name}/{path.relative_to(root).as_posix()}"


def _is_test_path(relative: str) -> bool:
    parts = Path(relative).parts
    if parts and parts[0] in {"tests", "test"}:
        return True
    name = Path(relative).name
    return name.startswith("test_") or name.endswith("_test.py")


def find_signer_calls(root: Path) -> list[SignerCall]:
    """Enumerate every call expression that reaches a signer.

    Two shapes are detected:

    1. Direct attribute calls -- ``account.sign_transaction(tx)``.
    2. Aliased calls -- ``signer = account.sign_transaction; signer(tx)``.

    The second shape is not a theoretical concern. Binding the bound method to a
    local and calling it through that name evades a check that only looks at
    attribute access, and the resulting signature is identical. Aliases are
    resolved within a module scope: a name assigned from a ``.sign_transaction``
    attribute, or from another name already known to be an alias, is tracked and
    any later call through it is reported.
    """
    found: list[SignerCall] = []
    for path in sorted(root.rglob("*.py")):
        if _is_excluded(path):
            continue
        relative = _report_path(path, root)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            print(f"warning: could not parse {relative}: {exc}", file=sys.stderr)
            continue

        aliases = _collect_signer_aliases(tree, relative, found)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func

            # Shape 1: <something>.sign_transaction(...)
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
                continue

            # Shape 2: <alias>(...) where <alias> was bound to a signer method
            if isinstance(func, ast.Name) and func.id in aliases:
                found.append(
                    SignerCall(
                        path=relative,
                        line=node.lineno,
                        column=node.col_offset,
                        expression=f"{_unparse(func)}(...)  [aliased from "
                        f"{aliases[func.id]}]",
                        is_test=_is_test_path(relative),
                    )
                )
    return found


def _collect_signer_aliases(
    tree: ast.AST, relative: str, found: list[SignerCall]
) -> dict[str, str]:
    """Return ``{local_name: origin}`` for names bound to a signer method.

    Only module-level and function-level assignments are considered. Names are
    resolved transitively so ``a = account.sign_transaction; b = a; b(tx)`` is
    still caught. Aliases created through attribute access on a module (for
    example ``from x import sign_transaction as st``) are also recorded, with
    their origin recorded so the report is readable.
    """
    aliases: dict[str, str] = {}

    def origin_of(node: ast.AST) -> str | None:
        """Return a description if ``node`` resolves to a signer callable."""
        if isinstance(node, ast.Attribute) and node.attr == SIGNER_ATTRIBUTE:
            return _unparse(node)
        if isinstance(node, ast.Name) and node.id in aliases:
            return aliases[node.id]
        return None

    # Repeated passes so a chain of aliases in any order still resolves.
    for _ in range(3):
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                resolved = origin_of(node.value)
                if resolved is None:
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name) and aliases.get(target.id) != resolved:
                        aliases[target.id] = resolved
                        changed = True
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                resolved = origin_of(node.value)
                if resolved is not None and isinstance(node.target, ast.Name):
                    if aliases.get(node.target.id) != resolved:
                        aliases[node.target.id] = resolved
                        changed = True
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == SIGNER_ATTRIBUTE:
                        local = alias.asname or alias.name
                        resolved = f"{node.module}.{SIGNER_ATTRIBUTE}"
                        if aliases.get(local) != resolved:
                            aliases[local] = resolved
                            changed = True
        if not changed:
            break

    return aliases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--root",
        default=str(default_root),
        help=(
            "package directory to scan (default: the installed "
            "web3_agent_kit package)"
        ),
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
