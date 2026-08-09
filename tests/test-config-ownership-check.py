"""Tests for scripts/config_ownership_check.py."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Load the config_ownership_check module
# ---------------------------------------------------------------------------
_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "config_ownership_check", _scripts_dir / "config_ownership_check.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

load_patterns = _module.load_patterns
is_orchestration_only = _module.is_orchestration_only
extract_env_vars = _module.extract_env_vars
get_changed_files = _module.get_changed_files
get_old_file_content = _module.get_old_file_content
resolve_base_ref = _module.resolve_base_ref
check = _module.check


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_PATTERNS = load_patterns("")


def _write_yaml(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# load_patterns
# ---------------------------------------------------------------------------


class TestLoadPatterns:
    def test_empty_string_returns_defaults(self) -> None:
        patterns = load_patterns("")
        assert len(patterns) > 10  # sanity check
        assert all(isinstance(p, re.Pattern) for p in patterns)

    def test_whitespace_only_returns_defaults(self) -> None:
        patterns = load_patterns("   \n  \n  ")
        assert len(patterns) > 10

    def test_comment_only_returns_defaults(self) -> None:
        patterns = load_patterns("# this is a comment\n# another comment")
        assert len(patterns) > 10

    def test_custom_patterns(self) -> None:
        patterns = load_patterns("^FOO$\n^BAR_.*")
        assert len(patterns) == 2
        assert patterns[0].match("FOO")
        assert not patterns[0].match("BAR")
        assert patterns[1].match("BAR_BAZ")

    def test_mixed_comments_and_patterns(self) -> None:
        patterns = load_patterns("# header comment\n^FOO$\n# mid comment\n^BAR$")
        assert len(patterns) == 2

    def test_invalid_regex_raises(self) -> None:
        with pytest.raises(re.error):
            load_patterns("^FOO$\n***INVALID[")


# ---------------------------------------------------------------------------
# is_orchestration_only
# ---------------------------------------------------------------------------


class TestIsOrchestrationOnly:
    def test_matching_pattern(self) -> None:
        assert is_orchestration_only("APP_PORT", _DEFAULT_PATTERNS)

    def test_non_matching_pattern(self) -> None:
        assert not is_orchestration_only("DATABASE_URL", _DEFAULT_PATTERNS)

    def test_empty_name(self) -> None:
        assert not is_orchestration_only("", _DEFAULT_PATTERNS)

    def test_empty_patterns(self) -> None:
        assert not is_orchestration_only("APP_PORT", [])

    def test_common_orchestration_vars(self) -> None:
        orchestration = [
            "PORT",  # ^PORT$
            "APP_PORT",  # .*_PORT$
            "DATA_VOLUME",  # .*_VOLUME$
            "CONFIG_MOUNT_PATH",  # .*_MOUNT_PATH$
            "MAX_MEMORY_LIMIT",  # .*_MEMORY(_LIMIT)?$
            "MAX_CPU_LIMIT",  # .*_CPU(_LIMIT)?$
            "APP_IMAGE",  # .*_IMAGE$
            "APP_TAG",  # .*_TAG$
            "IMAGE_PULL_POLICY",  # .*_PULL_POLICY$
            "SERVICE_HOSTNAME",  # .*_HOST(NAME)?$
            "CLUSTER_DNS",  # .*_DNS$
            "APP_REPLICAS",  # .*_REPLICAS$
            "AUTO_SCALE",  # .*_SCALE$
            "APP_HEALTHCHECK_INTERVAL",  # .*_HEALTHCHECK.*
            "APP_LIVENESS_PROBE",  # .*_LIVENESS.*
            "DOCKER_LOG_DRIVER",  # .*_LOG_DRIVER$
            "AWS_SECRET_ARN",  # .*_SECRET(_ARN|_NAME|_ID)?$
            "MANAGER_NODE",  # .*_NODE$
            "CONTAINER_RESTART_POLICY",  # .*_RESTART_POLICY$
            "PGID",  # ^PGID$
            "PUID",  # ^PUID$
            "USER",  # ^USER$
            "TZ",  # ^TZ$
            "COMPOSE_PROJECT_NAME",  # ^COMPOSE_.*
            "KUBERNETES_NAMESPACE",  # ^KUBERNETES_.*
            "HTTP_PROXY",  # ^HTTPS?_PROXY$
            "NO_PROXY",  # ^NO_PROXY$
            "TRACING_OTLP_ENDPOINT",  # .*_OTLP_ENDPOINT$
            "CONTAINER_RUNTIME_DIR",  # .*_RUNTIME_DIR$
        ]
        for var in orchestration:
            assert is_orchestration_only(var, _DEFAULT_PATTERNS), f"{var} should match"

    def test_common_component_internal_vars(self) -> None:
        internal = [
            "DATABASE_URL",
            "SECRET_KEY",
            "API_KEY",
            "FEATURE_FLAG_ENABLE_NEW_UI",
            "TIMEOUT_SECONDS",
            "LOG_LEVEL",
            "DEBUG",
            "REDIS_URL",
            "SENTRY_DSN",
            "OAUTH_CLIENT_ID",
        ]
        for var in internal:
            assert not is_orchestration_only(
                var, _DEFAULT_PATTERNS
            ), f"{var} should not match"


# ---------------------------------------------------------------------------
# extract_env_vars
# ---------------------------------------------------------------------------


class TestExtractEnvVars:
    def test_dict_form(self, tmp_path: Path) -> None:
        yaml_path = _write_yaml(
            tmp_path / "compose.yml",
            """\
