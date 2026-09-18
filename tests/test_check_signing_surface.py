"""Regression tests for the signing-surface guard.

The guard exists so the preflight bypass cannot silently come back. These
tests pin its detection behaviour and its fail-closed exit codes.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
# The check lives in the package so it ships in the wheel. tools/ keeps a thin
# wrapper for the source-checkout workflow, covered by
# test_p0_probe_packaging.py.
TOOL_PATH = REPO_ROOT / "web3_agent_kit" / "execution" / "check_signing_surface.py"

from web3_agent_kit.execution import check_signing_surface as tool  # noqa: E402


def _write(package: Path, relative: str, source: str) -> None:
    target = package / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(source), encoding="utf-8")


def test_detects_direct_account_signer(tmp_path: Path):
    package = tmp_path / "pkg"
    _write(
        package,
        "module.py",
        """
        def send(self, tx):
            signed = self._account.sign_transaction(tx)
            return signed
        """,
    )

    calls = tool.find_signer_calls(package)
    assert len(calls) == 1
    assert calls[0].expression == "self._account.sign_transaction"
    assert calls[0].is_test is False


def test_detects_wallet_wrapper_signer(tmp_path: Path):
    package = tmp_path / "pkg"
    _write(
        package,
        "defi/swap.py",
        """
        def swap(wallet, tx):
            return wallet.sign_transaction(tx, chain)
        """,
    )

    calls = tool.find_signer_calls(package)
    assert len(calls) == 1
    assert calls[0].expression == "wallet.sign_transaction"


def test_ignores_comments_and_strings(tmp_path: Path):
    package = tmp_path / "pkg"
    _write(
        package,
        "module.py",
        '''
        # never call account.sign_transaction directly
        DOCS = "use wallet.sign_transaction instead"
        '''
        ,
    )

    assert tool.find_signer_calls(package) == []


def test_attributes_same_name_are_still_detected(tmp_path: Path):
    """A differently named receiver must not hide the signer call."""
    package = tmp_path / "pkg"
    _write(
        package,
        "module.py",
        """
        def go(obj, tx):
            return obj.signer.sign_transaction(tx)
        """,
    )

    calls = tool.find_signer_calls(package)
    assert len(calls) == 1
    assert calls[0].expression == "obj.signer.sign_transaction"


def test_test_paths_are_classified(tmp_path: Path):
    package = tmp_path / "pkg"
    _write(package, "tests/test_thing.py", "a.sign_transaction(b)")
    _write(package, "thing_test.py", "a.sign_transaction(b)")

    calls = tool.find_signer_calls(package)
    assert len(calls) == 2
    assert all(call.is_test for call in calls)


def test_approved_file_is_not_a_violation(tmp_path: Path):
    package = tmp_path / "pkg"
    _write(
        package,
        "execution/interceptor.py",
        """
        def sign(self, tx):
            return self._signer(tx)
        """,
    )
    _write(package, "other.py", "w.sign_transaction(tx)")

    calls = tool.find_signer_calls(package)
    violations = [
        call
        for call in calls
        if call.path not in tool.APPROVED_FILES and not call.is_test
    ]
    assert len(violations) == 1
    assert violations[0].path == "pkg/other.py"


def test_clean_package_exits_zero(tmp_path: Path):
    package = tmp_path / "pkg"
    _write(
        package,
        "module.py",
        """
        from elsewhere import gate


        def send(self, tx):
            return gate.sign(tx)
        """,
    )
    _write(package, "execution/interceptor.py", "def sign(x):\n    return x\n")

    completed = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--root", str(package)],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout
    assert "OK" in completed.stdout


def test_violating_package_exits_nonzero(tmp_path: Path):
    package = tmp_path / "pkg"
    _write(package, "module.py", "signed = account.sign_transaction(tx)")

    completed = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--root", str(package)],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    assert "FAIL" in completed.stdout
    assert "module.py" in completed.stdout


def test_missing_root_exits_with_error(tmp_path: Path):
    completed = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--root", str(tmp_path / "does-not-exist")],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2


def test_virtualenv_is_excluded(tmp_path: Path):
    package = tmp_path / "pkg"
    _write(package, ".venv/lib/module.py", "a.sign_transaction(b)")
    _write(package, "module.py", "b.sign_transaction(c)")

    calls = tool.find_signer_calls(package)
    assert len(calls) == 1
    assert ".venv" not in calls[0].path


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


def _classify(calls, baseline):
    """Reproduce the tool's classification without spawning a subprocess."""
    by_file: dict[str, list] = {}
    for call in calls:
        if call.is_test or call.path in tool.APPROVED_FILES:
            continue
        by_file.setdefault(call.path, []).append(call)

    new = [c for p, g in by_file.items() if p not in baseline for c in g]
    regressions = [
        p for p, g in by_file.items() if p in baseline and len(g) > baseline[p]
    ]
    migrated = [
        p for p, n in baseline.items() if len(by_file.get(p, [])) < n
    ]
    return new, regressions, migrated


def test_new_file_with_signer_is_a_violation(tmp_path: Path):
    """A file absent from the baseline must fail, not be silently allowed."""
    package = tmp_path / "pkg"
    _write(package, "module.py", "account.sign_transaction(tx)")

    new, regressions, _ = _classify(tool.find_signer_calls(package), {})
    assert len(new) == 1
    assert not regressions


def test_baseline_file_growing_a_call_is_a_regression(tmp_path: Path):
    """A baseline entry is a ceiling, not a blanket exemption."""
    package = tmp_path / "pkg"
    _write(package, "bridge/bridge.py", "a.sign_transaction(b)\nc.sign_transaction(d)")

    calls = tool.find_signer_calls(package)
    path = calls[0].path

    new, regressions, _ = _classify(calls, {path: 1})
    assert not new
    assert regressions == [path]


def test_baseline_file_shrinking_is_reported_for_cleanup(tmp_path: Path):
    """Dropping below the baseline passes but asks for the entry to be removed."""
    package = tmp_path / "pkg"
    _write(package, "bridge/bridge.py", "a.sign_transaction(b)")

    calls = tool.find_signer_calls(package)
    path = calls[0].path

    new, regressions, migrated = _classify(calls, {path: 2})
    assert not new
    assert not regressions
    assert migrated == [path]


def test_repo_baseline_is_accurate():
    """The committed baseline must match the actual repository state."""
    package = REPO_ROOT / "web3_agent_kit"
    if not package.is_dir():  # pragma: no cover - repo layout guard
        pytest.skip("package directory not present")

    by_file: dict[str, int] = {}
    for call in tool.find_signer_calls(package):
        if call.is_test or call.path in tool.APPROVED_FILES:
            continue
        by_file[call.path] = by_file.get(call.path, 0) + 1

    assert by_file == tool.LEGACY_BASELINE, (
        "LEGACY_BASELINE is out of date. Migrated a call? Remove its entry. "
        f"Actual: {by_file}"
    )
