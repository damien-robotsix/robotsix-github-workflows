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
| `deps-bump.yml` | scheduled `uv lock --upgrade` PR |
| `dependabot-auto-merge.yml` | auto-merge Dependabot PRs (protected & unprotected branch handling) |

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

## Standards

This repo follows the [robotsix stack standards](https://github.com/damien-robotsix/robotsix-standards).
