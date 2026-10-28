#!/usr/bin/env python3
"""Emit lock-pinned ``uv run --with`` overlay arguments for the pytest step.

``uv run --with X`` resolves the overlay packages WITHOUT the project lock as
a constraint, so ``--with pytest-xdist`` can silently pull a newer ``pytest``
(and ``pluggy`` / ``pytest-asyncio`` / ``coverage``) than the one
``uv sync --frozen`` installed (incident 2026-10-28: pytest 9.2.0 overlaid on a
lock pinning 9.1.1).  This script reads the caller's lock, as exported by::

    uv export --frozen --no-hashes --no-emit-project [--extra X ...]

(with the same ``--extra`` flags ``uv sync`` used) on stdin, and prints one argv token per line:

* ``--with <pkg>==<locked>`` for every package in ``LOCK_PINNED`` that the
  lock contains, so the overlay cannot upgrade a locked package;
* ``--with <plugin>==<version>`` for every plugin in ``REQUIRED_PLUGINS``,
  using the locked version when present (the overlay is then a no-op) and the
  fallback pin otherwise.

A plugin missing from the lock is reported WARNING-FIRST: a ``::warning::``
annotation until ``FLIP_DATE``, an ``::error::`` (exit 1) on and after it.
Add ``pytest-xdist`` and ``pytest-cov`` to the dev dependency group to clear
it.

Usage::

    uv export --frozen --no-hashes --no-emit-project \\
        | uv_with_pins.py [--today YYYY-MM-DD]

Exit codes: 0 = ok (possibly with warnings), 1 = plugin missing after the
flip date, 2 = usage error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass, field

# Packages the overlay must never move away from the lock.
LOCK_PINNED: tuple[str, ...] = ("pytest", "pytest-asyncio", "pluggy", "coverage")

# Plugins the test step needs; value = fallback pin when the lock lacks them.
REQUIRED_PLUGINS: dict[str, str] = {
    "pytest-xdist": "3.8.0",
    "pytest-cov": "7.1.0",
}

# Missing REQUIRED_PLUGINS warn before this date and fail on/after it.
FLIP_DATE = dt.date(2027, 1, 15)

_REQ_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([^\s;\\]+)")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_locked(text: str) -> dict[str, str]:
    """Map normalized package name -> pinned version from requirements text."""
    locked: dict[str, str] = {}
    for raw in text.splitlines():
        match = _REQ_RE.match(raw.strip())
        if match is not None:
            locked.setdefault(_normalize(match.group(1)), match.group(2))
    return locked


@dataclass
class Result:
    """Overlay argv tokens plus warnings/errors to annotate."""

    args: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def build(text: str, today: dt.date) -> Result:
    """Compute the ``--with`` overlay for the exported lock *text*."""
    locked = parse_locked(text)
    result = Result()
    for pkg in LOCK_PINNED:
        if pkg in locked:
            result.args += ["--with", f"{pkg}=={locked[pkg]}"]
    for plugin, fallback in REQUIRED_PLUGINS.items():
        if plugin in locked:
            result.args += ["--with", f"{plugin}=={locked[plugin]}"]
            continue
        result.args += ["--with", f"{plugin}=={fallback}"]
        msg = (
            f"{plugin} is not in uv.lock; the test step provisions "
            f"{plugin}=={fallback} via --with. Add {plugin} to the dev "
            f"dependency group — this becomes a hard error on "
            f"{FLIP_DATE.isoformat()}."
        )
        if today >= FLIP_DATE:
            result.errors.append(msg)
        else:
            result.warnings.append(msg)
    return result


def _annotate(level: str, msg: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::{level}::{msg}", file=sys.stderr)
    else:
        print(f"{level}: {msg}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--today",
        type=dt.date.fromisoformat,
        default=None,
        help="Override today's date (YYYY-MM-DD), for tests.",
    )
    args = parser.parse_args(argv)
    today = args.today or dt.date.today()
    result = build(sys.stdin.read(), today)
    for msg in result.warnings:
        _annotate("warning", msg)
    for msg in result.errors:
        _annotate("error", msg)
    if result.errors:
        return 1
    sys.stdout.write("".join(f"{tok}\n" for tok in result.args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
