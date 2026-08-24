"""Tests for scripts/check_local_action_refs.py."""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the check_local_action_refs module
# ---------------------------------------------------------------------------
_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "check_local_action_refs", _scripts_dir / "check_local_action_refs.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

check = _module.check
_action_file_exists = _module._action_file_exists
_collect_local_refs_from_doc = _module._collect_local_refs_from_doc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))
    return path


def _write_workflow(workflow_dir: Path, name: str, content: str) -> Path:
    return _write_file(workflow_dir / name, content)


def _write_action(actions_dir: Path, name: str, filename: str = "action.yml") -> Path:
    return _write_file(
        actions_dir / name / filename,
        """
        name: Test action
        runs:
          using: composite
          steps: []
        """,
    )


_WORKFLOW = """
    jobs:
      test:
        runs-on: ubuntu-latest
        steps:
          - uses: ./.github/actions/{action}
    """


# ---------------------------------------------------------------------------
# _action_file_exists
# ---------------------------------------------------------------------------


class TestActionFileExists:
    def test_action_yml(self, tmp_path: Path) -> None:
        _write_action(tmp_path, "foo", "action.yml")
        assert _action_file_exists(str(tmp_path), "foo")

    def test_action_yaml(self, tmp_path: Path) -> None:
        _write_action(tmp_path, "foo", "action.yaml")
        assert _action_file_exists(str(tmp_path), "foo")

    def test_missing(self, tmp_path: Path) -> None:
        assert not _action_file_exists(str(tmp_path), "foo")


# ---------------------------------------------------------------------------
# _collect_local_refs_from_doc
# ---------------------------------------------------------------------------


class TestCollectLocalRefsFromDoc:
    def test_collects_local_refs(self) -> None:
        doc = {
            "jobs": {
                "a": {
                    "steps": [
                        {"uses": "./.github/actions/foo"},
                        {"uses": "actions/checkout@v4"},
                    ]
                }
            }
        }
        assert _collect_local_refs_from_doc(doc) == ["foo"]

    def test_collects_own_repo_absolute_refs(self) -> None:
        doc = {
            "jobs": {
                "a": {
                    "steps": [
                        {
                            "uses": "damien-robotsix/robotsix-github-workflows/.github/actions/python-setup@abc123"
                        },
                        {"uses": "actions/checkout@v4"},
                    ]
                }
            }
        }
        assert _collect_local_refs_from_doc(doc) == ["python-setup"]

    def test_non_dict_returns_empty(self) -> None:
        assert _collect_local_refs_from_doc(None) == []
        assert _collect_local_refs_from_doc([]) == []
        assert _collect_local_refs_from_doc({"jobs": None}) == []

    def test_malformed_steps_are_skipped(self) -> None:
        doc = {
            "jobs": {
                "a": {"steps": None},
                "b": {"steps": [None, {"uses": 42}, "not-a-dict"]},
            }
        }
        assert _collect_local_refs_from_doc(doc) == []


# ---------------------------------------------------------------------------
# check() integration tests
# ---------------------------------------------------------------------------


