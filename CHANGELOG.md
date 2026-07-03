## 0.0.0 (unreleased)

- Add `scripts/apply-branch-protection.sh` — an idempotent operator script that applies the fleet-standard branch-protection posture (main protected, PRs-only, squash-merge-only, force-push disabled, required-checks derived per repo from shared-workflow gate jobs).  Add "Branch protection" section to README.md with usage, when-to-run, and required `gh` auth scopes.
- Apply repo-baseline to `robotsix-github-workflows` itself: add `AGENT.md`, `.github/dependabot.yml`, and a `baseline-check.yml` caller template section in README.md.
- New reusable workflow `.github/workflows/baseline-check.yml` that enforces two mechanical repo-baseline rules across all caller repos:
  - `AGENT.md` must exist at the repo root and link to `damien-robotsix/robotsix-standards` within the first 20 lines.
  - `.github/dependabot.yml` must cover `uv`, `github-actions`, and `pre-commit` ecosystems, plus `docker` when the repo ships a container image (opt-in via `has-docker: true` or auto-detected from a root `Dockerfile`).
- Add `auto-release.yml` reusable workflow — scheduled towncrier-driven `0.x` tag-cutting release that pushes commits/tags via a caller-supplied token, with direct-push and protected-branch PR+auto-merge fallback paths. Remove the legacy `python-release.yml` PyPI-publish workflow which violates the fleet's no-package-index rule.
- Add `Skip-Changelog` label to bot-authored PRs in `dependabot-auto-merge.yml` so that fleet repos enforcing a `changelog` check do not block auto-merge for Dependabot and Renovate PRs.
- Fix `docker-release.yml` validation failure: `image-name` input `default` was `ghcr.io/${{ github.repository }}` which GitHub Actions rejects in `workflow_call` inputs. Changed default to `""` and compute the effective image name at job scope via `format('ghcr.io/{0}', github.repository)` when the input is empty.
- Add optional `image-name` input to `docker-release.yml` reusable workflow. When empty (the default), the image is published at `ghcr.io/<owner>/<repo>` of the calling repository (computed at job scope). Callers can override to publish multiple named images from a single repository.
- Add robotsix-standards reference link to README.md.
- Add reusable `dependabot-auto-merge` workflow (`on: workflow_call`) for fleet repos to auto-merge Dependabot PRs, handling both protected (--auto) and unprotected (poll checks then merge) branch configurations.
