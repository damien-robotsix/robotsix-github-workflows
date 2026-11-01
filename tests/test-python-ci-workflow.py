"""Structural tests for .github/workflows/python-ci.yml (pre-test / extra-check hooks)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_WORKFLOW = (
    Path(__file__).resolve().parent.parent / ".github" / "workflows" / "python-ci.yml"
)

_HOOKS = {
    "pre-test-command": ("PRE_TEST_COMMAND", "Pre-test setup (pre-test-command)"),
    "extra-check-command": ("EXTRA_CHECK_COMMAND", "Extra check (extra-check-command)"),
}


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text())


def _on(wf: dict) -> dict:
    # PyYAML parses the bare `on` key as boolean True.
    return wf.get("on", wf.get(True))


def _step_names(job: str) -> list[str]:
    return [s.get("name", "") for s in _load()["jobs"][job]["steps"]]


def _step(job: str, name: str) -> dict:
    matches = [s for s in _load()["jobs"][job]["steps"] if s.get("name") == name]
    assert len(matches) == 1, f"{job}: expected one step named {name!r}"
    return matches[0]


@pytest.mark.parametrize("inp", sorted(_HOOKS))
def test_hook_inputs_are_optional_empty_strings(inp: str) -> None:
    spec = _on(_load())["workflow_call"]["inputs"][inp]
    assert spec["type"] == "string"
    assert spec["required"] is False
    assert spec["default"] == ""


@pytest.mark.parametrize(
    ("inp", "job"),
    [
        ("pre-test-command", "tests"),
        ("pre-test-command", "test"),
        ("extra-check-command", "tests"),
        ("extra-check-command", "lint"),
    ],
)
def test_hook_step_is_guarded_and_uses_env(inp: str, job: str) -> None:
    env_var, name = _HOOKS[inp]
    step = _step(job, name)
    assert step["if"] == f"${{{{ inputs.{inp} != '' }}}}"
    assert step["env"][env_var] == f"${{{{ inputs.{inp} }}}}"
    assert step["env"]["UV_PROJECT_ENVIRONMENT"] == "system"
    # Rule 2: no template interpolation inside run:.
    assert "${{" not in step["run"]
    assert step["run"] == f'eval "${env_var}"'


@pytest.mark.parametrize(
    ("inp", "jobs"),
    [
        ("pre-test-command", {"typecheck", "lint", "vulture", "audit-sarif"}),
        ("extra-check-command", {"typecheck", "test", "vulture", "audit-sarif"}),
    ],
)
def test_hook_absent_from_other_jobs(inp: str, jobs: set[str]) -> None:
    _, name = _HOOKS[inp]
    for job in jobs:
        assert name not in _step_names(job)


@pytest.mark.parametrize("job", ["tests", "test"])
def test_pre_test_runs_right_after_setup(job: str) -> None:
    steps = _load()["jobs"][job]["steps"]
    assert steps[0]["uses"].startswith(
        "damien-robotsix/robotsix-github-workflows/.github/actions/python-setup@"
    )
    assert steps[1]["name"] == _HOOKS["pre-test-command"][1]


def test_pre_test_precedes_lint_type_and_pytest_in_tests_job() -> None:
    names = _step_names("tests")
    pre = names.index(_HOOKS["pre-test-command"][1])
    for later in ("Ruff (lint + format check)", "Mypy (static type check)", "Run tests"):
        assert pre < names.index(later)


@pytest.mark.parametrize("job", ["tests", "lint"])
def test_extra_check_runs_after_ruff(job: str) -> None:
    names = _step_names(job)
    ruff = names.index("Ruff (lint + format check)")
    assert names[ruff + 1] == _HOOKS["extra-check-command"][1]
