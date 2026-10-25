"""Tests for scripts/audit_ignore.py."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "audit_ignore", _scripts_dir / "audit_ignore.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

AuditIgnoreError = _module.AuditIgnoreError
build_flags = _module.build_flags
collect_ids = _module.collect_ids
parse = _module.parse
main = _module.main

TODAY = dt.date(2026, 10, 25)


class TestParse:
    def test_ids_reasons_and_expiry(self) -> None:
        entries = parse(
            "# header comment\n"
            "\n"
            "GHSA-w8v5-vhqr-4h9v  # diskcache pickle, no fix\n"
            "CVE-2026-1234 # transitive via foo  # expires: 2026-12-31\n"
        )
        assert [e.id for e in entries] == ["GHSA-w8v5-vhqr-4h9v", "CVE-2026-1234"]
        assert entries[0].reason == "diskcache pickle, no fix"
        assert entries[0].expires is None
        assert entries[1].reason == "transitive via foo"
        assert entries[1].expires == dt.date(2026, 12, 31)

    def test_missing_reason_rejected(self) -> None:
        with pytest.raises(AuditIgnoreError, match="no '# reason'"):
            parse("GHSA-aaaa-bbbb-cccc\n")

    def test_expiry_only_is_not_a_reason(self) -> None:
        with pytest.raises(AuditIgnoreError, match="no '# reason'"):
            parse("GHSA-aaaa-bbbb-cccc  # expires: 2027-01-01\n")

    def test_bad_date_rejected(self) -> None:
        with pytest.raises(AuditIgnoreError, match="invalid expires date"):
            parse("GHSA-aaaa-bbbb-cccc  # why  # expires: 31/12/2026\n")

    @pytest.mark.parametrize("line", ["--evil  # x", "A B  # x", "$(rm)  # x"])
    def test_unsafe_ids_rejected(self, line: str) -> None:
        with pytest.raises(AuditIgnoreError, match="invalid advisory id"):
            parse(line + "\n")

    def test_duplicate_rejected(self) -> None:
        with pytest.raises(AuditIgnoreError, match="duplicate"):
            parse("CVE-2026-1  # a\nCVE-2026-1  # b\n")


class TestCollectIds:
    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert collect_ids(".audit-ignore", root=tmp_path, today=TODAY) == []

    def test_file_merged_with_deprecated_inline(self, tmp_path: Path) -> None:
        (tmp_path / ".audit-ignore").write_text("CVE-2026-1  # a\n")
        ids = collect_ids(
            ".audit-ignore", "CVE-2026-1, GHSA-x-y-z", root=tmp_path, today=TODAY
        )
        assert ids == ["CVE-2026-1", "GHSA-x-y-z"]

    def test_expired_entry_fails(self, tmp_path: Path) -> None:
        (tmp_path / ".audit-ignore").write_text(
            "CVE-2026-1  # a  # expires: 2026-10-24\n"
        )
        with pytest.raises(AuditIgnoreError, match="expired on 2026-10-24"):
            collect_ids(".audit-ignore", root=tmp_path, today=TODAY)

    def test_expiry_today_still_valid(self, tmp_path: Path) -> None:
        (tmp_path / ".audit-ignore").write_text(
            "CVE-2026-1  # a  # expires: 2026-10-25\n"
        )
        assert collect_ids(".audit-ignore", root=tmp_path, today=TODAY) == [
            "CVE-2026-1"
        ]

    def test_path_outside_root_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(AuditIgnoreError, match="must live inside"):
            collect_ids("../../etc/passwd", root=tmp_path, today=TODAY)

    def test_bad_inline_id_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(AuditIgnoreError, match="invalid inline"):
            collect_ids(".audit-ignore", "--format", root=tmp_path, today=TODAY)


class TestBuildFlags:
    def test_uv(self) -> None:
        assert build_flags(["A-1", "B-2"], "uv") == [
            "--ignore-until-fixed",
            "A-1",
            "--ignore-until-fixed",
            "B-2",
        ]

    def test_pip_audit(self) -> None:
        assert build_flags(["A-1"], "pip-audit") == ["--ignore-vuln", "A-1"]

    def test_ids(self) -> None:
        assert build_flags(["A-1"], "ids") == ["A-1"]


class TestMain:
    def test_prints_flags(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".audit-ignore").write_text("CVE-2026-1  # a\n")
        assert main(["--format", "pip-audit"]) == 0
        assert capsys.readouterr().out.strip() == "--ignore-vuln CVE-2026-1"

    def test_deprecation_warning_for_inline(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        assert main(["--extra", "CVE-2026-9"]) == 0
        captured = capsys.readouterr()
        assert "::warning::" in captured.err
        assert captured.out.strip() == "--ignore-until-fixed CVE-2026-9"

    def test_check_fails_on_bad_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".audit-ignore").write_text("CVE-2026-1\n")
        assert main(["--check"]) == 1
        assert "no '# reason'" in capsys.readouterr().err

    def test_exec_appends_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".audit-ignore").write_text("CVE-2026-1  # a\n")
        calls: list[tuple[str, list[str]]] = []
        monkeypatch.setattr(_module.os, "execvp", lambda f, a: calls.append((f, a)))
        main(["--format", "uv", "--", "uv", "audit", "--frozen"])
        assert calls == [
            ("uv", ["uv", "audit", "--frozen", "--ignore-until-fixed", "CVE-2026-1"])
        ]
