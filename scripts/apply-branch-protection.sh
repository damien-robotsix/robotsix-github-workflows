#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# apply-branch-protection.sh
#
# Idempotent operator script that applies the robotsix fleet standard
# branch-protection posture to every fleet repo (or a user-supplied subset).
#
# Safe to re-run any number of times — the PUT and PATCH endpoints are
# full-replace, so re-applying the same settings produces no configuration
# diff on a repo that is already in the desired state.
#
# Required gh token scopes: repo, administration:write
#
# Usage:
#   scripts/apply-branch-protection.sh              # all fleet repos
#   scripts/apply-branch-protection.sh repo-a repo-b  # specific repos
#   scripts/apply-branch-protection.sh --dry-run    # preview only
#   CHECKS="ctx1,ctx2" scripts/apply-branch-protection.sh  # override checks
# ============================================================================

# --- Configuration ---------------------------------------------------------
OWNER="${OWNER:-damien-robotsix}"
DRY_RUN=false
REPOS=()

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

# --- Branch protection -----------------------------------------------------
# PUT /repos/$OWNER/$repo/branches/main/protection with a full JSON body.
# We use python3 to construct the body because it handles JSON escaping
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

  # Build the branch-protection JSON body via python3 (handles JSON
  # escaping correctly for arbitrary check-run names).  We pass the
  # check names as arguments (sys.argv[1:]) so they survive any
  # special characters intact, and send the Python script via stdin.
  local body
  body=$(python3 - "${checks[@]}" <<'PYEOF'
import json, sys

checks = sys.argv[1:]

body = {
    # A non-null reviews object is what enforces "PRs required / no
    # direct pushes".  We set the count to 0 so the fleet automated
    # auto-release and dependabot auto-merge flows still work without
    # a human reviewer in the loop.
    "required_pull_request_reviews": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews": False
    },
    "required_status_checks": {
        "strict": True,
        "checks": [{"context": c} for c in checks]
    },
    # enforce_admins: False
    # The fleet auto-release.yml pushes tags and commits using a PAT
    # that is an org admin.  Setting enforce_admins to True would block
    # those pushes, breaking the automated release pipeline.
    "enforce_admins": False,
    "restrictions": None,
    "allow_force_pushes": False,
    "allow_deletions": False,
    "required_linear_history": True
}

print(json.dumps(body, indent=2))
PYEOF
)

  if $DRY_RUN; then
    echo "  [dry-run] PUT /repos/$OWNER/$repo/branches/main/protection"
    echo "  $body"
    return 0
  fi

  local err_output
  err_output=$(gh api -X PUT "repos/$OWNER/$repo/branches/main/protection" \
    --input - 2>&1 1>/dev/null <<< "$body") || {
    if echo "$err_output" | grep -qi '403\|Forbidden'; then
      echo "ERROR: $repo — 403 Forbidden on branch-protection PUT." >&2
      echo "       Branch protection requires a token with 'administration:write' scope." >&2
    else
      echo "ERROR: $repo — branch-protection PUT failed:" >&2
      echo "       $err_output" >&2
    fi
    return 1
  }
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

  # Step 2 — branch protection on main.
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