services:
  app:
    environment:
      FOO: bar
      BAZ: qux
""",
        )
        result = extract_env_vars(str(yaml_path))
        assert result == {"FOO", "BAZ"}

    def test_list_form(self, tmp_path: Path) -> None:
        yaml_path = _write_yaml(
            tmp_path / "compose.yml",
            """\
services:
  app:
    environment:
      - FOO=bar
      - BAZ=qux
      - NO_EQUALS
""",
        )
        result = extract_env_vars(str(yaml_path))
        assert result == {"FOO", "BAZ"}

    def test_kubernetes_env_with_name_value(self, tmp_path: Path) -> None:
        yaml_path = _write_yaml(
            tmp_path / "deploy.yml",
            """\
spec:
  containers:
    - env:
        - name: FOO
          value: bar
        - name: BAZ
          value: qux
""",
        )
        result = extract_env_vars(str(yaml_path))
        assert result == {"FOO", "BAZ"}

    def test_kubernetes_env_with_value_from(self, tmp_path: Path) -> None:
        yaml_path = _write_yaml(
            tmp_path / "deploy.yml",
            """\
spec:
  containers:
    - env:
        - name: SECRET_TOKEN
          valueFrom:
            secretKeyRef:
              name: my-secret
              key: token
""",
        )
        result = extract_env_vars(str(yaml_path))
        assert result == {"SECRET_TOKEN"}

    def test_nested_services(self, tmp_path: Path) -> None:
        yaml_path = _write_yaml(
            tmp_path / "compose.yml",
            """\
services:
  web:
    environment:
      WEB_PORT: "8080"
  worker:
    environment:
      QUEUE_URL: redis://cache:6379
  db:
    environment:
      POSTGRES_USER: admin
""",
        )
        result = extract_env_vars(str(yaml_path))
        assert result == {"WEB_PORT", "QUEUE_URL", "POSTGRES_USER"}

    def test_missing_file(self) -> None:
        result = extract_env_vars("/nonexistent/path/config.yml")
        assert result == set()

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        yaml_path = _write_yaml(
            tmp_path / "broken.yml",
            "{ invalid: yaml: [[[",
        )
        result = extract_env_vars(str(yaml_path))
        assert result == set()

    def test_non_dict_top_level(self, tmp_path: Path) -> None:
        yaml_path = _write_yaml(
            tmp_path / "list.yml",
            "- item1\n- item2\n",
        )
        result = extract_env_vars(str(yaml_path))
        assert result == set()

    def test_no_environment_key(self, tmp_path: Path) -> None:
        yaml_path = _write_yaml(
            tmp_path / "simple.yml",
            """\
name: my-app
version: "1.0"
""",
        )
        result = extract_env_vars(str(yaml_path))
        assert result == set()

    def test_dict_and_kubernetes_env_in_same_file(self, tmp_path: Path) -> None:
        """docker-compose dict env + Kubernetes-style env in separate blocks."""
        yaml_path = _write_yaml(
            tmp_path / "compose.yml",
            """\
