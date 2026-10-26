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
- **No bypass actors** — the ruleset is written with an explicit empty
  `bypass_actors` list, so re-running the script also strips any actor added
  through the GitHub UI.  Until 2026-10-26 the fleet GitHub App was an
  `always` bypass actor (via the removed `BYPASS_APP_ID` option) so that
  `auto-release.yml` could direct-push release commits.  A bypass actor also
  skips **required status checks on PR merges**, and on 2026-10-25 a chat
  agent merged robotsix-chat #2208 with its Tests check red, turning `main`
  red.  `auto-release.yml` already falls back to a PR + auto-merge when the
  direct push is rejected, so nothing needs the bypass.  Setting
  `BYPASS_APP_ID` now makes the script exit with an error.

**Behaviour change from classic protection:** Under classic branch protection
`enforce_admins: false` allowed repository admins to push directly to `main`
(e.g. for emergency hotfixes).  Repository rulesets apply to *everyone* by
default, and this ruleset has **no** bypass actor at all — not admins, not the
fleet GitHub App.  Humans and bots go through PRs with green required checks.
This is an intentional, operator-approved tightening.

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
scripts/apply-branch-protection.sh robotsix-github-workflows
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

`BYPASS_APP_ID` is **refused** (exit 2).  A bypass actor skips required
status checks on PR merges, not only the direct-push rule — see the
"No bypass actors" bullet above.
