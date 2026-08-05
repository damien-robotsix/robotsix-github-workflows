#!/usr/bin/env bash
# Integration tests for scripts/apply-branch-protection.sh
#
# Exercises the script in --dry-run mode against a mock gh CLI so that
# no real API calls are made.  Validates:
#   - Correct JSON bodies for repo settings (squash-only, delete_branch_on_merge)
#   - Correct JSON bodies for the ruleset (name, enforcement, check contexts)
#   - CHECKS override short-circuits check derivation
#   - BYPASS_APP_ID adds a bypass actor
#   - Derived checks from mock check-run names on main
#   - Idempotency: re-running the script produces no errors
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ------------------------------------------------------------------
# Helper: create a mock gh CLI in $1 that returns fake responses.
# The mock is controlled via environment variables:
#   MOCK_RULESET_STATE — path to a state file; when empty/non-existent
#                        the mock reports no existing ruleset (POST path);
#                        when the file exists it reports id 12345 (PUT path)
#   MOCK_CHECK_RUNS   — colon-separated list of check-run names to return
#                        (default: "Baseline Check / baseline:Python CI / tests")
# ------------------------------------------------------------------
create_mock_gh() {
    local dest_dir="$1"
    cat > "$dest_dir/gh" << 'MOCKEOF'
#!/usr/bin/env bash
# Mock gh CLI for testing apply-branch-protection.sh

if [[ "$*" == *"auth status"* ]]; then
    exit 0
fi

if [[ "$1" != "api" ]]; then
    echo "MOCK: unexpected gh subcommand: $*" >&2
    exit 1
fi

url="$2"

case "$url" in
    repos/*/commits/main/check-runs)
        # Return mock check-run names (one per line).
        # MOCK_CHECK_RUNS is colon-separated; default if unset.
        IFS=':' read -ra NAMES <<< "${MOCK_CHECK_RUNS:-Baseline Check / baseline:Python CI / tests:Security Scan / security}"
        for n in "${NAMES[@]}"; do
            echo "$n"
        done
        ;;
    repos/*/rulesets)
        # When the state file exists, the mock reports an existing
        # ruleset with id 12345 (PUT path).  Otherwise reports none
        # (POST path).
        if [[ -n "${MOCK_RULESET_STATE:-}" && -f "$MOCK_RULESET_STATE" ]]; then
            echo "12345"
        fi
        ;;
    repos/*/*)
        # Default branch lookup — always "main".
        echo "main"
        ;;
    *)
        echo "MOCK: unexpected gh api URL: $url" >&2
        exit 1
        ;;
esac
MOCKEOF
    chmod +x "$dest_dir/gh"
}

# ------------------------------------------------------------------
# Helper: extract the JSON body following a [dry-run] header.
# $1 = script output (multi-line string)
# $2 = header pattern (e.g. "PATCH" or "POST.*rulesets" or "PUT.*rulesets")
# Prints the JSON body to stdout.
# ------------------------------------------------------------------
extract_json_body() {
    local output="$1"
    local header_pattern="$2"
    echo "$output" | awk "
        /\[dry-run\] $header_pattern/ { flag=1; next }
        /\[dry-run\]/                 { if (flag) exit }
        flag
    "
}

# ------------------------------------------------------------------
# Helper: validate JSON field values via python3.
# $1 = JSON string
# $2 = python3 assertion code (sourced via stdin)
# Returns 0 on success, 1 on failure.
# ------------------------------------------------------------------
validate_json() {
    local json_str="$1"
    local py_code="$2"
    echo "$json_str" | python3 -c "$py_code"
}

# ------------------------------------------------------------------
# Test 1: CHECKS override — validates that the CHECKS env var
# short-circuits check derivation and produces the expected
# required_status_checks in the ruleset JSON.
# ------------------------------------------------------------------
test_checks_override() {
    echo "=== Test 1: CHECKS override ==="

    local tmpdir
    tmpdir=$(mktemp -d)
    trap 'rm -rf "$tmpdir"' RETURN

    create_mock_gh "$tmpdir"
    local old_path="$PATH"
    export PATH="$tmpdir:$PATH"

    local output
    output=$(CHECKS="ctx-alpha,ctx-beta" \
        "$REPO_ROOT/scripts/apply-branch-protection.sh" --dry-run test-repo 2>&1) || {
        echo "FAIL: script exited non-zero: $output" >&2
        PATH="$old_path" return 1
    }

    PATH="$old_path"

    # Extract the repo-settings JSON (after PATCH).
    local patch_json
    patch_json=$(extract_json_body "$output" "PATCH")

    if [[ -z "$patch_json" ]]; then
        echo "FAIL: no PATCH JSON body found in output" >&2
        echo "Output: $output" >&2
        return 1
    fi

    # Validate repo settings.
    validate_json "$patch_json" '
import json, sys
data = json.load(sys.stdin)
assert data.get("allow_squash_merge") is True, f"allow_squash_merge not true: {data}"
assert data.get("allow_merge_commit") is False, f"allow_merge_commit not false: {data}"
assert data.get("allow_rebase_merge") is False, f"allow_rebase_merge not false: {data}"
assert data.get("delete_branch_on_merge") is True, f"delete_branch_on_merge not true: {data}"
' || { echo "FAIL: repo-settings JSON validation failed" >&2; return 1; }

    # Extract the ruleset JSON (after POST — no existing ruleset).
    local ruleset_json
    ruleset_json=$(extract_json_body "$output" "POST.*rulesets")

    if [[ -z "$ruleset_json" ]]; then
        echo "FAIL: no POST ruleset JSON body found in output" >&2
        echo "Output: $output" >&2
        return 1
    fi

    # Validate ruleset JSON.
    validate_json "$ruleset_json" '
import json, sys
data = json.load(sys.stdin)

# Name and enforcement.
assert data.get("name") == "robotsix-fleet-protection", f"name mismatch: {data.get('name')}"
assert data.get("enforcement") == "active", f"enforcement mismatch: {data.get('enforcement')}"
assert data.get("target") == "branch", f"target mismatch: {data.get('target')}"

# Conditions: only main.
conditions = data.get("conditions", {})
ref_name = conditions.get("ref_name", {})
assert ref_name.get("include") == ["refs/heads/main"], f"include mismatch: {ref_name.get('include')}"

# Pull request rule.
pr_rule = None
for r in data.get("rules", []):
    if r["type"] == "pull_request":
        pr_rule = r
        break
assert pr_rule is not None, "pull_request rule not found"
params = pr_rule.get("parameters", {})
assert params.get("required_approving_review_count") == 0
assert "squash" in params.get("allowed_merge_methods", [])
assert "merge" not in params.get("allowed_merge_methods", [])
assert "rebase" not in params.get("allowed_merge_methods", [])

# Required status checks.
checks_rule = None
for r in data.get("rules", []):
    if r["type"] == "required_status_checks":
        checks_rule = r
        break
assert checks_rule is not None, "required_status_checks rule not found"
checks_params = checks_rule.get("parameters", {})
assert checks_params.get("strict_required_status_checks_policy") is True

contexts = [c["context"] for c in checks_params.get("required_status_checks", [])]
assert "ctx-alpha" in contexts, f"ctx-alpha not in {contexts}"
assert "ctx-beta" in contexts, f"ctx-beta not in {contexts}"
assert len(contexts) == 2, f"expected 2 checks, got {len(contexts)}: {contexts}"

# Linear history rule.
assert any(r["type"] == "required_linear_history" for r in data.get("rules", []))
# Deletion rule.
assert any(r["type"] == "deletion" for r in data.get("rules", []))
# Non-fast-forward rule.
assert any(r["type"] == "non_fast_forward" for r in data.get("rules", []))

# No bypass actors (BYPASS_APP_ID not set).
assert "bypass_actors" not in data, f"unexpected bypass_actors: {data.get('bypass_actors')}"

print("OK")
' || { echo "FAIL: ruleset JSON validation failed" >&2; return 1; }

    # Verify the DELETE classic-protection call is present.
    if ! echo "$output" | grep -q '\[dry-run\] DELETE.*protection'; then
        echo "FAIL: missing DELETE classic-protection call" >&2
        return 1
    fi

    # Verify the ok: line.
    if ! echo "$output" | grep -q 'ok: test-repo'; then
        echo "FAIL: missing 'ok: test-repo' line" >&2
        return 1
    fi

    echo "PASS: CHECKS override produces correct JSON bodies"
    return 0
}

# ------------------------------------------------------------------
# Test 2: BYPASS_APP_ID — validates that setting BYPASS_APP_ID adds
# a bypass_actors array to the ruleset JSON.
# ------------------------------------------------------------------
test_bypass_app_id() {
    echo ""
    echo "=== Test 2: BYPASS_APP_ID ==="

    local tmpdir
    tmpdir=$(mktemp -d)
    trap 'rm -rf "$tmpdir"' RETURN

    create_mock_gh "$tmpdir"
    local old_path="$PATH"
    export PATH="$tmpdir:$PATH"

    local output
    output=$(BYPASS_APP_ID=99999 CHECKS="baseline" \
        "$REPO_ROOT/scripts/apply-branch-protection.sh" --dry-run test-repo 2>&1) || {
        echo "FAIL: script exited non-zero: $output" >&2
        PATH="$old_path" return 1
    }

    PATH="$old_path"

    local ruleset_json
    ruleset_json=$(extract_json_body "$output" "POST.*rulesets")

    if [[ -z "$ruleset_json" ]]; then
        echo "FAIL: no ruleset JSON body found" >&2
        return 1
    fi

    validate_json "$ruleset_json" '
import json, sys
data = json.load(sys.stdin)

bypass = data.get("bypass_actors")
assert bypass is not None, "bypass_actors missing"
assert len(bypass) == 1, f"expected 1 bypass actor, got {len(bypass)}"
actor = bypass[0]
assert actor["actor_id"] == 99999, f"actor_id mismatch: {actor['actor_id']}"
assert actor["actor_type"] == "Integration", f"actor_type mismatch: {actor['actor_type']}"
assert actor["bypass_mode"] == "always", f"bypass_mode mismatch: {actor['bypass_mode']}"

print("OK")
' || { echo "FAIL: bypass_actors validation failed" >&2; return 1; }

    echo "PASS: BYPASS_APP_ID adds bypass actor"
    return 0
}

# ------------------------------------------------------------------
# Test 3: Derived checks (no CHECKS override) — validates that when
# CHECKS is unset, the script derives required check contexts from
# the mock check-run names on main.
# ------------------------------------------------------------------
test_derived_checks() {
    echo ""
    echo "=== Test 3: Derived checks (no CHECKS override) ==="

    local tmpdir
    tmpdir=$(mktemp -d)
    trap 'rm -rf "$tmpdir"' RETURN

    create_mock_gh "$tmpdir"
    local old_path="$PATH"
    export PATH="$tmpdir:$PATH"

    # Supply mock check-run names that include known gate jobs.
    local output
    output=$(MOCK_CHECK_RUNS="Baseline Check / baseline:Python CI / tests:Some Lint / lint:Security Scan / security" \
        "$REPO_ROOT/scripts/apply-branch-protection.sh" --dry-run test-repo 2>&1) || {
        echo "FAIL: script exited non-zero: $output" >&2
        PATH="$old_path" return 1
    }

    PATH="$old_path"

    local ruleset_json
    ruleset_json=$(extract_json_body "$output" "POST.*rulesets")

    if [[ -z "$ruleset_json" ]]; then
        echo "FAIL: no ruleset JSON body found" >&2
        return 1
    fi

    validate_json "$ruleset_json" '
import json, sys
data = json.load(sys.stdin)

checks_rule = None
for r in data.get("rules", []):
    if r["type"] == "required_status_checks":
        checks_rule = r
        break
assert checks_rule is not None, "required_status_checks rule not found"

contexts = [c["context"] for c in checks_rule["parameters"]["required_status_checks"]]
# Known gates: baseline, tests, security.  "lint" is not a known gate,
# so "Some Lint / lint" should NOT appear.
known_contexts = [c for c in contexts if "lint" in c.lower()]
assert len(known_contexts) == 0, f"lint context should not be in required checks: {contexts}"

# baseline, tests, security should all be present.
assert any("baseline" in c.lower() for c in contexts), f"baseline not in {contexts}"
assert any("tests" in c.lower() for c in contexts), f"tests not in {contexts}"
assert any("security" in c.lower() for c in contexts), f"security not in {contexts}"
assert len(contexts) == 3, f"expected 3 checks, got {len(contexts)}: {contexts}"

print("OK")
' || { echo "FAIL: derived checks validation failed" >&2; return 1; }

    echo "PASS: derived checks match known gate jobs only"
    return 0
}

# ------------------------------------------------------------------
# Test 4: Derived checks with no matching gates — validates fallback
# to "baseline" only when no check runs match known gates.
# ------------------------------------------------------------------
test_derived_no_matching_gates() {
    echo ""
    echo "=== Test 4: Derived checks (no matching gates) ==="

    local tmpdir
    tmpdir=$(mktemp -d)
    trap 'rm -rf "$tmpdir"' RETURN

    create_mock_gh "$tmpdir"
    local old_path="$PATH"
    export PATH="$tmpdir:$PATH"

    # Supply check-run names that do NOT match any known gate.
    local output
    output=$(MOCK_CHECK_RUNS="Some Custom / lint:Other / build" \
        "$REPO_ROOT/scripts/apply-branch-protection.sh" --dry-run test-repo 2>&1) || {
        echo "FAIL: script exited non-zero: $output" >&2
        PATH="$old_path" return 1
    }

    PATH="$old_path"

    local ruleset_json
    ruleset_json=$(extract_json_body "$output" "POST.*rulesets")

    if [[ -z "$ruleset_json" ]]; then
        echo "FAIL: no ruleset JSON body found" >&2
        return 1
    fi

    validate_json "$ruleset_json" '
import json, sys
data = json.load(sys.stdin)

checks_rule = None
for r in data.get("rules", []):
    if r["type"] == "required_status_checks":
        checks_rule = r
        break
assert checks_rule is not None, "required_status_checks rule not found"

contexts = [c["context"] for c in checks_rule["parameters"]["required_status_checks"]]
assert contexts == ["baseline"], f"expected only baseline, got {contexts}"

print("OK")
' || { echo "FAIL: fallback to baseline validation failed" >&2; return 1; }

    echo "PASS: fallback to 'baseline' when no known gates match"
    return 0
}

# ------------------------------------------------------------------
# Test 5: Idempotency — re-running the script when a ruleset already
# exists uses PUT instead of POST and still succeeds.
# ------------------------------------------------------------------
test_idempotency() {
    echo ""
    echo "=== Test 5: Idempotency ==="

    local tmpdir
    tmpdir=$(mktemp -d)
    # Use a persistent trap that covers both runs.
    # We'll clean up manually at the end of this function.

    create_mock_gh "$tmpdir"
    local old_path="$PATH"
    export PATH="$tmpdir:$PATH"

    # First run: no existing ruleset (POST path).
    local state_file="$tmpdir/ruleset_state"
    export MOCK_RULESET_STATE=""

    local output1
    output1=$(CHECKS="baseline" \
        "$REPO_ROOT/scripts/apply-branch-protection.sh" --dry-run test-repo 2>&1) || {
        echo "FAIL: first run exited non-zero: $output1" >&2
        PATH="$old_path" rm -rf "$tmpdir"
        return 1
    }

    if ! echo "$output1" | grep -q '\[dry-run\] POST.*rulesets'; then
        echo "FAIL: first run should use POST (no existing ruleset)" >&2
        echo "Output: $output1" >&2
        PATH="$old_path" rm -rf "$tmpdir"
        return 1
    fi

    # Second run: existing ruleset (PUT path).  Create the state file
    # so the mock reports an existing ruleset.
    touch "$state_file"
    export MOCK_RULESET_STATE="$state_file"

    local output2
    output2=$(CHECKS="baseline" \
        "$REPO_ROOT/scripts/apply-branch-protection.sh" --dry-run test-repo 2>&1) || {
        echo "FAIL: second run exited non-zero: $output2" >&2
        PATH="$old_path" rm -rf "$tmpdir"
        return 1
    }

    PATH="$old_path"

    if ! echo "$output2" | grep -q '\[dry-run\] PUT.*rulesets'; then
        echo "FAIL: second run should use PUT (existing ruleset)" >&2
        echo "Output: $output2" >&2
        rm -rf "$tmpdir"
        return 1
    fi

    if ! echo "$output2" | grep -q 'ok: test-repo'; then
        echo "FAIL: second run missing 'ok: test-repo'" >&2
        rm -rf "$tmpdir"
        return 1
    fi

    rm -rf "$tmpdir"
    echo "PASS: idempotency — POST on first run, PUT on second"
    return 0
}

# ------------------------------------------------------------------
# Test 6: Case-insensitive gate matching.
# ------------------------------------------------------------------
test_case_insensitive_gates() {
    echo ""
    echo "=== Test 6: Case-insensitive gate matching ==="

    local tmpdir
    tmpdir=$(mktemp -d)
    trap 'rm -rf "$tmpdir"' RETURN

    create_mock_gh "$tmpdir"
    local old_path="$PATH"
    export PATH="$tmpdir:$PATH"

    # Mixed-case gate names should still match.
    local output
    output=$(MOCK_CHECK_RUNS="CI / BASELINE:CI / Tests" \
        "$REPO_ROOT/scripts/apply-branch-protection.sh" --dry-run test-repo 2>&1) || {
        echo "FAIL: script exited non-zero: $output" >&2
        PATH="$old_path" return 1
    }

    PATH="$old_path"

    local ruleset_json
    ruleset_json=$(extract_json_body "$output" "POST.*rulesets")

    validate_json "$ruleset_json" '
import json, sys
data = json.load(sys.stdin)

checks_rule = None
for r in data.get("rules", []):
    if r["type"] == "required_status_checks":
        checks_rule = r
        break
assert checks_rule is not None

contexts = [c["context"] for c in checks_rule["parameters"]["required_status_checks"]]
# Both "BASELINE" and "Tests" should match (case-insensitive).
assert any("BASELINE" in c for c in contexts), f"BASELINE not in {contexts}"
assert any("Tests" in c for c in contexts), f"Tests not in {contexts}"
assert len(contexts) == 2, f"expected 2 checks, got {len(contexts)}: {contexts}"

print("OK")
' || { echo "FAIL: case-insensitive gate matching failed" >&2; return 1; }

    echo "PASS: case-insensitive gate matching"
    return 0
}

# ------------------------------------------------------------------
# Test 7: Default branch is not "main" — repo is skipped.
# ------------------------------------------------------------------
test_skip_non_main() {
    echo ""
    echo "=== Test 7: Skip repos with non-main default branch ==="

    local tmpdir
    tmpdir=$(mktemp -d)
    trap 'rm -rf "$tmpdir"' RETURN

    # Custom mock that returns "develop" as default branch.
    cat > "$tmpdir/gh" << 'MOCKEOF'
#!/usr/bin/env bash
if [[ "$*" == *"auth status"* ]]; then exit 0; fi
if [[ "$1" != "api" ]]; then exit 1; fi
url="$2"
case "$url" in
    repos/*/*)
        # Return "develop" — not "main".
        echo "develop"
        ;;
    *)
        echo "MOCK: unexpected URL: $url" >&2
        exit 1
        ;;