services:
  app:
    environment:
      DICT_VAR: "val1"
  sidecar:
    env:
      - name: K8S_VAR
        value: val3
""",
        )
        result = extract_env_vars(str(yaml_path))
        assert result == {"DICT_VAR", "K8S_VAR"}

    def test_list_form_env_vars(self, tmp_path: Path) -> None:
        yaml_path = _write_yaml(
            tmp_path / "compose.yml",
            """\
services:
  app:
    environment:
      - LIST_VAR=val2
      - ANOTHER=val3
""",
        )
        result = extract_env_vars(str(yaml_path))
        assert result == {"LIST_VAR", "ANOTHER"}

    def test_nested_deployment_structure(self, tmp_path: Path) -> None:
        yaml_path = _write_yaml(
            tmp_path / "k8s.yml",
            """\
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - env:
            - name: NESTED_VAR
              value: deep
""",
        )
        result = extract_env_vars(str(yaml_path))
        assert result == {"NESTED_VAR"}


# ---------------------------------------------------------------------------
# resolve_base_ref
# ---------------------------------------------------------------------------


class TestResolveBaseRef:
    def test_explicit_ref_passed_through(self) -> None:
        assert resolve_base_ref("abc123def") == "abc123def"
        assert resolve_base_ref("origin/feature-branch") == "origin/feature-branch"

    def test_auto_detect_origin_main(self) -> None:
        with mock.patch.object(
            _module.subprocess, "run"
        ) as mock_run:
            mock_run.return_value = _mock_run_result(
                returncode=0, stdout="def456789\n"
            )
            result = resolve_base_ref("")
            assert result == "def456789"

    def test_auto_detect_fallback_to_main(self) -> None:
        with mock.patch.object(
            _module.subprocess, "run"
        ) as mock_run:
            # origin/main fails, main succeeds
            mock_run.side_effect = [
                _mock_run_result(returncode=1, stdout=""),
                _mock_run_result(returncode=0, stdout="ghi789012\n"),
            ]
            result = resolve_base_ref("")
            assert result == "ghi789012"

    def test_auto_detect_both_fail(self) -> None:
        with mock.patch.object(
            _module.subprocess, "run"
        ) as mock_run:
            mock_run.return_value = _mock_run_result(returncode=1, stdout="")
            result = resolve_base_ref("")
            assert result == ""


# ---------------------------------------------------------------------------
# get_changed_files
# ---------------------------------------------------------------------------


class TestGetChangedFiles:
    def test_matches_glob(self) -> None:
        with mock.patch.object(
            _module.subprocess, "run"
        ) as mock_run:
            mock_run.return_value = _mock_run_result(
                returncode=0,
                stdout="deploy/sub/app.yml\ndeploy/sub/db.yml\nsrc/main.py\n",
            )
            result = get_changed_files("HEAD~1", "deploy/**/*.yml")
            assert result == ["deploy/sub/app.yml", "deploy/sub/db.yml"]

    def test_empty_changes(self) -> None:
        with mock.patch.object(
            _module.subprocess, "run"
        ) as mock_run:
            mock_run.return_value = _mock_run_result(returncode=0, stdout="\n")
            result = get_changed_files("HEAD~1", "deploy/**/*.yml")
            assert result == []

    def test_git_diff_failure(self) -> None:
        with mock.patch.object(
            _module.subprocess, "run"
        ) as mock_run:
            mock_run.return_value = _mock_run_result(
                returncode=128, stderr="fatal: bad revision"
            )
            result = get_changed_files("bad-ref", "deploy/**/*.yml")
            assert result == []

    def test_no_globs(self) -> None:
        with mock.patch.object(
            _module.subprocess, "run"
        ) as mock_run:
            mock_run.return_value = _mock_run_result(
                returncode=0, stdout="deploy/app.yml\n"
            )
            result = get_changed_files("HEAD~1", "")
            assert result == []

    def test_multiple_glob_patterns(self) -> None:
        with mock.patch.object(
            _module.subprocess, "run"
        ) as mock_run:
            mock_run.return_value = _mock_run_result(
                returncode=0,
                stdout="deploy/sub/app.yml\ndeploy/db.yml\nconfig/ui.json\nsrc/main.py\n",
            )
            result = get_changed_files(
                "HEAD~1", "deploy/**/*.yml config/*.json"
            )
            assert sorted(result) == ["config/ui.json", "deploy/sub/app.yml"]


# ---------------------------------------------------------------------------
# get_old_file_content
# ---------------------------------------------------------------------------


class TestGetOldFileContent:
    def test_returns_content(self) -> None:
        with mock.patch.object(
            _module.subprocess, "run"
        ) as mock_run:
            mock_run.return_value = _mock_run_result(
                returncode=0, stdout="services:\n  app:\n    image: foo\n"
            )
            result = get_old_file_content("HEAD~1", "deploy/app.yml")
            assert result == "services:\n  app:\n    image: foo\n"

    def test_file_did_not_exist(self) -> None:
        with mock.patch.object(
            _module.subprocess, "run"
        ) as mock_run:
            mock_run.return_value = _mock_run_result(returncode=128, stdout="")
            result = get_old_file_content("HEAD~1", "deploy/new.yml")
            assert result is None


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------


class TestCheck:
    def test_no_base_ref_skips(self, capsys) -> None:
        """When base_ref resolves to empty, check returns 0 with notice."""
        with mock.patch.object(
            _module, "resolve_base_ref", return_value=""
        ):
            result = check(deploy_config_glob="deploy/**/*.yml")
            assert result == 0
        captured = capsys.readouterr()
        assert "Could not determine base ref" in captured.out

    def test_deleted_files_skipped(self, tmp_path: Path, capsys) -> None:
        """Files returned by git diff that no longer exist are skipped."""
        with mock.patch.object(
            _module, "resolve_base_ref", return_value="abc123"
        ), mock.patch.object(
            _module,
            "get_changed_files",
            return_value=["deploy/deleted.yml"],
        ):
            # File does not exist on disk → os.path.exists returns False
            result = check(deploy_config_glob="deploy/**/*.yml")
            assert result == 0
        captured = capsys.readouterr()
        assert "No config-ownership violations found" in captured.out

    def test_violation_detected(self, tmp_path: Path) -> None:
        """A new non-orchestration env var triggers an error."""
        yaml_path = _write_yaml(
            tmp_path / "compose.yml",
            """\
