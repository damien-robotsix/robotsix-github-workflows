## 0.0.0 (unreleased)

- Add optional `image-name` input to `docker-release.yml` reusable workflow, defaulting to `ghcr.io/${{ github.repository }}` so callers can publish multiple named images from a single repository.
- Add robotsix-standards reference link to README.md.
- Add reusable `dependabot-auto-merge` workflow (`on: workflow_call`) for fleet repos to auto-merge Dependabot PRs, handling both protected (--auto) and unprotected (poll checks then merge) branch configurations.
