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


# Each stamp is anchored to the sentence that carries it, because the same files
# also mention older versions as history and those must not be rewritten.
STAMPS = [
    ("docs/index.md", r'class="docs-eyebrow">.*?v(\d+\.\d+\.\d+)</p>'),
    ("docs/versioning-policy.md", r"\*\*Current version:\*\* v(\d+\.\d+\.\d+)"),
    ("docs/security-model.md", r"\*\*Last updated:\*\* v(\d+\.\d+\.\d+)"),
    ("assets/readme-banner.svg", r">v(\d+\.\d+\.\d+)<"),
    ("assets/readme-banner.svg", r"Web3 Agent Kit v(\d+\.\d+\.\d+)"),
    ("README.md", r"alt=\"Web3 Agent Kit v(\d+\.\d+\.\d+)"),
]


@pytest.mark.parametrize("rel,pattern", STAMPS, ids=[f"{r}:{i}" for i, (r, _) in enumerate(STAMPS)])
def test_every_version_stamp_matches_the_package(rel, pattern):
    match = re.search(pattern, _text(rel))
    assert match, f"no version stamp matched in {rel}"
    assert match.group(1) == VERSION, f"{rel} stamps {match.group(1)}, package is {VERSION}"


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
