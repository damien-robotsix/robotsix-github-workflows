# robotsix-github-workflows

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/damien-robotsix/robotsix-github-workflows/badge)](https://scorecard.dev/viewer/?uri=github.com/damien-robotsix/robotsix-github-workflows)

Shared **reusable** GitHub Actions workflows (`workflow_call`) for the robotsix fleet.
Consumers reference these SHA-pinned, e.g.:

```yaml
jobs:
  tests:
    uses: damien-robotsix/robotsix-github-workflows/.github/workflows/python-ci.yml@<sha-of-vX.Y.Z> # vX.Y.Z
```

**Pinning.** Every `uses:` ref must be a 40-char commit SHA followed by a
`# vX.Y.Z` comment, e.g.
`python-ci.yml@86a722f2938c1dda343bbf8d3c5989613cbf1794 # v1.5.0`
([WORKFLOW-AUTHORING Rule 1](docs/WORKFLOW-AUTHORING.md);
enforced by the `sha-pin` check in `scripts/check_workflow_rules.py`, which
rejects unlabelled refs and `# main`). Resolve the SHA for a tag with
`git ls-remote https://github.com/damien-robotsix/robotsix-github-workflows "refs/tags/vX.Y.Z^{}" "refs/tags/vX.Y.Z"`
(prefer the peeled `^{}` line). Keep the comment version-shaped: Dependabot's
`github-actions` ecosystem only updates `# vX.Y.Z` comments, so `# main`,
SHA or date labels go stale. The `<sha-of-vX.Y.Z> # vX.Y.Z` placeholders in
the caller templates in the
[Workflow Reference](docs/workflow-reference.md) follow this form.

Each workflow links to its section in the
[Workflow Reference](docs/workflow-reference.md), which holds the caller
template, inputs, defaults and secrets.

| Workflow | Purpose |
|---|---|
| [`python-ci.yml`](docs/workflow-reference.md#python-ciyml) | lint/format/type/test gate for Python packages |
| [`python-security.yml`](docs/workflow-reference.md#python-securityyml) | bandit / pip-audit / trufflehog security scan |
| [`python-docs.yml`](docs/workflow-reference.md#python-docsyml) | mkdocs build/deploy |
| [`auto-release.yml`](docs/workflow-reference.md#auto-releaseyml) | scheduled towncrier-driven `0.x` tag-cutting release workflow (deprecated — use `release-please.yml`) |
| [`release-please.yml`](docs/workflow-reference.md#release-pleaseyml) | conventional-commits release automation (replaces deprecated `auto-release.yml`) |
| [`docker-release.yml`](docs/workflow-reference.md#docker-releaseyml) | build + push container image |
| [`docker-pr-scan.yml`](docs/workflow-reference.md#docker-pr-scanyml) | build (no push) + Trivy CRITICAL/HIGH scan for PRs |
| [`scan-container.yml`](docs/workflow-reference.md#scan-containeryml) | weekly Trivy rescan of published :main image (SARIF, report-only) |
| [`deps-bump.yml`](docs/workflow-reference.md#deps-bumpyml) | scheduled `uv lock --upgrade` PR |
| [`bump.yml`](docs/workflow-reference.md#bumpyml) | shared bump engine behind the `deps-bump.yml` / `pin-bump.yml` wrappers (`bump-mode: deps|pins`) |
| [`dependabot-auto-merge.yml`](docs/workflow-reference.md#dependabot-auto-mergeyml) | auto-merge Dependabot PRs (protected & unprotected branch handling) |
| [`baseline-check.yml`](docs/workflow-reference.md#baseline-checkyml) | enforce repo baseline rules: AGENT.md, README.md and LICENSE (MIT), `.github/dependabot.yml` ecosystems, `release-please-config.json`, `.secrets-patterns-excluded` (warning-first until 2027-01-31), plus the opt-in modules-drift gate |
| [`codeql.yml`](docs/workflow-reference.md#codeqlyml) | CodeQL static analysis |
| [`semgrep.yml`](docs/workflow-reference.md#semgrepyml) | fleet SAST gate: Semgrep scan failing on `ERROR` findings, SARIF uploaded as a workflow artifact (`contents: read` only), plus a rule-id check on suppression comments |
| [`scorecard.yml`](docs/workflow-reference.md#scorecardyml) | OpenSSF Scorecard supply-chain posture analysis (SARIF to Code Scanning) |
| [`dependency-review.yml`](docs/workflow-reference.md#dependency-reviewyml) | PR gate: dependency-review-action vulnerability-severity + license policy check |
| [`config-ownership-check.yml`](docs/workflow-reference.md#config-ownership-checkyml) | PR gate: prevents deploy-plane config from leaking component-internal settings |
| [`lint-workflows.yml`](docs/workflow-reference.md#lint-workflowsyml) | actionlint + zizmor audit of workflow files, SARIF-upload-permission validation, trigger-coverage validation, opt-in workflow-conventions checker, opt-in Dockerfile `FROM` digest-pin check, and opt-in `.trivyignore` expiry gate |
| [`lint-dockerfile.yml`](docs/workflow-reference.md#lint-dockerfileyml) | opt-in hadolint lint of one or more Dockerfiles (skipped when none exist) |
| [`mutation-test.yml`](docs/workflow-reference.md#mutation-testyml) | weekly advisory mutmut mutation testing (HTML report + step-summary score) |
| [`pin-bump.yml`](docs/workflow-reference.md#pin-bumpyml) | scheduled per-repo first-party git pin bump PR |
| [`pin-bump-sweep.yml`](docs/workflow-reference.md#pin-bump-sweepyml) | fleet-wide coherent-set pin-bump sweep orchestrator |

Mill-domain checks (e.g. `check_kind_literals`) live in robotsix-mill's own CI, not here.

## Documentation

- [Workflow Reference](docs/workflow-reference.md) — per-workflow caller templates plus the
  consolidated input, default, and secret reference for every reusable workflow.
- [Branch Protection](docs/branch-protection.md) — ruleset semantics, usage, and required `gh` auth scopes.
- [Workflow Authoring](docs/WORKFLOW-AUTHORING.md) — conventions for authoring new reusable workflows:
  structure, input design and validation, error reporting, and the pre-commit checklist.

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
