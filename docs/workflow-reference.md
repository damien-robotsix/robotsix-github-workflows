# Workflow Reference

Consolidated caller-template, input, default, and secret reference for all
reusable workflows in this repository.  Each section ends with a
`### Caller template` showing the consumer-side wrapper workflow; the
`<sha-of-vX.Y.Z> # vX.Y.Z` placeholders stand for a 40-char commit SHA plus
its version comment (see the README's **Pinning** note).

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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/auto-release.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

## `baseline-check.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `has-docker` | boolean | `false` | Require `package-ecosystem: docker` in dependabot.yml. |
| `has-board` | boolean | `false` | Enable modules-drift job (robotsix board). |
| `python-version` | string | `3.14` | Python version for the modules-drift job. |
| `uv-version` | string | `0.8.15` | uv version for the modules-drift job. |

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/baseline-check.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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
- `.secrets-patterns-excluded` at the repo root: one regular expression per line (not gitignore globs; blank lines and `#` comments allowed), and no detect-secrets `--exclude-files .secrets-patterns-excluded` wiring in `.pre-commit-config.yaml` (see robotsix-standards `docs/secret-files-are-never-tracked.md`). Warning-first: reported as `::warning::` until 2027-01-31, failing from then.

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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/bump.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

## `codeql.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `languages` | string | `python` | Languages to analyze. |
| `queries` | string | `security-and-quality` | Query suite. |
| `config-file` | string | `""` | Path to a repo-local CodeQL configuration file (e.g. .github/codeql/codeql-config.yml). Empty = no config file. |
| `build-mode` | string | `""` | CodeQL build mode forwarded to `codeql-action/init` (`none`, `autobuild`, or `manual`). Empty = not passed to init and the autobuild step runs; when set, the autobuild step is skipped. Use `none` for Python. |
| `runs-on` | string | `ubuntu-latest` | Runner label. |

No secrets.

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/codeql.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

## `config-ownership-check.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `deploy-config-glob` | string | `deploy/**/*.{yml,yaml} **/docker-compose*.{yml,yaml} kubernetes/**/*.{yml,yaml} helm/**/*.{yml,yaml}` | Glob patterns for deploy-plane config. |
| `orchestration-only-patterns` | string | `""` | Newline-separated regex overrides. |
| `ui-config-glob` | string | `""` | Glob patterns for central-deploy UI config. |
| `base-ref` | string | `""` | Git ref to diff against. |

No secrets.

### Caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/config-ownership-check.yml`)
that triggers on pull requests:

```yaml
name: Config Ownership Check

on:
  pull_request:

jobs:
  config-ownership:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/config-ownership-check.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

## `dependabot-auto-merge.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `runs-on` | string | `ubuntu-latest` | Runner label for every job; `self-hosted` for a private repo without GitHub-hosted minutes. |

The App-token inputs (`app-id`, secret `app-private-key`) are documented in the workflow file.

### Caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/dependabot-auto-merge.yml`)
that triggers on `pull_request`:

```yaml
name: Dependency Bot Auto-Merge

on:
  pull_request:

jobs:
  auto-merge:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/dependabot-auto-merge.yml@<sha-of-vX.Y.Z> # vX.Y.Z
```

The workflow declares no inputs and no secrets.  The calling job needs
`contents: write` and `pull-requests: write` permissions, which the reusable
workflow requests on the `auto-merge` job.  It auto-merges PRs from
Dependabot, Renovate, and robotsix-mill bot actors, labels them
`Skip-Changelog`, and squash-merges via `gh pr merge --auto --squash
--delete-branch` with a fallback for repos without branch protection.

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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/dependency-review.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

The job is skipped (clean "skipped" status) on any event other than
`pull_request`, so the wrapper may share a file with push triggers.

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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/deps-bump.yml@<sha-of-vX.Y.Z> # vX.Y.Z
    with:
      packages: "robotsix-mill robotsix-llmio"  # space-separated first-party packages
      app-id: "3752211"  # fleet GitHub App
    secrets:
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}  # GitHub App private key
```

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

### Caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/docker-pr-scan.yml`) that triggers on pull requests:

