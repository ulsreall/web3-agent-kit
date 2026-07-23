# Versioning Policy

> **Current version:** v1.15.0

## SemVer Commitment

Web3 Agent Kit follows **Semantic Versioning 2.0.0** (`MAJOR.MINOR.PATCH`).

| Bump | When | Example |
|------|------|---------|
| **MAJOR** | Breaking API change, module removal, data format change | `1.15.0` → `2.0.0` |
| **MINOR** | New feature, new module, new chain, new protocol support | `1.14.0` → `1.15.0` |
| **PATCH** | Bug fix, security fix, documentation, refactoring (no new API surface) | `1.15.0` → `1.15.1` |

## Pre-2.0 Guidelines

While the kit is pre-2.0, the following policy applies:

1. **Minor bumps** may include breaking changes if they fix a security vulnerability or correct an API that was clearly broken (e.g., `honeypot` fail-open → `Optional[bool]`).
2. All breaking changes must be documented in `CHANGELOG.md` with a `### ⚠️ Breaking` heading.
3. No pre-release suffixes (alpha, beta, rc) are used — every release is production-ready.

## Deprecation Process

1. Mark the deprecated API with a `DeprecationWarning` for 2 minor releases
2. Announce in CHANGELOG and ROADMAP
3. Remove in the next MAJOR or MINOR release

## Release Cadence

- **Patch releases:** As needed for bug/security fixes
- **Minor releases:** Every 1–2 weeks during active development
- **Major releases:** Post-2.0, no fixed schedule