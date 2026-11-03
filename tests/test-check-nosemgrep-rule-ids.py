"""Tests for scripts/check_nosemgrep_rule_ids.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "check_nosemgrep_rule_ids",
    _scripts_dir / "check_nosemgrep_rule_ids.py",
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

# Built at runtime so the repo's own self-test scan never sees a bare marker.
NS = "nosem" + "grep"


@pytest.mark.parametrize(
    "line",
    [
        f"x = eval(s)  # {NS}",
        f"x = eval(s)  # {NS}  ",
        f"eval(s); // {NS}",
        f"/* {NS} */ eval(s)",
        f"<!-- {NS} -->",
        f"x = 1  # {NS} : ",
    ],
)
def test_bare_suppression_flagged(line: str) -> None:
    assert _module.bare_suppressions(line) == [1]


@pytest.mark.parametrize(
    "line",
    [
        f"x = eval(s)  # {NS}: python.lang.security.audit.eval-detected",
        f"x = eval(s)  # {NS}:rule-a, rule-b",
        f"eval(s); // {NS}: javascript.eval",
        f"Use `{NS}` comments sparingly.",
        "x = 1  # unrelated comment",
    ],
)
def test_named_or_prose_not_flagged(line: str) -> None:
    assert _module.bare_suppressions(line) == []


def test_line_numbers_reported() -> None:
    text = f"a = 1\nb = eval(s)  # {NS}\nc = eval(s)  # {NS}: r\n"
    assert _module.bare_suppressions(text) == [2]


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "good.py"
    good.write_text(f"x = eval(s)  # {NS}: rule.id\n")
    bad = tmp_path / "bad.py"
    bad.write_text(f"x = 1\nx = eval(s)  # {NS}\n")

    assert _module.main(["--root", str(tmp_path), str(good)]) == 0
    assert _module.main(["--root", str(tmp_path), str(good), str(bad)]) == 1
    assert "::error file=bad.py,line=2::" in capsys.readouterr().out


def test_main_walks_root_without_git(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "bad.py").write_text(f"x = 1  # {NS}\n")
    (tmp_path / "blob.bin").write_bytes(b"\xff\xfe\x00")
    assert _module.main(["--root", str(tmp_path)]) == 1
