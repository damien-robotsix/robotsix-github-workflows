"""Tests for scripts/check_workflow_rules.py."""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the check_workflow_rules module
# ---------------------------------------------------------------------------
_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "check_workflow_rules", _scripts_dir / "check_workflow_rules.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

check = _module.check

SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
OWN = "damien-robotsix/robotsix-github-workflows"


@pytest.fixture(autouse=True)
def _no_github_repository(monkeypatch):
    # Exercise the fallback slug in check_local_action_refs.
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)


def _run(tmp_path: Path, *, workflow: str | None = None, action: str | None = None) -> int:
    wf_dir = tmp_path / "workflows"
    act_dir = tmp_path / "actions"
    wf_dir.mkdir()
    act_dir.mkdir()
    if workflow is not None:
        (wf_dir / "wf.yml").write_text(textwrap.dedent(workflow))
    if action is not None:
        (act_dir / "my-action").mkdir()
        (act_dir / "my-action" / "action.yml").write_text(textwrap.dedent(action))
    return check(workflow_dir=str(wf_dir), actions_dir=str(act_dir))


def _wf_step(step: str) -> str:
    return (
        "on: push\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n" + textwrap.indent(textwrap.dedent(step), "      ")
    )


# ---------------------------------------------------------------------------
# Rule 1
# ---------------------------------------------------------------------------


def test_sha_with_version_comment_passes(tmp_path):
    assert _run(tmp_path, workflow=_wf_step(f"- uses: foo/bar@{SHA}  # v7.0.2\n")) == 0


def test_short_version_comment_accepted(tmp_path):
    assert _run(tmp_path, workflow=_wf_step(f"- uses: foo/bar@{SHA}  # v4\n")) == 0


def test_floating_tag_fails(tmp_path, capsys):
    assert _run(tmp_path, workflow=_wf_step("- uses: foo/bar@v4  # v4\n")) == 1
    err = capsys.readouterr().err
    assert "::error::" in err
    assert "wf.yml:6:" in err
    assert "40-char" in err


def test_sha_without_comment_fails(tmp_path, capsys):
    assert _run(tmp_path, workflow=_wf_step(f"- uses: foo/bar@{SHA}\n")) == 1
    err = capsys.readouterr().err
    assert "wf.yml:6:" in err
    assert "version comment" in err


def test_own_repo_ref_without_comment_passes(tmp_path):
    step = f"- uses: {OWN}/.github/actions/python-setup@{SHA}\n"
    assert _run(tmp_path, workflow=_wf_step(step)) == 0


def test_own_repo_ref_without_sha_fails(tmp_path):
    step = f"- uses: {OWN}/.github/actions/python-setup@main\n"
    assert _run(tmp_path, workflow=_wf_step(step)) == 1


def test_own_repo_prefix_follows_github_repository(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "other/repo")
    step = f"- uses: {OWN}/.github/actions/python-setup@{SHA}\n"
    assert _run(tmp_path, workflow=_wf_step(step)) == 1


def test_local_ref_ignored(tmp_path):
    workflow = (
        "on: push\n"
        "jobs:\n"
        "  call:\n"
        "    uses: ./.github/workflows/baseline-check.yml  # zizmor: ignore[self-repository]\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: ./.github/actions/python-setup\n"
    )
    assert _run(tmp_path, workflow=workflow) == 0


# ---------------------------------------------------------------------------
# Rule 5
# ---------------------------------------------------------------------------

_WC = """\
on:
  workflow_call:
    inputs:
      image:
        type: string
        default: {default}
jobs: {{}}
"""


def test_static_default_passes(tmp_path):
    assert _run(tmp_path, workflow=_WC.format(default='""')) == 0


def test_expression_default_fails(tmp_path, capsys):
    workflow = _WC.format(default="'ghcr.io/${{ github.repository }}'")
    assert _run(tmp_path, workflow=workflow) == 1
    err = capsys.readouterr().err
    assert "wf.yml:6:" in err
    assert "Rule 5" in err


# ---------------------------------------------------------------------------
# Rule 3
# ---------------------------------------------------------------------------


def test_checkout_with_persist_false_passes(tmp_path):
    step = f"""\
    - uses: actions/checkout@{SHA}  # v4
      with:
        persist-credentials: false
    """
    assert _run(tmp_path, workflow=_wf_step(step)) == 0


def test_checkout_missing_persist_fails(tmp_path, capsys):
    step = f"""\
    - uses: actions/checkout@{SHA}  # v4
      with:
        fetch-depth: 0
    """
    assert _run(tmp_path, workflow=_wf_step(step)) == 1
    err = capsys.readouterr().err
    assert "wf.yml:6:" in err
    assert "persist-credentials" in err


def test_checkout_without_with_fails(tmp_path):
    assert _run(tmp_path, workflow=_wf_step(f"- uses: actions/checkout@{SHA}  # v4\n")) == 1


def test_checkout_persist_true_fails(tmp_path):
    step = f"""\
    - uses: actions/checkout@{SHA}  # v4
      with:
        persist-credentials: true
    """
    assert _run(tmp_path, workflow=_wf_step(step)) == 1


def test_checkout_artipacked_suppression_honoured(tmp_path):
    step = f"""\
    - name: Checkout with credential
      # zizmor: ignore[artipacked]
      uses: actions/checkout@{SHA}  # v4
      with:
        fetch-depth: 0
    """
    assert _run(tmp_path, workflow=_wf_step(step)) == 0


_ACTION = """\
name: my-action
runs:
  using: composite
  steps:
    - uses: actions/checkout@{sha}  # v4
{with_block}"""


def test_composite_action_checkout_passes(tmp_path):
    action = _ACTION.format(sha=SHA, with_block="      with:\n        persist-credentials: false\n")
    assert _run(tmp_path, action=action) == 0


def test_composite_action_checkout_fails(tmp_path, capsys):
    assert _run(tmp_path, action=_ACTION.format(sha=SHA, with_block="")) == 1
    err = capsys.readouterr().err
    assert "action.yml:5:" in err


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def test_invalid_yaml_fails(tmp_path, capsys):
    assert _run(tmp_path, workflow="on: [push\njobs: {\n") == 1
    assert "invalid YAML" in capsys.readouterr().err


def test_empty_dirs_pass(tmp_path):
    assert _run(tmp_path) == 0
