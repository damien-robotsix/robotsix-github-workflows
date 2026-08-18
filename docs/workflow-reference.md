# Workflow Reference

Consolidated input, default, and secret reference for all reusable workflows in
this repository.

## `auto-release.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `app-id` | string | — | GitHub App ID for release authentication. |
| `python-version` | string | `3.14` | Python version for the release job. |
| `uv-version` | string | `0.8.15` | uv version for the release job. |
| `runs-on` | string | `ubuntu-latest` | Runner label for the release job. |
| `default-branch` | string | `main` | Name of the default branch (e.g. "main" or "master"). |

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
| `config-file` | string | `""` | Path to a repo-local CodeQL configuration file (e.g. .github/codeql/codeql-config.yml). Empty = no config file. |
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
| `uv-version` | string | `0.8.15` | uv version to install. |
| `default-branch` | string | `main` | Base branch for the PR and the git push target. |
| `bump-branch` | string | `deps-bump/first-party` | Branch to force-push the bump commit to. |

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

The GHA layer cache (`cache-from`/`cache-to`) is enabled by default. For
large images (multi-GB), exporting layers to the GHA cache API can add
45–55 minutes per run — far longer than a cold build. Time both paths on
the actual image before enabling the cache. Set `use-gha-cache: false` to
skip the cache entirely.

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

## `mutation-test.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `python-version` | string | `3.14` | Python version. |
| `timeout-minutes` | number | `120` | Job timeout in minutes. |
| `dependency-group` | string | `dev` | uv dependency group that installs mutmut. |

No secrets.

## `pin-bump.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `packages` | string | — | Space-separated package names (empty = all git-sourced). |
| `app-id` | string | — | GitHub App ID for PR creation. |
| `uv-version` | string | `0.8.15` | uv version to install. |
| `default-branch` | string | `main` | Base branch for the PR and git push target. |
| `bump-branch` | string | `pin-bump/first-party` | Branch to force-push the bump commit to. |

| Secret | Required | Description |
|---|---|---|
| `app-private-key` | yes | GitHub App private key. |

## `pin-bump-sweep.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `owner` | string | `damien-robotsix` | GitHub org/owner to sweep. |
| `app-id` | string | — | GitHub App ID for PR creation. |
| `uv-version` | string | `0.8.15` | uv version to install. |

| Secret | Required | Description |
|---|---|---|
| `app-private-key` | yes | GitHub App private key. |

## `release-please.yml`

Conventional-commit release automation: opens/updates the release PR on every
push to the default branch, then creates the tag and GitHub Release when that
PR merges.  The caller keeps the triggers, the concurrency group and the
release-PR guard; this workflow owns the token minting, the release-please
action and the `uv.lock` sync.

| Input | Type | Default | Description |
|---|---|---|---|
| `app-id` | string | — | GitHub App ID for release authentication. |
| `runs-on` | string | `ubuntu-latest` | Runner label for the release job. |
| `default-branch` | string | `main` | Default branch; the release branch is derived as `release-please--branches--<default-branch>`. |
| `timeout-minutes` | number | `10` | Job timeout. |
| `sync-uv-lock` | boolean | `true` | Regenerate `uv.lock` on the release branch after the bump.  Turn off for repos with no `uv.lock`. |
| `skip-labeling` | boolean | `false` | Pass through to release-please's `skip-labeling`. |
| `harden-runner` | boolean | `false` | Run `step-security/harden-runner` in audit mode first. |
| `permission-contents` | string | `write` | Minted-token scope: release commit, tag, Release. |
| `permission-pull-requests` | string | `write` | Minted-token scope: open and update the release PR. |
| `permission-workflows` | string | `write` | Minted-token scope: tag a commit whose workflows differ from the default branch — see below. |

| Secret | Required | Description |
|---|---|---|
| `app-private-key` | yes | GitHub App private key for token minting. |

**Why `workflows: write` is not optional in practice.** Creating the Release
creates a tag ref at the release commit, and GitHub treats creating a ref whose
`.github/workflows/**` differ from the default branch as *modifying workflow
files* — permitted only with `workflows: write`.  Dependabot bumping an action
while the release PR is open is enough to cause that drift.  Without the scope
the release creation fails with `Resource not accessible by integration`, the
tag is never cut, and every later push retries the same failure.  The API
states the accepted alternatives in its response header:
`x-accepted-github-permissions: contents=write; contents=write,workflows=write`.

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
| `retries` | string | `4` | Number of dependency-install attempts in the retry loop. |

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
| `ignore-unfixed` | boolean | `false` | Skip CVEs with no upstream fix. Defaults to false so all findings surface in the Security tab. |

No secrets (caller needs `security-events: write` and `contents: read`).
