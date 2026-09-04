# Changelog

## [1.0.1](https://github.com/damien-robotsix/robotsix-github-workflows/compare/v1.0.0...v1.0.1) (2026-09-03)


### Bug Fixes

* **ci:** restore workflow_call on the shared dependabot-auto-merge workflow ([#139](https://github.com/damien-robotsix/robotsix-github-workflows/issues/139)) ([290e985](https://github.com/damien-robotsix/robotsix-github-workflows/commit/290e985800ff5a6ad6e05382aaaf8ff21e0e392d))
* **dependabot-auto-merge:** mint an App token so workflow-touching PRs can merge ([#145](https://github.com/damien-robotsix/robotsix-github-workflows/issues/145)) ([ad42434](https://github.com/damien-robotsix/robotsix-github-workflows/commit/ad424349c05a3336cb418be5f37f0b2fb9e82934))
* **lint:** broaden actionlint $/-ignore to cover local action refs ([#142](https://github.com/damien-robotsix/robotsix-github-workflows/issues/142)) ([daa74f7](https://github.com/damien-robotsix/robotsix-github-workflows/commit/daa74f7c13e04bc77109021922e3fcaa9644b75c))
* **lint:** run shared lint scripts from the workflow repo, not the caller ([#143](https://github.com/damien-robotsix/robotsix-github-workflows/issues/143)) ([8e713c7](https://github.com/damien-robotsix/robotsix-github-workflows/commit/8e713c7c8867caa653483a934e2b74a62e31fc0b))

## 1.0.0 (2026-08-31)


### Features

* Add CI validation for local composite action references in .github/workflows (20260821T101907Z-add-ci-validation-for-local-composite-ac-81a1) ([#100](https://github.com/damien-robotsix/robotsix-github-workflows/issues/100)) ([005743e](https://github.com/damien-robotsix/robotsix-github-workflows/commit/005743e6b88ff27fc4dec2c5c879e359ce27b624))
* copy-paste: 2-file clone in bump workflows — extract shared app-auth input contract (20260817T102904Z-copy-paste-2-file-clone-in-bump-workflow-820c) ([#99](https://github.com/damien-robotsix/robotsix-github-workflows/issues/99)) ([f343f5c](https://github.com/damien-robotsix/robotsix-github-workflows/commit/f343f5ca84b1d54bb4c2fdcb83568724aa9f743c))
* Promote mutmut mutation-test to a reusable workflow (20260817T220114Z-promote-mutmut-mutation-test-to-a-reusab-a89f) ([#98](https://github.com/damien-robotsix/robotsix-github-workflows/issues/98)) ([9134bd5](https://github.com/damien-robotsix/robotsix-github-workflows/commit/9134bd5595af397c4571fbfb659a741e7adec3a7))
* **release:** promote release-please to a reusable workflow ([#95](https://github.com/damien-robotsix/robotsix-github-workflows/issues/95)) ([b2c5f36](https://github.com/damien-robotsix/robotsix-github-workflows/commit/b2c5f36c25e318d81f89a2a0b24ae92872ba4606))
* robotsix-github-workflows: Enable triage_boilerplate periodic workflow (20260809T090254Z-robotsix-github-workflows-enable-triage-2e94) ([#84](https://github.com/damien-robotsix/robotsix-github-workflows/issues/84)) ([454851c](https://github.com/damien-robotsix/robotsix-github-workflows/commit/454851ccfdba26ba4d08f3effea09258dfc3fe2f))


### Bug Fixes

* Add self-test caller workflow for reusable workflow contract validation (20260821T131240Z-add-self-test-caller-workflow-for-reusab-8a5c) ([#112](https://github.com/damien-robotsix/robotsix-github-workflows/issues/112)) ([af32c21](https://github.com/damien-robotsix/robotsix-github-workflows/commit/af32c21418a02796b619eb22ce9b8aee79dc82c5))
* **auto-merge:** fall back to a direct merge when auto-merge is unavailable ([#73](https://github.com/damien-robotsix/robotsix-github-workflows/issues/73)) ([e33f19f](https://github.com/damien-robotsix/robotsix-github-workflows/commit/e33f19f0657947c239ffcbaf3b47f149571e2bc1))
* **auto-merge:** stop a missing Skip-Changelog label blocking every merge ([#72](https://github.com/damien-robotsix/robotsix-github-workflows/issues/72)) ([e7ad86b](https://github.com/damien-robotsix/robotsix-github-workflows/commit/e7ad86bbc792a9abbfd2cc770255d295282a34f3))
* **baseline:** accept release-please repos, not just towncrier ([#70](https://github.com/damien-robotsix/robotsix-github-workflows/issues/70)) ([a6378ac](https://github.com/damien-robotsix/robotsix-github-workflows/commit/a6378accaf26c75b12fac324c3056255647c107b))
* **ci:** grant the release caller job the write permissions the reusable workflow needs ([#134](https://github.com/damien-robotsix/robotsix-github-workflows/issues/134)) ([94d7adb](https://github.com/damien-robotsix/robotsix-github-workflows/commit/94d7adb43db9ddd7222ad25834231ac41314359b))
* completeness_check scan: 2 findings (2026-08-21) (20260821T104018Z-completeness-check-scan-2-findings-2026-5aea) ([#101](https://github.com/damien-robotsix/robotsix-github-workflows/issues/101)) ([34e5362](https://github.com/damien-robotsix/robotsix-github-workflows/commit/34e53629ee72af5abda012115d62a3b2bff6e058))
* Fix local-action resolution in python-ci.yml reusable workflow (20260823T161654Z-fix-local-action-resolution-in-python-ci-349a) ([#122](https://github.com/damien-robotsix/robotsix-github-workflows/issues/122)) ([35150af](https://github.com/damien-robotsix/robotsix-github-workflows/commit/35150afd6879d382fd349c1b74af556f4f1b0214))
* Fix relative composite-action paths in reusable workflows (20260817T085254Z-ci-failure-dependency-bump-on-main-a8ac) ([#97](https://github.com/damien-robotsix/robotsix-github-workflows/issues/97)) ([f3a25a8](https://github.com/damien-robotsix/robotsix-github-workflows/commit/f3a25a871b70cd0cbe47371ceb65ab69f62c46a2))
* pin-bump sweep aborts the whole fleet when one repo fails to lock (20260822T183320Z-pin-bump-sweep-aborts-the-whole-fleet-wh-38e6) ([#119](https://github.com/damien-robotsix/robotsix-github-workflows/issues/119)) ([3ee051d](https://github.com/damien-robotsix/robotsix-github-workflows/commit/3ee051ddf89e047598a2a6da5c0c110605c91d70))
* pin-bump sweep is not coherent for first-party repos that pin each other (20260822T183322Z-pin-bump-sweep-is-not-coherent-for-first-51c7) ([#126](https://github.com/damien-robotsix/robotsix-github-workflows/issues/126)) ([513c343](https://github.com/damien-robotsix/robotsix-github-workflows/commit/513c343db7ee0164e60bf31412d5fcf9af17417b))
* pin-bump-sweep's weekly cron has never run: job if: excludes the schedule trigger (20260821T105536Z-pin-bump-sweep-s-weekly-cron-has-never-r-b802) ([#102](https://github.com/damien-robotsix/robotsix-github-workflows/issues/102)) ([a3580a2](https://github.com/damien-robotsix/robotsix-github-workflows/commit/a3580a2cb85b4f53faf7e4741af5cb7b0bb47cab))
* **pin-bump-sweep:** add GITHUB_STEP_SUMMARY, track skipped repos, resilient resolution ([#121](https://github.com/damien-robotsix/robotsix-github-workflows/issues/121)) ([31713aa](https://github.com/damien-robotsix/robotsix-github-workflows/commit/31713aa8d646489e00f375e628318506142288fb))
* **pin-bump-sweep:** check out this repo, not the caller's ([#115](https://github.com/damien-robotsix/robotsix-github-workflows/issues/115)) ([6da79b1](https://github.com/damien-robotsix/robotsix-github-workflows/commit/6da79b160866c3efbd5d4b145ea30122064f017b))
* **pin-bump-sweep:** justify the installation-wide token to zizmor ([#117](https://github.com/damien-robotsix/robotsix-github-workflows/issues/117)) ([a6ec1da](https://github.com/damien-robotsix/robotsix-github-workflows/commit/a6ec1daaa6273505e3bf8f90830b3ce2bf0bfb59))
* **pin-bump-sweep:** make it workflow_call-only so it runs with a caller's credentials ([#113](https://github.com/damien-robotsix/robotsix-github-workflows/issues/113)) ([07c25b8](https://github.com/damien-robotsix/robotsix-github-workflows/commit/07c25b89e01e61368f85958b41673fa193b9d058))
* **pin-bump-sweep:** mint a fleet-wide token by passing owner ([#116](https://github.com/damien-robotsix/robotsix-github-workflows/issues/116)) ([8e3f30e](https://github.com/damien-robotsix/robotsix-github-workflows/commit/8e3f30e71516dd9233a3fbda8acb0c135148d987))
* **pin-bump:** target gh at the swept repo, not the CWD ([#118](https://github.com/damien-robotsix/robotsix-github-workflows/issues/118)) ([284c459](https://github.com/damien-robotsix/robotsix-github-workflows/commit/284c45946f90721cacf947f0a6943150566f84a8))
* **python-ci:** skip the burndown nudge when the baseline is empty ([#124](https://github.com/damien-robotsix/robotsix-github-workflows/issues/124)) ([98b5cbb](https://github.com/damien-robotsix/robotsix-github-workflows/commit/98b5cbbec2a5c3b1343b4c9fae9b3fb0b3f0c4ef))
* **python-security:** scan with TruffleHog before installing dependencies ([#137](https://github.com/damien-robotsix/robotsix-github-workflows/issues/137)) ([49e3747](https://github.com/damien-robotsix/robotsix-github-workflows/commit/49e37477e8c1a1a3436e1618750a632bf275359f))
* **release-please:** retry the lock sync when the release branch moves ([#96](https://github.com/damien-robotsix/robotsix-github-workflows/issues/96)) ([2d66a20](https://github.com/damien-robotsix/robotsix-github-workflows/commit/2d66a20eef37f8b8dd5bb66cc134c76dbbf9ad39))
* resolve composite actions absolutely in the remaining reusable workflows ([#123](https://github.com/damien-robotsix/robotsix-github-workflows/issues/123)) ([ddcc5b5](https://github.com/damien-robotsix/robotsix-github-workflows/commit/ddcc5b57eba4914708fc64dbf30c446a3fdbe4da))
* scripts/pin-bump.py: sweep() and its four helpers have zero test coverage (20260821T185555Z-scripts-pin-bump-py-sweep-and-its-four-h-3d3a) ([#125](https://github.com/damien-robotsix/robotsix-github-workflows/issues/125)) ([9055f06](https://github.com/damien-robotsix/robotsix-github-workflows/commit/9055f06a3b70b8d7452482cde349ce3444d5fbfe))
* **uv:** bump the default uv 0.8.15 → 0.12.5 across the shared workflows ([#136](https://github.com/damien-robotsix/robotsix-github-workflows/issues/136)) ([99d6b3d](https://github.com/damien-robotsix/robotsix-github-workflows/commit/99d6b3da069f81ddc7194520c5b1dca4347154a2))

## 0.0.0 (unreleased)

- Add Rule 6 to `AGENT.md`: reusable-workflow Python must live in `scripts/*.py` as importable modules, never inline `python3 << 'PYEOF'` heredocs.
- Restore `use-gha-cache` timing prose in `docs/workflow-reference.md` that was
  dropped during the health-ticket docs split (the README pointer is now live again).
- Replace empty `repos: []` in `.pre-commit-config.yaml` with canonical hook set: `actionlint` (workflow syntax/expression validation), `yamllint` (YAML formatting), and `shellcheck` (shell script linting in `run:` blocks).
- Extracted inline Python from `config-ownership-check.yml` and `lint-workflows.yml` into
  dedicated scripts (`config_ownership_check.py`, `lint_sarif_permissions.py`) so the
  logic is testable and the workflow YAML stays lean.  Updated the integration test for
  config-ownership to call the shared module instead of a stale heredoc copy.
- Added `tests/test-lint-sarif-permissions.py` (19 tests covering SARIF-upload
  permission validation) and `tests/test-baseline-check.sh` (AGENT.md and LICENSE
  checks) to close test-coverage gaps for the fleet's own CI gates.
- Moved Branch Protection deep-dive into `docs/branch-protection.md` and added
  `docs/workflow-reference.md` (consolidated input/default/secret reference for all
  16 reusable workflows).  Kept README.md as a browsable overview with links into
  the docs directory.
- Extract the duplicated bump/release prelude (GitHub App token minting, credentialed checkout, `astral-sh/setup-uv` install, git identity) into a shared composite action `.github/actions/bump-setup/action.yml`. `deps-bump.yml`, `pin-bump.yml`, `auto-release.yml`, and `pin-bump-sweep.yml` now reference it (a `bump-setup` step with `id: setup`, exposing the minted token via `steps.setup.outputs.token`) instead of copy-pasting the same `~80` lines, so a token/action/version-pin update now lands in one place.
- `python-ci.yml`: run `coverage combine` before uploading the `coverage-data` artifact so the `.coverage` database is always included — fixes `No data to report.` errors in `python-coverage-comment-action` for consumers with `[tool.coverage.run] parallel = true`.
- Fix pre-existing zizmor `--persona=pedantic` error-level findings across six workflow files: replace spoofable `github.actor` bot checks with `github.event.pull_request.user.login` in `dependabot-auto-merge.yml`, scope `actions/create-github-app-token` calls with explicit `repositories:` (single-repo workflows) and limit token permissions via `permission-*` inputs on every token-minting step, keep `pin-bump-sweep.yml`'s token fleet-wide (restricting it to one repo would 403 the org enumeration and cross-repo PRs), and move `docker-release.yml` permissions from workflow-level to job-level with `permissions: {}` as the default-deny baseline.
- Extract Trivy SARIF scan + upload into a shared composite action (`.github/actions/trivy-sarif/action.yml`). Replaces the two-step SARIF+upload tail in `docker-pr-scan.yml`, `docker-release.yml`, and `scan-container.yml` with a single `uses:` reference, eliminating ~40 lines of byte-identical duplication.
- Add `ci.yml` caller workflow — dogfoods `lint-workflows.yml` (actionlint + zizmor), runs the config-ownership integration test, and validates workflow YAML schema via `mpalmer/action-validator` on every push to `main` and every pull request.
- README: add missing `python-security.yml` and `dependabot-auto-merge.yml` caller-template sections, and fix stale `sarif-workflows` default comment in `lint-workflows.yml` section
- Move periodic agent configs from `.robotsix-mill/` root into `.robotsix-mill/periodic/*.yaml` files to match the mill periodic loader convention.
- Bootstrap `.robotsix-mill/` periodic workflow presence files for `audit`, `health`, `survey`, `changelog_autofill`, `repo_description_sync`, `completeness_check`, and `copy_paste`.
- Add `config-ownership-check.yml` reusable workflow — a PR gate that
  prevents deploy-plane config (docker-compose, Kubernetes, Helm) from
  introducing environment variables for component-internal settings.
  New env vars are checked against a conservative orchestration-only
  whitelist (ports, volumes, resource limits, health checks, etc.);
  violations cite robotsix-standards config-standard.md.  An opt-in
  central-deploy UI check flags component-internal setting names in UI
  config files.  Includes integration tests (compliant change passes,
  violating change fails) and a README caller template.
- `python-ci.yml`: upload `coverage-data` artifact (`coverage.xml` + `.coverage`) after test runs, and emit `--cov-report=xml:coverage.xml` so the XML report is always available for downstream coverage-diff tooling.
- **Breaking:** all four bump/release reusable workflows (`pin-bump.yml`, `auto-release.yml`, `deps-bump.yml`, `pin-bump-sweep.yml`) now require a GitHub App (`app-id` input + `app-private-key` secret). All PAT fallback secrets (`bump-token`, `release-token`, `sweep-token`) have been retired. Every workflow mints installation tokens via `actions/create-github-app-token` with a single consistent input/secret naming convention.
- Add `job_split` input to `python-ci.yml` (default `false`). When `true`,
  emits separate `lint`, `typecheck`, and `test` jobs instead of one
  monolithic `tests` job, reducing CI wall-clock time from ~sum-of-all to
  ~max-of-three.
- Make `uv` ecosystem requirement in baseline-check.yml conditional on `pyproject.toml`, matching the existing Docker and npm auto-detection patterns. Fixes a recurring CI ping-pong where Dependabot fails on repos without Python code.
- `python-security.yml`: change SBOM artifact upload `if-no-files-found` from `error` to `warn` so that best-effort SBOM generation (which uses `|| true`) doesn't cause a hard CI failure when `sbom.json` is absent.
- `dependabot-auto-merge.yml`: extend auto-merge to `robotsix-mill[bot]` PRs so mill-authored branches have a merge path instead of silently skipping.
- `python-ci.yml`: remove unused `security-events:write` job permission (the workflow never uploads SARIF results), eliminating `startup_failure` when the caller cannot grant the scope.
- `python-docs.yml`: guard `deploy` job with `if: github.event_name != 'pull_request'` so Pages permissions are only evaluated on push-to-main, not on PR branches.
- `lint-workflows.yml`: drop `python-ci.yml` from the default `sarif-workflows` list (it no longer uploads SARIF).
- README: document explicit `permissions` blocks for `python-ci.yml` and `python-docs.yml` caller templates.
- Guard `pin-bump-sweep` job with `if: github.event_name == 'workflow_call'` to prevent scheduled/dispatch runs from failing when the `sweep-token` repository secret is not configured.
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
