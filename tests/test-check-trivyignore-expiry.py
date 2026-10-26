"""Tests for scripts/check_trivyignore_expiry.py."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "check_trivyignore_expiry", _scripts_dir / "check_trivyignore_expiry.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
# Register before exec: @dataclass resolves its module via sys.modules.
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

check = _module.check
main = _module.main

TODAY = dt.date(2026, 10, 25)


class TestCheck:
    def test_future_expiry_ok(self) -> None:
        res = check("CVE-2025-12345  # expires: 2026-12-31\n", TODAY)
        assert res.errors == [] and res.warnings == []

    def test_comments_and_blank_lines_ignored(self) -> None:
        text = "# header comment\n\n   # indented comment\n"
        res = check(text, TODAY)
        assert res.errors == [] and res.warnings == []

    def test_past_expiry_fails(self) -> None:
        res = check("GHSA-aaaa-bbbb-cccc # expires: 2026-01-01\n", TODAY)
        assert len(res.errors) == 1
        assert ".trivyignore:1" in res.errors[0]
        assert "GHSA-aaaa-bbbb-cccc" in res.errors[0]
        assert "2026-01-01" in res.errors[0]

    def test_expiry_today_fails(self) -> None:
        res = check("CVE-2025-1 # expires: 2026-10-25\n", TODAY)
        assert len(res.errors) == 1

    def test_line_number_reported(self) -> None:
        text = "# c\nCVE-1 # expires: 2027-01-01\nCVE-2 # expires: 2020-01-01\n"
        res = check(text, TODAY, path="x/.trivyignore")
        assert len(res.errors) == 1
        assert res.errors[0].startswith("x/.trivyignore:3:")

    def test_expiry_with_trailing_justification(self) -> None:
        res = check("CVE-1  # expires: 2027-01-01 — no fix upstream\n", TODAY)
        assert res.errors == []

    def test_case_and_spacing_tolerant(self) -> None:
        res = check("CVE-1 #Expires:2027-01-01\n", TODAY)
        assert res.errors == [] and res.warnings == []

    @pytest.mark.parametrize("bad", ["2026-13-01", "2026/12/01", "soon", "2026-2-1"])
    def test_invalid_date_fails(self, bad: str) -> None:
        res = check(f"CVE-1 # expires: {bad}\n", TODAY)
        assert len(res.errors) == 1
        assert "invalid expiry date" in res.errors[0]

    def test_missing_expiry_warns_by_default(self) -> None:
        res = check("CVE-1\nCVE-2 # no fix yet\n", TODAY)
        assert res.errors == []
        assert len(res.warnings) == 2
        assert "CVE-2" in res.warnings[1]

    def test_missing_expiry_fail_policy(self) -> None:
        res = check("CVE-1\n", TODAY, missing_expiry="fail")
        assert len(res.errors) == 1
        assert res.warnings == []


class TestMain:
    def _write(self, tmp_path: Path, text: str) -> str:
        p = tmp_path / ".trivyignore"
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_clean_file_exits_zero(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "CVE-1 # expires: 2027-01-01\n")
        assert main([p, "--today", "2026-10-25"]) == 0

    def test_expired_entry_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(tmp_path, "CVE-1 # expires: 2026-01-01\n")
        assert main([p, "--today", "2026-10-25"]) == 1
        assert "CVE-1" in capsys.readouterr().out

    def test_missing_expiry_warn_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(tmp_path, "CVE-1\n")
        assert main([p, "--today", "2026-10-25"]) == 0
        assert "warning" in capsys.readouterr().out

    def test_missing_expiry_fail_exits_one(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "CVE-1\n")
        assert main([p, "--missing-expiry", "fail", "--today", "2026-10-25"]) == 1

    def test_missing_file_exits_one(self, tmp_path: Path) -> None:
        assert main([str(tmp_path / "nope")]) == 1

    def test_actions_annotations(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        p = self._write(tmp_path, "CVE-1 # expires: 2026-01-01\nCVE-2\n")
        assert main([p, "--today", "2026-10-25"]) == 1
        out = capsys.readouterr().out
        assert "::error::" in out
        assert "::warning::" in out

    def test_bad_policy_is_usage_error(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "")
        with pytest.raises(SystemExit) as exc:
            main([p, "--missing-expiry", "ignore"])
        assert exc.value.code == 2
