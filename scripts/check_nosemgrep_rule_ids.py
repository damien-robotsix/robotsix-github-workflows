#!/usr/bin/env python3
"""Fail when a ``nosemgrep`` suppression comment does not name a rule id.

robotsix-standards ``docs/security-posture.md`` requires every Semgrep
suppression to name the rule it silences (``nosemgrep: RULE_ID`` after a
comment marker).  A bare marker silences *every* rule on that line, so a future, more
serious finding would be hidden too.  The reusable ``semgrep.yml`` runs this
check against the CALLER's checkout.

Only comment-shaped occurrences are flagged: ``nosemgrep`` must follow a
comment marker (``#``, ``//``, ``/*``, ``--``, ``<!--`` or ``;``) on the same
line.  Prose mentions such as backtick-quoted ``nosemgrep`` are ignored.

Usage::

    check_nosemgrep_rule_ids.py [--root DIR] [PATH ...]

Without explicit paths, the files tracked by git under ``--root`` are scanned
(falling back to a recursive walk when ``git ls-files`` is unavailable).
Exit code is 1 when at least one bare suppression is found, else 0.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# A comment marker, then ``nosemgrep`` as a word.
_SUPPRESSION = re.compile(r"(?:#|//|/\*|--|<!--|;)\s*nosemgrep\b(?P<rest>.*)$")
# ``: rule.id`` or ``: rule-a, rule-b`` — at least one rule id after a colon.
_RULE_IDS = re.compile(r"^\s*:\s*[A-Za-z0-9_.\-/]+")

_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__"}


def bare_suppressions(text: str) -> list[int]:
    """Return the 1-indexed line numbers carrying a bare ``nosemgrep``."""
    bad: list[int] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _SUPPRESSION.finditer(line):
            if not _RULE_IDS.match(match.group("rest")):
                bad.append(lineno)
                break
    return bad


def _tracked_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return [
            p
            for p in root.rglob("*")
            if p.is_file() and not _SKIP_DIRS.intersection(p.relative_to(root).parts)
        ]
    return [root / name for name in out.decode().split("\0") if name]


def problems(files: list[Path], root: Path) -> list[str]:
    """Return one ``path:line`` message per bare suppression in *files*."""
    found: list[str] = []
    for path in files:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable — cannot carry a comment
        try:
            shown = path.relative_to(root)
        except ValueError:
            shown = path
        for lineno in bare_suppressions(text):
            found.append(f"{shown}:{lineno}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: .)")
    parser.add_argument("paths", nargs="*", help="files to scan (default: git-tracked files)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    files = [Path(p).resolve() for p in args.paths] if args.paths else _tracked_files(root)
    found = problems(files, root)
    for loc in found:
        file, _, line = loc.rpartition(":")
        print(
            f"::error file={file},line={line}::bare nosemgrep suppression — "
            "name the rule id (e.g. 'nosemgrep: RULE_ID')"
        )
    if found:
        print(f"{len(found)} bare nosemgrep suppression(s) found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
