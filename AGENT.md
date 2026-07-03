# AGENT.md — robotsix-github-workflows

This repo is part of the [robotsix standards](https://github.com/damien-robotsix/robotsix-standards) fleet.

**Tier:** workflow-library — ships only reusable `workflow_call` YAML; no
runtime code, no Python package, no container image.

## Repo-specific rules

### Rule 1 — Pin all actions to a 40-char commit SHA

All `uses:` lines carry a 40-character commit SHA **and** a trailing `# vX.Y.Z`
comment.  Floating tags can be force-pushed to a different (potentially
malicious) commit.  SHA-pinning guarantees supply-chain integrity and
reproducibility.

### Rule 2 — No inline `${{ }}` in `run:` blocks

Never interpolate `${{ }}` expressions directly inside `run:` shell blocks;
always pass them through the step's `env:` map.  Direct interpolation is a
template-injection vector flagged by zizmor; `env:` escapes values safely
before they reach the shell.

### Rule 3 — `persist-credentials: false` on every checkout

Every `actions/checkout` step sets `persist-credentials: false`.  The
auto-provisioned `GITHUB_TOKEN` persisted to `.git/config` by default can leak
through job artifacts or downstream steps; dropping it limits blast radius.

### Rule 4 — Job-level `if:` guards for `workflow_call` targets

For `workflow_call` triggers, prefer job-level `if:` guards over
workflow-level conditions.  Job-level guards produce a clean "skipped" status
in the GitHub Actions UI; workflow-level conditions collapse everything into a
single skip, losing per-job signal.

### Rule 5 — `workflow_call` input defaults must be static literals

`workflow_call` input `default:` values must be static string or boolean
literals — never `${{ }}` expressions.  For dynamic defaults (e.g.
`ghcr.io/<owner>/<repo>`), use `default: ""` and compute the fallback inside a
job step with `${{ inputs.x != '' && inputs.x || format('ghcr.io/{0}',
github.repository) }}`.  GitHub rejects dynamic defaults in `workflow_call`
inputs as an "Invalid workflow file" error, which causes every caller run on
that branch to fail immediately.
