# robotsix-github-workflows

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/damien-robotsix/robotsix-github-workflows/badge)](https://scorecard.dev/viewer/?uri=github.com/damien-robotsix/robotsix-github-workflows)

Shared **reusable** GitHub Actions workflows (`workflow_call`) for the robotsix fleet.
Consumers reference these SHA-pinned, e.g.:

```yaml
jobs:
  tests:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/python-ci.yml@<sha>
```

| Workflow | Purpose |
|---|---|
| `python-ci.yml` | lint/format/type/test gate for Python packages |
| `python-security.yml` | bandit / pip-audit / trufflehog security scan |
| `python-docs.yml` | mkdocs build/deploy |
| `auto-release.yml` | scheduled towncrier-driven `0.x` tag-cutting release workflow (deprecated — use `release-please.yml`) |
| `release-please.yml` | conventional-commits release automation (replaces deprecated `auto-release.yml`) |
| `docker-release.yml` | build + push container image |
| `docker-pr-scan.yml` | build (no push) + Trivy CRITICAL/HIGH scan for PRs |
| `scan-container.yml` | weekly Trivy rescan of published :main image (SARIF, report-only) |
| `deps-bump.yml` | scheduled `uv lock --upgrade` PR |
| `bump.yml` | shared bump engine behind the `deps-bump.yml` / `pin-bump.yml` wrappers (`bump-mode: deps|pins`) |
| `dependabot-auto-merge.yml` | auto-merge Dependabot PRs (protected & unprotected branch handling) |
| `baseline-check.yml` | enforce AGENT.md and .github/dependabot.yml baseline rules |
| `codeql.yml` | CodeQL static analysis |
| `scorecard.yml` | OpenSSF Scorecard supply-chain posture analysis (SARIF to Code Scanning) |
| `dependency-review.yml` | PR gate: dependency-review-action vulnerability-severity + license policy check |
| `config-ownership-check.yml` | PR gate: prevents deploy-plane config from leaking component-internal settings |
| `lint-workflows.yml` | actionlint + zizmor audit of workflow files, SARIF-upload-permission validation, trigger-coverage validation, opt-in workflow-conventions checker, opt-in Dockerfile `FROM` digest-pin check, and opt-in `.trivyignore` expiry gate |
| `lint-dockerfile.yml` | opt-in hadolint lint of one or more Dockerfiles (skipped when none exist) |
| `mutation-test.yml` | weekly advisory mutmut mutation testing (HTML report + step-summary score) |
| `pin-bump.yml` | scheduled per-repo first-party git pin bump PR |
| `pin-bump-sweep.yml` | fleet-wide coherent-set pin-bump sweep orchestrator |

Mill-domain checks (e.g. `check_kind_literals`) live in robotsix-mill's own CI, not here.

## Documentation

- [Workflow Reference](docs/workflow-reference.md) — consolidated input, default, and secret reference
  for all 18 reusable workflows.
- [Branch Protection](docs/branch-protection.md) — ruleset semantics, usage, and required `gh` auth scopes.
- [Workflow Authoring](docs/WORKFLOW-AUTHORING.md) — conventions for authoring new reusable workflows:
  structure, input design and validation, error reporting, and the pre-commit checklist.

## `auto-release.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/auto-release.yml`)
that triggers on a weekly schedule + manual dispatch:

```yaml
name: Auto Release

on:
  schedule:
    - cron: "0 9 * * 1"  # every Monday at 09:00 UTC
  workflow_dispatch:

jobs:
  release:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/auto-release.yml@<sha>
    # Preferred: authenticate as a GitHub App (no expiry, bot identity).
    # The installation token is minted inside the reusable workflow —
    # app tokens live ~1h, so they cannot be a static secret, and
    # reusable-workflow `secrets:` cannot carry runtime step outputs.
    with:
      app-id: ${{ vars.RELEASE_APP_ID }}      # repo/org variable, not a secret
    secrets:
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}
```

On squash-only repos (the fleet branch-protection standard), a direct push
to the default branch is rejected and the workflow falls back to a release
PR with **squash** auto-merge; the annotated `v*` tag keeps the original
release commit reachable.

**Consumer prerequisites:**

- A `[project] version` on the `0.x` line (e.g. `version = "0.1.0"`).
  The workflow only handles the pre-1.0 release cadence — a non-`0.x`
  version causes a hard failure.

- An existing `docker-release.yml` caller workflow that maps `v*` tags
  to `X.Y.Z` image tags via `type=semver,pattern={{version}}`.

> **Note:** This workflow is deprecated in favour of `release-please.yml`,
> which uses conventional commits instead of towncrier fragments.

## `release-please.yml` — caller template

Conventional-commit release automation — the recommended replacement for
the deprecated `auto-release.yml`.  The caller keeps the triggers and the
release-PR guard; this workflow owns token minting, the release-please
action and the `uv.lock` sync.  Consumer repos add a wrapper workflow
(e.g. `.github/workflows/release.yml`) that triggers on pushes to the
default branch + manual dispatch:

```yaml
name: Release Please
on:
  push:
    branches: ["main"]
  workflow_dispatch:
jobs:
  release:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/release-please.yml@<sha>
    with:
      app-id: ${{ vars.RELEASE_APP_ID }}  # repo/org variable, not a secret
    # Optional inputs — defaults shown:
    #   runs-on: "ubuntu-latest"
    #   default-branch: "main"
    #   timeout-minutes: 10
    #   sync-uv-lock: true
    #   skip-labeling: false
    #   harden-runner: false
    #   permission-contents: "write"
    #   permission-pull-requests: "write"
    #   permission-workflows: "write"
    secrets:
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}  # GitHub App private key
```

The release PR is opened with the App token (never `GITHUB_TOKEN`), so
its `pull_request` CI actually runs and required checks can report their
status.  `sync-uv-lock` regenerates `uv.lock` on the release branch after
the version bump — turn it off for repos with no `uv.lock`.

## `docker-pr-scan.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/docker-pr-scan.yml`) that triggers on pull requests:

```yaml
name: Docker PR Scan

on:
  pull_request:

jobs:
  scan:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/docker-pr-scan.yml@<sha>
    # Optional overrides — omit if your Dockerfile is ./Dockerfile
    # and your image name is ghcr.io/<owner>/<repo>:
    # with:
    #   dockerfile: ./docker/Dockerfile.prod
    #   image-name: ghcr.io/my-org/my-repo-sandbox
    #   use-gha-cache: false
    #   trivyignores: .trivyignore          # default; skipped if absent
    #   build-args: |
    #     PYTHON_VERSION=3.14
    #   github-token-secret-id: github_token  # RUN --mount=type=secret,id=github_token
    # Optional extra BuildKit secrets (id=value lines):
    # secrets:
    #   build-secrets: |
    #     npm_token=${{ secrets.NPM_TOKEN }}
```

The `trivyignores` file (default `.trivyignore` in the repository root) is passed
explicitly to both the gating and the SARIF Trivy scans for suppressing known
false positives; it is skipped when the file does not exist.

See [Workflow Reference](docs/workflow-reference.md) for all inputs and defaults, including
`use-gha-cache` timing notes.

## `python-ci.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/python-ci.yml`)
that triggers on `push`/`pull_request` targeting `main`:

```yaml
name: Python CI

on:
  push:
    branches: ["main"]
  pull_request:

jobs:
  tests:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/python-ci.yml@<sha>
    permissions:
      contents: read
    # All inputs are optional — defaults shown in comments:
    # with:
    #   python-version: "3.14"                    # default
    #   uv-version: "0.8.15"                      # default
    #   install-extras: "tracing"                 # default
    #   cov-package: "robotsix_mill"              # default
    #   coverage-threshold: "80"                  # default (fleet hard minimum)
    #   pytest-args: '-m "not docker"'            # default
    #   pytest-numprocesses: "auto"               # default
    #   runs-on: "ubuntu-latest"                  # default
    #   run-deptry: true                          # default
    #   run-audit: true                           # default
    #   run-bandit: true                          # default
    #   bandit-severity: "medium"                 # default
    #   mypy-advisory: false                      # default
    #   audit-ignore-file: ".audit-ignore"        # default — single-source ignore list
    #     # One "ID  # reason" per line, optional "# expires: YYYY-MM-DD".
    #     # Example .audit-ignore:
    #     #   GHSA-w8v5-vhqr-4h9v  # diskcache unsafe pickle, no fix available (2026-07)
    #   audit-ignore: ""                          # DEPRECATED — use audit-ignore-file
    #   audit-sarif: false                        # default — true adds an audit-sarif job that
    #     # uploads `uv audit --output-format sarif` to code scanning (still blocking).
    #     # REQUIRES the calling job to grant `security-events: write` (+ contents: read).
    #   check-lock: false                         # default — true runs `uv lock --check`
    #     # (fails when uv.lock has drifted from pyproject.toml).
    #   run-vulture: false                        # default — true adds a Vulture job running
    #     # `uv run vulture` (vulture 2.16) as a dead-code gate; job needs only contents: read.
    #   vulture-args: ""                          # default — empty reads [tool.vulture] from
    #     # pyproject.toml; else passed verbatim, e.g. `src/ vulture_whitelist.py --min-confidence 80`.
    #   job_split: false                          # default — single monolithic Tests job
    #     # When true, emits three parallel jobs (Lint, Type Check, Test)
    #     # instead of one sequential Tests job.  Each reports its own
    #     # green/red status check, reducing CI wall-clock time from
    #     # ~sum-of-all to ~max-of-three.
```

See [Workflow Reference](docs/workflow-reference.md) for all inputs, including the
`.audit-ignore` convention for suppressing advisories.

## `python-docs.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/docs.yml`)
that triggers on pushes to `main` and pull requests:

```yaml
name: Docs

on:
  push:
    branches: ["main"]
  pull_request:

jobs:
  docs:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/python-docs.yml@<sha>
    permissions:
      contents: read
      pages: write       # required for Pages deploy
      id-token: write    # required for Pages deploy
    # All inputs are optional — defaults shown in comments:
    # with:
    #   docs-install-args: "--group docs"      # default
    #   python-version: "3.14"                 # default
    #   uv-version: "0.8.15"                   # default
    #   retries: "4"                           # default
```

## `mutation-test.yml` — caller template

Consumer repos add a thin wrapper workflow (e.g. `.github/workflows/mutation-test.yml`)
that triggers on a weekly schedule + manual dispatch.  A reusable workflow cannot
own its own `schedule`, so the cron stays in the caller:

```yaml
name: Weekly mutation test

on:
  schedule:
    - cron: "0 6 * * 2"  # every Tuesday at 06:00 UTC
  workflow_dispatch:

jobs:
  mutate:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/mutation-test.yml@<sha>
    permissions:
      contents: read
    # All inputs are optional — defaults shown in comments:
    # with:
    #   python-version: "3.14"          # default
    #   timeout-minutes: 120            # default
    #   dependency-group: "dev"         # default
```

The run is advisory, never a blocking check: the `mutmut run` step always passes
(`|| true`), the HTML report is uploaded as an artifact, and the mutation score
is written to the job step summary.

See [Workflow Reference](docs/workflow-reference.md) for all inputs and defaults.
```

**Consumer prerequisites:**

- The repository must have GitHub Pages enabled with source **"GitHub Actions"**
  (`build_type: workflow`).  Enable once per repo:
  ```bash
  gh api "repos/$(gh repo view --json nameWithOwner -q .nameWithOwner)/pages" \
    -X POST \
    -f "source[build_type]=workflow"
  ```
  or visit Settings → Pages and select "GitHub Actions" as the source.

## `scan-container.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/scan-container.yml`)
that triggers on a weekly schedule + manual dispatch:

```yaml
name: Container Rescan
on:
  schedule:
    - cron: "0 6 * * 1"  # Monday 06:00 UTC
  workflow_dispatch:
jobs:
  rescan:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/scan-container.yml@<sha>
    # with:
    #   image-name: "ghcr.io/<owner>/<repo>:main"  # default: ghcr.io/$GITHUB_REPOSITORY:main
    permissions:
      security-events: write
      contents: read
```

## `scorecard.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/scorecard.yml`)
that triggers on pushes to `main` and a weekly schedule:

```yaml
name: Scorecard
on:
  push:
    branches: ["main"]
  schedule:
    - cron: "0 5 * * 1"  # Monday 05:00 UTC
  workflow_dispatch:
permissions:
  contents: read
jobs:
  scorecard:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/scorecard.yml@<sha>
    permissions:
      # Required — SARIF upload to code scanning.
      security-events: write
      contents: read
```

Results land in the Security tab only.  The public Scorecard badge needs
`publish_results: true`, which Scorecard refuses for reusable-workflow
callers — repos that want the badge copy this repo's standalone
[`self-scorecard.yml`](.github/workflows/self-scorecard.yml) instead.

## `docker-release.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/docker-release.yml`) that triggers on pushes to `main` and on version tags:

```yaml
name: Docker Release

on:
  push:
    branches: [main]
    tags: ["v*"]

jobs:
  publish:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/docker-release.yml@<sha>
    # Optional overrides — omit if your Dockerfile is ./Dockerfile
    # and your image name is ghcr.io/<owner>/<repo>:
    # with:
    #   dockerfile: ./docker/Dockerfile.prod
    #   image-name: ghcr.io/my-org/my-repo-sandbox
    #   trivyignores: .trivyignore          # default; skipped if absent
    #   build-args: |
    #     PYTHON_VERSION=3.14
    #   github-token-secret-id: github_token  # RUN --mount=type=secret,id=github_token
    #   push-retries: 3                     # default; extra push attempts on GHCR `unknown blob` (0-10), 0 = single attempt
    secrets: inherit
    # Or, to pass extra BuildKit secrets (replaces `secrets: inherit`):
    # secrets:
    #   build-secrets: |
    #     npm_token=${{ secrets.NPM_TOKEN }}
```

The `packages: write`, `id-token: write`, `attestations: write`, and `security-events: write` permissions are declared inside the reusable workflow and do not need to be re-declared in the caller. Secrets are passed via `secrets: inherit` so `GITHUB_TOKEN` is available for GHCR login.

Both the component base push-by-digest (Stage 1, retried only when its first push fails) and the hardened-image push (Stage 2) are retried up to `push-retries` extra times (default `3`, must be 0–10) with a short back-off, because GHCR intermittently fails a push mid-stream with `unknown blob`. The retry loops live inside the push steps, so the Trivy gate, smoke test and provenance/SBOM attestations run once, against the image that was actually published.

## `baseline-check.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/baseline-check.yml`)
that triggers on `push`/`pull_request` targeting `main`:

```yaml
name: Baseline Check

on:
  push:
    branches: ["main"]
  pull_request:

jobs:
  baseline:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/baseline-check.yml@<sha>
    with:
      # Set true when this repo builds and pushes a container image.
      # The check then additionally requires package-ecosystem: docker
      # in dependabot.yml.  Auto-detection also fires when a Dockerfile
      # exists at the repo root.
      has-docker: false

      # Set true when this repo uses the robotsix board (docs/modules.yaml).
      # Enables the modules-drift job which validates module registration.
      has-board: false
```

**Consumer prerequisites:**

- `AGENT.md` at the repo root with a `damien-robotsix/robotsix-standards` link within the first 20 lines.
- `README.md` at the repo root with a `damien-robotsix/robotsix-standards` reference.
- `LICENSE` at the repo root using the MIT license.
- `.github/dependabot.yml` covering at minimum `uv`, `github-actions`, and `pre-commit` ecosystems (plus `docker` when `has-docker: true` or a root `Dockerfile` exists, plus `npm` when `package.json` exists).
- `release-please-config.json` at the repo root.

## `config-ownership-check.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/config-ownership-check.yml`)
that triggers on pull requests:

```yaml
name: Config Ownership Check

on:
  pull_request:

jobs:
  config-ownership:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/config-ownership-check.yml@<sha>
    # All inputs are optional — defaults shown in comments:
    # with:
    #   deploy-config-glob: "deploy/**/*.{yml,yaml} **/docker-compose*.{yml,yaml} kubernetes/**/*.{yml,yaml} helm/**/*.{yml,yaml}"
    #   orchestration-only-patterns: ""
    #     # When empty, a conservative built-in set is used (ports, volumes,
    #     # resource limits, health checks, secrets references, etc.).
    #     # Override with newline-separated Python regex patterns — one per line:
    #     # orchestration-only-patterns: |
    #     #   .*_PORT$
    #     #   .*_MEMORY_LIMIT$
    #   ui-config-glob: ""
    #     # Only set when the repo hosts a central-deploy UI.  Most repos
    #     # should leave this empty.
    #   base-ref: ""
    #     # Git ref to diff against.  When empty, merge-base with origin/main
    #     # (or main) is used automatically.
```

See [Workflow Reference](docs/workflow-reference.md) for all inputs and the
config-ownership model description.

## `codeql.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/codeql.yml`)
that triggers on push, pull request, and a weekly schedule:

```yaml
name: CodeQL
on:
  push:
    branches: ["main"]
  pull_request:
  schedule:
    - cron: "0 7 * * 1"  # weekly on Monday
permissions:
  contents: read
jobs:
  codeql:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/codeql.yml@<sha>
    # All inputs are optional — defaults shown in comments:
    # with:
    #   languages: "python"                   # default
    #   queries: "security-and-quality"       # default
    #   config-file: ".github/codeql/codeql-config.yml"  # optional
    #   build-mode: "none"                    # optional; "none", "autobuild", or "manual". Empty = autobuild step runs
    #                                         # ("none" skips the autobuild step — use for Python)
    #   runs-on: "ubuntu-latest"              # default
    permissions:
      # Required — the reusable workflow needs security-events: write
      # to upload SARIF results to code scanning.
      security-events: write
      contents: read
```

**Consumer prerequisites:**

- The calling job must declare `permissions.security-events: write` so
  CodeQL SARIF results can be uploaded to the repository's code scanning.

- **Optional:** a `.github/codeql/codeql-config.yml` file in the calling
  repo to customise query packs, paths, or exclusion patterns.  Pass its
  path via the `config-file` input.  Example config:

  ```yaml
  name: "Custom CodeQL config"
  disable-default-queries: false
  queries:
    - uses: security-and-quality
  paths:
    - src
  paths-ignore:
    - tests
    - '**/*.test.py'
  ```

## `dependency-review.yml` — caller template

Consumer repos add a wrapper workflow (e.g.
`.github/workflows/dependency-review.yml`) that triggers on pull requests.
The `actions/dependency-review-action` SHA is pinned once here, so
Dependabot bumps it for every caller.

```yaml
name: Dependency Review
on:
  pull_request:
permissions:
  contents: read
jobs:
  dependency-review:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/dependency-review.yml@<sha>
    # All inputs are optional — defaults shown in comments:
    # with:
    #   fail-on-severity: "moderate"          # default
    #   config-file: ".github/dependency-review-config.yml"  # optional
    #   deny-licenses: "GPL-2.0-only, GPL-3.0-only, AGPL-3.0-only"  # optional
    #   allow-licenses: ""                    # optional, exclusive with deny-licenses
    #   comment-summary-in-pr: true           # default
    #   runs-on: "ubuntu-latest"              # default
    permissions:
      contents: read
      pull-requests: write  # PR summary comment
```

**Inputs:**

| Input | Default | Description |
|---|---|---|
| `fail-on-severity` | `moderate` | Lowest severity (`low`/`moderate`/`high`/`critical`) that fails the check. Overrides the same key in `config-file`. |
| `config-file` | `""` | Path to a dependency-review-action config file in the calling repo (the repo is checked out only when this is set). |
| `deny-licenses` | `""` | Comma-separated SPDX identifiers that fail the check. |
| `allow-licenses` | `""` | Comma-separated SPDX identifiers that are the only ones allowed. Mutually exclusive with `deny-licenses`. |
| `comment-summary-in-pr` | `true` | Post the review summary as a PR comment. |
| `runs-on` | `ubuntu-latest` | Runner label for the job. |

The job is skipped (clean "skipped" status) on any event other than
`pull_request`, so the wrapper may share a file with push triggers.

## `bump.yml` — caller template

Shared bump *engine* behind the `deps-bump.yml` and `pin-bump.yml`
wrappers — both are thin delegates that only set `bump-mode`.  Consumers
that need the engine directly, or a caller-controlled `bump-mode`, add a
wrapper workflow (e.g. `.github/workflows/bump.yml`) that triggers on a
weekly schedule + manual dispatch:

```yaml
name: Bump
on:
  schedule:
    - cron: "0 8 * * 1"  # Monday 08:00 UTC
  workflow_dispatch:
jobs:
  bump:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/bump.yml@<sha>
    with:
      bump-mode: "deps"   # "deps" = uv lock --upgrade-package; "pins" = scripts/pin-bump.py per-repo
      packages: "robotsix-mill robotsix-llmio"  # space-separated; omit for "pins" to bump all git-sourced
      app-id: "3752211"   # fleet GitHub App
    # Optional inputs — defaults shown:
    #   uv-version: "0.12.5"
    #   default-branch: "main"
    #   bump-branch: "deps-bump/first-party"
    #   permission-contents: "write"
    #   permission-pull-requests: "write"
    secrets:
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}  # GitHub App private key
```

The workflow pushes commits and creates PRs with a caller-supplied GitHub
App credential — never `GITHUB_TOKEN`, which suppresses workflow runs on
the bump PR (so CI never fires).  `app-id` + `app-private-key` are
required.  For standard fleet usage prefer the self-documenting
`deps-bump.yml` / `pin-bump.yml` wrappers.

## `deps-bump.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/deps-bump.yml`)
that triggers on a weekly schedule + manual dispatch:

```yaml
name: Deps Bump
on:
  schedule:
    - cron: "0 8 * * 1"  # Monday 08:00 UTC
  workflow_dispatch:
