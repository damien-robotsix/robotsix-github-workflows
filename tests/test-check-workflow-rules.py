"""Tests for scripts/check_workflow_rules.py."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

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
parse_rules = _module.parse_rules

SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
OWN = "damien-robotsix/robotsix-github-workflows"


@pytest.fixture(autouse=True)
def _no_github_repository(monkeypatch):
    # Exercise the fallback slug in check_local_action_refs.
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)


def _run(
    tmp_path: Path,
    *,
    workflow: str | None = None,
    action: str | None = None,
    rules=None,
) -> int:
    wf_dir = tmp_path / "workflows"
    act_dir = tmp_path / "actions"
    wf_dir.mkdir()
    act_dir.mkdir()
    if workflow is not None:
        (wf_dir / "wf.yml").write_text(textwrap.dedent(workflow))
    if action is not None:
        (act_dir / "my-action").mkdir()
        (act_dir / "my-action" / "action.yml").write_text(textwrap.dedent(action))
    return check(workflow_dir=str(wf_dir), actions_dir=str(act_dir), rules=rules)


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


# ---------------------------------------------------------------------------
# Rule selection
# ---------------------------------------------------------------------------


def test_parse_rules_default():
    assert parse_rules("") == {"sha-pin", "persist-credentials", "static-defaults"}
    assert parse_rules(None) == set(_module.DEFAULT_RULES)


def test_parse_rules_all_and_list():
    assert parse_rules("all") == set(_module.ALL_RULES)
    assert parse_rules(" harden-runner-first, uv-sync-frozen ") == {
        "harden-runner-first",
        "uv-sync-frozen",
    }


def test_parse_rules_unknown_raises():
    with pytest.raises(ValueError, match="bogus"):
        parse_rules("sha-pin,bogus")


def test_disabled_rule_is_not_enforced(tmp_path):
    workflow = _wf_step("- uses: foo/bar@v4\n")
    assert _run(tmp_path, workflow=workflow, rules={"persist-credentials"}) == 0


def test_cli_rules_flag(tmp_path):
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "wf.yml").write_text(_wf_step(f"- uses: foo/bar@{SHA}  # v1\n"))
    base = [
        sys.executable,
        str(_scripts_dir / "check_workflow_rules.py"),
        "--workflow-dir",
        str(wf_dir),
        "--actions-dir",
        str(tmp_path / "none"),
    ]
    env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_REPOSITORY", "WORKFLOW_RULES")}
    ok = subprocess.run(base, check=False, env=env, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    bad = subprocess.run(
        [*base, "--rules", "harden-runner-first"], check=False, env=env, capture_output=True, text=True
    )
    assert bad.returncode == 1
    assert "harden-runner" in bad.stderr
    unknown = subprocess.run(
        [*base, "--rules", "nope"], check=False, env=env, capture_output=True, text=True
    )
    assert unknown.returncode == 2


# ---------------------------------------------------------------------------
# harden-runner-first
# ---------------------------------------------------------------------------

_HARDEN = f"- uses: step-security/harden-runner@{SHA}  # v2.13.0\n  with:\n    egress-policy: audit\n"
_HR = {"harden-runner-first"}


def test_harden_runner_first_passes(tmp_path):
    workflow = _wf_step(_HARDEN + "- run: echo hi\n")
    assert _run(tmp_path, workflow=workflow, rules=_HR) == 0


def test_harden_runner_not_first_fails(tmp_path, capsys):
    workflow = _wf_step("- run: echo hi\n" + _HARDEN)
    assert _run(tmp_path, workflow=workflow, rules=_HR) == 1
    err = capsys.readouterr().err
    assert "wf.yml:3:" in err
    assert "job 'build'" in err


def test_harden_runner_skips_reusable_workflow_jobs(tmp_path):
    workflow = (
        "on: push\n"
        "jobs:\n"
        "  call:\n"
        f"    uses: {OWN}/.github/workflows/lint-workflows.yml@{SHA}  # v1.0.0\n"
    )
    assert _run(tmp_path, workflow=workflow, rules=_HR) == 0


def test_harden_runner_via_local_composite(tmp_path):
    action = "runs:\n  using: composite\n  steps:\n" + textwrap.indent(_HARDEN, "    ")
    workflow = _wf_step("- uses: ./.github/actions/my-action\n- run: echo hi\n")
    assert _run(tmp_path, workflow=workflow, action=action, rules=_HR) == 0


def test_harden_runner_not_checked_in_composite_actions(tmp_path):
    action = "runs:\n  using: composite\n  steps:\n    - run: echo hi\n      shell: bash\n"
    assert _run(tmp_path, action=action, rules=_HR) == 0


# ---------------------------------------------------------------------------
# setup-uv
# ---------------------------------------------------------------------------

_SETUP_UV = f"- uses: astral-sh/setup-uv@{SHA}  # v6.0.0\n"
_UV = {"setup-uv"}


def test_uv_job_with_setup_uv_passes(tmp_path):
    workflow = _wf_step(_SETUP_UV + "- run: uv sync --frozen\n")
    assert _run(tmp_path, workflow=workflow, rules=_UV) == 0


def test_uv_job_without_setup_uv_fails(tmp_path, capsys):
    workflow = _wf_step("- run: |\n    set -e\n    uv run pytest\n")
    assert _run(tmp_path, workflow=workflow, rules=_UV) == 1
    assert "astral-sh/setup-uv" in capsys.readouterr().err


def test_uv_mentioned_in_text_is_not_a_uv_job(tmp_path):
    workflow = _wf_step('- run: echo "install uv first" # uv sync\n')
    assert _run(tmp_path, workflow=workflow, rules=_UV) == 0


def test_setup_uv_found_in_local_composite(tmp_path):
    action = "runs:\n  using: composite\n  steps:\n" + textwrap.indent(_SETUP_UV, "    ")
    workflow = _wf_step("- uses: ./.github/actions/my-action\n- run: uv run pytest\n")
    assert _run(tmp_path, workflow=workflow, action=action, rules=_UV) == 0


def test_setup_uv_found_in_own_repo_composite(tmp_path):
    action = "runs:\n  using: composite\n  steps:\n" + textwrap.indent(_SETUP_UV, "    ")
    workflow = _wf_step(
        f"- uses: {OWN}/.github/actions/my-action@{SHA}\n- run: uv run pytest\n"
    )
    assert _run(tmp_path, workflow=workflow, action=action, rules=_UV) == 0


def test_uv_inside_local_composite_requires_setup_uv(tmp_path):
    action = "runs:\n  using: composite\n  steps:\n    - run: uv sync --frozen\n      shell: bash\n"
    workflow = _wf_step("- uses: ./.github/actions/my-action\n")
    assert _run(tmp_path, workflow=workflow, action=action, rules=_UV) == 1


# ---------------------------------------------------------------------------
# uv-sync-frozen
# ---------------------------------------------------------------------------

_FROZEN = {"uv-sync-frozen"}


@pytest.mark.parametrize(
    "run",
    [
        "uv sync --frozen",
        "uv sync --frozen --all-extras",
        "cd sub && uv sync --group dev --frozen",
        "|\n    uv sync \\\n      --all-groups \\\n      --frozen",
        "uv run --frozen pytest",
    ],
)
def test_uv_sync_frozen_passes(tmp_path, run):
    assert _run(tmp_path, workflow=_wf_step(f"- run: {run}\n"), rules=_FROZEN) == 0


@pytest.mark.parametrize(
    "run",
    [
        "uv sync",
        "uv sync --locked",
        "cd sub && uv sync --all-extras",
        "|\n    uv sync --frozen\n    uv sync --group docs",
    ],
)
def test_uv_sync_without_frozen_fails(tmp_path, capsys, run):
    assert _run(tmp_path, workflow=_wf_step(f"- run: {run}\n"), rules=_FROZEN) == 1
    assert "--frozen" in capsys.readouterr().err


def test_uv_sync_frozen_checked_in_composite_actions(tmp_path):
    action = "runs:\n  using: composite\n  steps:\n    - run: uv sync\n      shell: bash\n"
    assert _run(tmp_path, action=action, rules=_FROZEN) == 1


# ---------------------------------------------------------------------------
# github-auth's check_ci_conventions rules are expressible via the toggles
# ---------------------------------------------------------------------------

_AUTH_RULES = "harden-runner-first,persist-credentials,setup-uv,uv-sync-frozen"


def test_github_auth_conventions_compliant_workflow(tmp_path):
    step = (
        _HARDEN
        + f"- uses: actions/checkout@{SHA}  # v4\n  with:\n    persist-credentials: false\n"
        + _SETUP_UV
        + "- run: uv sync --frozen\n"
    )
    assert _run(tmp_path, workflow=_wf_step(step), rules=parse_rules(_AUTH_RULES)) == 0


def test_github_auth_conventions_violations(tmp_path, capsys):
    step = f"- uses: actions/checkout@{SHA}  # v4\n- run: uv sync\n"
    assert _run(tmp_path, workflow=_wf_step(step), rules=parse_rules(_AUTH_RULES)) == 1
    err = capsys.readouterr().err
    assert "harden-runner" in err
    assert "persist-credentials" in err
    assert "astral-sh/setup-uv" in err
    assert "--frozen" in err


# ---------------------------------------------------------------------------
# lint-workflows.yml wiring
# ---------------------------------------------------------------------------


def _lint_workflows() -> dict:
    path = _scripts_dir.parent / ".github" / "workflows" / "lint-workflows.yml"
    return yaml.safe_load(path.read_text())


def test_lint_workflows_exposes_opt_in_inputs():
    doc = _lint_workflows()
    inputs = (doc.get("on") or doc[True])["workflow_call"]["inputs"]
    assert inputs["run-workflow-rules"]["type"] == "boolean"
    assert inputs["run-workflow-rules"]["default"] is False
    assert inputs["workflow-rules"]["type"] == "string"
    # The default rule list must be valid and match the script's default.
    assert parse_rules(inputs["workflow-rules"]["default"]) == set(_module.DEFAULT_RULES)


def test_lint_workflows_job_runs_checker_with_rules():
    job = _lint_workflows()["jobs"]["workflow-rules"]
    assert job["if"] == "${{ inputs.run-workflow-rules }}"
    run_steps = [s for s in job["steps"] if "run" in s]
    assert len(run_steps) == 1
    step = run_steps[0]
    assert step["env"]["WORKFLOW_RULES"] == "${{ inputs.workflow-rules }}"
    assert "_workflow-lib/scripts/check_workflow_rules.py" in step["run"]
    assert '--rules "$WORKFLOW_RULES"' in step["run"]
    assert "${{" not in step["run"]
