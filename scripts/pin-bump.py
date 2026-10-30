#!/usr/bin/env python3
"""Resolve latest commits for ``[tool.uv.sources]`` git pins and update them.

Two modes
---------
*per-repo* (default)
    Operates on the *current* directory's ``pyproject.toml``.  For every
    ``[tool.uv.sources]`` entry whose value is a dict containing a ``git``
    key, resolves the HEAD commit of that repository's default branch and
    rewrites the ``rev`` if it changed, then runs ``uv lock``.

*sweep*
    When ``--sweep`` is passed, enumerates every non-archived, non-fork
    repository owned by ``--owner``, collects all git-sourced pins, resolves
    each unique dependency URL **once** (coherent-set), and then clones +
    updates + opens a PR for every affected repository.

Layout
------
This file is the CLI entry point and holds the per-repo mode.  Shared
subprocess / ``gh`` / push-retry / TOML helpers live in
``pin_bump_common.py`` and the fleet sweep mode in ``pin_bump_sweep.py``
(sibling importable modules in ``scripts/``).

Exit codes
----------
0   No pins changed (or sweep completed with no changes).
1   Runtime error (bad token, missing CLI, etc.).
2   Pins were updated (per-repo mode only — signals the caller to
    commit / push / open a PR).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

# Make the sibling modules importable when this file is loaded by path
# (e.g. ``importlib.util.spec_from_file_location`` in the tests).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pin_bump_common as common  # noqa: E402
from pin_bump_sweep import sweep  # noqa: E402

# ---------------------------------------------------------------------------
# Per-repo mode
# ---------------------------------------------------------------------------


def per_repo(pyproject_path: Path, filter_packages: list[str] | None = None) -> int:
    """Resolve latest SHAs, rewrite revs, run ``uv lock``.

    Returns 2 if any pins changed, 0 otherwise.
    """
    sources = common.parse_git_sources(pyproject_path)
    if not sources:
        print(
            "No git-sourced pins found in [tool.uv.sources] or direct-URL dependencies."
        )
        return 0

    # Apply package filter if given
    if filter_packages:
        sources = {k: v for k, v in sources.items() if k in filter_packages}
        if not sources:
            print(f"No matching git-sourced pins for filter: {filter_packages}")
            return 0

    bumps: dict[str, str] = {}
    for pkg, spec in sources.items():
        current_rev = spec["rev"]
        print(f"Resolving {pkg} ({spec['git']}) …")
        latest = common.resolve_default_branch_head(spec["git"])
        if latest != current_rev:
            print(f"  {pkg}: {current_rev[:8]} → {latest[:8]}")
            bumps[pkg] = latest
        else:
            print(f"  {pkg}: {current_rev[:8]} (current)")

    if not bumps:
        print("All pins are current.")
        return 0

    print(f"\nUpdating {len(bumps)} pin(s) in pyproject.toml …")
    common.rewrite_revs(pyproject_path, bumps)

    print("Running uv lock …")
    common.run("uv", "lock")

    # Build a summary for GitHub Actions output
    summary = ", ".join(f"{pkg} → {sha[:8]}" for pkg, sha in bumps.items())
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as fh:
        fh.write(f"bumped={json.dumps(list(bumps.keys()))}\n")
        fh.write(f"summary={shlex.quote(summary)}\n")

    print(f"Done — bumped: {summary}")
    return 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump first-party git pin revs.")
    sub = parser.add_subparsers(dest="mode", required=True)

    # per-repo
    p = sub.add_parser("per-repo", help="Operate on the local pyproject.toml")
    p.add_argument(
        "--pyproject", default="pyproject.toml", help="Path to pyproject.toml"
    )
    p.add_argument(
        "--packages", nargs="*", default=None, help="Limit to specific package names"
    )

    # sweep
    s = sub.add_parser("sweep", help="Coherent-set fleet-wide sweep")
    s.add_argument("--owner", default="damien-robotsix", help="GitHub org/owner name")
    s.add_argument(
        "--token-env", default="SWEEP_TOKEN", help="Env var holding the GitHub token"
    )
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned bumps without cloning, pushing or opening PRs",
    )

    args = parser.parse_args()

    if args.mode == "per-repo":
        pyproject = Path(args.pyproject)
        if not pyproject.exists():
            print(f"pyproject.toml not found at {pyproject}", file=sys.stderr)
            sys.exit(1)
        sys.exit(per_repo(pyproject, args.packages))

    elif args.mode == "sweep":
        sys.exit(sweep(args.owner, args.token_env, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
