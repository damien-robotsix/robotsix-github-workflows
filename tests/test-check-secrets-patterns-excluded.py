"""Tests for scripts/check_secrets_patterns_excluded.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "check_secrets_patterns_excluded",
    _scripts_dir / "check_secrets_patterns_excluded.py",
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

WARN_DAY = "2026-11-01"
BLOCK_DAY = "2027-01-31"


def _run(root: Path, today: str) -> int:
    return _module.main(["--root", str(root), "--today", today])


def test_pattern_lines_skip_blank_and_comments() -> None:
    assert _module.pattern_lines("# c\n\n  ^a$  \n") == ["^a$"]


def test_glob_is_invalid_regex() -> None:
    assert _module.invalid_patterns("^ok/\n*secret*\n") == ["*secret*"]


@pytest.mark.parametrize(
    "text",
    [
        "args: ['--exclude-files', '.secrets-patterns-excluded']",
        "args:\n  - '--exclude-files'\n  - '.secrets-patterns-excluded'\n",
        "args: [--exclude-files .secrets-patterns-excluded]",
    ],
)
def test_noop_wiring_detected(text: str) -> None:
    assert _module.detect_secrets_noop(text)


def test_regex_exclude_not_flagged() -> None:
    assert not _module.detect_secrets_noop("exclude: ^tests/fixtures/\n")


def test_valid_repo_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / ".secrets-patterns-excluded").write_text("# c\n^vendor/\n")
    assert _run(tmp_path, BLOCK_DAY) == 0
    assert "OK" in capsys.readouterr().out


def test_missing_warns_before_blocking_date(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path, WARN_DAY) == 0
    out = capsys.readouterr().out
    assert "::warning::.secrets-patterns-excluded is missing" in out


def test_missing_fails_from_blocking_date(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path, BLOCK_DAY) == 1
    assert "::error::.secrets-patterns-excluded is missing" in capsys.readouterr().out


def test_invalid_regex_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / ".secrets-patterns-excluded").write_text("*secret*\n")
    assert _run(tmp_path, BLOCK_DAY) == 1
    assert "`*secret*` is not a valid regular expression" in capsys.readouterr().out


def test_noop_precommit_wiring_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".secrets-patterns-excluded").write_text("^vendor/\n")
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "args: ['--exclude-files', '.secrets-patterns-excluded']\n"
    )
    assert _run(tmp_path, BLOCK_DAY) == 1
    assert "silent no-op" in capsys.readouterr().out


def test_this_repo_passes_its_own_gate() -> None:
    assert _run(_scripts_dir.parent, BLOCK_DAY) == 0
