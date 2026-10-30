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

## `bump.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `bump-mode` | string | — | Bump mode: "deps" (uv lock --upgrade-package) or "pins" (scripts/pin-bump.py per-repo). Required. |
| `packages` | string | — | Space-separated package names; empty = all git-sourced (pins). Required. |
| `uv-version` | string | `0.12.5` | uv version to install. |
| `default-branch` | string | `main` | Base branch for the PR and git push target. |
| `bump-branch` | string | `deps-bump/first-party` | Branch to force-push the bump commit to. |
| `app-id` | string | — | GitHub App ID for PR creation. Required. |
| `permission-contents` | string | `write` | Minted token's repo contents scope (push bump branch). |
| `permission-pull-requests` | string | `write` | Minted token's PR scope (create/update PRs). |

| Secret | Required | Description |
|---|---|---|
| `app-private-key` | yes | GitHub App private key (PEM) paired with `app-id`. |

## `codeql.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `languages` | string | `python` | Languages to analyze. |
| `queries` | string | `security-and-quality` | Query suite. |
| `config-file` | string | `""` | Path to a repo-local CodeQL configuration file (e.g. .github/codeql/codeql-config.yml). Empty = no config file. |
| `build-mode` | string | `""` | CodeQL build mode forwarded to `codeql-action/init` (`none`, `autobuild`, or `manual`). Empty = not passed to init and the autobuild step runs; when set, the autobuild step is skipped. Use `none` for Python. |
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

| Input | Type | Default | Description |
|---|---|---|---|
| `runs-on` | string | `ubuntu-latest` | Runner label for every job; `self-hosted` for a private repo without GitHub-hosted minutes. |

The App-token inputs (`app-id`, secret `app-private-key`) are documented in the workflow file.

## `dependency-review.yml`