jobs:
  bump:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/deps-bump.yml@<sha>
    with:
      packages: "robotsix-mill robotsix-llmio"  # space-separated first-party packages
      app-id: "3752211"  # fleet GitHub App
    secrets:
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}  # GitHub App private key
```

## `dependabot-auto-merge.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/dependabot-auto-merge.yml`)
that triggers on `pull_request`:

```yaml
name: Dependency Bot Auto-Merge

on:
  pull_request:

jobs:
  auto-merge:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/dependabot-auto-merge.yml@<sha>
```

The workflow declares no inputs and no secrets.  The calling job needs
`contents: write` and `pull-requests: write` permissions, which the reusable
workflow requests on the `auto-merge` job.  It auto-merges PRs from
Dependabot, Renovate, and robotsix-mill bot actors, labels them
`Skip-Changelog`, and squash-merges via `gh pr merge --auto --squash
--delete-branch` with a fallback for repos without branch protection.

## `lint-workflows.yml` — caller template

Lints the repo's own workflow files (actionlint + zizmor) and validates that
every reusable workflow uploading SARIF has `security-events: write` on its
calling jobs. All checks are opt-in via inputs:

```yaml
name: Lint Workflows
on:
  push:
    branches: ["main"]
  pull_request:
jobs:
  lint-workflows:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/lint-workflows.yml@<sha>
    with:
      run-actionlint: true
      run-zizmor: true
      # sarif-workflows: "codeql.yml scan-container.yml scorecard.yml"  # default
      # dockerfiles: "Dockerfile sandbox/Dockerfile"  # opt-in FROM digest-pin gate; default "" skips
      # run-workflow-rules: true  # opt-in workflow-conventions checker
      # workflow-rules: "sha-pin,persist-credentials,static-defaults"  # default; or "all"
      # trivyignore: .trivyignore  # opt-in "# expires: YYYY-MM-DD" gate; default "" skips
      # trivyignore-missing-expiry: warn  # or "fail" for entries without an expiry
