"""Tests for scripts/check_security_md.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "check_security_md",
    _scripts_dir / "check_security_md.py",
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

_REPO_ROOT = Path(__file__).resolve().parent.parent

CONFORMING = """# Security Policy

## Reporting a Vulnerability
Email security@example.org.

## Response Time
We aim to acknowledge reports within 5 business days.

## Disclosure
We practice coordinated disclosure.
"""


def _write(root: Path, text: str) -> Path:
    (root / "SECURITY.md").write_text(text, encoding="utf-8")
    return root


def test_conforming_file_passes(tmp_path: Path, capsys) -> None:
    _write(tmp_path, CONFORMING)
    assert _module.main(["--root", str(tmp_path)]) == 0
    assert "OK" in capsys.readouterr().out


def test_this_repo_security_md_passes() -> None:
    # test-self.yml runs baseline-check.yml on this repo.
    assert _module.problems(_REPO_ROOT) == []


def test_missing_file_fails_closed(tmp_path: Path, capsys) -> None:
    assert _module.main(["--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "::error::SECURITY.md is missing at repo root" in out


@pytest.mark.parametrize(
    "text",
    [
        "Email admin@robotsix.net",
        "Use https://example.org/report",
        "Open a private advisory at github.com/o/r/security/advisories/new",
        "Use GitHub private vulnerability reporting.",
    ],
)
def test_contact_detected(text: str) -> None:
    assert _module.has_contact(text)


def test_contact_missing() -> None:
    assert not _module.has_contact("Please tell us somehow.")


@pytest.mark.parametrize(
    "text",
    [
        "within **5 business days**",
        "within 48 hours",
        "in 2 weeks",
        "within 3-5 working days",
        "handled on a best-effort basis",
        "best effort only",
    ],
)
def test_response_time_detected(text: str) -> None:
    assert _module.has_response_time(text)


def test_response_time_missing() -> None:
    assert not _module.has_response_time("We will respond eventually.")


@pytest.mark.parametrize(
    "text",
    [
        "We follow Coordinated Disclosure.",
        "responsible disclosure is expected",
        "coordinated vulnerability disclosure",
    ],
)
def test_disclosure_detected(text: str) -> None:
    assert _module.has_disclosure(text)


def test_disclosure_missing() -> None:
    assert not _module.has_disclosure("Please do not post publicly.")


@pytest.mark.parametrize(
    ("drop", "expected"),
    [
        ("Email security@example.org.", "no vulnerability-reporting contact"),
        (
            "We aim to acknowledge reports within 5 business days.",
            "no response-time expectation",
        ),
        ("We practice coordinated disclosure.", "no coordinated-disclosure"),
    ],
)
def test_each_missing_element_fails(
    tmp_path: Path, capsys, drop: str, expected: str
) -> None:
    _write(tmp_path, CONFORMING.replace(drop, ""))
    assert _module.main(["--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert f"::error::SECURITY.md has {expected}" in out
    assert out.count("::error::") == 1
