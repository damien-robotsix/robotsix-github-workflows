#!/usr/bin/env bash
# Integration test for the config-ownership check.
#
# Creates a temporary git repo, commits a baseline docker-compose.yml,
# applies a change, and runs the shared config-ownership check script
# (scripts/config_ownership_check.py).  Asserts that:
#   - A compliant change (adding an orchestration-only env var) passes.
#   - A violating change (adding a component-internal env var) fails.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHECK_SCRIPT="$REPO_ROOT/scripts/config_ownership_check.py"

# ------------------------------------------------------------------
# Helper: run the check logic against a git repo at $1.
# Arguments: $1 = path to git repo, $2 = glob pattern, $3 = expected exit code.
# ------------------------------------------------------------------
run_check() {
    local repo_dir="$1"
    local glob="$2"
    local expected_exit="$3"

    cd "$repo_dir"

    # Determine the first commit as the base ref
    local base_ref
    base_ref=$(git rev-list --max-parents=0 HEAD)
    if [ -z "$base_ref" ]; then
        echo "ERROR: could not determine base ref" >&2
        return 2
    fi

    set +e
    DEPLOY_CONFIG_GLOB="$glob" \
    BASE_REF="$base_ref" \
        python3 "$CHECK_SCRIPT"
    local actual_exit=$?
    set -e

    if [ "$actual_exit" -ne "$expected_exit" ]; then
        echo "FAIL: expected exit ${expected_exit}, got ${actual_exit}" >&2
        return 1
    fi
    echo "PASS: exit code ${actual_exit} as expected"
    return 0
}

# ------------------------------------------------------------------
# Test 1: compliant change (adding APP_RESTART_POLICY)
# ------------------------------------------------------------------
echo "=== Test 1: compliant change (orchestration-only env var) ==="

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

cd "$TMPDIR"
git init --quiet
git config user.email "test@example.com"
git config user.name "Test"

# Baseline
cp "$REPO_ROOT/tests/fixtures/compliant/baseline.yml" docker-compose.yml
git add docker-compose.yml
git commit --quiet -m "baseline"

# Compliant change: add APP_RESTART_POLICY (matches .*_RESTART_POLICY$)
cp "$REPO_ROOT/tests/fixtures/compliant/after-change.yml" docker-compose.yml
git add docker-compose.yml
git commit --quiet -m "add restart policy env var"

run_check "$TMPDIR" "docker-compose.yml" 0

# ------------------------------------------------------------------
# Test 2: violating change (adding DATABASE_URL)
# ------------------------------------------------------------------
echo ""
echo "=== Test 2: violating change (component-internal env var) ==="

TMPDIR2=$(mktemp -d)
# Extend trap to clean up both dirs
trap 'rm -rf "$TMPDIR" "$TMPDIR2"' EXIT

cd "$TMPDIR2"
git init --quiet
git config user.email "test@example.com"
git config user.name "Test"

# Baseline
cp "$REPO_ROOT/tests/fixtures/violating/baseline.yml" docker-compose.yml
git add docker-compose.yml
git commit --quiet -m "baseline"

# Violating change: add DATABASE_URL
cp "$REPO_ROOT/tests/fixtures/violating/after-change.yml" docker-compose.yml
git add docker-compose.yml
git commit --quiet -m "add database url env var"

run_check "$TMPDIR2" "docker-compose.yml" 1

echo ""
echo "=== All tests passed ==="