```

## `lint-dockerfile.yml` — caller template

Runs [hadolint](https://github.com/hadolint/hadolint) on the listed
Dockerfiles. Paths that do not exist are ignored; when nothing matches, the
lint step is skipped with a notice.

```yaml
name: Lint Dockerfile
on:
  push:
    branches: ["main"]
  pull_request:
jobs:
  hadolint:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/lint-dockerfile.yml@<sha>
    with:
      dockerfiles: "Dockerfile Dockerfile.dev"  # space-separated paths/globs; default "Dockerfile"
      # failure-threshold: warning  # default
      # config: .hadolint.yaml      # optional hadolint config
      # upload-sarif: false         # default — true adds a hadolint-sarif job that
      #   # uploads findings to code scanning (category `hadolint`).
      #   # REQUIRES the calling job to grant `security-events: write` (+ contents: read).
```

To publish findings to code scanning, opt in and grant the permission on the
calling job (the `hadolint-sarif` job inherits the caller's token; callers
that leave `upload-sarif` off need no extra permission):

```yaml
jobs:
  hadolint:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/lint-dockerfile.yml@<sha>
    permissions:
      contents: read
      security-events: write
    with:
      upload-sarif: true
```

## `pin-bump.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/pin-bump.yml`)
that triggers on a weekly schedule + manual dispatch:

```yaml
name: Pin Bump
on:
  schedule:
    - cron: "0 10 * * 1"  # Monday 10:00 UTC
  workflow_dispatch:
