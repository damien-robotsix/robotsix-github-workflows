"""Every consumer-facing reusable workflow must be documented in both
README.md and docs/workflow-reference.md.

README.md is a short index: each workflow gets one row linking to its
section in docs/workflow-reference.md, which holds the caller template and
the input/secret tables.  The tests below keep that index from drifting."""

from __future__ import annotations

import re
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

_INDEX_LINK_RE = re.compile(
    r"^\| \[`(?P<name>[^`]+\.yml)`\]\(docs/workflow-reference\.md#(?P<anchor>[^)]+)\) \|",
    re.MULTILINE,
)


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


def _anchor(name: str) -> str:
    # GitHub slug of the "## `<name>`" heading: lowercased, punctuation other
    # than '-' / '_' dropped (so "python-ci.yml" -> "python-ciyml").
    return re.sub(r"[^a-z0-9_-]", "", name.lower())


def _readme_index() -> dict[str, str]:
    return {
        m.group("name"): m.group("anchor") for m in _INDEX_LINK_RE.finditer(_README.read_text())
    }


def _reference_section(name: str) -> list[str]:
    lines = _REFERENCE.read_text().splitlines()
    start = lines.index(f"## `{name}`")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return lines[start:end]


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


@pytest.mark.parametrize("name", _reusable_workflows())
def test_readme_index_links_to_reference(name: str) -> None:
    index = _readme_index()
    assert name in index, (
        f"README.md index has no '| [`{name}`](docs/workflow-reference.md#...) |' row"
    )
    assert index[name] == _anchor(name), (
        f"README.md links {name} to '#{index[name]}', expected '#{_anchor(name)}'"
    )


def test_readme_index_matches_reference_sections() -> None:
    sections = set(re.findall(r"^## `([^`]+\.yml)`$", _REFERENCE.read_text(), re.MULTILINE))
    assert set(_readme_index()) == sections


@pytest.mark.parametrize("name", _reusable_workflows())
def test_reference_has_caller_template(name: str) -> None:
    section = _reference_section(name)
    assert "### Caller template" in section, (
        f"docs/workflow-reference.md '{name}' section has no '### Caller template'"
    )
    uses_ref = f"robotsix-github-workflows/.github/workflows/{name}@"
    assert any(uses_ref in line for line in section), (
        f"docs/workflow-reference.md '{name}' caller template has no uses: line"
    )


def test_readme_has_no_per_workflow_sections() -> None:
    headings = re.findall(r"^## .*\.yml.*$", _README.read_text(), re.MULTILINE)
    assert not headings, (
        "per-workflow sections belong in docs/workflow-reference.md, not README.md: "
        + ", ".join(headings)
    )
