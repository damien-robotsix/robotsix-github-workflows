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
| `python-release.yml` | release-please / version bump |
| `docker-release.yml` | build + push container image |
| `deps-bump.yml` | scheduled `uv lock --upgrade` PR |

Mill-domain checks (e.g. `check_kind_literals`) live in robotsix-mill's own CI, not here.
