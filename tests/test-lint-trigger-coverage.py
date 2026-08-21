"""Tests for scripts/lint_trigger_coverage.py."""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the lint_trigger_coverage module
# ---------------------------------------------------------------------------
_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "lint_trigger_coverage", _scripts_dir / "lint_trigger_coverage.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

check = _module.check
_extract_event_names = _module._extract_event_names


# ---------------------------------------------------------------------------
# _extract_event_names unit tests
# ---------------------------------------------------------------------------


class TestExtractEventNames:
    def test_string(self) -> None:
        assert _extract_event_names("push") == {"push"}

    def test_list(self) -> None:
        assert _extract_event_names(["push", "pull_request"]) == {
            "push",
            "pull_request",
        }

    def test_dict(self) -> None:
        assert _extract_event_names(
            {"push": None, "schedule": [{"cron": "0 0 * * 1"}]}
        ) == {"push", "schedule"}

    def test_none(self) -> None:
        assert _extract_event_names(None) == set()

    def test_empty_list(self) -> None:
        assert _extract_event_names([]) == set()


# ---------------------------------------------------------------------------
# check() integration tests
# ---------------------------------------------------------------------------


def _write_workflow(workflow_dir: Path, name: str, content: str) -> Path:
    path = workflow_dir / name
    path.write_text(textwrap.dedent(content))
    return path


class TestCheck:
    def test_missing_workflow_dir(self, capsys) -> None:
        """Non-existent workflow_dir returns 0 with notice."""
        assert check(workflow_dir="/nonexistent/path") == 0
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_job_with_matching_trigger(self, tmp_path: Path) -> None:
        """Job if: matches a declared trigger — passes."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "test.yml",
            """
            on:
              schedule:
                - cron: "0 6 * * 1"
              workflow_dispatch:
              workflow_call:
            jobs:
              sweep:
                if: ${{ github.event_name == 'workflow_call' }}
                runs-on: ubuntu-latest
                steps:
                  - run: echo hi
            """,
        )
        assert check(workflow_dir=str(wf_dir)) == 0

    def test_job_excludes_every_trigger_eq(self, tmp_path: Path) -> None:
        """Job if: targets an event NOT in on: — fails."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "test.yml",
            """
            on:
              schedule:
                - cron: "0 6 * * 1"
              workflow_dispatch:
            jobs:
              sweep:
                if: ${{ github.event_name == 'workflow_call' }}
                runs-on: ubuntu-latest
                steps:
                  - run: echo hi
            """,
        )
        assert check(workflow_dir=str(wf_dir)) == 1

    def test_job_excludes_only_trigger_neq(self, tmp_path: Path) -> None:
        """Job if: != the ONLY declared trigger — fails."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "test.yml",
            """
            on: push
            jobs:
              build:
                if: ${{ github.event_name != 'push' }}
                runs-on: ubuntu-latest
                steps:
                  - run: echo hi
            """,
        )
        assert check(workflow_dir=str(wf_dir)) == 1

    def test_job_neq_with_multiple_triggers(self, tmp_path: Path) -> None:
        """Job if: != one trigger but others exist — passes."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "test.yml",
            """
            on: [push, pull_request]
            jobs:
              build:
                if: ${{ github.event_name != 'push' }}
                runs-on: ubuntu-latest
                steps:
                  - run: echo hi
            """,
        )
        assert check(workflow_dir=str(wf_dir)) == 0

    def test_job_no_if(self, tmp_path: Path) -> None:
        """Job without an if: — passes."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "test.yml",
            """
            on: push
            jobs:
              build:
                runs-on: ubuntu-latest
                steps:
                  - run: echo hi
            """,
        )
        assert check(workflow_dir=str(wf_dir)) == 0

    def test_multiple_errors(self, tmp_path: Path) -> None:
        """Multiple violating jobs in one file — all reported."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(
            wf_dir,
            "test.yml",
            """
            on: push
            jobs:
              a:
                if: ${{ github.event_name == 'schedule' }}
                runs-on: ubuntu-latest
                steps:
                  - run: echo a
              b:
                if: ${{ github.event_name == 'workflow_call' }}
                runs-on: ubuntu-latest
                steps:
                  - run: echo b
            """,
        )
        assert check(workflow_dir=str(wf_dir)) == 1