#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# apply-branch-protection.sh
#
# Idempotent operator script that applies the robotsix fleet standard
# branch-protection posture to every fleet repo (or a user-supplied subset).
#
# Uses GitHub repository rulesets (not classic branch protection).
# Safe to re-run any number of times — an existing ruleset is updated
# in-place via PUT; a missing one is created via POST.  Classic branch
# protection is removed after the ruleset is applied, completing the
# migration.
#
# Required gh token scopes: repo, administration:write
#
# Usage:
#   scripts/apply-branch-protection.sh              # all fleet repos
#   scripts/apply-branch-protection.sh repo-a repo-b  # specific repos
#   scripts/apply-branch-protection.sh --dry-run    # preview only
#   CHECKS="ctx1,ctx2" scripts/apply-branch-protection.sh  # override checks
#   BYPASS_APP_ID=12345 scripts/apply-branch-protection.sh  # add bypass actor
# ============================================================================

# --- Configuration ---------------------------------------------------------
OWNER="${OWNER:-damien-robotsix}"
DRY_RUN=false
REPOS=()

# Optional GitHub App ID added as a ruleset bypass actor so the release
# App can direct-push to main.  Set to the numeric App ID (not the
# installation ID).  When empty or unset, no bypass actor is configured.
BYPASS_APP_ID="${BYPASS_APP_ID:-}"

# Known shared-workflow gate job names.  Required check contexts are derived
# per repo by inspecting actual check-run names on the tip of main and keeping
# only those whose trailing segment (the part after the last ' / ', or the
# whole name when there is no ' / ') matches one of these gate names.
KNOWN_GATES=(baseline tests security scan)

# --- Parse arguments -------------------------------------------------------
for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=true
      ;;
    -h|--help)
      cat <<HELP
Usage: $0 [--dry-run] [repo-name ...]

Apply the fleet-standard branch-protection posture.

Without positional arguments, operates on every non-fork, non-archived
repo owned by \$OWNER (default: damien-robotsix).  When repo names are
given, operates only on those repos.

Options:
  --dry-run       Print the intended gh api calls and JSON bodies
                  without executing any mutations.

Environment:
  OWNER           GitHub org/user name (default: damien-robotsix).
  CHECKS          Comma-separated list of exact status-check contexts.
                  Overrides the per-repo derivation.  Example:
                    CHECKS="Baseline Check / baseline,Python CI / tests"
  BYPASS_APP_ID   Numeric GitHub App ID to add as a ruleset bypass
                  actor.  When set, the App can direct-push to main
                  (needed for auto-release.yml).  Leave unset for no
                  bypass actor.  Example:
                    BYPASS_APP_ID=123456

Required gh token scopes: repo, administration:write
HELP
      exit 0
      ;;
    *)
      REPOS+=("$arg")
      ;;
  esac
done

# --- Preconditions ---------------------------------------------------------
check_prereqs() {
  local missing=()

  if ! command -v gh &>/dev/null; then
    missing+=("gh (GitHub CLI — https://cli.github.com/)")
  fi
  if ! command -v python3 &>/dev/null; then
    missing+=("python3 (required for JSON construction)")
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "ERROR: missing required tools:" >&2
    for m in "${missing[@]}"; do
      echo "  - $m" >&2
    done
    exit 1
  fi

  # Verify gh is authenticated.  The token must have 'repo' +
  # 'administration:write' scopes — we can't introspect scopes from the
  # CLI, but gh auth status confirms a valid token is present.  If the
  # token lacks the right scopes the API will return 403 and we report it
  # clearly per-repo.
  if ! gh auth status &>/dev/null; then
    echo "ERROR: 'gh' is not authenticated. Run 'gh auth login' first." >&2
    echo "The token needs these scopes: repo, administration:write" >&2
    exit 1
  fi
}

