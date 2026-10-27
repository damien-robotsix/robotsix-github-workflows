"""Structural tests for .github/workflows/lint-dockerfile.yml (upload-sarif)."""

from __future__ import annotations

from pathlib import Path

import yaml

_WORKFLOW = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "lint-dockerfile.yml"
)
UPLOAD_SARIF_SHA = "9b3254085494b55a0f7c4c2b3d2d52cc712ce370"


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text())


def _on(wf: dict) -> dict:
    # PyYAML parses the bare `on` key as boolean True.
    return wf.get("on", wf.get(True))


def test_upload_sarif_input_defaults_to_false() -> None:
    inp = _on(_load())["workflow_call"]["inputs"]["upload-sarif"]
    assert inp["type"] == "boolean"
    assert inp["default"] is False


def test_no_workflow_level_permissions() -> None:
    # A workflow-level block would stop hadolint-sarif from inheriting the
    # caller's security-events:write grant.
    assert "permissions" not in _load()


def test_hadolint_job_keeps_least_privilege() -> None:
    job = _load()["jobs"]["hadolint"]
    assert job["permissions"] == {"contents": "read"}
    assert "if" not in job


def test_sarif_job_is_opt_in_and_inherits_caller_token() -> None:
    job = _load()["jobs"]["hadolint-sarif"]
    assert job["if"] == "${{ inputs.upload-sarif }}"
    assert "permissions" not in job


def test_sarif_job_runs_hadolint_with_sarif_output() -> None:
    steps = _load()["jobs"]["hadolint-sarif"]["steps"]
    runs = [
        s for s in steps if s.get("uses", "").startswith("hadolint/hadolint-action@")
    ]
    assert len(runs) == 1
    w = runs[0]["with"]
    assert w["format"] == "sarif"
    assert w["output-file"] == "hadolint.sarif"
    assert w["failure-threshold"] == "${{ inputs.failure-threshold }}"


def test_sarif_job_uploads_one_sarif_with_hadolint_category() -> None:
    steps = _load()["jobs"]["hadolint-sarif"]["steps"]
    uploads = [
        s
        for s in steps
        if s.get("uses", "").startswith("github/codeql-action/upload-sarif@")
    ]
    assert len(uploads) == 1
    up = uploads[0]
    assert up["uses"] == f"github/codeql-action/upload-sarif@{UPLOAD_SARIF_SHA}"
    assert up["with"] == {"sarif_file": "hadolint.sarif", "category": "hadolint"}
    assert "success() || failure()" in up["if"]
