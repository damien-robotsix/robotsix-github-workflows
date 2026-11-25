#!/usr/bin/env python3
"""Check a repo's root ``SECURITY.md`` carries the three required elements.

Implements the fail-closed ``SECURITY.md`` gate of robotsix-standards
``docs/repo-baseline.md`` ("Vulnerability disclosure" and "Baseline
conformance"), run by the reusable ``baseline-check.yml`` against the
CALLER's checkout.  The check fails (``::error::``, exit 1) when:

  1. ``SECURITY.md`` is missing at the repo root, or
  2. the file lacks any of the three required elements, detected with
     simple, case-insensitive heuristics:

     * **reporting contact** — an email address, an ``http(s)://`` URL, or a
       GitHub security-advisory reference (``security/advisories`` link or
       "security advisory" / "private vulnerability reporting" wording);
     * **response-time expectation** — a number followed by a time unit
       (``48 hours``, ``5 business days``, ``2 weeks``), or an explicit
       best-effort statement (``best-effort`` / ``best effort``);
     * **coordinated-disclosure statement** — the phrase "coordinated
       disclosure" or "responsible disclosure" (also matches
       "coordinated vulnerability disclosure").

Unlike the ``.secrets-patterns-excluded`` check there is no warning-first
grace window: the standard mandates fail-closed behaviour.

Usage::

    check_security_md.py [--root DIR]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SECURITY_NAME = "SECURITY.md"
STANDARD_REF = "robotsix-standards docs/repo-baseline.md"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_ADVISORY = re.compile(
    r"security/advisories|security advisor(?:y|ies)"
    r"|private vulnerability reporting",
    re.IGNORECASE,
)
_RESPONSE_TIME = re.compile(
    r"\b\d+\s*(?:-\s*\d+\s*)?"
    r"(?:business\s+|working\s+|calendar\s+)?"
    r"(?:hours?|hrs?|days?|weeks?)\b"
    r"|\bbest[\s-]effort\b",
    re.IGNORECASE,
)
_DISCLOSURE = re.compile(
    r"\b(?:coordinated|responsible)\s+(?:vulnerability\s+)?disclosure\b",
    re.IGNORECASE,
)


def has_contact(text: str) -> bool:
    """True when *text* names a reporting contact (email, URL, advisory)."""
    return any(p.search(text) for p in (_EMAIL, _URL, _ADVISORY))


def has_response_time(text: str) -> bool:
    """True when *text* states a response-time expectation."""
    return _RESPONSE_TIME.search(text) is not None


def has_disclosure(text: str) -> bool:
    """True when *text* carries a coordinated-disclosure statement."""
    return _DISCLOSURE.search(text) is not None


def problems(root: Path) -> list[str]:
    """Return a human-readable message per problem found under *root*."""
    path = root / SECURITY_NAME
    if not path.is_file():
        return [
            f"{SECURITY_NAME} is missing at repo root; every repo must ship "
            "one with a reporting contact, a response-time expectation and "
            f"a coordinated-disclosure statement ({STANDARD_REF})"
        ]
    text = path.read_text(encoding="utf-8")
    found: list[str] = []
    if not has_contact(text):
        found.append(
            f"{SECURITY_NAME} has no vulnerability-reporting contact (expected "
            "an email address, a URL or a GitHub security advisory link) "
            f"({STANDARD_REF})"
        )
    if not has_response_time(text):
        found.append(
            f"{SECURITY_NAME} has no response-time expectation (expected e.g. "
            "'within 5 business days', '48 hours' or an explicit "
            f"'best-effort' statement) ({STANDARD_REF})"
        )
    if not has_disclosure(text):
        found.append(
            f"{SECURITY_NAME} has no coordinated-disclosure statement "
            "(expected 'coordinated disclosure' or 'responsible disclosure') "
            f"({STANDARD_REF})"
        )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repo root to check")
    args = parser.parse_args(argv)

    found = problems(Path(args.root))
    if not found:
        print(f"{SECURITY_NAME} presence and required elements: OK")
        return 0
    for msg in found:
        print(f"::error::{msg}")
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
