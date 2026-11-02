"""secret-scan.yml is the language-agnostic TruffleHog workflow; its
TruffleHog steps must stay identical to python-security.yml's (single
source of truth for pins and flags)."""

from __future__ import annotations

from pathlib import Path

import yaml

_WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((_WORKFLOWS / name).read_text())


def _steps(wf: dict, job: str) -> list[dict]:
    return wf["jobs"][job]["steps"]


def _trufflehog_steps(steps: list[dict]) -> list[dict]:
    return [s for s in steps if str(s.get("uses", "")).startswith("trufflesecurity/trufflehog@")]


def _normalise_if(cond: str) -> str:
    # python-security.yml gates on its extra run-trufflehog input.
    return cond.replace("inputs.run-trufflehog && ", "")


def test_on_workflow_call_only() -> None:
    wf = _load("secret-scan.yml")
    on = wf.get("on", wf.get(True))
    assert list(on) == ["workflow_call"]
    assert set(on["workflow_call"]["inputs"]) == {
        "runs-on",
        "trufflehog-pr-diff",
        "trufflehog-extra-args",
    }


def test_least_privilege_permissions() -> None:
    assert _load("secret-scan.yml")["permissions"] == {"contents": "read"}


def test_no_uv_or_python_setup() -> None:
    steps = _steps(_load("secret-scan.yml"), "secret-scan")
    uses = [str(s.get("uses", "")) for s in steps]
    assert not any(u.startswith(("astral-sh/setup-uv@", "actions/setup-python@")) for u in uses)
    assert not any("run" in s for s in steps)


def test_checkout_full_history_without_credentials() -> None:
    steps = _steps(_load("secret-scan.yml"), "secret-scan")
    checkout = steps[0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False


def test_trufflehog_steps_match_python_security() -> None:
    ours = _trufflehog_steps(_steps(_load("secret-scan.yml"), "secret-scan"))
    theirs = _trufflehog_steps(_steps(_load("python-security.yml"), "security"))
    assert len(ours) == 2
    assert len(ours) == len(theirs)
    for a, b in zip(ours, theirs, strict=True):
        assert a["name"] == b["name"]
        assert a["uses"] == b["uses"]
        assert a["with"] == b["with"]
        assert a["if"] == _normalise_if(b["if"])


def test_trufflehog_pin_comment_matches() -> None:
    def pins(name: str) -> set[str]:
        return {
            line.split("uses:", 1)[1].strip()
            for line in (_WORKFLOWS / name).read_text().splitlines()
            if "trufflesecurity/trufflehog@" in line
        }

    assert pins("secret-scan.yml") == pins("python-security.yml")
