"""The published site must not drift from the released version.

release-please bumps ``__init__.py`` and ``pyproject.toml``; the version stamps
scattered across the docs, the README banner and its SVG are edited by hand, so
they silently lag a release. These tests make the build fail instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import web3_agent_kit

ROOT = Path(__file__).resolve().parents[1]
VERSION = web3_agent_kit.__version__


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# No surface may hardcode a release version: release-please owns __version__, and
# a hand-edited stamp in prose silently lagged v1.19.2 by a full release. The
# home page reads the version from PyPI instead, so it cannot go stale.
SURFACES = ["docs/index.md", "assets/readme-banner.svg"]
_VERSION_LITERAL = re.compile(r"\bv\d+\.\d+\.\d+\b")


@pytest.mark.parametrize("rel", SURFACES)
def test_no_surface_hardcodes_a_release_version(rel):
    found = _VERSION_LITERAL.findall(_text(rel))
    assert not found, (
        f"{rel} hardcodes {found}; point at PyPI or the changelog instead so the "
        "value cannot drift from __version__"
    )


def test_the_readme_banner_does_not_hardcode_a_version():
    # The rest of the README legitimately cites contract versions (Safe v1.4.3)
    # and breaking-change ranges (v1.14.0+); only the banner is a release stamp.
    match = re.search(r'alt="Web3 Agent Kit[^"]*"', _text("README.md"))
    assert match, "the README banner alt text is missing"
    found = _VERSION_LITERAL.findall(match.group(0))
    assert not found, f"the README banner hardcodes {found}"


def test_the_risk_register_is_published():
    # It lived at the repo root, outside docs_dir, so the site returned 404.
    assert (ROOT / "docs/risks.md").is_file()
    assert "Risk Register: risks.md" in _text("mkdocs.yml")


def test_no_link_points_at_the_old_risk_register_path():
    for rel in ["README.md", "docs/index.md", "docs/project-maturity.md"]:
        assert "RISKS.md" not in _text(rel), f"{rel} still links the unpublished RISKS.md"


TEST_COUNT_RE = re.compile(r"([\d,]+)\s+tests (?:passing|passed)")
COVERAGE_RE = re.compile(r"(\d+)%\s*coverage|(\d+) percent test coverage")


def _headline_numbers(rel: str) -> tuple[str | None, str | None]:
    text = _text(rel)
    tests = TEST_COUNT_RE.search(text)
    coverage = COVERAGE_RE.search(text)
    return (
        tests.group(1) if tests else None,
        (coverage.group(1) or coverage.group(2)) if coverage else None,
    )


def test_the_headline_numbers_agree_across_surfaces():
    surfaces = ["docs/index.md", "assets/readme-banner.svg", "README.md"]
    pairs = {rel: _headline_numbers(rel) for rel in surfaces}
    tests = {value[0] for value in pairs.values() if value[0]}
    coverage = {value[1] for value in pairs.values() if value[1]}
    assert len(tests) == 1, f"test counts disagree: {pairs}"
    assert len(coverage) == 1, f"coverage figures disagree: {pairs}"
