# robotsix-github-workflows

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
| `auto-release.yml` | scheduled towncrier-driven `0.x` tag-cutting release workflow |
| `docker-release.yml` | build + push container image |
| `docker-pr-scan.yml` | build (no push) + Trivy CRITICAL/HIGH scan for PRs |
| `scan-container.yml` | weekly Trivy rescan of published :main image (SARIF, report-only) |
| `deps-bump.yml` | scheduled `uv lock --upgrade` PR |
| `dependabot-auto-merge.yml` | auto-merge Dependabot PRs (protected & unprotected branch handling) |
| `baseline-check.yml` | enforce AGENT.md and .github/dependabot.yml baseline rules |
| `codeql.yml` | CodeQL static analysis |

Mill-domain checks (e.g. `check_kind_literals`) live in robotsix-mill's own CI, not here.

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
    secrets:
      # MUST NOT be the default GITHUB_TOKEN — GitHub suppresses
      # workflow runs for events created by GITHUB_TOKEN, so the
      # v* tag push will NOT trigger docker-release.yml and no
      # image will ever be built. Use a fine-grained PAT, a GitHub
      # App installation token, or a deploy key.
      release-token: ${{ secrets.RELEASE_PAT }}
```

**Consumer prerequisites:**

- A `[tool.towncrier]` config in `pyproject.toml` with `directory = "changelog.d"`
  and the four fragment types `breaking`, `feature`, `bugfix`, `misc`:

  ```toml
  [tool.towncrier]
  directory = "changelog.d"
  package = "your_package"

  [[tool.towncrier.type]]
  directory = "breaking"
  name = "Breaking Changes"
  showcontent = true

  [[tool.towncrier.type]]
  directory = "feature"
  name = "Features"
  showcontent = true

  [[tool.towncrier.type]]
  directory = "bugfix"
  name = "Bug Fixes"
  showcontent = true

  [[tool.towncrier.type]]
  directory = "misc"
  name = "Miscellaneous"
  showcontent = true
  ```

- A `[project] version` on the `0.x` line (e.g. `version = "0.1.0"`).
  The workflow only handles the pre-1.0 release cadence — a non-`0.x`
  version causes a hard failure.

- An existing `docker-release.yml` caller workflow that maps `v*` tags
  to `X.Y.Z` image tags via `type=semver,pattern={{version}}`.

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
```

The workflow automatically respects `.trivyignore` in the repository root for suppressing known false positives.

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
    secrets: inherit
```

The `packages: write`, `id-token: write`, `attestations: write`, and `security-events: write` permissions are declared inside the reusable workflow and do not need to be re-declared in the caller. Secrets are passed via `secrets: inherit` so `GITHUB_TOKEN` is available for GHCR login.

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
```

**Consumer prerequisites:**

- `AGENT.md` at the repo root with a `damien-robotsix/robotsix-standards` link within the first 20 lines.
- `.github/dependabot.yml` covering at minimum `uv`, `github-actions`, and `pre-commit` ecosystems (plus `docker` when `has-docker: true` or a root `Dockerfile` exists).

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
jobs:
  codeql:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/codeql.yml@<sha>
    # with:
    #   languages: "python"  # default
```

## Branch protection

The fleet standard branch-protection posture is applied via
`scripts/apply-branch-protection.sh` — an idempotent operator script safe to
re-run any number of times.  It enforces:

- **main** branch protected (PRs required — no direct pushes).
- **Squash merge only** (`allow_squash_merge=true`; merge-commit and
  rebase-merge disabled).
- **Force-push disabled** (`allow_force_pushes: false`).
- **Branch deletion disabled** (`allow_deletions: false`).
- **Linear history required** (`required_linear_history: true` — consistent
  with squash-only merges).
- **Required status checks** derived per repo from actual check-run names on
  the tip of `main`, filtered to the shared-workflow gate jobs (`baseline`,
  `tests`, `security`, `scan`).  Repos that do not produce a given check
  (e.g. a workflow-library repo has no `tests`) are not required to pass it.
- **Admin enforcement disabled** (`enforce_admins: false`) — the fleet's
  `auto-release.yml` pushes tags and commits via an admin PAT and would be
  blocked if admin enforcement were turned on.
- **No required approving reviews** — the `required_pull_request_reviews`
  object is non-null (which is what enforces PRs-only), but
  `required_approving_review_count` is `0` so the fleet's automated
  auto-release and Dependabot auto-merge flows still function without a human
  reviewer in the loop.

### Usage

```bash
# Apply to all non-fork, non-archived repos owned by damien-robotsix:
OWNER=damien-robotsix scripts/apply-branch-protection.sh

# Apply to specific repos only:
scripts/apply-branch-protection.sh my-repo another-repo

# Dry-run — print intended API calls and JSON bodies without mutating:
scripts/apply-branch-protection.sh --dry-run

# Override the derived required-check set:
CHECKS="Baseline Check / baseline,Python CI / tests" \
  scripts/apply-branch-protection.sh my-repo
```

### When to run

- **At repo creation** — new repos start with no branch protection and must
  be brought into the fleet baseline.
- **When the shared required-check set changes** — e.g. a new gate job is
  added to the fleet workflows, or an existing one is renamed.  Re-run the
  script across all repos to pick up the new contexts.

The script is **idempotent**: re-running it against an already-configured
repo produces no configuration change and exits 0.  Repos whose default
branch is not `main` are **skipped** (warning printed, non-fatal).

### Required `gh` auth scopes

The authenticated `gh` token needs:

| Scope | Why |
|---|---|
| `repo` | Read repo settings, list repos, read check-run names. |
| `administration:write` | Set branch protection via the `branches/main/protection` endpoint. |

A token lacking `administration:write` will receive a **403 Forbidden** when
the script attempts to PUT branch protection.  The script reports this
clearly and continues to the next repo.

### `--dry-run` and `CHECKS=`

| Option | Effect |
|---|---|
| `--dry-run` | Print the intended `gh api` calls and JSON bodies; no mutations are performed. |
| `CHECKS=…` | Comma-separated list of exact status-check contexts (e.g. `"Baseline Check / baseline,Python CI / tests"`).  Skips per-repo derivation entirely.  Use when you know the exact set of required contexts for a repo. |

## Standards

This repo follows the [robotsix stack standards](https://github.com/damien-robotsix/robotsix-standards).