```yaml
name: Docker PR Scan

on:
  pull_request:

jobs:
  scan:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/docker-pr-scan.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

### Caller template

Consumer repos add a wrapper workflow (e.g. `.github/workflows/docker-release.yml`) that triggers on pushes to `main` and on version tags:

```yaml
name: Docker Release

on:
  push:
    branches: [main]
    tags: ["v*"]

jobs:
  publish:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/docker-release.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

Every job in the reusable workflows declares `timeout-minutes` (fleet default 15).
The `publish` job in `docker-release.yml` is the exception at 20 minutes, because
large base-layer pulls, the multi-arch build and the Trivy scan can exceed 15 minutes.
Callers cannot override a `uses:` job's timeout, so raise the ceiling in the
reusable workflow itself, not in the caller.

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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/lint-workflows.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/lint-dockerfile.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/lint-dockerfile.yml@<sha-of-vX.Y.Z> # vX.Y.Z
    permissions:
      contents: read
      security-events: write
    with:
      upload-sarif: true
```

## `mutation-test.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `python-version` | string | `3.14` | Python version. |
| `timeout-minutes` | number | `120` | Job timeout in minutes. |
| `dependency-group` | string | `dev` | uv dependency group that installs mutmut. |

No secrets.

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/mutation-test.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/pin-bump.yml@<sha-of-vX.Y.Z> # vX.Y.Z
    with:
      packages: "robotsix-mill robotsix-llmio"  # space-separated subset of git-pinned names (`[tool.uv.sources]` or PEP 508 `name @ git+URL@<sha>`); omit for all
      app-id: "3752211"  # fleet GitHub App
    secrets:
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}  # GitHub App private key
```

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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/pin-bump-sweep.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/release-please.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

`sync-uv-lock` regenerates `uv.lock` on the release branch after
the version bump — turn it off for repos with no `uv.lock`.

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
| `pre-test-command` | string | `""` | Shell snippet run (bash `eval`, `UV_PROJECT_ENVIRONMENT=system`) after `uv sync --frozen` and before lint/type/test in the job that runs pytest (`tests`, or `test` when `job_split`), e.g. `uv run playwright install --with-deps chromium`. Empty → step skipped. |
| `extra-check-command` | string | `""` | Repo-specific check (bash `eval`) run after Ruff in `tests` (or `lint` when `job_split`), e.g. a config-schema drift check; non-zero exit fails the job. Empty → step skipped. |

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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/python-ci.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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
    #   test-timeout-minutes: 15                  # default — job timeout for the tests/test jobs
    #     # (fleet default 15). Raise only for slow suites; every other job has a fixed ceiling.
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
    #   pre-test-command: ""                      # default — shell snippet run after `uv sync`
    #     # and before lint/type/test in the job that runs pytest (Tests, or Test when
    #     # job_split), e.g. "uv run playwright install --with-deps chromium".
    #   extra-check-command: ""                   # default — repo-specific gate run after Ruff
    #     # (Tests, or Lint when job_split), e.g. a config-schema drift check.
    #   job_split: false                          # default — single monolithic Tests job
    #     # When true, emits three parallel jobs (Lint, Type Check, Test)
    #     # instead of one sequential Tests job.  Each reports its own
    #     # green/red status check, reducing CI wall-clock time from
    #     # ~sum-of-all to ~max-of-three.
```

Repos whose tests need extra runtime setup (e.g. Playwright browsers) or a
repo-specific gate can still adopt the shared workflow:

```yaml
jobs:
  tests:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/python-ci.yml@<sha-of-vX.Y.Z> # vX.Y.Z
    permissions:
      contents: read
    with:
      pre-test-command: uv run playwright install --with-deps chromium
      extra-check-command: uv run python scripts/check_config_schema.py
```

Both inputs reach the shell through `env:` (never `${{ }}` in `run:`) and run
with `UV_PROJECT_ENVIRONMENT=system`, so `uv run` targets the synced env.

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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/python-docs.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

**Consumer prerequisites:**

