"""The ruff / mypy / types-* pins installed by ``ci.yml``'s Python lint job
must match the ``ruff-pre-commit`` / ``mirrors-mypy`` revs and mypy's
``additional_dependencies`` in ``.pre-commit-config.yaml``.

Dependabot's ``pre-commit`` ecosystem bumps only the pre-commit revs, never the
inline ``pip install`` pins in the workflow, so without this test local hooks
and CI would silently drift onto different linter versions."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_PRECOMMIT = _ROOT / ".pre-commit-config.yaml"
_CI = _ROOT / ".github" / "workflows" / "ci.yml"

_REPO_TOOL = {
    "https://github.com/astral-sh/ruff-pre-commit": "ruff",
    "https://github.com/pre-commit/mirrors-mypy": "mypy",
}
_PIN_RE = re.compile(r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s;]+)")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _precommit_pins() -> dict[str, str]:
    config = yaml.safe_load(_PRECOMMIT.read_text())
    pins: dict[str, str] = {}
    for repo in config.get("repos", []):
        tool = _REPO_TOOL.get(repo.get("repo", ""))
        if tool is None:
            continue
        pins[tool] = str(repo["rev"]).removeprefix("v")
        if tool != "mypy":
            continue
        for hook in repo.get("hooks", []):
            for dep in hook.get("additional_dependencies", []):
                m = _PIN_RE.fullmatch(dep.strip())
                if m and _norm(m.group("name")).startswith("types-"):
                    pins[_norm(m.group("name"))] = m.group("version")
    return pins


def _ci_pins() -> dict[str, str]:
    workflow = yaml.safe_load(_CI.read_text())
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            if step.get("name") == "Install lint dependencies":
                return {
                    _norm(m.group("name")): m.group("version")
                    for m in _PIN_RE.finditer(step.get("run", ""))
                }
    raise AssertionError(
        f"{_CI.relative_to(_ROOT)}: no 'Install lint dependencies' step found"
    )


def test_precommit_declares_lint_tools() -> None:
    pins = _precommit_pins()
    assert {"ruff", "mypy"} <= pins.keys(), (
        f"{_PRECOMMIT.name}: expected ruff-pre-commit and mirrors-mypy repos, "
        f"got {sorted(pins)}"
    )


def test_ci_lint_pins_match_precommit() -> None:
    precommit = _precommit_pins()
    ci = _ci_pins()
    ci_path = _CI.relative_to(_ROOT)
    mismatches = []
    for name, version in sorted(precommit.items()):
        ci_version = ci.get(name)
        if ci_version != version:
            mismatches.append(
                f"  {name}: {_PRECOMMIT.name}={version} vs "
                f"{ci_path}={ci_version or '<missing>'}"
            )
    for name in sorted(ci):
        if (name in ("ruff", "mypy") or name.startswith("types-")) and name not in precommit:
            mismatches.append(
                f"  {name}: {ci_path}={ci[name]} vs {_PRECOMMIT.name}=<missing>"
            )
    assert not mismatches, (
        f"lint tool pins drifted between {_PRECOMMIT.name} and {ci_path} "
        "('Install lint dependencies' step); update both:\n" + "\n".join(mismatches)
    )