class TestCheck:
    def test_missing_workflow_dir(self, capsys) -> None:
        assert check(workflow_dir="/nonexistent/path") == 0
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_no_workflow_files(self, tmp_path: Path, capsys) -> None:
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        assert check(workflow_dir=str(wf_dir)) == 0
        captured = capsys.readouterr()
        assert "No workflow files" in captured.out

    def test_valid_reference_action_yml(self, tmp_path: Path) -> None:
        wf_dir = tmp_path / "workflows"
        actions_dir = tmp_path / "actions"
        _write_workflow(wf_dir, "ci.yml", _WORKFLOW.format(action="foo"))
        _write_action(actions_dir, "foo", "action.yml")
        assert check(workflow_dir=str(wf_dir), actions_dir=str(actions_dir)) == 0

    def test_valid_reference_action_yaml(self, tmp_path: Path) -> None:
        wf_dir = tmp_path / "workflows"
        actions_dir = tmp_path / "actions"
        _write_workflow(wf_dir, "ci.yml", _WORKFLOW.format(action="foo"))
        _write_action(actions_dir, "foo", "action.yaml")
        assert check(workflow_dir=str(wf_dir), actions_dir=str(actions_dir)) == 0

    def test_missing_action_fails(self, tmp_path: Path, capsys) -> None:
        wf_dir = tmp_path / "workflows"
        actions_dir = tmp_path / "actions"
        _write_workflow(wf_dir, "ci.yml", _WORKFLOW.format(action="foo"))
        assert check(workflow_dir=str(wf_dir), actions_dir=str(actions_dir)) == 1
        captured = capsys.readouterr()
        assert "foo" in captured.err

    def test_non_local_uses_are_ignored(self, tmp_path: Path) -> None:
        wf_dir = tmp_path / "workflows"
        _write_workflow(
            wf_dir,
            "ci.yml",
            """
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                  - uses: owner/repo/.github/workflows/lint.yml@main
            """,
        )
        assert check(workflow_dir=str(wf_dir), actions_dir="/nonexistent") == 0

    def test_invalid_yaml_fails(self, tmp_path: Path, capsys) -> None:
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        _write_workflow(wf_dir, "ci.yml", "jobs: [unclosed\n")
        assert check(workflow_dir=str(wf_dir)) == 1
        captured = capsys.readouterr()
        assert "invalid YAML" in captured.err

    def test_invalid_local_reference_with_subpath_fails(
        self, tmp_path: Path, capsys
    ) -> None:
        wf_dir = tmp_path / "workflows"
        _write_workflow(
            wf_dir,
            "ci.yml",
            _WORKFLOW.format(action="foo/bar"),
        )
        assert check(workflow_dir=str(wf_dir)) == 1
        captured = capsys.readouterr()
        assert "invalid local action reference" in captured.err

    def test_orphan_check_disabled_by_default(self, tmp_path: Path) -> None:
        wf_dir = tmp_path / "workflows"
        actions_dir = tmp_path / "actions"
        _write_workflow(wf_dir, "ci.yml", _WORKFLOW.format(action="foo"))
        _write_action(actions_dir, "foo")
        _write_action(actions_dir, "orphan")
        assert check(workflow_dir=str(wf_dir), actions_dir=str(actions_dir)) == 0

    def test_orphan_check_flags_unreferenced_action(
        self, tmp_path: Path, capsys
    ) -> None:
        wf_dir = tmp_path / "workflows"
        actions_dir = tmp_path / "actions"
        _write_workflow(wf_dir, "ci.yml", _WORKFLOW.format(action="foo"))
        _write_action(actions_dir, "foo")
        _write_action(actions_dir, "orphan")
        assert (
            check(
                workflow_dir=str(wf_dir),
                actions_dir=str(actions_dir),
                check_orphans=True,
            )
            == 1
        )
        captured = capsys.readouterr()
        assert "orphan" in captured.err

    def test_orphan_check_passes_when_all_referenced(self, tmp_path: Path) -> None:
        wf_dir = tmp_path / "workflows"
        actions_dir = tmp_path / "actions"
        _write_workflow(wf_dir, "ci.yml", _WORKFLOW.format(action="foo"))
        _write_action(actions_dir, "foo")
        assert (
            check(
                workflow_dir=str(wf_dir),
                actions_dir=str(actions_dir),
                check_orphans=True,
            )
            == 0
        )

    def test_reference_in_any_workflow_counts_for_orphan_check(
        self, tmp_path: Path
    ) -> None:
        wf_dir = tmp_path / "workflows"
        actions_dir = tmp_path / "actions"
        _write_workflow(wf_dir, "a.yml", _WORKFLOW.format(action="foo"))
        _write_workflow(wf_dir, "b.yml", _WORKFLOW.format(action="bar"))
        _write_action(actions_dir, "foo")
        _write_action(actions_dir, "bar")
        assert (
            check(
                workflow_dir=str(wf_dir),
                actions_dir=str(actions_dir),
                check_orphans=True,
            )
            == 0
        )
