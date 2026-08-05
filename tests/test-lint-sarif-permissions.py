"""Tests for scripts/lint_sarif_permissions.py."""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the lint_sarif_permissions module
# ---------------------------------------------------------------------------
_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "lint_sarif_permissions", _scripts_dir / "lint_sarif_permissions.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

check = _module.check
_has_se_write = _module._has_se_write


# ---------------------------------------------------------------------------
# _has_se_write unit tests
# ---------------------------------------------------------------------------


class TestHasSeWrite:
    def test_dict_with_write(self) -> None:
        assert _has_se_write({"security-events": "write"})

    def test_dict_without_write(self) -> None:
        assert not _has_se_write({"security-events": "read"})
        assert not _has_se_write({"security-events": "none"})
        assert not _has_se_write({"contents": "read"})

    def test_dict_empty(self) -> None:
        assert not _has_se_write({})

    def test_string_write_all(self) -> None:
        assert _has_se_write("write-all")

    def test_string_read_all(self) -> None:
        assert not _has_se_write("read-all")

    def test_none(self) -> None:
        assert not _has_se_write(None)


# ---------------------------------------------------------------------------
# check() integration tests
# ---------------------------------------------------------------------------


def _write_workflow(workflow_dir: Path, name: str, content: str) -> Path:
    path = workflow_dir / name
    path.write_text(textwrap.dedent(content))
    return path


class TestCheck:
    def test_no_sarif_workflows(self, capsys) -> None:
        """Empty sarif_workflows returns 0 with notice."""
        assert check(sarif_workflows=set()) == 0
        captured = capsys.readouterr()
        assert "No SARIF workflows configured" in captured.out

    def test_missing_workflow_dir(self, capsys) -> None:
        """Non-existent workflow_dir returns 0 with notice."""
        assert (
            check(sarif_workflows={"codeql.yml"}, workflow_dir="/nonexistent/path")
            == 0
        )
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_job_with_security_events_write(self, tmp_path: Path) -> None:
        """Job with explicit security-events:write passes."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "ci.yml",
            """
            permissions:
              security-events: write
            jobs:
              codeql:
                runs-on: ubuntu-latest
                steps:
                  - uses: owner/repo/.github/workflows/codeql.yml@abc
            """,
        )
        assert check(sarif_workflows={"codeql.yml"}, workflow_dir=str(wf_dir)) == 0

    def test_job_with_security_events_none_fails(self, tmp_path: Path) -> None:
        """Job with explicit security-events: none fails."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "ci.yml",
            """
            permissions:
              security-events: none
            jobs:
              codeql:
                runs-on: ubuntu-latest
                steps:
                  - uses: owner/repo/.github/workflows/codeql.yml@abc
            """,
        )
        assert check(sarif_workflows={"codeql.yml"}, workflow_dir=str(wf_dir)) == 1

    def test_job_with_security_events_read_fails(self, tmp_path: Path) -> None:
        """Job with explicit security-events: read fails."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "ci.yml",
            """
            permissions:
              security-events: read
            jobs:
              codeql:
                runs-on: ubuntu-latest
                steps:
                  - uses: owner/repo/.github/workflows/codeql.yml@abc
            """,
        )
        assert check(sarif_workflows={"codeql.yml"}, workflow_dir=str(wf_dir)) == 1

    def test_job_level_permission_overrides_root(self, tmp_path: Path) -> None:
        """Job-level security-events:write overrides restrictive root."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "ci.yml",
            """
            permissions: {}
            jobs:
              codeql:
                runs-on: ubuntu-latest
                permissions:
                  security-events: write
                steps:
                  - uses: owner/repo/.github/workflows/codeql.yml@abc
            """,
        )
        assert check(sarif_workflows={"codeql.yml"}, workflow_dir=str(wf_dir)) == 0

    def test_write_all_at_root_passes(self, tmp_path: Path) -> None:
        """write-all at root level grants security-events:write."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "ci.yml",
            """
            permissions: write-all
            jobs:
              codeql:
                runs-on: ubuntu-latest
                steps:
                  - uses: owner/repo/.github/workflows/codeql.yml@abc
            """,
        )
        assert check(sarif_workflows={"codeql.yml"}, workflow_dir=str(wf_dir)) == 0

    def test_no_permissions_block_inherits_defaults(self, tmp_path: Path) -> None:
        """No permissions block at all → defaults are permissive → passes."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "ci.yml",
            """
            jobs:
              codeql:
                runs-on: ubuntu-latest
                steps:
                  - uses: owner/repo/.github/workflows/codeql.yml@abc
            """,
        )
        assert check(sarif_workflows={"codeql.yml"}, workflow_dir=str(wf_dir)) == 0

    def test_job_not_using_sarif_workflow_is_ignored(self, tmp_path: Path) -> None:
        """Jobs not using SARIF workflows are not checked."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "ci.yml",
            """
            permissions: {}
            jobs:
              tests:
                runs-on: ubuntu-latest
                steps:
                  - uses: owner/repo/.github/workflows/python-ci.yml@abc
            """,
        )
        assert check(sarif_workflows={"codeql.yml"}, workflow_dir=str(wf_dir)) == 0

    def test_multiple_sarif_workflows(self, tmp_path: Path) -> None:
        """Multiple SARIF workflows checked in one run."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "ci.yml",
            """
            permissions:
              security-events: write
            jobs:
              codeql:
                runs-on: ubuntu-latest
                steps:
                  - uses: owner/repo/.github/workflows/codeql.yml@abc
              scan:
                runs-on: ubuntu-latest
                steps:
                  - uses: owner/repo/.github/workflows/scan-container.yml@abc
            """,
        )
        assert (
            check(
                sarif_workflows={"codeql.yml", "scan-container.yml"},
                workflow_dir=str(wf_dir),
            )
            == 0
        )

    def test_uses_with_at_sign_ref(self, tmp_path: Path) -> None:
        """uses: lines with @ref suffix are stripped correctly."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "ci.yml",
            """
            permissions:
              security-events: write
            jobs:
              codeql:
                runs-on: ubuntu-latest
                steps:
                  - uses: damien-robotsix/robotsix-github-workflows/.github/workflows/codeql.yml@abc123def
            """,
        )
        assert check(sarif_workflows={"codeql.yml"}, workflow_dir=str(wf_dir)) == 0

    def test_invalid_yaml_reports_error(self, tmp_path: Path) -> None:
        """Invalid YAML in a workflow file is reported as an error."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(wf_dir, "broken.yml", "{\tinvalid: yaml")
        assert check(sarif_workflows={"codeql.yml"}, workflow_dir=str(wf_dir)) == 1

    def test_non_workflow_files_skipped(self, tmp_path: Path) -> None:
        """Files without a jobs: key are skipped."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(wf_dir, "action.yml", "name: some action\nruns:\n  using: composite\n")
        assert check(sarif_workflows={"codeql.yml"}, workflow_dir=str(wf_dir)) == 0