services:
  app:
    environment:
      DATABASE_URL: postgres://localhost/db
""",
        )
        with mock.patch.object(
            _module, "resolve_base_ref", return_value="abc123"
        ), mock.patch.object(
            _module,
            "get_changed_files",
            return_value=[str(yaml_path)],
        ), mock.patch.object(
            _module,
            "get_old_file_content",
            return_value="services:\n  app:\n    environment: {}\n",
        ):
            result = check(deploy_config_glob="deploy/**/*.yml")
            assert result == 1

    def test_orchestration_only_no_violation(self, tmp_path: Path) -> None:
        """A new orchestration-only env var passes."""
        yaml_path = _write_yaml(
            tmp_path / "compose.yml",
            """\
services:
  app:
    environment:
      APP_PORT: "8080"
""",
        )
        with mock.patch.object(
            _module, "resolve_base_ref", return_value="abc123"
        ), mock.patch.object(
            _module,
            "get_changed_files",
            return_value=[str(yaml_path)],
        ), mock.patch.object(
            _module,
            "get_old_file_content",
            return_value="services:\n  app:\n    environment: {}\n",
        ):
            result = check(deploy_config_glob="deploy/**/*.yml")
            assert result == 0

    def test_new_file_all_violations(self, tmp_path: Path) -> None:
        """Brand-new file (old content is None) — all env vars checked."""
        yaml_path = _write_yaml(
            tmp_path / "compose.yml",
            """\
services:
  app:
    environment:
      SECRET_KEY: abc123
      API_TOKEN: xyz789
