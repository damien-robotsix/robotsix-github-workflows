#!/usr/bin/env python3
"""Dockerfile base-image digest-pin linter.

Fails when a ``FROM`` instruction references an external image without an
``@sha256:<64-hex>`` digest. A tag alone (``node:22-alpine``) is mutable: the
registry can repoint it at any time, so builds are neither reproducible nor
protected against a compromised upstream tag.

Exempt references:

* ``scratch`` (the empty image);
* a stage name declared by an earlier ``FROM ... AS <name>`` in the same file.

``$VAR`` / ``${VAR}`` references are expanded from ``ARG`` defaults declared
before the first ``FROM``; a reference that cannot be resolved is reported,
since the linter cannot prove it is pinned.

Ported from robotsix-browser's ``scripts/lint_dockerfile_pins.py``.

Usage as a standalone script::

    python3 scripts/lint_dockerfile_pins.py Dockerfile sandbox/Dockerfile

Usage as an importable module::

    from scripts.lint_dockerfile_pins import check
    errors = check("FROM python:3.14\\n", path="Dockerfile")
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
_VAR_RE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
_ARG_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?$")


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Join backslash continuations and drop comments/blank lines.

    Returns ``(first_line_number, joined_line)`` pairs.
    """
    out: list[tuple[int, str]] = []
    buf: list[str] = []
    start = 0
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("#"):
            # Comment lines inside a continuation are ignored by Docker.
            continue
        if not buf:
            if not stripped:
                continue
            start = lineno
        if stripped.endswith("\\"):
            buf.append(stripped[:-1].strip())
            continue
        buf.append(stripped)
        out.append((start, " ".join(part for part in buf if part)))
        buf = []
    if buf:
        out.append((start, " ".join(part for part in buf if part)))
    return out


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _expand(image: str, args: dict[str, str | None]) -> str | None:
    """Expand ``$VAR`` references; return None when one is unresolvable."""
    unresolved = False

    def repl(match: re.Match[str]) -> str:
        nonlocal unresolved
        name = match.group(1) or match.group(2)
        value = args.get(name)
        if value is None:
            unresolved = True
            return match.group(0)
        return value

    expanded = _VAR_RE.sub(repl, image)
    return None if unresolved else expanded


def check(text: str, path: str = "Dockerfile") -> list[str]:
    """Return one error message per unpinned ``FROM`` in *text*."""
    errors: list[str] = []
    stages: set[str] = set()
    global_args: dict[str, str | None] = {}
    seen_from = False

    for lineno, line in _logical_lines(text):
        parts = line.split()
        instr = parts[0].upper()
        if instr == "ARG" and not seen_from:
            for token in parts[1:]:
                m = _ARG_RE.match(token)
                if m:
                    default = m.group(2)
                    global_args[m.group(1)] = (
                        _unquote(default) if default is not None else None
                    )
            continue
        if instr != "FROM":
            continue
        seen_from = True

        operands = [p for p in parts[1:] if not p.startswith("--")]
        if not operands:
            errors.append(f"{path}:{lineno}: FROM without an image reference")
            continue
        image = operands[0]
        if len(operands) >= 3 and operands[1].upper() == "AS":
            alias = operands[2].lower()
        else:
            alias = None

        resolved = _expand(image, global_args)
        if resolved is None:
            errors.append(
                f"{path}:{lineno}: FROM {image} uses an unresolved build ARG; "
                "give it a digest-pinned default before the first FROM"
            )
        elif resolved.lower() == "scratch" or resolved.lower() in stages:
            pass
        elif not _DIGEST_RE.search(resolved):
            errors.append(
                f"{path}:{lineno}: FROM {resolved} is not pinned to a digest "
                "(expected <image>:<tag>@sha256:<64-hex>)"
            )

        if alias:
            stages.add(alias)

    return errors


def main(argv: list[str] | None = None) -> int:
    paths = sys.argv[1:] if argv is None else argv
    if not paths:
        print("usage: lint_dockerfile_pins.py DOCKERFILE [DOCKERFILE ...]", file=sys.stderr)
        return 2
    errors: list[str] = []
    for p in paths:
        try:
            text = Path(p).read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{p}: cannot read Dockerfile ({exc.strerror})")
            continue
        errors.extend(check(text, path=p))
    for err in errors:
        print(f"::error::{err}" if _in_actions() else err)
    if errors:
        print(f"{len(errors)} unpinned FROM reference(s) found.", file=sys.stderr)
        return 1
    print(f"All FROM references digest-pinned in: {' '.join(paths)}")
    return 0


def _in_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


if __name__ == "__main__":
    sys.exit(main())
