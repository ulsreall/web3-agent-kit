# Governance

> **Last updated:** v1.15.0 (2026-07-23)

## Maintainers

Currently a single-maintainer project:

- **Khasbi Maulana** ([@ulsreall](https://github.com/ulsreall)) — creator and primary maintainer

## Bus Factor

Bus factor is **1**. This is a known risk. Mitigations in place:
- Full CI/CD pipeline (tests, lint, coverage) ensures regressions are caught automatically
- All security-relevant decisions documented in ADRs (`docs/adr/`)
- Public ROADMAP.md so community can see direction
- Good-first-issue labels to encourage contributors

## Decision Process

| Scope | Decision by | Notes |
|-------|-------------|-------|
| Day-to-day code changes | Maintainer | PR review + CI green |
| Breaking API changes | Maintainer + Issue discussion | Must announce in Discussions before PR |
| New module / chain addition | Maintainer | Should open issue for feedback first |
| Security vulnerability fix | Maintainer (private) | Disclosed via SECURITY.md process |
| Ownership transfer | Maintainer + Community | Requires 2+ weeks public notice |

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for technical setup, and `good first issue` labels on GitHub Issues for beginner-friendly tasks.

## Communication

- **Bug reports / security issues:** [SECURITY.md](./SECURITY.md)
- **Feature requests / ideas:** GitHub Discussions (Ideas category)
- **Questions:** GitHub Discussions (Q&A category)
- **Direct:** Create an issue for maintainer attention

## Code of Conduct

All contributors must follow the [Code of Conduct](./CODE_OF_CONDUCT.md).