""",
        )
        with mock.patch.object(
            _module, "resolve_base_ref", return_value="abc123"
        ), mock.patch.object(
            _module,
            "get_changed_files",
            return_value=[str(yaml_path)],
        ), mock.patch.object(
            _module,
            "get_old_file_content",
            return_value=None,
        ):
            result = check(deploy_config_glob="deploy/**/*.yml")
            assert result == 1

    def test_custom_orchestration_patterns(self, tmp_path: Path) -> None:
        """Custom patterns allow non-default env vars."""
        yaml_path = _write_yaml(
            tmp_path / "compose.yml",
            """\
services:
  app:
    environment:
      CUSTOM_CONFIG_KEY: "some-value"
""",
        )
        with mock.patch.object(
            _module, "resolve_base_ref", return_value="abc123"
        ), mock.patch.object(
            _module,
            "get_changed_files",
            return_value=[str(yaml_path)],
        ), mock.patch.object(
            _module,
            "get_old_file_content",
            return_value="services:\n  app:\n    environment: {}\n",
        ):
            result = check(
                deploy_config_glob="deploy/**/*.yml",
                orchestration_only_patterns="^CUSTOM_CONFIG_KEY$",
            )
            assert result == 0

    def test_multiple_files_mixed_violations(self, tmp_path: Path) -> None:
        """Multiple changed files — some violations, some not."""
        yaml1 = _write_yaml(
            tmp_path / "compose1.yml",
            """\
services:
  app:
    environment:
      DATABASE_URL: postgres://localhost/db
""",
        )
        yaml2 = _write_yaml(
            tmp_path / "compose2.yml",
            """\
services:
  app:
    environment:
      APP_PORT: "8080"
""",
        )
        with mock.patch.object(
            _module, "resolve_base_ref", return_value="abc123"
        ), mock.patch.object(
            _module,
            "get_changed_files",
            return_value=[str(yaml1), str(yaml2)],
        ), mock.patch.object(
            _module,
            "get_old_file_content",
            side_effect=[
                "services:\n  app:\n    environment: {}\n",
                "services:\n  app:\n    environment: {}\n",
            ],
        ):
            result = check(deploy_config_glob="deploy/**/*.yml")
            assert result == 1

    def test_ui_config_glob_added_line(self, tmp_path: Path) -> None:
        """UI config check flags non-orchestration tokens in added lines."""
        ui_path = _write_yaml(
            tmp_path / "ui-config.yml",
            "some: content\n",
        )
        # git diff returns a line adding a non-orchestration token
        git_diff_output = (
            "+++ b/config/ui.yml\n"
            "@@ -0,0 +1 @@\n"
            "+    DATABASE_URL: postgres://localhost/db\n"
        )
        with mock.patch.object(
            _module, "resolve_base_ref", return_value="abc123"
        ), mock.patch.object(
            _module,
            "get_changed_files",
            return_value=[str(ui_path)],
        ), mock.patch.object(
            _module.subprocess,
            "run",
            return_value=_mock_run_result(returncode=0, stdout=git_diff_output),
        ):
            result = check(
                deploy_config_glob="",
                ui_config_glob="config/**/*.yml",
            )
            assert result == 1

    def test_ui_config_glob_orchestration_token_ok(self, tmp_path: Path) -> None:
        """UI config check passes orchestration-only tokens."""
        ui_path = _write_yaml(
            tmp_path / "ui-config.yml",
            "some: content\n",
        )
        git_diff_output = (
            "+++ b/config/ui.yml\n"
            "@@ -0,0 +1 @@\n"
            "+    APP_PORT: \"8080\"\n"
        )
        with mock.patch.object(
            _module, "resolve_base_ref", return_value="abc123"
        ), mock.patch.object(
            _module,
            "get_changed_files",
            return_value=[str(ui_path)],
        ), mock.patch.object(
            _module.subprocess,
            "run",
            return_value=_mock_run_result(returncode=0, stdout=git_diff_output),
        ):
            result = check(
                deploy_config_glob="",
                ui_config_glob="config/**/*.yml",
            )
            assert result == 0

    def test_no_globs_provided(self) -> None:
        """No deploy or UI globs — exits early with no violations."""
        with mock.patch.object(
            _module, "resolve_base_ref", return_value="abc123"
        ):
            result = check()
            assert result == 0


# ---------------------------------------------------------------------------
# Helpers for mocking subprocess
# ---------------------------------------------------------------------------


def _mock_run_result(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )
