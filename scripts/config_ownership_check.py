#!/usr/bin/env python3
"""Config-ownership check for deploy-plane configuration files.

Checks that new environment variables or config keys added to deploy
config files (docker-compose, Kubernetes, Helm, etc.) are
orchestration-only — i.e. they concern infrastructure concerns
(ports, volumes, resource limits, etc.) rather than component-internal
settings (database URLs, API keys, feature flags, timeouts, etc.).

Usage as a standalone script (called from CI workflow)::

    DEPLOY_CONFIG_GLOB="deploy/**/*.yml" python3 scripts/config_ownership_check.py

Usage as an importable module (called from tests)::

    from scripts.config_ownership_check import check

The module exposes its core functions and a ``check()`` entry point
that accepts keyword arguments mirroring the environment variables.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from fnmatch import fnmatch

try:
    import yaml
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", "pyyaml"]
    )
    import yaml


# -------------------------------------------------------------------
# Default orchestration-only patterns — env vars / config keys
# matching these are infrastructure concerns that legitimately
# belong in deploy-plane config (volume mounts, ports, resource
# limits, etc.).  Everything else should be owned internally by
# the component.
# -------------------------------------------------------------------
_DEFAULT_ORCHESTRATION_ONLY: list[str] = [
    # --- port mappings ---
    r".*_PORT$",
    r"^PORT$",
    # --- volume / mount paths (infrastructure) ---
    r".*_VOLUME$",
    r".*_MOUNT$",
    r".*_MOUNT_PATH$",
    r".*_VOLUME_DIR$",
    r".*_DATA_DIR$",
    # --- resource limits ---
    r".*_MEMORY(_LIMIT)?$",
    r".*_CPU(_LIMIT)?$",
    r".*_LIMITS?$",
    r".*_REQUESTS?$",
    # --- container / image ---
    r".*_IMAGE$",
    r".*_TAG$",
    r".*_PULL_POLICY$",
    # --- network ---
    r".*_HOST(NAME)?$",
    r".*_NETWORK$",
    r".*_DNS$",
    r".*_SUBNET$",
    r".*_INGRESS$",
    # --- replicas / scale ---
    r".*_REPLICAS$",
    r".*_SCALE$",
    r".*_COUNT$",
    # --- health checks ---
    r".*_HEALTHCHECK.*",
    r".*_LIVENESS.*",
    r".*_READINESS.*",
    # --- logging *driver* (orchestration-level only) ---
    r".*_LOG_DRIVER$",
    r".*_LOG_OPTS$",
    # --- secrets *references* (not values) ---
    r".*_SECRET(_ARN|_NAME|_ID)?$",
    r".*_SECRETS?$",
    # --- node / placement ---
    r".*_NODE$",
    r".*_PLACEMENT$",
    r".*_AFFINITY$",
    # --- restart policy ---
    r".*_RESTART_POLICY$",
    r".*_RESTART$",
    # --- container runtime user/group ---
    r"^PGID$",
    r"^PUID$",
    r"^(CONTAINER_)?USER$",
    r"^(CONTAINER_)?GROUP$",
    # --- timezone (infrastructure) ---
    r"^TZ$",
    r"^TIMEZONE$",
    # --- Docker / Compose built-ins ---
    r"^COMPOSE_.*",
    r"^DOCKER_.*",
    # --- Kubernetes built-in env vars ---
    r"^KUBERNETES_.*",
    # --- proxy (infrastructure) ---
    r".*_PROXY$",
    r"^NO_PROXY$",
    r"^HTTPS?_PROXY$",
    r"^HTTP_PROXY$",
    r"^HTTPS_PROXY$",
    # --- service discovery ---
    r".*_SERVICE_NAME$",
    r".*_NAMESPACE$",
    # --- tracing endpoint (infrastructure URL) ---
    r".*_OTLP_ENDPOINT$",
    r".*_TRACING_ENDPOINT$",
    r".*_METRICS_ENDPOINT$",
    # --- runtime directory (infrastructure) ---
    r".*_RUNTIME_DIR$",
    r".*_TMP_DIR$",
]


def load_patterns(patterns_str: str) -> list[re.Pattern[str]]:
    """Parse newline-separated regex patterns.

    When *patterns_str* is empty, returns compiled patterns from the
    built-in default set.  Lines starting with ``#`` are treated as
    comments and skipped.
    """
    if not patterns_str or not patterns_str.strip():
        return [re.compile(p) for p in _DEFAULT_ORCHESTRATION_ONLY]

    compiled: list[re.Pattern[str]] = []
    for line in patterns_str.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            compiled.append(re.compile(line))

    if not compiled:
        return [re.compile(p) for p in _DEFAULT_ORCHESTRATION_ONLY]
    return compiled


def is_orchestration_only(name: str, patterns: list[re.Pattern[str]]) -> bool:
    """Return True if *name* matches at least one orchestration-only pattern."""
    for pat in patterns:
        if pat.match(name):
            return True
    return False


def extract_env_vars(yaml_path: str) -> set[str]:
    """Extract environment variable *names* from a deploy-config YAML file.

    Handles common patterns:

    docker-compose::

        environment: {FOO: bar}        # dict form
        environment: ["FOO=bar"]        # list form

    Kubernetes::

        env: [{name: FOO, value: bar}]
        env: [{name: FOO, valueFrom: ...}]

    Returns a set of uppercase env-var name strings.
    """
    env_vars: set[str] = set()
    try:
        with open(yaml_path) as fh:
            doc = yaml.safe_load(fh)
    except (yaml.YAMLError, OSError):
        return env_vars

    if not isinstance(doc, dict):
        return env_vars

    def _walk(obj: object) -> None:
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


def get_changed_files(base_ref: str, glob_str: str) -> list[str]:
    """Return list of changed files between *base_ref* and HEAD matching *glob_str*.

    *glob_str* is a space-separated list of ``fnmatch`` glob patterns.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref, "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(
            f"::warning::git diff failed: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return []

    files = [f for f in result.stdout.strip().split("\n") if f]
    globs = [g for g in glob_str.split() if g]
    if not globs:
        return []

    matched: list[str] = []
    for f in files:
        for g in globs:
            if fnmatch(f, g):
                matched.append(f)
                break
    return matched


def get_old_file_content(base_ref: str, filepath: str) -> str | None:
    """Return the file content at *base_ref*, or None if it didn't exist."""
    result = subprocess.run(
        ["git", "show", f"{base_ref}:{filepath}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def resolve_base_ref(base_ref: str) -> str:
    """Resolve the base ref to diff against.

    When *base_ref* is non-empty, returns it unchanged.  Otherwise
    tries ``origin/main`` and ``main`` merge-bases.
    """
    if base_ref:
        return base_ref

    for candidate in ("origin/main", "main"):
        result = subprocess.run(
            ["git", "merge-base", "HEAD", candidate],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

    return ""


# -------------------------------------------------------------------
# Main entry point — usable both as a standalone script and as an
# importable function (call ``check(...)`` from tests).
# -------------------------------------------------------------------


def check(
    *,
    deploy_config_glob: str = "",
    orchestration_only_patterns: str = "",
    ui_config_glob: str = "",
    base_ref: str = "",
) -> int:
    """Run the config-ownership check and return an exit code.

    Parameters mirror the workflow inputs / environment variables.
    Returns 0 when no violations are found, 1 when violations exist.
    """
    patterns = load_patterns(orchestration_only_patterns)
    resolved_base = resolve_base_ref(base_ref)

    if not resolved_base:
        print(
            "::notice::Could not determine base ref — "
            "skipping config ownership check"
        )
        return 0

    errors: list[str] = []

    # ---- deploy-plane config check ----
    if deploy_config_glob:
        for filepath in get_changed_files(resolved_base, deploy_config_glob):
            if not os.path.exists(filepath):
                # File was deleted — nothing to check
                continue

            old_raw = get_old_file_content(resolved_base, filepath)
            old_env_vars: set[str] = set()
            if old_raw is not None:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".yml", delete=False
                ) as tf:
                    tf.write(old_raw)
                    tmp_path = tf.name
                try:
                    old_env_vars = extract_env_vars(tmp_path)
                finally:
                    os.unlink(tmp_path)

            new_env_vars = extract_env_vars(filepath)
            added = new_env_vars - old_env_vars

            for ev in sorted(added):
                if not is_orchestration_only(ev, patterns):
                    errors.append(
                        f"{filepath}: new environment variable '{ev}' "
                        f"is not orchestration-only — this setting "
                        f"should be owned by the component internally, "
                        f"not exposed in deploy-plane config.  "
                        f"See robotsix-standards config-standard.md "
                        f"for the config-ownership model."
                    )

    # ---- central-deploy UI check (opt-in) ----
    if ui_config_glob:
        for filepath in get_changed_files(resolved_base, ui_config_glob):
            if not os.path.exists(filepath):
                continue

            result = subprocess.run(
                ["git", "diff", resolved_base, "HEAD", "--", filepath],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                continue

            for line in result.stdout.split("\n"):
                if not line.startswith("+") or line.startswith("+++"):
                    continue
                # Heuristic: find UPPER_CASE_WITH_UNDERSCORES tokens
                # in added lines — these are likely config key
                # references.
                for token in re.findall(
                    r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b", line
                ):
                    if not is_orchestration_only(token, patterns):
                        errors.append(
                            f"{filepath}: added line references "
                            f"'{token}' which appears to be a "
                            f"component-internal setting exposed in "
                            f"central-deploy UI.  Central-deploy UIs "
                            f"should only handle "
                            f"uniform-across-all-UIs settings.  "
                            f"See robotsix-standards config-standard.md."
                        )

    if errors:
        for msg in errors:
            print(f"::error::{msg}", file=sys.stderr)
        print(
            f"\n{len(errors)} config-ownership violation(s) found.",
            file=sys.stderr,
        )
        print(
            "See robotsix-standards config-standard.md for "
            "the config-ownership model.",
            file=sys.stderr,
        )
        return 1

    print("::notice::No config-ownership violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(
        check(
            deploy_config_glob=os.environ.get("DEPLOY_CONFIG_GLOB", ""),
            orchestration_only_patterns=os.environ.get(
                "ORCHESTRATION_ONLY_PATTERNS", ""
            ),
            ui_config_glob=os.environ.get("UI_CONFIG_GLOB", ""),
            base_ref=os.environ.get("BASE_REF", ""),
        )
    )