jobs:
  bump:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/pin-bump.yml@<sha>
    with:
      packages: "robotsix-mill robotsix-llmio"  # space-separated subset of git-pinned names (`[tool.uv.sources]` or PEP 508 `name @ git+URL@<sha>`); omit for all
      app-id: "3752211"  # fleet GitHub App
    secrets:
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}  # GitHub App private key
```

## `pin-bump-sweep.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/pin-bump-sweep.yml`)
that triggers on a weekly schedule + manual dispatch:

```yaml
name: Pin Bump Sweep
on:
  schedule:
    - cron: "0 6 * * 1"  # Monday 06:00 UTC
  workflow_dispatch:
jobs:
  sweep:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/pin-bump-sweep.yml@<sha>
    with:
      owner: "damien-robotsix"  # GitHub org/owner to sweep; default shown
      app-id: "3752211"  # fleet GitHub App
    secrets:
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}  # GitHub App private key
```

Each repo's force-push of the `pin-bump/sweep` branch is retried up to 3 times
(10 s, 20 s, 40 s back-off) when GitHub returns a transient 5xx (e.g.
`remote: Internal Server Error`, `HTTP 5xx`, `The remote end hung up
unexpectedly`); auth, protected-branch and non-fast-forward rejections still
fail immediately. A repo that succeeded only after a retry is listed under
`### Bumped` in the sweep summary with a `(retried N×)` note, and each retry
logs the GitHub request id.

