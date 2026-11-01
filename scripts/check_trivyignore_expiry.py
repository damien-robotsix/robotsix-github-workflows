#!/usr/bin/env python3
"""Fail when a ``.trivyignore`` suppression has reached its expiry date.

Every suppression line should carry an expiry annotation::

    CVE-2025-12345  # expires: 2026-12-31

Blank lines and full-line ``#`` comments are ignored.  An entry whose
``expires`` date is today or earlier is an error, as is a malformed date.
Entries without an ``# expires:`` annotation are governed by
``--missing-expiry``: ``warn`` (the default) reports them without failing,
``fail`` treats them as errors.

Usage::

    check_trivyignore_expiry.py [--missing-expiry warn|fail]
                                [--today YYYY-MM-DD] PATH [PATH ...]

Exit codes: 0 = all entries valid, 1 = expired/invalid entries (or missing
expiries under ``--missing-expiry fail``), 2 = usage error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_EXPIRES_RE = re.compile(r"#\s*expires:\s*(\S+)", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Result:
    """Errors (fail the gate) and warnings (reported only)."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check(
    text: str,
    today: dt.date,
    path: str = ".trivyignore",
    missing_expiry: str = "warn",
) -> Result:
    """Check every suppression line in *text* against *today*."""
    result = Result()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entry = line.split("#", 1)[0].strip()
        where = f"{path}:{lineno}"
        match = _EXPIRES_RE.search(line)
        if match is None:
            msg = f"{where}: {entry} has no '# expires: YYYY-MM-DD' annotation"
            if missing_expiry == "fail":
                result.errors.append(msg)
            else:
                result.warnings.append(msg)
            continue
        value = match.group(1)
        try:
            if not _DATE_RE.match(value):
                raise ValueError(value)
            expires = dt.date.fromisoformat(value)
        except ValueError:
            result.errors.append(
                f"{where}: {entry} has an invalid expiry date {value!r} "
                "(expected YYYY-MM-DD)"
            )
            continue
        if expires <= today:
            result.errors.append(
                f"{where}: {entry} suppression expired on {expires.isoformat()} "
                "— re-assess the finding and remove or re-date the entry"
            )
    return result


def _in_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", metavar="PATH")
    parser.add_argument(
        "--missing-expiry",
        choices=("warn", "fail"),
        default="warn",
        help="policy for entries without an '# expires:' annotation",
    )
    parser.add_argument(
        "--today",
        type=dt.date.fromisoformat,
        default=None,
        help="override today's date (YYYY-MM-DD); defaults to the UTC date",
    )
    args = parser.parse_args(argv)
    today = args.today or dt.datetime.now(dt.timezone.utc).date()

    total = Result()
    for p in args.paths:
        try:
            text = Path(p).read_text(encoding="utf-8")
        except OSError as exc:
            total.errors.append(f"{p}: cannot read file ({exc.strerror})")
            continue
        res = check(text, today, path=p, missing_expiry=args.missing_expiry)
        total.errors.extend(res.errors)
        total.warnings.extend(res.warnings)

    actions = _in_actions()
    for warn in total.warnings:
        print(f"::warning::{warn}" if actions else f"warning: {warn}")
    for err in total.errors:
        print(f"::error::{err}" if actions else f"error: {err}")
    if total.errors:
        print(
            f"{len(total.errors)} expired or invalid suppression(s) found.",
            file=sys.stderr,
        )
        return 1
    print(f"No expired suppressions in: {' '.join(args.paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
