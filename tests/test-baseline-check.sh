#!/usr/bin/env bash
# Integration tests for the baseline-check workflow's critical checks.
#
# Tests the AGENT.md, LICENSE and .secrets-patterns-excluded validation
# logic used in .github/workflows/baseline-check.yml.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ------------------------------------------------------------------
# Test 1: AGENT.md must reference robotsix-standards in first 20 lines
# ------------------------------------------------------------------
echo "=== Test 1: AGENT.md standards link ==="

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

cd "$TMPDIR"

# Test: missing AGENT.md → fails
echo "--- 1a: missing AGENT.md ---"
if [ -f AGENT.md ]; then echo "FAIL: AGENT.md should not exist" >&2; exit 1; fi
# The check: if AGENT.md is missing, error
set +e
test -f AGENT.md
missing_exit=$?
set -e
if [ "$missing_exit" -eq 0 ]; then
    echo "FAIL: expected AGENT.md to be missing" >&2
    exit 1
fi
echo "PASS: missing AGENT.md correctly detected"

# Test: AGENT.md without standards link in first 20 lines → fails
echo "--- 1b: AGENT.md missing standards link ---"
printf '# My Agent\n\nSome content.\n' > AGENT.md
if head -n 20 AGENT.md | grep -qE 'damien-robotsix/robotsix-standards'; then
    echo "FAIL: should not have found standards link" >&2
    exit 1
fi
echo "PASS: missing standards link correctly detected"

# Test: AGENT.md with standards link → passes
echo "--- 1c: AGENT.md with standards link ---"
printf '# My Agent\n\nSee damien-robotsix/robotsix-standards for conventions.\n' > AGENT.md
if ! head -n 20 AGENT.md | grep -qE 'damien-robotsix/robotsix-standards'; then
    echo "FAIL: standards link not found" >&2
    exit 1
fi
echo "PASS: standards link correctly detected"

# ------------------------------------------------------------------
# Test 2: LICENSE must be MIT
# ------------------------------------------------------------------
echo ""
echo "=== Test 2: LICENSE is MIT ==="

# Test: missing LICENSE → fails
echo "--- 2a: missing LICENSE ---"
set +e
test -f LICENSE
missing_exit=$?
set -e
if [ "$missing_exit" -eq 0 ]; then
    echo "FAIL: expected LICENSE to be missing" >&2
    exit 1
fi
echo "PASS: missing LICENSE correctly detected"

# Test: non-MIT LICENSE → fails
echo "--- 2b: non-MIT LICENSE ---"
printf 'Proprietary License\nAll rights reserved.\n' > LICENSE
if head -n 20 LICENSE | grep -qE 'MIT License|Permission is hereby granted'; then
    echo "FAIL: should not have found MIT markers" >&2
    exit 1
fi
echo "PASS: non-MIT LICENSE correctly detected"

# Test: MIT LICENSE → passes
echo "--- 2c: MIT LICENSE ---"
printf 'MIT License\n\nPermission is hereby granted, free of charge...\n' > LICENSE
if ! head -n 20 LICENSE | grep -qE 'MIT License|Permission is hereby granted'; then
    echo "FAIL: MIT markers not found" >&2
    exit 1
fi
echo "PASS: MIT LICENSE correctly detected"

# ------------------------------------------------------------------
# Test 3: .secrets-patterns-excluded (scripts/check_secrets_patterns_excluded.py)
# ------------------------------------------------------------------
echo ""
echo "=== Test 3: .secrets-patterns-excluded ==="

CHECK="$REPO_ROOT/scripts/check_secrets_patterns_excluded.py"
WARN_DAY=2026-11-01
BLOCK_DAY=2027-01-31

# run_check <root> <today>: sets RC and OUT.
run_check() {
    set +e
    OUT=$(python3 "$CHECK" --root "$1" --today "$2" 2>&1)
    RC=$?
    set -e
}

SPE="$TMPDIR/spe"
mkdir -p "$SPE"

echo "--- 3a: present and valid → passes ---"
printf '# comment\n\n^vendor/\n.*\\.lock$\n' > "$SPE/.secrets-patterns-excluded"
run_check "$SPE" "$BLOCK_DAY"
if [ "$RC" -ne 0 ] || ! grep -q 'OK' <<<"$OUT"; then
    echo "FAIL: valid file should pass (rc=$RC): $OUT" >&2
    exit 1
fi
echo "PASS: valid .secrets-patterns-excluded accepted"

echo "--- 3b: missing → warning before blocking date, error after ---"
rm "$SPE/.secrets-patterns-excluded"
run_check "$SPE" "$WARN_DAY"
if [ "$RC" -ne 0 ] || ! grep -q '::warning::.secrets-patterns-excluded is missing' <<<"$OUT"; then
    echo "FAIL: missing file should warn with exit 0 (rc=$RC): $OUT" >&2
    exit 1
fi
run_check "$SPE" "$BLOCK_DAY"
if [ "$RC" -ne 1 ] || ! grep -q '::error::.secrets-patterns-excluded is missing' <<<"$OUT"; then
    echo "FAIL: missing file should error with exit 1 (rc=$RC): $OUT" >&2
    exit 1
fi
echo "PASS: missing .secrets-patterns-excluded detected"

echo "--- 3c: gitignore glob (invalid regex) → rejected ---"
printf '*secret*\n' > "$SPE/.secrets-patterns-excluded"
run_check "$SPE" "$BLOCK_DAY"
if [ "$RC" -ne 1 ] || ! grep -q 'line `\*secret\*` is not a valid regular expression' <<<"$OUT"; then
    echo "FAIL: glob line should be rejected (rc=$RC): $OUT" >&2
    exit 1
fi
echo "PASS: invalid regex detected"

echo "--- 3d: no-op detect-secrets wiring → rejected ---"
printf '^vendor/\n' > "$SPE/.secrets-patterns-excluded"
printf "      - id: detect-secrets\n        args:\n          - '--exclude-files'\n          - '.secrets-patterns-excluded'\n" > "$SPE/.pre-commit-config.yaml"
run_check "$SPE" "$BLOCK_DAY"
if [ "$RC" -ne 1 ] || ! grep -q 'silent no-op' <<<"$OUT"; then
    echo "FAIL: no-op --exclude-files wiring should be rejected (rc=$RC): $OUT" >&2
    exit 1
fi
echo "PASS: no-op detect-secrets wiring detected"

echo ""
echo "=== All tests passed ==="