## `python-security.yml` — caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/python-security.yml`)
that triggers on `push`/`pull_request` targeting `main`:

```yaml
name: Python Security

on:
  push:
    branches: ["main"]
  pull_request:

jobs:
  security:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/python-security.yml@<sha>
    # All inputs are optional — defaults shown:
    # with:
    #   python-version: "3.14"
    #   uv-version: "0.8.15"
    #   install-extras: "tracing"
    #   runs-on: "ubuntu-latest"
    #   run-trufflehog: true
    #   trufflehog-pr-diff: false
    #   trufflehog-extra-args: ""
    #   run-pip-audit: true
    #   pip-audit-requirements-file: ""
    #   pip-audit-ignore-packages: ""
    #   audit-ignore-file: ".audit-ignore"   # shared with python-ci.yml
    #   pip-audit-ignore-vulns: ""           # DEPRECATED — use audit-ignore-file
```

The workflow requires only `contents: read` (declared in the reusable workflow).
It runs a single `security` job that executes TruffleHog secret scanning,
pip-audit dependency vulnerability auditing, and uploads a CycloneDX SBOM as
the `sbom` artifact.

## Branch Protection

See [docs/branch-protection.md](docs/branch-protection.md) for ruleset semantics, usage,
`gh` auth scopes, and the self-protection note.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for local development setup and test instructions.

Key commands:

- `make test` — run all test suites
- `make pytest` — run Python/pytest tests only
- `make shell-tests` — run shell script tests only
- `make lint` — run pre-commit hooks (actionlint, yamllint, shellcheck)

## Standards

This repo follows the [robotsix stack standards](https://github.com/damien-robotsix/robotsix-standards).
