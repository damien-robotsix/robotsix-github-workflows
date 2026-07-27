#!/usr/bin/env bash
# Integration test for the config-ownership check.
#
# Creates a temporary git repo, commits a baseline docker-compose.yml,
# applies a change, and runs the same Python check logic that the
# reusable workflow uses.  Asserts that:
#   - A compliant change (adding an orchestration-only env var) passes.
#   - A violating change (adding a component-internal env var) fails.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ------------------------------------------------------------------
# Helper: run the check logic against a git repo at $1.
# Arguments: $1 = path to git repo, $2 = expected exit code.
# ------------------------------------------------------------------
run_check() {
    local repo_dir="$1"
    local expected_exit="$2"

    cd "$repo_dir"

    # Install pyyaml (quietly) and run the check.
    # This is the SAME logic as the inline script in the workflow YAML,
    # extracted here for testability.
    python3 -m pip install --quiet pyyaml 2>/dev/null

    set +e
    python3 << 'PYEOF'
import os, re, sys, subprocess, tempfile
import yaml

_DEFAULT_ORCHESTRATION_ONLY = [
    r".*_PORT$", r"^PORT$",
    r".*_VOLUME$", r".*_MOUNT$", r".*_MOUNT_PATH$",
    r".*_VOLUME_DIR$", r".*_DATA_DIR$",
    r".*_MEMORY(_LIMIT)?$", r".*_CPU(_LIMIT)?$",
    r".*_LIMITS?$", r".*_REQUESTS?$",
    r".*_IMAGE$", r".*_TAG$", r".*_PULL_POLICY$",
    r".*_HOST(NAME)?$", r".*_NETWORK$", r".*_DNS$",
    r".*_SUBNET$", r".*_INGRESS$",
    r".*_REPLICAS$", r".*_SCALE$", r".*_COUNT$",
    r".*_HEALTHCHECK.*", r".*_LIVENESS.*", r".*_READINESS.*",
    r".*_LOG_DRIVER$", r".*_LOG_OPTS$",
    r".*_SECRET(_ARN|_NAME|_ID)?$", r".*_SECRETS?$",
    r".*_NODE$", r".*_PLACEMENT$", r".*_AFFINITY$",
    r".*_RESTART_POLICY$", r".*_RESTART$",
    r"^PGID$", r"^PUID$", r"^(CONTAINER_)?USER$",
    r"^(CONTAINER_)?GROUP$",
    r"^TZ$", r"^TIMEZONE$",
    r"^COMPOSE_.*", r"^DOCKER_.*",
    r"^KUBERNETES_.*",
    r".*_PROXY$", r"^NO_PROXY$", r"^HTTPS?_PROXY$",
    r"^HTTP_PROXY$", r"^HTTPS_PROXY$",
    r".*_SERVICE_NAME$", r".*_NAMESPACE$",
    r".*_OTLP_ENDPOINT$", r".*_TRACING_ENDPOINT$",
    r".*_METRICS_ENDPOINT$",
    r".*_RUNTIME_DIR$", r".*_TMP_DIR$",
]

PATTERNS = [re.compile(p) for p in _DEFAULT_ORCHESTRATION_ONLY]

def _is_orchestration_only(name):
    for pat in PATTERNS:
        if pat.match(name):
            return True
    return False

def _extract_env_vars(yaml_path):
    env_vars = set()
    try:
        with open(yaml_path) as fh:
            doc = yaml.safe_load(fh)
    except (yaml.YAMLError, OSError):
        return env_vars
    if not isinstance(doc, dict):
        return env_vars

    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("environment", "env"):
                    if isinstance(v, dict):
                        for ek in v:
                            if isinstance(ek, str):
                                env_vars.add(ek)
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, str) and "=" in item:
                                env_vars.add(item.split("=", 1)[0])
                            elif isinstance(item, dict):
                                name = item.get("name")
                                if isinstance(name, str):
                                    env_vars.add(name)
                else:
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(doc)
    return env_vars

# Determine base ref (first commit)
result = subprocess.run(
    ["git", "rev-list", "--max-parents=0", "HEAD"],
    capture_output=True, text=True,
)
base_ref = result.stdout.strip()
if not base_ref:
    print("ERROR: could not determine base ref", file=sys.stderr)
    sys.exit(2)

# Find changed docker-compose files
result = subprocess.run(
    ["git", "diff", "--name-only", base_ref, "HEAD"],
    capture_output=True, text=True,
)
changed = [f for f in result.stdout.strip().split("\n") if f]
compose_files = [f for f in changed if "docker-compose" in f or f.endswith(".yml")]

errors = []
for filepath in compose_files:
    if not os.path.exists(filepath):
        continue

    # Get old version
    result = subprocess.run(
        ["git", "show", f"{base_ref}:{filepath}"],
        capture_output=True, text=True,
    )
    old_env_vars = set()
    if result.returncode == 0:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tf:
            tf.write(result.stdout)
            tmp_path = tf.name
        try:
            old_env_vars = _extract_env_vars(tmp_path)
        finally:
            os.unlink(tmp_path)

    new_env_vars = _extract_env_vars(filepath)
    added = new_env_vars - old_env_vars

    for ev in sorted(added):
        if not _is_orchestration_only(ev):
            errors.append(
                f"{filepath}: new env var '{ev}' is not orchestration-only"
            )

if errors:
    for msg in errors:
        print(f"::error::{msg}", file=sys.stderr)
    sys.exit(1)

print("OK: no config-ownership violations")
PYEOF
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

run_check "$TMPDIR" 0

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

run_check "$TMPDIR2" 1

echo ""
echo "=== All tests passed ==="
