#!/usr/bin/env python3
"""Single-source CVE/GHSA audit ignore list (``.audit-ignore``).

One repo-root file feeds every dependency-audit gate (``python-ci.yml``'s
``uv audit`` step and its pip-audit fallback, ``python-security.yml``'s
pip-audit steps, and the pre-commit ``uv audit`` hook), so consumers keep
exactly one list instead of several hand-synced inline copies.

File format — one advisory per line::

    # comments and blank lines are ignored
    GHSA-w8v5-vhqr-4h9v  # diskcache unsafe pickle, no fix available
    CVE-2026-12345       # transitive via foo, upstream PR open  # expires: 2026-12-31

* The first token is the advisory id (GHSA / CVE / PYSEC / ...).
* A ``# reason`` comment is REQUIRED on every entry (same convention as
  ``.trivyignore``): an unexplained ignore is rejected.
* An optional ``# expires: YYYY-MM-DD`` marker turns the entry into a hard
  failure once the date has passed, forcing a re-review.

Flag mapping:

* ``--format uv``        -> ``--ignore-until-fixed <id>`` (auto-clears once a
  fixed version ships);
* ``--format pip-audit`` -> ``--ignore-vuln <id>`` (pip-audit has no
  until-fixed mode, so use ``# expires:`` to bound the ignore);
* ``--format ids``       -> bare ids.

Usage::

    # print the flags
    python3 scripts/audit_ignore.py --format uv
    # append the flags to a command and exec it (stdin is inherited)
    python3 scripts/audit_ignore.py --format uv -- uv audit --frozen --preview
    # validate the file only (pre-commit)
    python3 scripts/audit_ignore.py --check

``--extra`` accepts the deprecated inline ``audit-ignore`` /
``pip-audit-ignore-vulns`` values (space- or comma-separated); they are
merged with the file and a deprecation warning is emitted.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FILE = ".audit-ignore"

# Advisory ids are restricted to a conservative charset so they can never
# smuggle extra CLI flags or shell metacharacters into the audit command.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_EXPIRES_RE = re.compile(r"#\s*expires:\s*(\S+)", re.IGNORECASE)

FLAG_BY_FORMAT = {
    "uv": "--ignore-until-fixed",
    "pip-audit": "--ignore-vuln",
}


@dataclass(frozen=True)
class Entry:
    id: str
    reason: str
    expires: dt.date | None
    line: int


class AuditIgnoreError(ValueError):
    """Raised when the ignore file is malformed or contains expired entries."""


def parse(text: str, path: str = DEFAULT_FILE) -> list[Entry]:
    """Parse ``.audit-ignore`` content; raise on malformed lines."""
    entries: list[Entry] = []
    errors: list[str] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ident, _, comment = line.partition("#")
        ident = ident.strip()
        where = f"{path}:{lineno}"
        if not ident or len(ident.split()) != 1 or not _ID_RE.match(ident):
            errors.append(f"{where}: invalid advisory id {ident!r}")
            continue
        expires: dt.date | None = None
        m = _EXPIRES_RE.search("#" + comment)
        if m:
            try:
                expires = dt.date.fromisoformat(m.group(1))
            except ValueError:
                errors.append(
                    f"{where}: invalid expires date {m.group(1)!r} (want YYYY-MM-DD)"
                )
                continue
        reason = _EXPIRES_RE.sub("", "#" + comment).strip().strip("#").strip()
        if not reason:
            errors.append(f"{where}: {ident} has no '# reason' comment")
            continue
        if ident in seen:
            errors.append(f"{where}: duplicate advisory id {ident}")
            continue
        seen.add(ident)
        entries.append(Entry(ident, reason, expires, lineno))
    if errors:
        raise AuditIgnoreError("\n".join(errors))
    return entries


def expired(entries: list[Entry], today: dt.date) -> list[Entry]:
    """Return entries whose ``expires`` date is strictly before *today*."""
    return [e for e in entries if e.expires is not None and e.expires < today]


def split_extra(extra: str) -> list[str]:
    """Split a deprecated inline id list (space- or comma-separated)."""
    ids = extra.replace(",", " ").split()
    bad = [i for i in ids if not _ID_RE.match(i)]
    if bad:
        raise AuditIgnoreError(f"invalid inline advisory id(s): {' '.join(bad)}")
    return ids


def resolve_path(file: str, root: Path) -> Path:
    """Resolve *file* and refuse anything outside *root*."""
    root = root.resolve()
    path = (root / file).resolve()
    if path != root and root not in path.parents:
        raise AuditIgnoreError(f"{file}: ignore file must live inside {root}")
    return path


def collect_ids(
    file: str,
    extra: str = "",
    *,
    today: dt.date | None = None,
    root: Path | None = None,
) -> list[str]:
    """Return the de-duplicated id list from *file* plus *extra*."""
    path = resolve_path(file, root or Path.cwd())
    entries: list[Entry] = []
    if path.is_file():
        entries = parse(path.read_text(encoding="utf-8"), path=file)
        stale = expired(entries, today or dt.date.today())
        if stale:
            raise AuditIgnoreError(
                "\n".join(
                    f"{file}:{e.line}: {e.id} expired on {e.expires} — "
                    "re-review the advisory and drop or re-date the entry"
                    for e in stale
                )
            )
    ids = [e.id for e in entries]
    for i in split_extra(extra):
        if i not in ids:
            ids.append(i)
    return ids


def build_flags(ids: list[str], fmt: str) -> list[str]:
    """Map *ids* to CLI flags for *fmt* (``uv``, ``pip-audit`` or ``ids``)."""
    if fmt == "ids":
        return list(ids)
    flag = FLAG_BY_FORMAT[fmt]
    out: list[str] = []
    for i in ids:
        out += [flag, i]
    return out


def _gha() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command: list[str] = []
    if "--" in argv:
        idx = argv.index("--")
        argv, command = argv[:idx], argv[idx + 1 :]

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", default=DEFAULT_FILE, help="ignore file path")
    parser.add_argument(
        "--extra",
        default="",
        help="deprecated inline ids (space/comma-separated), merged with the file",
    )
    parser.add_argument(
        "--format", choices=["uv", "pip-audit", "ids"], default="uv", dest="fmt"
    )
    parser.add_argument(
        "--check", action="store_true", help="validate the file only; print nothing"
    )
    args = parser.parse_args(argv)

    try:
        ids = collect_ids(args.file or DEFAULT_FILE, args.extra)
    except AuditIgnoreError as exc:
        for msg in str(exc).splitlines():
            print(f"::error::{msg}" if _gha() else f"error: {msg}", file=sys.stderr)
        return 1

    if args.extra.strip():
        msg = (
            "inline audit-ignore / pip-audit-ignore-vulns inputs are deprecated; "
            f"move the ids into {args.file or DEFAULT_FILE} (one 'ID  # reason' per line)"
        )
        print(f"::warning::{msg}" if _gha() else f"warning: {msg}", file=sys.stderr)

    if args.check:
        return 0

    flags = build_flags(ids, args.fmt)
    if command:
        os.execvp(command[0], command + flags)
    print(" ".join(flags))
    return 0


if __name__ == "__main__":
    sys.exit(main())
