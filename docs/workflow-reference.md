# Workflow Reference

Consolidated input, default, and secret reference for all reusable workflows in
this repository.

## `auto-release.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `app-id` | string | — | GitHub App ID for release authentication. |
| `python-version` | string | `3.14` | Python version for the release job. |
| `uv-version` | string | `0.8.15` | uv version for the release job. |

| Secret | Required | Description |
|---|---|---|
| `app-private-key` | yes | GitHub App private key for token minting. |

## `baseline-check.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `has-docker` | boolean | `false` | Require `package-ecosystem: docker` in dependabot.yml. |
| `has-board` | boolean | `false` | Enable modules-drift job (robotsix board). |
| `python-version` | string | `3.14` | Python version for the modules-drift job. |
| `uv-version` | string | `0.8.15` | uv version for the modules-drift job. |

## `changelog-check.yml`

No inputs.  No secrets.

## `codeql.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `languages` | string | `python` | Languages to analyze. |
| `queries` | string | `security-and-quality` | Query suite. |
| `config-file` | string | `.github/codeql/codeql-config.yml` | Config file path. |
| `runs-on` | string | `ubuntu-latest` | Runner label. |

No secrets.

## `config-ownership-check.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `deploy-config-glob` | string | `deploy/**/*.{yml,yaml} **/docker-compose*.{yml,yaml} kubernetes/**/*.{yml,yaml} helm/**/*.{yml,yaml}` | Glob patterns for deploy-plane config. |
| `orchestration-only-patterns` | string | `""` | Newline-separated regex overrides. |
| `ui-config-glob` | string | `""` | Glob patterns for central-deploy UI config. |
| `base-ref` | string | `""` | Git ref to diff against. |

No secrets.

## `dependabot-auto-merge.yml`

No inputs.  No secrets.

## `deps-bump.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `packages` | string | — | Space-separated first-party package names (subset of `[tool.uv.sources]`). |
| `app-id` | string | — | GitHub App ID for PR creation. |

| Secret | Required | Description |
|---|---|---|
| `app-private-key` | yes | GitHub App private key. |

## `docker-pr-scan.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `dockerfile` | string | `./Dockerfile` | Path to Dockerfile. |
| `image-name` | string | `ghcr.io/<owner>/<repo>` | Image name for scanning. |
| `use-gha-cache` | boolean | `true` | Use GHA layer cache. |

No secrets (uses `GITHUB_TOKEN` via caller workflow).

## `docker-release.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `dockerfile` | string | `./Dockerfile` | Path to Dockerfile. |
| `image-name` | string | `ghcr.io/<owner>/<repo>` | Image name for publishing. |

No explicit secrets input (callers pass `secrets: inherit`).

## `lint-workflows.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `run-actionlint` | boolean | `false` | Run actionlint on workflow files. |
| `run-zizmor` | boolean | `false` | Run zizmor security audit. |
| `sarif-workflows` | string | `codeql.yml scan-container.yml` | Workflow basenames requiring security-events:write. |

No secrets.

## `pin-bump.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `packages` | string | — | Space-separated package names (empty = all git-sourced). |
| `app-id` | string | — | GitHub App ID for PR creation. |

| Secret | Required | Description |
|---|---|---|
| `app-private-key` | yes | GitHub App private key. |

## `pin-bump-sweep.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `owner` | string | `damien-robotsix` | GitHub org/owner to sweep. |
| `app-id` | string | — | GitHub App ID for PR creation. |

| Secret | Required | Description |
|---|---|---|
| `app-private-key` | yes | GitHub App private key. |

## `python-ci.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `python-version` | string | `3.14` | Python version. |
| `uv-version` | string | `0.8.15` | uv version. |
| `install-extras` | string | `tracing` | Extras to install. |
| `cov-package` | string | `robotsix_mill` | Package for coverage. |
| `coverage-threshold` | string | `80` | Minimum coverage %. |
| `pytest-args` | string | `-m "not docker"` | Extra pytest arguments. |
| `pytest-numprocesses` | string | `auto` | pytest-xdist workers. |
| `runs-on` | string | `ubuntu-latest` | Runner label. |
| `run-deptry` | boolean | `true` | Run deptry. |
| `run-audit` | boolean | `true` | Run uv audit. |
| `run-bandit` | boolean | `true` | Run bandit. |
| `bandit-severity` | string | `medium` | Bandit severity threshold. |
| `mypy-advisory` | boolean | `false` | Advisory-only mypy (don't fail). |
| `audit-ignore` | string | `""` | Space/comma-separated advisory IDs. |
| `job_split` | boolean | `false` | Split into parallel lint/type/test jobs. |

No secrets.

## `python-docs.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `docs-install-args` | string | `--group docs` | uv sync args for docs deps. |
| `python-version` | string | `3.14` | Python version. |
| `uv-version` | string | `0.8.15` | uv version. |
| `retries` | string | `4` | mkdocs deploy retries. |

No secrets.

## `python-security.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `python-version` | string | `3.14` | Python version. |
| `uv-version` | string | `0.8.15` | uv version. |
| `install-extras` | string | `tracing` | Extras to install. |
| `runs-on` | string | `ubuntu-latest` | Runner label. |
| `run-trufflehog` | boolean | `true` | Run TruffleHog. |
| `trufflehog-pr-diff` | boolean | `false` | Limit TruffleHog to PR diff. |
| `trufflehog-extra-args` | string | `""` | Extra TruffleHog args. |
| `run-pip-audit` | boolean | `true` | Run pip-audit. |
| `pip-audit-requirements-file` | string | `""` | Requirements file for pip-audit. |
| `pip-audit-ignore-packages` | string | `""` | Packages to ignore. |
| `pip-audit-ignore-vulns` | string | `""` | Vuln IDs to ignore. |

No secrets.

## `scan-container.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `image-name` | string | `ghcr.io/<owner>/<repo>:main` | Image to rescan. |

No secrets (caller needs `security-events: write` and `contents: read`).
