"""Every README caller example that references a reusable workflow from this
repo must carry a ``# vX.Y.Z`` version label (AGENT.md / WORKFLOW-AUTHORING
Rule 1), so consumers copying it do not drift to ``# main`` or unlabelled pins
that the ``sha-pin`` check in ``scripts/check_workflow_rules.py`` rejects."""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_README = _ROOT / "README.md"

_USES_RE = re.compile(
    r"^\s*-?\s*uses:\s*damien-robotsix/robotsix-github-workflows/\S+@\S+(?P<rest>.*)$"
)
_VERSION_COMMENT_RE = re.compile(r"#\s*v(?:\d+|X)(?:\.(?:\d+|Y))*(?:\.(?:\d+|Z))?\b")


def _uses_lines() -> list[tuple[int, str, str]]:
    out = []
    for lineno, line in enumerate(_README.read_text().splitlines(), start=1):
        m = _USES_RE.match(line)
        if m:
            out.append((lineno, line, m.group("rest")))
    return out


def test_readme_has_caller_examples() -> None:
    assert _uses_lines(), "expected README.md to contain caller examples"


def test_readme_caller_examples_have_version_label() -> None:
    bad = [
        f"README.md:{lineno}: {line.strip()}"
        for lineno, line, rest in _uses_lines()
        if not _VERSION_COMMENT_RE.search(rest)
    ]
    assert not bad, "uses: examples missing a '# vX.Y.Z' label:\n" + "\n".join(bad)
