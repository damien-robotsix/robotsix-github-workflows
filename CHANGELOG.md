## 0.0.0 (unreleased)

- `scripts/apply-branch-protection.sh`: `KNOWN_GATES` trailing-segment match is now case-insensitive, preventing the ruleset from requiring stale contexts when shared-workflow job names change casing (e.g. `Tests` vs `tests`).  Documented the need to re-run the script after any change that renames gate jobs.
- `python-docs.yml`: build step now passes `--strict` to `mkdocs build`, turning warnings into hard errors.  Build job gained `pages: read` permission (needed by `configure-pages`).  Added caller template to `README.md` documenting the Pages `build_type: workflow` prerequisite and the correct (none-needed) caller permissions.
- `docker-pr-scan.yml`: add `use-gha-cache` boolean input (default `true`) to let callers skip the GHA layer cache for large images where cache export dominates build time.
- `python-ci.yml`: add `audit-ignore` input for passing GHSA/CVE ids as `--ignore-until-fixed` flags to `uv audit`, matching the fleet policy of blocking on fixable findings only. Document the justifying-comment convention in the README caller template.
- `auto-release.yml` now regenerates `uv.lock` after bumping the version in `pyproject.toml`, so the release commit passes the `uv lock --check` freshness gate in CI. Uses `uv lock --upgrade-package <project-name>` (not bare `uv lock`) to avoid silently pulling new commits of git dependencies.
- `pin-bump.yml`: add optional `app-id` input + `app-private-key` secret for GitHub App authentication (mirrors auto-release.yml pattern). The existing `bump-token` PAT remains as the fallback when `app-id` is not set.
- Migrate `scripts/apply-branch-protection.sh` from classic branch protection to
  GitHub repository rulesets. The script now creates/updates a
  `robotsix-fleet-protection` ruleset (PRs required, required status checks,
  squash-only, linear history, no force-push/deletion) and removes classic
  protection after applying the ruleset.  Set `BYPASS_APP_ID` to add a GitHub
  App as a bypass actor so auto-release can direct-push to main.
  **Behaviour change:** Under classic protection `enforce_admins: false`
  allowed repository admins to push directly to `main` (e.g. for emergency
  hotfixes).  Repository rulesets apply to *everyone* by default, and this
  migration does **not** add an admin bypass actor — only the release App
  (when `BYPASS_APP_ID` is set) can bypass.  Human admins must now go
  through PRs like everyone else.  This is an intentional, operator-approved
  tightening.
- Add `changelog-check.yml` reusable workflow — a towncrier fragment gate for pull requests that is skipped when the PR carries the `skip-changelog` label.
- `auto-release.yml`: support authenticating as a **GitHub App** (`app-id` input + `app-private-key` secret; installation token minted in-workflow via `actions/create-github-app-token`) as the preferred alternative to a PAT — `release-token` becomes optional, with a fail-fast check when neither credential is supplied. The protected-branch fallback now also handles **squash-only** repos: when merge commits are disallowed it enables squash auto-merge instead of leaving the release PR open.
- Added README caller-template sections for `pin-bump.yml` and `pin-bump-sweep.yml`.
- Add `pin-bump.yml` reusable workflow (`workflow_call`) that resolves the latest commit on the default branch of every ``[tool.uv.sources]`` git-sourced dependency and rewrites the ``rev`` field, runs ``uv lock``, and opens a PR. Add `pin-bump-sweep.yml` scheduled (weekly Monday 06:00 UTC) + ``workflow_dispatch`` + ``workflow_call`` workflow that performs a coherent-set fleet-wide sweep: enumerates all fleet repos, collects git-sourced pins, resolves each unique URL *once*, and opens PRs in every affected repo with the same SHA.
- Enhanced `baseline-check.yml` with new checks: README links robotsix-standards, LICENSE is MIT, npm ecosystem auto-detection in dependabot.yml, changelog.d/ and towncrier config validation. Added optional `has-board` input for modules.yaml drift gate (robotsix-modules validate/check-registration/validate-paths). Added MIT LICENSE and uv ecosystem to this repo's own dependabot.yml.
- Add `queries` and `config-file` inputs to the shared `codeql.yml` reusable workflow.  `queries` defaults to `security-and-quality`; `config-file` supports per-repo CodeQL configuration files (e.g. `.github/codeql/codeql-config.yml`).
- Create minimal `.pre-commit-config.yaml` (empty `repos: []`) and restore the `pre-commit` ecosystem
  in Dependabot config — the repo had no `.pre-commit-config.yaml`, causing the weekly update job to
  fail with "dependency_file_not_found", but the baseline check requires the ecosystem entry.
- Remove `uv` (Python) package-ecosystem from Dependabot config — this
  repo has no Python dependency files, causing Dependabot CI failures.
- Add `lint-workflows.yml` reusable workflow that validates SARIF-uploading jobs declare `security-events:write` (prevents silent `startup_failure` on workflow dispatch). Includes optional `actionlint` and `zizmor` jobs gated behind `run-actionlint` / `run-zizmor` boolean inputs (both default `false`).
- Add `deps-bump.yml` reusable workflow for scheduled first-party pin bumps via `uv lock --upgrade-package`.
- Enforce 80% coverage floor as hard minimum in `python-ci.yml`: default threshold raised from 70 to 80, with a validation step that rejects caller-supplied values below 80.
- Add `scan-container.yml` shared workflow: weekly Trivy rescan of published :main image (SARIF, report-only). Callers provide `on: schedule:` in their local wrapper; the reusable workflow handles Trivy scan + SARIF upload to Code Scanning with no gate/exit-code.
- Add `codeql.yml` reusable workflow for CodeQL static analysis across the fleet
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
