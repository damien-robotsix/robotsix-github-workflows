# Contributing

## Prerequisites

- Python 3.x with `pip`
- `pytest` (installed automatically by `make pytest`)
- `bash`
- Optional: `uv` — a faster Python package manager (the Makefile targets use `pip` by default)

## Running tests

Run all test suites:

```bash
make test
```

Or run individual suites:

```bash
make pytest        # Python/pytest tests only
make shell-tests   # shell script tests only
```

The Python test suite covers:

| Test file | What it covers |
|---|---|
| `tests/test-pin-bump.py` | `scripts/pin-bump.py` |
| `tests/test-lint-sarif-permissions.py` | `scripts/lint_sarif_permissions.py` |

The shell test suite covers:

| Test file | What it covers |
|---|---|
| `tests/test-apply-branch-protection.sh` | `scripts/apply-branch-protection.sh` |
| `tests/test-config-ownership-check.sh` | `scripts/config_ownership_check.py` |
| `tests/test-baseline-check.sh` | `.github/workflows/baseline-check.yml` |

## Adding a new test

- **Python tests:** place them in `tests/test_*.py`. Import or reference
  production scripts from `scripts/`. Use existing fixtures under
  `tests/fixtures/` where applicable.
- **Shell tests:** place them in `tests/test-*.sh`. Follow the existing
  pattern: use `set -euo pipefail`, create temporary directories with
  `mktemp -d`, and clean up via `trap`.

## Linting

Run all pre-commit hooks:

```bash
make lint
```

This executes:

- **actionlint** — validates GitHub Actions workflow YAML
- **yamllint** — general YAML style checks
- **shellcheck** — static analysis for shell scripts

## Workflow validation

When making changes to `.github/workflows/*.yml`, validate locally:

- `make lint` runs actionlint and yamllint across all workflow files.
- Consider running `zizmor` for additional security audit of workflow
  definitions.

## Pull request process

This repo is part of the [robotsix standards](https://github.com/damien-robotsix/robotsix-standards)
fleet. All PRs must pass:

- Pre-commit hooks (actionlint, yamllint, shellcheck)
- Fleet CI expectations as defined in the
  [standards](https://github.com/damien-robotsix/robotsix-standards)

See the companion `AGENT.md` for repo-specific rules for all contributors.
