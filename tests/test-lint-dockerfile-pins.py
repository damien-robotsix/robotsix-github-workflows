"""Tests for scripts/lint_dockerfile_pins.py."""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "lint_dockerfile_pins", _scripts_dir / "lint_dockerfile_pins.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

check = _module.check
main = _module.main

DIGEST = "sha256:" + "a" * 64


def _df(text: str) -> str:
    return textwrap.dedent(text).lstrip()


class TestCheck:
    def test_pinned_tag_and_digest_ok(self) -> None:
        assert check(f"FROM python:3.14-slim@{DIGEST}\n") == []

    def test_digest_only_ok(self) -> None:
        assert check(f"FROM python@{DIGEST}\n") == []

    def test_tag_only_flagged(self) -> None:
        errors = check("FROM node:22-alpine AS ui\n")
        assert len(errors) == 1
        assert "Dockerfile:1" in errors[0]
        assert "node:22-alpine" in errors[0]

    def test_untagged_flagged(self) -> None:
        assert len(check("FROM ubuntu\n")) == 1

    def test_short_digest_flagged(self) -> None:
        assert len(check("FROM python@sha256:abc\n")) == 1

    def test_scratch_exempt(self) -> None:
        assert check("FROM scratch\n") == []

    def test_earlier_stage_exempt(self) -> None:
        text = _df(
            f"""
            FROM python:3.14@{DIGEST} AS Builder
            RUN true
            FROM builder
            """
        )
        assert check(text) == []

    def test_later_stage_name_not_exempt(self) -> None:
        text = _df(
            f"""
            FROM builder
            FROM python:3.14@{DIGEST} AS builder
            """
        )
        assert len(check(text)) == 1

    def test_platform_flag_skipped(self) -> None:
        assert check(f"FROM --platform=$BUILDPLATFORM golang:1.23@{DIGEST} AS b\n") == []
        assert len(check("FROM --platform=linux/amd64 golang:1.23\n")) == 1

    def test_lowercase_instruction(self) -> None:
        assert len(check("from node:22\n")) == 1

    def test_comments_and_continuations(self) -> None:
        text = _df(
            """
            # FROM node:22 (comment, ignored)
            FROM \\
              node:22-alpine
            """
        )
        errors = check(text)
        assert len(errors) == 1
        assert "Dockerfile:2" in errors[0]

    def test_arg_default_expanded(self) -> None:
        text = _df(
            f"""
            ARG BASE=python:3.14@{DIGEST}
            FROM ${{BASE}}
            """
        )
        assert check(text) == []

    def test_arg_unpinned_default_flagged(self) -> None:
        text = _df(
            """
            ARG BASE="python:3.14"
            FROM $BASE
            """
        )
        errors = check(text)
        assert len(errors) == 1
        assert "python:3.14" in errors[0]

    def test_arg_without_default_flagged(self) -> None:
        text = _df(
            """
            ARG BASE
            FROM ${BASE}
            """
        )
        errors = check(text)
        assert len(errors) == 1
        assert "unresolved" in errors[0]

    def test_multiple_errors_reported(self) -> None:
        text = _df(
            f"""
            FROM node:22 AS ui
            FROM python:3.14@{DIGEST}
            FROM debian:13
            """
        )
        errors = check(text, path="sandbox/Dockerfile")
        assert len(errors) == 2
        assert errors[0].startswith("sandbox/Dockerfile:1:")
        assert errors[1].startswith("sandbox/Dockerfile:3:")


class TestMain:
    def test_ok(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        df = tmp_path / "Dockerfile"
        df.write_text(f"FROM python:3.14@{DIGEST}\n")
        assert main([str(df)]) == 0

    def test_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        df = tmp_path / "Dockerfile"
        df.write_text("FROM node:22-alpine\n")
        assert main([str(df)]) == 1

    def test_missing_file(self, tmp_path: Path) -> None:
        assert main([str(tmp_path / "nope")]) == 1

    def test_no_args(self) -> None:
        assert main([]) == 2
