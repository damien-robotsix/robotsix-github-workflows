## 0.0.0 (unreleased)

- Add `auto-release.yml` reusable workflow — scheduled towncrier-driven `0.x` tag-cutting release that pushes commits/tags via a caller-supplied token, with direct-push and protected-branch PR+auto-merge fallback paths. Remove the legacy `python-release.yml` PyPI-publish workflow which violates the fleet's no-package-index rule.
- Add `Skip-Changelog` label to bot-authored PRs in `dependabot-auto-merge.yml` so that fleet repos enforcing a `changelog` check do not block auto-merge for Dependabot and Renovate PRs.
- Fix `docker-release.yml` validation failure: `image-name` input `default` was `ghcr.io/${{ github.repository }}` which GitHub Actions rejects in `workflow_call` inputs. Changed default to `""` and compute the effective image name at job scope via `format('ghcr.io/{0}', github.repository)` when the input is empty.
- Add optional `image-name` input to `docker-release.yml` reusable workflow. When empty (the default), the image is published at `ghcr.io/<owner>/<repo>` of the calling repository (computed at job scope). Callers can override to publish multiple named images from a single repository.
- Add robotsix-standards reference link to README.md.
- Add reusable `dependabot-auto-merge` workflow (`on: workflow_call`) for fleet repos to auto-merge Dependabot PRs, handling both protected (--auto) and unprotected (poll checks then merge) branch configurations.
