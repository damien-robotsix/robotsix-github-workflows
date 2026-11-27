"""The docker-pr-scan.yml and docker-release.yml reusable workflows share a
byte-identical scaffold of `workflow_call` inputs (plus the `build-secrets`
secret).  Nothing previously enforced that scaffold stays in sync — e.g. a
one-sided change to the trivy-db-repository default silently diverges the two
variants.  These tests parse both input tables and fail on any divergence."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOWS = _ROOT / ".github" / "workflows"
_PR_SCAN = _WORKFLOWS / "docker-pr-scan.yml"
_RELEASE = _WORKFLOWS / "docker-release.yml"

# The 12 inputs both variants share.  pr-scan additionally declares
# `use-gha-cache` and release additionally declares `push-retries`; those
# one-sided inputs are intentional and out of scope for this guard.
_SHARED_INPUTS = [
    "dockerfile",
    "image-name",
    "smoke",
    "smoke_command",
    "strip-pip",
    "runs-on",
    "trivy-db-repository",
    "trivy-java-db-repository",
    "upload-sarif",
    "trivyignores",
    "build-args",
    "github-token-secret-id",
]

# Attributes that form the shared scaffold.  Descriptions are excluded:
# image-name's description is intentionally worded differently in each
# variant ("falls back to…" vs "publishes to…").
_SCOPED_ATTRS = ("required", "type", "default")


def _on(wf: dict) -> dict:
    # PyYAML parses the bare `on` key as boolean True.
    return wf.get("on", wf.get(True))


def _workflow_call(path: Path) -> dict:
    wf = yaml.safe_load(path.read_text())
    return _on(wf)["workflow_call"]


def _input_specs(path: Path) -> dict[str, dict]:
    return {
        name: {attr: spec.get(attr) for attr in _SCOPED_ATTRS}
        for name, spec in _workflow_call(path)["inputs"].items()
    }


@pytest.mark.parametrize("inp", _SHARED_INPUTS)
def test_shared_input_present_in_both_docker_workflows(inp: str) -> None:
    assert inp in _input_specs(_PR_SCAN), f"docker-pr-scan.yml lacks shared input {inp!r}"
    assert inp in _input_specs(_RELEASE), f"docker-release.yml lacks shared input {inp!r}"


def test_shared_inputs_keep_identical_types_defaults() -> None:
    pr_scan = _input_specs(_PR_SCAN)
    release = _input_specs(_RELEASE)
    mismatches = []
    for name in sorted(pr_scan.keys() & release.keys()):
        for attr in _SCOPED_ATTRS:
            pr_spec = pr_scan[name][attr]
            rel_spec = release[name][attr]
            if pr_spec != rel_spec:
                mismatches.append(
                    f"input {name!r} {attr}: docker-pr-scan.yml={pr_spec!r} "
                    f"vs docker-release.yml={rel_spec!r}"
                )
    assert not mismatches, (
        "docker-pr-scan.yml / docker-release.yml shared scaffold drifted:\n" + "\n".join(mismatches)
    )


def test_shared_build_secrets_secret_matches() -> None:
    pr_scan = _workflow_call(_PR_SCAN)["secrets"]
    release = _workflow_call(_RELEASE)["secrets"]
    assert "build-secrets" in pr_scan, "docker-pr-scan.yml lacks build-secrets secret"
    assert "build-secrets" in release, "docker-release.yml lacks build-secrets secret"
    assert pr_scan["build-secrets"].get("required") == release["build-secrets"].get("required"), (
        "build-secrets required differs: "
        f"docker-pr-scan.yml={pr_scan['build-secrets'].get('required')!r} "
        f"vs docker-release.yml={release['build-secrets'].get('required')!r}"
    )
