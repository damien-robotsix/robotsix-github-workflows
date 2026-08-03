# Branch Protection

The fleet standard branch-protection posture is applied via
`scripts/apply-branch-protection.sh` — an idempotent operator script safe to
re-run any number of times.  It enforces:

- **Repository rulesets** (not classic branch protection) — the script creates
  or updates a `robotsix-fleet-protection` ruleset targeting `refs/heads/main`.
- **PRs required** (`pull_request` rule with 0 required reviews — no direct pushes).
- **Squash merge only** (`allow_squash_merge=true` at the repo level; merge-commit
  and rebase-merge disabled; `pull_request` rule restricts `allowed_merge_methods`
  to `["squash"]`).
- **Force-push disabled** (`non_fast_forward` rule).
- **Branch deletion disabled** (`deletion` rule).
- **Linear history required** (`required_linear_history` rule — consistent
  with squash-only merges).
- **Required status checks** (`required_status_checks` rule with strict policy,
  derived per repo from actual check-run names on the tip of `main`, filtered
  to the shared-workflow gate jobs `baseline`, `tests`, `security`, `scan`).
  Repos that do not produce a given check (e.g. a workflow-library repo has no
  `tests`) are not required to pass it.
- **No required approving reviews** — the `pull_request` rule sets
  `required_approving_review_count` to `0` so the fleet's automated
  auto-release and Dependabot auto-merge flows still function without a human
  reviewer in the loop.
- **Optional App bypass** — when `BYPASS_APP_ID` is set, the designated GitHub
  App is added as an `always` bypass actor.  This allows the fleet's
  `auto-release.yml` (authenticated as a GitHub App) to direct-push release
  commits and tags to `main`, eliminating the PR+auto-merge fallback that
  classic branch protection required.  Without `BYPASS_APP_ID`, no bypass
  actor is configured and *everyone* must go through PRs.

**Behaviour change from classic protection:** Under classic branch protection
`enforce_admins: false` allowed repository admins to push directly to `main`
(e.g. for emergency hotfixes).  Repository rulesets apply to *everyone* by
default, and this migration does **not** add an admin bypass actor — only the
release App (when `BYPASS_APP_ID` is set) can bypass.  Human admins must now
go through PRs like everyone else.  This is an intentional, operator-approved
tightening.

## Usage

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

# Add a GitHub App bypass actor so auto-release can direct-push to main:
BYPASS_APP_ID=123456 scripts/apply-branch-protection.sh my-repo
```

## When to run

- **At repo creation** — new repos start with no branch protection and must
  be brought into the fleet baseline.
- **When the shared required-check set changes** — e.g. a new gate job is
  added to the fleet workflows, or an existing one is renamed.  Re-run the
  script across all repos to pick up the new contexts.

The script is **idempotent**: re-running it against an already-configured
repo produces no configuration change and exits 0.  Repos whose default
branch is not `main` are **skipped** (warning printed, non-fatal).

## Self-protection note

`robotsix-github-workflows` itself must run this script — its `main` branch
is currently unprotected, which violates the repo-baseline it hosts for the
fleet.  Run once after deploying the updated script:

```bash
BYPASS_APP_ID=<release-app-id> scripts/apply-branch-protection.sh robotsix-github-workflows
```

## Required `gh` auth scopes

The authenticated `gh` token needs:

| Scope | Why |
|---|---|
| `repo` | Read repo settings, list repos, read check-run names. |
| `administration:write` | Create/update repository rulesets and remove classic branch protection. |

A token lacking `administration:write` will receive a **403 Forbidden** when
the script attempts to create or update a ruleset.  The script reports this
clearly and continues to the next repo.

## `--dry-run` and `CHECKS=`

| Option | Effect |
|---|---|
| `--dry-run` | Print the intended `gh api` calls and JSON bodies; no mutations are performed. |
| `CHECKS=…` | Comma-separated list of exact status-check contexts (e.g. `"Baseline Check / baseline,Python CI / tests"`).  Skips per-repo derivation entirely.  Use when you know the exact set of required contexts for a repo. |
| `BYPASS_APP_ID=…` | Numeric GitHub App ID added as a ruleset bypass actor.  The App can direct-push to `main` (bypasses the `pull_request` rule and required status checks), needed for `auto-release.yml`.  Leave unset for no bypass actor — then *everyone* must go through PRs. |