# --- Repo enumeration ------------------------------------------------------
# Prints "<name> <defaultBranch>" one per line to stdout.
# When explicit repos were given on the command line, looks each one up
# individually.  Otherwise enumerates via 'gh repo list'.
enumerate_repos() {
  if [[ ${#REPOS[@]} -gt 0 ]]; then
    # User supplied explicit repo names — validate each one.
    for repo in "${REPOS[@]}"; do
      local db
      db=$(gh api "repos/$OWNER/$repo" --jq '.default_branch' 2>/dev/null) || {
        echo "WARNING: cannot access repo '$OWNER/$repo' — skipping." >&2
        continue
      }
      echo "$repo $db"
    done
    return
  fi

  # Enumerate all non-fork, non-archived source repos for the owner.
  # --source excludes forks; --no-archived excludes archived repos.
  # We fetch the default branch so we can skip repos whose default is
  # not 'main' without an extra API call per repo.
  gh repo list "$OWNER" --source --no-archived --limit 200 \
    --json name,defaultBranchRef \
    --jq '.[] | "\(.name) \(.defaultBranchRef.name // "")"' 2>/dev/null || {
    echo "ERROR: failed to list repos for owner '$OWNER'." >&2
    echo "Check that your token has 'repo' scope and the org/user name is correct." >&2
    exit 1
  }
}

# --- Check derivation ------------------------------------------------------
# Prints one check-run name per line (the FULL observed name, e.g.
# "Baseline Check / baseline").  Filters to known gate job names only.
#
# Falls back to "baseline" when no matching check runs exist yet — e.g. a
# brand-new repo whose CI has never executed.  Every fleet repo must wire
# up baseline-check.yml, so "baseline" is always a safe minimum.
#
# The optional CHECKS env var (comma-separated exact contexts) short-circuits
# all derivation.  Use it when you know the exact set of required contexts.
derive_checks() {
  local repo="$1"

  # CHECKS override: operator specifies exact contexts, comma-separated.
  # We split on commas, trim whitespace, and print one per line.
  if [[ -n "${CHECKS:-}" ]]; then
    echo "${CHECKS}" | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | grep -v '^$' || true
    return
  fi

  # Fetch check-run names from the tip of main.
  local runs
  runs=$(gh api "repos/$OWNER/$repo/commits/main/check-runs" \
    --jq '.check_runs[].name' 2>/dev/null) || true

  if [[ -z "$runs" ]]; then
    # No check runs on main.  This happens for brand-new repos whose
    # CI has never executed, or repos with an empty commit history.
    # Fall back to 'baseline' only — every fleet repo must have
    # baseline-check.yml wired up, so this is a safe minimum.
    # Re-run the script after CI has executed once to pick up the full
    # derived set.
    echo "WARNING: $repo — no check runs on main; defaulting required checks to 'baseline' only." >&2
    echo "         Re-run this script after CI has executed once to derive the full set." >&2
    echo "baseline"
    return
  fi

  # Filter: for each check-run name, extract the trailing segment after
  # the last ' / ' (or the whole name if there's no ' / ').  Keep the
  # FULL observed name as the context only if the trailing segment is
  # one of the known gate job names.
  local derived=()
  while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    local trailing="$name"
    if [[ "$name" == *" / "* ]]; then
      trailing="${name##* / }"
    fi
    for gate in "${KNOWN_GATES[@]}"; do
      if [[ "$trailing" == "$gate" ]]; then
        derived+=("$name")
        break
      fi
    done
  done <<< "$runs"

  if [[ ${#derived[@]} -eq 0 ]]; then
    echo "WARNING: $repo — no known gate check runs found on main; defaulting to 'baseline' only." >&2
    echo "baseline"
    return
  fi

  printf '%s\n' "${derived[@]}"
}

# --- Repo-level merge settings ---------------------------------------------
# Merge method is a *repo* setting, not part of the branch-protection
# endpoint.  We enforce the "squash merge only" fleet requirement via a
# separate PATCH to /repos/$OWNER/$repo.
apply_repo_settings() {
  local repo="$1"

  local body
  body='{
  "allow_squash_merge": true,
  "allow_merge_commit": false,
  "allow_rebase_merge": false,
  "delete_branch_on_merge": true
}'

  if $DRY_RUN; then
    echo "  [dry-run] PATCH /repos/$OWNER/$repo"
    echo "  $body"
    return 0
  fi

  local err_output
  # --input - reads the request body from stdin (the heredoc piped via <<<).
  err_output=$(gh api -X PATCH "repos/$OWNER/$repo" --input - 2>&1 1>/dev/null <<< "$body") || {
    if echo "$err_output" | grep -qi '403\|Forbidden'; then
      echo "ERROR: $repo — 403 Forbidden on repo PATCH." >&2
      echo "       Ensure your gh token has 'administration:write' scope." >&2
    else
      echo "ERROR: $repo — repo PATCH failed:" >&2
      echo "       $err_output" >&2
    fi
    return 1
  }
  return 0
}

# --- Branch protection (repository ruleset) --------------------------------
# Manages a repository ruleset named "robotsix-fleet-protection" that
# enforces the fleet-standard posture:
#   - PRs required (0 reviews — automation-friendly)
#   - Required status checks (strict, derived from check runs on main)
#   - Squash-only merges via PR
#   - Linear history required
#   - No force-pushes, no branch deletion
#
# If BYPASS_APP_ID is set, the designated GitHub App is added as a
# bypass actor so it can push releases directly to main.
#
# Classic branch protection (if present) is removed after the ruleset
# is applied, completing the migration from classic to rulesets.
#
# We use python3 to construct the JSON body because it handles escaping
# correctly for arbitrary check-run names, and because nested arrays
# cannot be expressed with gh's -f / -F flags.
apply_branch_protection() {
  local repo="$1"

  # Derive required status-check contexts for this repo.
  local checks=()
  while IFS= read -r c; do
    [[ -z "$c" ]] && continue
    checks+=("$c")
  done < <(derive_checks "$repo")

  # Build the ruleset JSON body via python3.  We pass the check names
  # as arguments (sys.argv[1:]) so they survive any special characters
  # intact, and send the Python script via stdin.  BYPASS_APP_ID is
  # forwarded through the environment.
  local body
  body=$(BYPASS_APP_ID="${BYPASS_APP_ID:-}" python3 - "${checks[@]}" <<'PYEOF'
import json, os, sys

checks = sys.argv[1:]
bypass_app_id = os.environ.get("BYPASS_APP_ID", "")

rules = [
    # A non-null pull_request rule is what enforces "PRs required /
    # no direct pushes".  We set the review count to 0 so the fleet
    # automated auto-release and dependabot auto-merge flows still
    # work without a human reviewer in the loop.
    {
        "type": "pull_request",
        "parameters": {
            "required_approving_review_count": 0,
            "dismiss_stale_reviews_on_push": False,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_review_thread_resolution": False,
            "allowed_merge_methods": ["squash"]
        }
    },
    {"type": "required_linear_history"},
    {
        "type": "required_status_checks",
        "parameters": {
            "strict_required_status_checks_policy": True,
            "required_status_checks": [{"context": c} for c in checks]
        }
    },
    {"type": "deletion"},
    {"type": "non_fast_forward"}
]

body = {
    "name": "robotsix-fleet-protection",
    "target": "branch",
    "enforcement": "active",
    "conditions": {
        "ref_name": {
            "include": ["refs/heads/main"],
            "exclude": []
        }
    },
    "rules": rules
}

# The fleet auto-release.yml pushes commits and tags as a GitHub App.
# Under classic branch protection an App cannot bypass; under rulesets
# the App can be listed as a bypass actor, allowing direct pushes to
# main without the PR+auto-merge fallback.
if bypass_app_id:
    body["bypass_actors"] = [
        {
            "actor_id": int(bypass_app_id),
            "actor_type": "Integration",
            "bypass_mode": "always"
        }
    ]

print(json.dumps(body, indent=2))
PYEOF
)

  # Resolve the ruleset: look for an existing one by name, then
  # create or update.  This is what makes the script idempotent.
  local existing_id
  existing_id=$(gh api "repos/$OWNER/$repo/rulesets" \
    --jq '.[] | select(.name == "robotsix-fleet-protection") | .id' 2>/dev/null) || true

  if $DRY_RUN; then
    if [[ -n "$existing_id" ]]; then
      echo "  [dry-run] PUT /repos/$OWNER/$repo/rulesets/$existing_id"
    else
      echo "  [dry-run] POST /repos/$OWNER/$repo/rulesets"
    fi
    echo "  $body"
    echo "  [dry-run] DELETE /repos/$OWNER/$repo/branches/main/protection"
    return 0
  fi

  local err_output
  if [[ -n "$existing_id" ]]; then
    err_output=$(gh api -X PUT "repos/$OWNER/$repo/rulesets/$existing_id" \
      --input - 2>&1 1>/dev/null <<< "$body") || {
      if echo "$err_output" | grep -qi '403\|Forbidden'; then
        echo "ERROR: $repo — 403 Forbidden on ruleset PUT." >&2
        echo "       Rulesets require a token with 'administration:write' scope." >&2
      else
        echo "ERROR: $repo — ruleset PUT failed:" >&2
        echo "       $err_output" >&2
      fi
      return 1
    }
  else
    err_output=$(gh api -X POST "repos/$OWNER/$repo/rulesets" \
      --input - 2>&1 1>/dev/null <<< "$body") || {
      if echo "$err_output" | grep -qi '403\|Forbidden'; then
        echo "ERROR: $repo — 403 Forbidden on ruleset POST." >&2
        echo "       Rulesets require a token with 'administration:write' scope." >&2
      else
        echo "ERROR: $repo — ruleset POST failed:" >&2
        echo "       $err_output" >&2
      fi
      return 1
    }
  fi

  # Remove classic branch protection if it exists — completes the
  # migration from classic to rulesets.  Non-fatal: the classic
  # protection may already have been removed, or the token may lack
  # the scope (we already applied the ruleset, which is the primary
  # goal).
  gh api -X DELETE "repos/$OWNER/$repo/branches/main/protection" \
    2>/dev/null || true

  return 0
}

# --- Process a single repo -------------------------------------------------
# Applies both the repo-level merge settings and the branch protection.
# Returns 0 on success or non-fatal skip, 1 on failure.
process_one_repo() {
  local repo="$1"
  local default_branch="$2"

  # We only protect repos whose default branch is 'main'.
  if [[ "$default_branch" != "main" ]]; then
    echo "skip: $repo (default branch is '$default_branch', not 'main')"
    return 0  # Non-fatal — this is a deliberate skip.
  fi

  # Step 1 — repo-level merge settings (squash-merge enforcement).
  apply_repo_settings "$repo" || return 1

  # Step 2 — repository ruleset on main (with classic-protection cleanup).
  apply_branch_protection "$repo" || return 1

  echo "ok: $repo"
  return 0
}

# --- Main ------------------------------------------------------------------
main() {
  check_prereqs

  local failed=()
  local count=0

  while read -r repo default_branch; do
    [[ -z "$repo" ]] && continue
    count=$((count + 1))

    if ! process_one_repo "$repo" "$default_branch"; then
      failed+=("$repo")
    fi
  done < <(enumerate_repos)

  # Summary.
  echo ""
  echo "---"
  echo "Processed $count repo(s)."
  if [[ ${#failed[@]} -gt 0 ]]; then
    echo "FAILED: ${failed[*]}"
    echo ""
    echo "Common causes of failure:"
    echo "  1. Token lacks 'administration:write' scope (required for branch protection)."
    echo "  2. Token lacks 'repo' scope (required to read/write repo settings)."
    echo "  3. Repo does not exist or the token cannot access it."
    exit 1
  fi

  echo "All repos processed successfully."
}

main "$@"
