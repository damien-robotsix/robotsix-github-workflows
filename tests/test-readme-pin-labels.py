"""Every README / workflow-reference caller example that references a reusable
workflow from this repo must carry a ``# vX.Y.Z`` version label (AGENT.md /
WORKFLOW-AUTHORING Rule 1), so consumers copying it do not drift to ``# main``
or unlabelled pins that the ``sha-pin`` check in
``scripts/check_workflow_rules.py`` rejects."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_README = _ROOT / "README.md"
_REFERENCE = _ROOT / "docs" / "workflow-reference.md"
_DOCS = [_README, _REFERENCE]

_USES_RE = re.compile(
    r"^\s*-?\s*uses:\s*damien-robotsix/robotsix-github-workflows/\S+@\S+(?P<rest>.*)$"
)
_VERSION_COMMENT_RE = re.compile(r"#\s*v(?:\d+|X)(?:\.(?:\d+|Y))*(?:\.(?:\d+|Z))?\b")


def _uses_lines(path: Path = _README) -> list[tuple[int, str, str]]:
    out = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        m = _USES_RE.match(line)
        if m:
            out.append((lineno, line, m.group("rest")))
    return out


@pytest.mark.parametrize("path", _DOCS, ids=lambda p: p.name)
def test_readme_has_caller_examples(path: Path) -> None:
    assert _uses_lines(path), f"expected {path.name} to contain caller examples"


@pytest.mark.parametrize("path", _DOCS, ids=lambda p: p.name)
def test_readme_caller_examples_have_version_label(path: Path) -> None:
    rel = path.relative_to(_ROOT)
    bad = [
        f"{rel}:{lineno}: {line.strip()}"
        for lineno, line, rest in _uses_lines(path)
        if not _VERSION_COMMENT_RE.search(rest)
    ]
    assert not bad, "uses: examples missing a '# vX.Y.Z' label:\n" + "\n".join(bad)
