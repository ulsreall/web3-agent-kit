"""Tests that the P0 probe is reachable from an installed package.

The evidence bundle told readers to run the probe from the wheel. That was
false: ``pyproject.toml`` included only ``web3_agent_kit*``, so ``tools/``
shipped in neither the wheel nor the sdist, and the verification instruction
could not be followed. The probe now lives in the package.

These tests pin the reachability so the claim cannot go stale again. They assert
the *packaging* property, not just that the module imports -- an import test in
a source checkout passes even when the module is absent from the distribution,
which is exactly how the original claim survived review.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
PROBE_MODULE = "web3_agent_kit/execution/p0_probe.py"


def test_package_include_covers_the_probe_module() -> None:
    """The probe must live under a path the packaging config includes."""
    with PYPROJECT.open("rb") as handle:
        config = tomllib.load(handle)

    include = config["tool"]["setuptools"]["packages"]["find"]["include"]
    assert "web3_agent_kit*" in include

    # And the probe must actually be under that prefix.
    assert PROBE_MODULE.startswith("web3_agent_kit/")
    assert (REPO_ROOT / PROBE_MODULE).is_file()


def test_probe_has_a_console_entry_point() -> None:
    with PYPROJECT.open("rb") as handle:
        config = tomllib.load(handle)

    scripts = config["project"]["scripts"]
    assert "wak-p0-probe" in scripts
    assert scripts["wak-p0-probe"] == "web3_agent_kit.execution.p0_probe:main"


def test_signing_surface_check_is_packaged_too() -> None:
    """The check the probe delegates to must also ship in the package."""
    checker = REPO_ROOT / "web3_agent_kit/execution/check_signing_surface.py"
    assert checker.is_file()

    with PYPROJECT.open("rb") as handle:
        config = tomllib.load(handle)

    scripts = config["project"]["scripts"]
    assert scripts["wak-signing-surface"] == (
        "web3_agent_kit.execution.check_signing_surface:main"
    )


def test_signing_surface_check_runs_from_the_package() -> None:
    """Default --root must resolve inside the installed package, not the cwd."""
    from web3_agent_kit.execution import check_signing_surface

    assert check_signing_surface.main(["--root", str(REPO_ROOT / "web3_agent_kit")]) == 0


def test_checker_reports_paths_relative_to_a_repository_root() -> None:
    """Labels in the report must match the names used in APPROVED_FILES.

    The installed package's parent is site-packages, which would produce
    meaningless labels, so the checker falls back to the package name. In a
    repository checkout the label must be the repo-relative path.
    """
    from web3_agent_kit.execution.check_signing_surface import _report_path

    root = REPO_ROOT / "web3_agent_kit"
    target = root / "wallet" / "wallet.py"
    assert _report_path(target, root) == "web3_agent_kit/wallet/wallet.py"

    installed_like = Path("/usr/lib/python3/site-packages/web3_agent_kit")
    assert (
        _report_path(installed_like / "wallet" / "wallet.py", installed_like)
        == "web3_agent_kit/wallet/wallet.py"
    )


def test_probe_is_importable_from_the_package() -> None:
    from web3_agent_kit.execution import run_all_probes

    results = run_all_probes()
    ids = {r["id"] for r in results}
    assert ids == {
        "CHAIN_MISMATCH_SIGNED",
        "UNBOUND_CONTRACT_CREATION_SIGNED",
        "POLICY_ALLOW_SIGNS_WITHOUT_AUTHORIZATION",
        "ALIASED_SIGNER_ESCAPES_CHECKER",
    }


def test_probe_module_runs_via_dash_m() -> None:
    """The documented invocation must work without a source checkout."""
    proc = subprocess.run(
        [sys.executable, "-m", "web3_agent_kit.execution.p0_probe", "--json"],
        capture_output=True,
        text=True,
        cwd="/tmp",  # away from the repo, so only the installed package resolves
    )
    assert proc.returncode in {0, 1, 2}, proc.stderr
    assert '"results"' in proc.stdout


def test_built_wheel_contains_the_probe(tmp_path: Path) -> None:
    """Build a wheel and confirm the probe is inside it.

    This is the assertion that would have caught the original bad claim. It
    inspects the distribution rather than the working tree.
    """
    build = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if build.returncode != 0:
        pytest.skip(f"`python -m build` unavailable or failed: {build.stderr[-200:]}")

    wheels = list(tmp_path.glob("*.whl"))
    assert wheels, "no wheel produced"

    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()

    for module in (PROBE_MODULE, "web3_agent_kit/execution/check_signing_surface.py"):
        assert module in names, (
            f"{module} is not in the built wheel. It would be unreachable from "
            "an installed package, which is the packaging bug this test exists "
            "to prevent."
        )


def test_probe_exit_code_treats_unknown_as_not_a_pass() -> None:
    """A probe that cannot evaluate must not report success.

    If the static checker is missing, the alias probe returns UNKNOWN. That must
    not be counted as a closed gap, or a missing file would look like a fix.
    """
    from web3_agent_kit.execution import p0_probe

    assert p0_probe._status({"observed": None, "expected": False}) == "UNKNOWN"

    # And main() must refuse to exit 0 when anything is unknown.
    original = p0_probe.run_all_probes
    try:
        p0_probe.run_all_probes = lambda: [
            {"id": "X", "status": "UNKNOWN", "observed": None, "detail": "n/a"}
        ]
        assert p0_probe.main(["--json"]) == 2
    finally:
        p0_probe.run_all_probes = original
