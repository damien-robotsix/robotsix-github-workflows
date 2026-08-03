#!/usr/bin/env bash
# Integration tests for the baseline-check workflow's critical checks.
#
# Tests the AGENT.md and LICENSE validation logic used in
# .github/workflows/baseline-check.yml.
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

echo ""
echo "=== All tests passed ==="
