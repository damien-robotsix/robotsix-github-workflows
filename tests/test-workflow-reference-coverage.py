"""Every consumer-facing reusable workflow must be documented in both
README.md and docs/workflow-reference.md."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOWS = _ROOT / ".github" / "workflows"
_README = _ROOT / "README.md"
_REFERENCE = _ROOT / "docs" / "workflow-reference.md"

# Internal-only workflows that consumers never call.
_INTERNAL = {
    "test-self.yml",
    "self-dependabot-auto-merge.yml",
    "self-scorecard.yml",
}


def _on(wf: dict) -> object:
    # PyYAML parses the bare `on` key as boolean True.
    return wf.get("on", wf.get(True))


def _has_workflow_call(path: Path) -> bool:
    wf = yaml.safe_load(path.read_text()) or {}
    on = _on(wf)
    if isinstance(on, str):
        return on == "workflow_call"
    if isinstance(on, list):
        return "workflow_call" in on
    if isinstance(on, dict):
        return "workflow_call" in on
    return False


def _reusable_workflows() -> list[str]:
    return sorted(
        p.name
        for p in _WORKFLOWS.glob("*.yml")
        if p.name not in _INTERNAL and _has_workflow_call(p)
    )


def test_reusable_workflows_found() -> None:
    assert _reusable_workflows()


@pytest.mark.parametrize("name", _reusable_workflows())
def test_workflow_in_readme(name: str) -> None:
    assert name in _README.read_text(), f"{name} is not mentioned in README.md"


@pytest.mark.parametrize("name", _reusable_workflows())
def test_workflow_in_reference(name: str) -> None:
    heading = f"## `{name}`"
    assert heading in _REFERENCE.read_text().splitlines(), (
        f"docs/workflow-reference.md has no '{heading}' section"
    )
