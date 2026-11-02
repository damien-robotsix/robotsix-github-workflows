#!/usr/bin/env python3
"""Check a repo's ``.secrets-patterns-excluded`` file and its wiring.

Fleet-wide counterpart of robotsix-standards'
``scripts/check-secrets-patterns-excluded.py`` (rule
docs/secret-files-are-never-tracked.md), run by the reusable
``baseline-check.yml`` against the CALLER's checkout.  Three checks:

  1. ``.secrets-patterns-excluded`` exists at the repo root.
  2. Every non-blank, non-``#`` line compiles as a Python regex — the file is
     newline-separated regexes, not gitignore globs (``*secret*`` is rejected).
  3. ``.pre-commit-config.yaml``, if present, does not wire detect-secrets with
     the no-op ``--exclude-files .secrets-patterns-excluded`` form
     (``--exclude-files`` takes a single regex, not a file path).

Rollout is warning-first, matching the standards gate: before
``BLOCKING_FROM`` (2027-01-31) problems are ``::warning::`` annotations and
the exit code is 0; from that date they are ``::error::`` and the exit code
is 1.

Usage::

    check_secrets_patterns_excluded.py [--root DIR] [--today YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

PATTERNS_NAME = ".secrets-patterns-excluded"
PRECOMMIT_NAME = ".pre-commit-config.yaml"
BLOCKING_FROM = dt.date(2027, 1, 31)

# Same tolerant matcher as the standards gate: spans the split-argument
# (``- '--exclude-files'`` / ``- '.secrets-patterns-excluded'``) and inline
# spellings via a bounded gap.
_NOOP_WIRING = re.compile(
    r"--exclude-files.{0,40}?\.secrets-patterns-excluded",
    re.DOTALL,
)


def pattern_lines(text: str) -> list[str]:
    """Return the non-blank, non-comment lines of the exclusion file."""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def invalid_patterns(text: str) -> list[str]:
    """Return the pattern lines that do not compile as a Python regex."""
    bad: list[str] = []
    for line in pattern_lines(text):
        try:
            re.compile(line)
        except re.error:
            bad.append(line)
    return bad


def detect_secrets_noop(precommit_text: str) -> bool:
    """True when detect-secrets uses the no-op ``--exclude-files`` wiring."""
    return _NOOP_WIRING.search(precommit_text) is not None


def problems(root: Path) -> list[str]:
    """Return a human-readable message per problem found under *root*."""
    found: list[str] = []
    patterns = root / PATTERNS_NAME
    if not patterns.is_file():
        found.append(
            f"{PATTERNS_NAME} is missing at repo root; every repo must ship "
            "it as the reviewed scanner-exclusion file, one regex per line "
            "(robotsix-standards docs/secret-files-are-never-tracked.md)"
        )
    else:
        for line in invalid_patterns(patterns.read_text(encoding="utf-8")):
            found.append(
                f"{PATTERNS_NAME} line `{line}` is not a valid regular "
                "expression — the file is newline-separated regexes, not "
                "gitignore globs "
                "(robotsix-standards docs/secret-files-are-never-tracked.md)"
            )
    precommit = root / PRECOMMIT_NAME
    if precommit.is_file() and detect_secrets_noop(
        precommit.read_text(encoding="utf-8")
    ):
        found.append(
            f"{PRECOMMIT_NAME} wires detect-secrets with "
            f"`--exclude-files {PATTERNS_NAME}` — a silent no-op "
            "(--exclude-files takes a regex, not a file). Move path "
            "exclusions to the hook's `exclude:` regex "
            "(robotsix-standards docs/secret-files-are-never-tracked.md)"
        )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repo root to check")
    parser.add_argument(
        "--today",
        type=dt.date.fromisoformat,
        default=None,
        help="override today's date (YYYY-MM-DD), for tests",
    )
    args = parser.parse_args(argv)

    today = args.today or dt.date.today()
    blocking = today >= BLOCKING_FROM
    level = "error" if blocking else "warning"

    found = problems(Path(args.root))
    if not found:
        print(f"{PATTERNS_NAME} presence and wiring: OK")
        return 0
    for msg in found:
        print(f"::{level}::{msg}")
    if blocking:
        return 1
    print(
        f"{PATTERNS_NAME}: problems found; warning-first until "
        f"{BLOCKING_FROM.isoformat()}, blocking from then"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
