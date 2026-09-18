"""Regression tests for the signing-surface guard.

The guard exists so the preflight bypass cannot silently come back. These
tests pin its detection behaviour and its fail-closed exit codes.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "check_signing_surface.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("check_signing_surface", TOOL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


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