esac
MOCKEOF
    chmod +x "$tmpdir/gh"

    local old_path="$PATH"
    export PATH="$tmpdir:$PATH"

    local output
    output=$("$REPO_ROOT/scripts/apply-branch-protection.sh" --dry-run test-repo 2>&1) || {
        echo "FAIL: script exited non-zero: $output" >&2
        PATH="$old_path" return 1
    }

    PATH="$old_path"

    if ! echo "$output" | grep -q "skip: test-repo.*not 'main'"; then
        echo "FAIL: expected skip message for non-main default branch" >&2
        echo "Output: $output" >&2
        return 1
    fi

    echo "PASS: non-main default branch triggers skip"
    return 0
}

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
main() {
    local failed=0

    test_checks_override || { failed=$((failed + 1)); }
    test_bypass_app_id || { failed=$((failed + 1)); }
    test_derived_checks || { failed=$((failed + 1)); }
    test_derived_no_matching_gates || { failed=$((failed + 1)); }
    test_idempotency || { failed=$((failed + 1)); }
    test_case_insensitive_gates || { failed=$((failed + 1)); }
    test_skip_non_main || { failed=$((failed + 1)); }

    # Clear any RETURN trap inherited from test functions so it does
    # not fire when main returns (the referenced tmpdir is out of scope).
    trap - RETURN

    echo ""
    if [[ $failed -eq 0 ]]; then
        echo "=== All tests passed ==="
    else
        echo "=== $failed test(s) FAILED ==="
        return 1
    fi
}

main "$@"