- The repository must have GitHub Pages enabled with source **"GitHub Actions"**
  (`build_type: workflow`).  Enable once per repo:
  ```bash
  gh api "repos/$(gh repo view --json nameWithOwner -q .nameWithOwner)/pages" \
    -X POST \
    -f "source[build_type]=workflow"
  ```
  or visit Settings → Pages and select "GitHub Actions" as the source.

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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/python-security.yml@<sha-of-vX.Y.Z> # vX.Y.Z
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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/scorecard.yml@<sha-of-vX.Y.Z> # vX.Y.Z
    permissions:
      # Required — SARIF upload to code scanning.
      security-events: write
      contents: read
```

Results land in the Security tab only.  The public Scorecard badge needs
`publish_results: true`, which Scorecard refuses for reusable-workflow
callers — repos that want the badge copy this repo's standalone
[`self-scorecard.yml`](../.github/workflows/self-scorecard.yml) instead.

## `semgrep.yml`

| Input | Type | Default | Description |
|---|---|---|---|
| `config` | string | `p/default` | Space-separated rulesets expanded into repeated `--config` flags (registry packs such as `p/default`, `p/python`, or repo-relative rule files). A repo-local `.semgrep.yml` / `.semgrep.yaml` / `.semgrep/` is always added on top when present. |
| `severity` | string | `ERROR` | Space-separated severities expanded into repeated `--severity` flags; the job fails (`--error`) on any finding at these levels. |
| `paths` | string | `.` | Space-separated repo-relative scan targets. |
| `exclude` | string | `""` | Space-separated path globs expanded into repeated `--exclude` flags. |
| `diff-scan` | boolean | `false` | On `pull_request` events, report only findings introduced relative to the PR base (`--baseline-commit`). Other events always run a full scan. |
| `semgrep-version` | string | `1.91.0` | Exact `semgrep` PyPI version installed with pip. |
| `check-nosemgrep-ids` | boolean | `true` | Fail when a suppression comment does not name a rule id (`scripts/check_nosemgrep_rule_ids.py`). |
| `runs-on` | string | `ubuntu-latest` | Runner label. |

No secrets (caller needs only `contents: read`).

Runs `semgrep scan --error --severity <severity>` and uploads the SARIF
results as the `semgrep-sarif` workflow artifact — not to Code Scanning, so
no `security-events: write` permission is needed.  Metrics are disabled
(`--metrics off`).

### Caller template

Semgrep is the fleet SAST standard (robotsix-standards
`docs/security-posture.md`).  Consumer repos add a wrapper workflow (e.g.
`.github/workflows/semgrep.yml`) that runs on every PR and every push to
`main`, and mark its `Semgrep / Semgrep` check as a required status check:

```yaml
name: Semgrep
on:
  push:
    branches: ["main"]
  pull_request:
permissions:
  contents: read
jobs:
  semgrep:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/semgrep.yml@<sha-of-vX.Y.Z> # vX.Y.Z
    # All inputs are optional — defaults shown:
    # with:
    #   config: "p/default"          # add language packs, e.g. "p/default p/python"
    #   severity: "ERROR"
    #   paths: "."
    #   exclude: ""                  # e.g. "tests/fixtures"
    #   diff-scan: false             # true = PR findings relative to the base commit only
    #   semgrep-version: "1.91.0"
    #   check-nosemgrep-ids: true
    #   runs-on: "ubuntu-latest"
```

The workflow needs only `contents: read`: findings are uploaded as the
`semgrep-sarif` artifact, not to the GitHub Security tab.  A repo-local
`.semgrep.yml` (or `.semgrep/` directory) is added to the configured rulesets
automatically.

**Suppressions must name a rule id.**  Write `nosemgrep: <rule-id>` after a
comment marker on the offending line (e.g. a Python `#` comment followed by
`nosemgrep: python.lang.security.audit.eval-detected.eval-detected`).  A bare
marker without a rule id silences every rule on the line and fails the
`check-nosemgrep-ids` step.

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

### Caller template

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
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/scan-container.yml@<sha-of-vX.Y.Z> # vX.Y.Z
    # with:
    #   image-name: "ghcr.io/<owner>/<repo>:main"  # default: ghcr.io/$GITHUB_REPOSITORY:main
    permissions:
      security-events: write
      contents: read
```