Runs [`actions/dependency-review-action`](https://github.com/actions/dependency-review-action)
on pull requests to block newly introduced vulnerable or disallowed-license
dependencies. The job is skipped on non-`pull_request` events.

| Input | Type | Default | Description |
|---|---|---|---|
| `fail-on-severity` | string | `moderate` | Lowest vulnerability severity that fails the check (`low`, `moderate`, `high`, `critical`). Inline inputs take precedence over `config-file`. |
| `config-file` | string | `""` | Path to a dependency-review-action config file (e.g. `.github/dependency-review-config.yml`). Empty = no config file; the caller repo is checked out only when set. |
| `deny-licenses` | string | `""` | Comma-separated SPDX identifiers that fail the check. Mutually exclusive with `allow-licenses`. |
| `allow-licenses` | string | `""` | Comma-separated SPDX identifiers that are the only ones allowed. Mutually exclusive with `deny-licenses`. |
| `comment-summary-in-pr` | boolean | `true` | Post the review summary as a PR comment. |
| `runs-on` | string | `ubuntu-latest` | Runner label for the job. |

No secrets. The job requests `contents: read` and `pull-requests: write`
(for the PR summary comment).

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
| `smoke` | boolean | `true` | Run the post-build smoke test that executes the image once to prove its entrypoint can `exec`. |
| `smoke_command` | string | `""` | Command run inside the image via `sh -c` (e.g. `python -c "import mypkg"`). When empty, execs the image's own entrypoint/CMD binary with `--help`. |
| `strip-pip` | boolean | `true` | Hardening layer uninstalls pip (and its site-packages/bin leftovers) from any python3 in the image — the base image's pip vendors a certifi that trips the Trivy gate. Set `false` for images that need pip at runtime; images without python are unaffected. |
| `runs-on` | string | `ubuntu-latest` | Runner label for the job, e.g. `self-hosted` for zero billed minutes. |
| `trivy-db-repository` | string | `""` | Exported as `TRIVY_DB_REPOSITORY` to every Trivy step. Empty uses Trivy's built-in default source; opt in to the ghcr.io mirror with `ghcr.io/aquasecurity/trivy-db:2` (avoids the mirror.gcr.io download hanging on self-hosted runners). |
| `trivy-java-db-repository` | string | `""` | Exported as `TRIVY_JAVA_DB_REPOSITORY` to every Trivy step. Empty uses Trivy's built-in default source; opt in to the ghcr.io mirror with `ghcr.io/aquasecurity/trivy-java-db:1`. |
| `upload-sarif` | boolean | `true` | Run the Trivy SARIF scan and upload it to Code Scanning. Always skipped for private repositories (code-scanning upload requires GitHub Advanced Security). |
| `trivyignores` | string | `.trivyignore` | Trivy ignore file passed explicitly to both the gate and the SARIF scans. Skipped when the file does not exist. |
| `build-args` | string | `""` | Newline-separated `NAME=value` build args for the component Dockerfile build. Not for secrets (recorded in image history). |
| `github-token-secret-id` | string | `""` | When set, exposes the job's `GITHUB_TOKEN` to the component Dockerfile build as a BuildKit secret with this id (`RUN --mount=type=secret,id=<id>`). |

| Secret | Required | Description |
|---|---|---|
| `build-secrets` | no | Newline-separated `id=value` BuildKit secrets for the component Dockerfile build (`RUN --mount=type=secret,id=<id>`). |

`GITHUB_TOKEN` is always available to the reusable workflow; no `secrets: inherit` needed.

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
| `smoke` | boolean | `true` | Run the post-build smoke test that executes the image once to prove its entrypoint can `exec`. |
| `smoke_command` | string | `""` | Command run inside the image via `sh -c` (e.g. `python -c "import mypkg"`). When empty, execs the image's own entrypoint/CMD binary with `--help`. |
| `strip-pip` | boolean | `true` | Hardening layer uninstalls pip (and its site-packages/bin leftovers) from any python3 in the image — the base image's pip vendors a certifi that trips the Trivy gate. Set `false` for images that need pip at runtime; images without python are unaffected. |
| `runs-on` | string | `ubuntu-latest` | Runner label for the job, e.g. `self-hosted` for zero billed minutes. |
| `trivy-db-repository` | string | `""` | Exported as `TRIVY_DB_REPOSITORY` to every Trivy step. Empty uses Trivy's built-in default source; opt in to the ghcr.io mirror with `ghcr.io/aquasecurity/trivy-db:2` (avoids the mirror.gcr.io download hanging on self-hosted runners). |
| `trivy-java-db-repository` | string | `""` | Exported as `TRIVY_JAVA_DB_REPOSITORY` to every Trivy step. Empty uses Trivy's built-in default source; opt in to the ghcr.io mirror with `ghcr.io/aquasecurity/trivy-java-db:1`. |
| `upload-sarif` | boolean | `true` | Run the Trivy SARIF scan and upload it to Code Scanning. Always skipped for private repositories (code-scanning upload requires GitHub Advanced Security). |
| `trivyignores` | string | `.trivyignore` | Trivy ignore file passed explicitly to both the gate and the SARIF scans. Skipped when the file does not exist. |
| `build-args` | string | `""` | Newline-separated `NAME=value` build args for the component Dockerfile build. Not for secrets (recorded in image history). |
| `github-token-secret-id` | string | `""` | When set, exposes the job's `GITHUB_TOKEN` to the component Dockerfile build as a BuildKit secret with this id (`RUN --mount=type=secret,id=<id>`). |
| `push-retries` | number | `3` | Extra attempts for the component base push-by-digest (Stage 1, only when its first push fails) and the hardened-image build+push (Stage 2) when they fail (e.g. GHCR's intermittent `unknown blob`), with a short back-off; already-uploaded blobs are reused. Must be 0–10; larger values are rejected. Retries stay inside the push steps, so the Trivy gate and attestations run once. `0` = single attempt. |

| Secret | Required | Description |
|---|---|---|
| `build-secrets` | no | Newline-separated `id=value` BuildKit secrets for the component Dockerfile build (`RUN --mount=type=secret,id=<id>`). |

Callers either pass `secrets: inherit` or, to supply `build-secrets`, an explicit
`secrets:` map (the two are mutually exclusive). `GITHUB_TOKEN` is always available.

## `lint-workflows.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `run-actionlint` | boolean | `false` | Run actionlint on workflow files. |
| `runs-on` | string | `ubuntu-latest` | Runner label for every job; `self-hosted` for a private repo without GitHub-hosted minutes. |
| `run-zizmor` | boolean | `false` | Run zizmor security audit. |
| `sarif-workflows` | string | `codeql.yml scan-container.yml scorecard.yml` | Workflow basenames requiring security-events:write. |
| `dockerfiles` | string | `""` | Space-separated Dockerfile paths whose `FROM` lines must be digest-pinned (e.g. `Dockerfile sandbox/Dockerfile`). Empty skips the check. |
| `run-workflow-rules` | boolean | `false` | Run `scripts/check_workflow_rules.py` on the caller's `.github/workflows` and `.github/actions`. |
| `workflow-rules` | string | `sha-pin,persist-credentials,static-defaults` | Comma-separated rules enforced when `run-workflow-rules` is true, or `all`. |
| `trivyignore` | string | `""` | Path of a `.trivyignore` whose entries must carry `# expires: YYYY-MM-DD` (e.g. `.trivyignore`). Empty skips the check. |
| `trivyignore-missing-expiry` | string | `warn` | Policy for entries without an `# expires:` annotation: `warn` or `fail`. |

No secrets.

When `run-workflow-rules` is true, the `workflow-rules` job enforces the
selected conventions:

| Rule | Checks |
|---|---|
| `sha-pin` | Every remote `uses:` is pinned to a 40-char commit SHA with a trailing `# vX[.Y[.Z]]` comment (own-repo composite-action refs need no comment). |
| `persist-credentials` | Every `actions/checkout` sets `persist-credentials: false`, unless the step carries `# zizmor: ignore[artipacked]`. |
| `static-defaults` | `workflow_call` input defaults are static literals, not `${{ }}` expressions. |
| `harden-runner-first` | The first step of every job is `step-security/harden-runner`. |
| `setup-uv` | Every job whose `run:` steps invoke `uv` includes an `astral-sh/setup-uv` step. |
| `uv-sync-frozen` | Every `uv sync` invocation passes `--frozen`. |

The job-level rules (`harden-runner-first`, `setup-uv`) expand local composite
actions into the calling job and skip reusable-workflow jobs. The
robotsix-github-auth `check_ci_conventions.py` set maps to
`workflow-rules: "harden-runner-first,persist-credentials,setup-uv,uv-sync-frozen"`.

When `dockerfiles` is set, the `dockerfile-pins` job runs
`scripts/lint_dockerfile_pins.py` (ported from robotsix-browser) on each
listed file and fails on any `FROM` that lacks an `@sha256:<64-hex>` digest,
e.g. `FROM node:22-alpine AS ui`. `FROM scratch` and references to an earlier
build stage are exempt; `$ARG` references are expanded from `ARG` defaults
declared before the first `FROM`, and an ARG with no default is reported
because the linter cannot prove it is pinned. Pin a tag with
`<image>:<tag>@sha256:<digest>`.

When `trivyignore` is set, the `trivyignore-expiry` job runs
`scripts/check_trivyignore_expiry.py` (ported from robotsix-mill) on that
file. Every suppression is expected to look like
`CVE-2025-12345  # expires: 2026-12-31`; blank lines and full-line comments
are ignored. The job fails once any entry's expiry date is reached (the date
itself counts as expired) or when a date is malformed, so suppressions come
back up for review instead of living forever. Entries with no `# expires:`
annotation are reported as warnings, or fail the job when
`trivyignore-missing-expiry: fail`. A path that does not exist fails the job.

## `lint-dockerfile.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `dockerfiles` | string | `Dockerfile` | Space-separated Dockerfile paths or glob patterns (e.g. `Dockerfile Dockerfile.dev`). Non-existent paths are ignored; if nothing matches, hadolint is skipped with a notice. |
| `failure-threshold` | string | `warning` | Fail only on rules at or above this severity (`error`, `warning`, `info`, `style`, `ignore`). |
| `config` | string | `""` | Path to a hadolint config file. Empty uses hadolint's default config discovery. |
| `upload-sarif` | boolean | `false` | Also run hadolint with `format: sarif` in a separate `hadolint-sarif` job and upload `hadolint.sarif` to code scanning (`github/codeql-action/upload-sarif`, category `hadolint`). The job applies the same `failure-threshold`. |
| `runs-on` | string | `ubuntu-latest` | Runner label for every job; `self-hosted` for a private repo without GitHub-hosted minutes. |

No secrets.

**Permissions with `upload-sarif: true`:** the `hadolint-sarif` job inherits
the caller's token, so the **calling job** must grant `security-events: write`
and `contents: read`. Callers that leave `upload-sarif` off need no extra
permission, which is why `lint-dockerfile.yml` is not in the
`lint-workflows.yml` `sarif-workflows` default. A caller that opts in may add
it to its own `sarif-workflows` input. The SARIF is uploaded with
`if: success() || failure()`, so findings are published even when hadolint
fails the job.

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

`scripts/pin-bump.py` bumps two shapes of SHA-pinned git source: entries in
`[tool.uv.sources]` with a 40-char `rev`, and PEP 508 direct-URL requirements
`name @ git+URL@<40-hex>` in `[project.dependencies]`,
`[project.optional-dependencies]` or `[dependency-groups]`. Branch, tag and
short-SHA refs are not pins and are left alone. Both shapes are rewritten
in place and the lock is regenerated with `uv lock`.

## `pin-bump-sweep.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `owner` | string | `damien-robotsix` | GitHub org/owner to sweep. |
| `app-id` | string | — | GitHub App ID for PR creation. |
| `uv-version` | string | `0.8.15` | uv version to install. |

| Secret | Required | Description |
|---|---|---|
| `app-private-key` | yes | GitHub App private key. |

The sweep collects the same git pins as `pin-bump.yml`, including PEP 508
direct-URL pins (`name @ git+URL@<sha>`), so a repo that pins a fleet sibling
that way is bumped together with its consumers. The sweep script's `--dry-run`
flag (summary only, no clones, pushes or PRs) is not exposed as a workflow
input.

## `release-please.yml`

Conventional-commit release automation: opens/updates the release PR on every
push to the default branch, then creates the tag and GitHub Release when that
PR merges.  The caller keeps the triggers, the concurrency group and the
release-PR guard; this workflow owns the token minting, the release-please
action and the `uv.lock` sync.

The release PR is opened with the App token (rather than `GITHUB_TOKEN`), so
its `pull_request` CI actually runs — required checks are triggered and can
report their status.  Merge authority stays with the chat periodic agent,
which decides merge as a function of the release content.

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
| `test-timeout-minutes` | number | `15` | `timeout-minutes` for the `tests` and `test` jobs. Raise only for slow suites. The `lint`, `typecheck`, `vulture` and `audit-sarif` jobs have fixed ceilings (5, 10, 5 and 10 minutes). |
| `run-deptry` | boolean | `true` | Run deptry. |
| `run-audit` | boolean | `true` | Run uv audit. |
| `run-bandit` | boolean | `true` | Run bandit. |
| `bandit-severity` | string | `medium` | Bandit severity threshold. |
| `mypy-advisory` | boolean | `false` | Advisory-only mypy (don't fail). |
| `audit-ignore-file` | string | `.audit-ignore` | Single-source advisory ignore file (see [Audit ignore file](#audit-ignore-file)). |
| `audit-ignore` | string | `""` | **Deprecated** — space/comma-separated advisory IDs, merged with `audit-ignore-file`. |
| `audit-sarif` | boolean | `false` | Also run `uv audit --frozen --output-format sarif` in a separate `audit-sarif` job and upload it to code scanning (`github/codeql-action/upload-sarif`, category `uv-audit`). The job stays blocking. Requires `run-audit: true` and a uv that ships `uv audit`. |
| `check-lock` | boolean | `false` | Run `uv lock --check` (fails when `uv.lock` has drifted from `pyproject.toml`). |
| `run-vulture` | boolean | `false` | Add a separate `vulture` job running `uv run vulture` (vulture `2.16`, provisioned via `--with`) as a dead-code gate. The job declares its own `contents: read` permissions — callers need grant nothing extra. |
| `vulture-args` | string | `""` | Arguments passed verbatim to vulture (shell quoting honoured), e.g. `src/ vulture_whitelist.py --min-confidence 80 --ignore-decorators "@field_validator,@model_validator"`. Empty → vulture reads `[tool.vulture]` from `pyproject.toml`. |
| `job_split` | boolean | `false` | Split into parallel lint/type/test jobs. |

Every job in `python-ci.yml` declares `timeout-minutes`, because callers cannot set
it on a `uses:` job. Ceilings are 15 minutes for `tests` and `test`
(`test-timeout-minutes`), 5 for `lint` and `vulture`, 10 for `typecheck` and
`audit-sarif`.

No secrets.

**Permissions with `audit-sarif: true`:** the `audit-sarif` job inherits the
caller's token, so the **calling job** must grant `security-events: write` and
`contents: read`. Callers that leave `audit-sarif` off need no extra
permission, which is why `python-ci.yml` is not in the `lint-workflows.yml`
`sarif-workflows` default. A caller that opts in may add it to its own
`sarif-workflows` input. The SARIF is uploaded with `if: success() || failure()`,
so findings still reach code scanning when the audit fails the job.

## `python-docs.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `docs-install-args` | string | `--group docs` | uv sync args for docs deps. |
| `python-version` | string | `3.14` | Python version. |
| `uv-version` | string | `0.8.15` | uv version. |
| `retries` | string | `4` | Number of dependency-install attempts in the retry loop. |

No secrets.

Deploys to GitHub Pages via the modern Pages Actions (build type: "workflow").
Callers must grant `pages: write` + `id-token: write` (not `contents: write`),
so this workflow does NOT use `mkdocs gh-deploy` (which pushes to the
`gh-pages` branch and needs `contents: write`).  Enable Pages once per repo
with source "GitHub Actions".

No workflow-level concurrency group is set — `github.workflow` resolves to
the *caller's* workflow name in a reusable workflow, so a caller-side
`${{ github.workflow }}-...` group would deadlock. Callers own concurrency
(e.g. `group: pages`).

Dependency installation retries up to `retries` times with a 10-second
backoff between attempts to handle transient PyPI or registry errors.

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
| `audit-ignore-file` | string | `.audit-ignore` | Single-source advisory ignore file shared with `python-ci.yml` (see [Audit ignore file](#audit-ignore-file)). |
| `pip-audit-ignore-vulns` | string | `""` | **Deprecated** — vuln IDs to ignore, merged with `audit-ignore-file`. |

No secrets.

Runs TruffleHog secret-scanning and pip-audit dependency-vulnerability
scanning in a single job.  TruffleHog supports two modes: PR-diff scan
(`trufflehog-pr-diff: true`, scans only the base/head diff) and full
checkout scan (default, scans the entire repository).  pip-audit supports
two audit modes: when `pip-audit-requirements-file` is set, exports a
locked requirements file and audits that; when empty, audits the synced
environment directly via `uv run pip-audit`.

An SBOM (CycloneDX JSON) is generated and uploaded as a build artifact on
every run via `always()`, so it is available even when scans fail.

### Audit ignore file

`python-ci.yml` (uv audit and its pip-audit fallback), `python-security.yml`
(pip-audit) and the `uv-audit` pre-commit hook all read one repo-root file,
`.audit-ignore` by default, parsed by `scripts/audit_ignore.py`:

```text
# one advisory per line; a "# reason" comment is mandatory
GHSA-w8v5-vhqr-4h9v  # diskcache unsafe pickle, no fix available
CVE-2026-12345       # transitive via foo, upstream PR open  # expires: 2026-12-31
```

* Ids become `--ignore-until-fixed` on `uv audit` (auto-clears once a fix
  ships) and `--ignore-vuln` on pip-audit (which has no until-fixed mode —
  use `# expires:` to bound the ignore).
* An entry without a reason, a duplicate, a malformed id or an entry whose
  `# expires:` date has passed fails the audit step.
* A missing file means no advisories are ignored.
* The inline `audit-ignore` / `pip-audit-ignore-vulns` inputs still work
  (merged with the file) but emit a deprecation warning.

Consumers can reuse the same file locally via `.pre-commit-hooks.yaml`:

```yaml
- repo: https://github.com/damien-robotsix/robotsix-github-workflows
  rev: <sha>
  hooks:
    - id: audit-ignore-check   # validate format / reasons / expiry
    - id: uv-audit             # uv audit --frozen --preview + .audit-ignore ids
```

## `scorecard.yml`

No inputs.  No secrets (caller needs `security-events: write` and
`contents: read`).

Runs [OpenSSF Scorecard](https://github.com/ossf/scorecard-action) against
the calling repository and uploads the SARIF results to Code Scanning
(category `scorecard`).  Checks cover repository-level supply-chain posture:
Token-Permissions, Branch-Protection, Dangerous-Workflow, Maintained,
Pinned-Dependencies, Signed-Releases and more.

Results are not published to the public Scorecard API
(`publish_results: false`): Scorecard's publish verification inspects the
calling workflow file and rejects reusable-workflow callers.  Repos that want
the public badge add a standalone workflow — see
`.github/workflows/self-scorecard.yml` in this repo for the reference shape.

## `scan-container.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `image-name` | string | `""` | Full image ref to scan (e.g. `ghcr.io/<owner>/<repo>:main`). When empty, falls back to `ghcr.io/$GITHUB_REPOSITORY:main` at runtime. |
| `ignore-unfixed` | boolean | `false` | Skip CVEs with no upstream fix. Defaults to false so all findings surface in the Security tab. |

No secrets (caller needs `security-events: write` and `contents: read`).

Report-only scheduled rescan workflow — there is no exit-code gate, so
findings do not fail the run.  No severity filter is applied; scheduled
rescans surface all findings (including LOW) for trend tracking in the
Code Scanning dashboard.  Scans are performed via the
`.github/actions/trivy-sarif` composite action, which uploads SARIF results
to the repository's Code Scanning endpoint.

The `image-name` default is a static empty string because `workflow_call`
input `default:` values cannot contain `${{ }}` expressions (GitHub rejects
them as an invalid workflow file).  The dynamic `ghcr.io/<owner>/<repo>:main`
fallback is computed inside the job step.
