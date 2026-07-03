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
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    tomllib = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(
    *args: str, check: bool = True, **kwargs: object
) -> subprocess.CompletedProcess[str]:
    """Thin wrapper around ``subprocess.run`` with text=True."""
    return subprocess.run(args, text=True, check=check, **kwargs)  # type: ignore[call-overload,no-any-return]


def gh(*args: str, env: dict[str, str] | None = None) -> str:
    """Run ``gh`` and return stripped stdout."""
    kwargs: dict[str, object] = {"capture_output": True}
    if env is not None:
        kwargs["env"] = env
    cp = subprocess.run(("gh",) + args, text=True, check=True, **kwargs)  # type: ignore[call-overload]
    return cp.stdout.strip()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def resolve_default_branch_head(git_url: str) -> str:
    """Return the HEAD commit SHA of *git_url*'s default branch.

    Uses ``git ls-remote --symref`` to discover the default branch and
    then resolves its tip SHA in a single call.
    """
    cp = run("git", "ls-remote", "--symref", git_url, "HEAD", capture_output=True)
    # Output looks like:
    #   ref: refs/heads/main	HEAD
    #   abc123def456...	HEAD
    lines = cp.stdout.strip().splitlines()
    # Find the peeled line (the one without "ref:")
    for line in lines:
        if not line.startswith("ref:"):
            sha = line.split()[0]
            if len(sha) == 40:
                return sha
    raise RuntimeError(f"Could not resolve HEAD for {git_url}\nstdout:\n{cp.stdout}")


# ---------------------------------------------------------------------------
# TOML parsing
# ---------------------------------------------------------------------------


def parse_git_sources(pyproject_path: Path) -> dict[str, dict[str, str]]:
    """Return ``{pkg_name: {git: url, rev: sha}}`` for every git-sourced entry.

    Only entries whose value is a dict containing a ``git`` key are
    included.  Entries without a ``rev`` are skipped (they are unpinned).
    """
    if tomllib is None:
        raise RuntimeError("tomllib requires Python >= 3.11")

    with pyproject_path.open("rb") as fh:
        data = tomllib.load(fh)

    sources: dict[str, dict[str, str]] = {}
    raw = data.get("tool", {}).get("uv", {}).get("sources", {})
    for name, spec in raw.items():
        if isinstance(spec, dict) and "git" in spec:
            rev = spec.get("rev")
            if rev and isinstance(rev, str) and len(rev) == 40:
                sources[name] = {"git": spec["git"], "rev": rev}
    return sources


# ---------------------------------------------------------------------------
# Rewriting pyproject.toml
# ---------------------------------------------------------------------------


def rewrite_revs(pyproject_path: Path, bumps: dict[str, str]) -> None:
    """Replace ``rev`` values in *pyproject_path* for the given package names.

    *bumps* maps package name → new SHA.

    Only matches ``rev`` lines inside a ``[tool.uv.sources.<name>]``
    inline-table — the regex is intentionally narrow to avoid accidental
    replacements in unrelated TOML sections.
    """
    text = pyproject_path.read_text()
    for pkg, new_sha in bumps.items():
        # Match: <pkg> = { git = "...", rev = "<40-hex>" ... }
        pattern = re.compile(
            rf'^(\s*{re.escape(pkg)}\s*=\s*\{{.*?\brev\s*=\s*")[0-9a-f]{{40}}(".*\}}.*)$',
            re.MULTILINE,
        )
        m = pattern.search(text)
        if m is None:
            print(
                f"::warning::Could not locate rev for {pkg} in pyproject.toml — skipping rewrite",
                file=sys.stderr,
            )
            continue
        text = pattern.sub(rf"\g<1>{new_sha}\g<2>", text, count=1)
    pyproject_path.write_text(text)


# ---------------------------------------------------------------------------
# Per-repo mode
# ---------------------------------------------------------------------------


def per_repo(pyproject_path: Path, filter_packages: list[str] | None = None) -> int:
    """Resolve latest SHAs, rewrite revs, run ``uv lock``.

    Returns 2 if any pins changed, 0 otherwise.
    """
    sources = parse_git_sources(pyproject_path)
    if not sources:
        print("No git-sourced pins found in [tool.uv.sources].")
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
        latest = resolve_default_branch_head(spec["git"])
        if latest != current_rev:
            print(f"  {pkg}: {current_rev[:8]} → {latest[:8]}")
            bumps[pkg] = latest
        else:
            print(f"  {pkg}: {current_rev[:8]} (current)")

    if not bumps:
        print("All pins are current.")
        return 0

    print(f"\nUpdating {len(bumps)} pin(s) in pyproject.toml …")
    rewrite_revs(pyproject_path, bumps)

    print("Running uv lock …")
    run("uv", "lock")

    # Build a summary for GitHub Actions output
    summary = ", ".join(f"{pkg} → {sha[:8]}" for pkg, sha in bumps.items())
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as fh:
        fh.write(f"bumped={json.dumps(list(bumps.keys()))}\n")
        fh.write(f"summary={shlex.quote(summary)}\n")

    print(f"Done — bumped: {summary}")
    return 2


# ---------------------------------------------------------------------------
# Sweep (coherent-set) mode
# ---------------------------------------------------------------------------


def sweep(owner: str, token_env: str) -> int:
    """Enumerate fleet repos, resolve pins once, open PRs for affected repos."""
    token = os.environ.get(token_env)
    if not token:
        raise RuntimeError(
            f"Environment variable {token_env} is not set. "
            "The sweep needs a token with repo + workflow scope across all fleet repos."
        )

    env = {**os.environ, "GH_TOKEN": token}

    print(f"Enumerating non-archived, non-fork repos owned by {owner} …")
    repo_list_json = run(
        "gh",
        "repo",
        "list",
        owner,
        "--source",
        "--no-archived",
        "--limit",
        "200",
        "--json",
        "name",
        capture_output=True,
        env=env,
    ).stdout
    repo_names = [r["name"] for r in json.loads(repo_list_json)]
    print(f"Found {len(repo_names)} repos.")

    # Phase 1 — collect all git-sourced pins across the fleet
    #           mapping: git_url → [(repo_name, pkg_name, current_rev)]
    dep_map: dict[str, list[tuple[str, str, str]]] = {}

    for repo in repo_names:
        print(f"  Fetching pyproject.toml from {owner}/{repo} …")
        try:
            content = gh(
                "api",
                f"repos/{owner}/{repo}/contents/pyproject.toml",
                "--jq",
                ".content",
                env=env,
            )
        except subprocess.CalledProcessError:
            continue  # no pyproject.toml — skip

        import base64

        toml_text = base64.b64decode(content).decode()
        try:
            data = tomllib.loads(toml_text)
        except Exception:
            print(f"    Failed to parse pyproject.toml for {repo} — skipping")
            continue

        raw = data.get("tool", {}).get("uv", {}).get("sources", {})
        for pkg, spec in raw.items():
            if isinstance(spec, dict) and "git" in spec:
                rev = spec.get("rev")
                if rev and isinstance(rev, str) and len(rev) == 40:
                    dep_map.setdefault(spec["git"], []).append((repo, pkg, rev))

    if not dep_map:
        print("No git-sourced pins found across fleet.")
        return 0

    # Phase 2 — resolve the latest SHA for each unique git URL ONCE
    print(f"\nResolving latest SHAs for {len(dep_map)} unique git URLs …")
    latest_map: dict[str, str] = {}
    for git_url in dep_map:
        latest_map[git_url] = resolve_default_branch_head(git_url)
        print(f"  {git_url}: {latest_map[git_url][:8]}")

    # Phase 3 — determine which repos need bumps
    #            repo → [(pkg, new_sha)]
    repo_bumps: dict[str, list[tuple[str, str]]] = {}
    for git_url, pins in dep_map.items():
        new_sha = latest_map[git_url]
        for repo, pkg, current_rev in pins:
            if current_rev != new_sha:
                repo_bumps.setdefault(repo, []).append((pkg, new_sha))

    if not repo_bumps:
        print("All fleet pins are already current.")
        return 0

    # Phase 4 — clone, update, lock, PR for each affected repo
    print(f"\n{len(repo_bumps)} repo(s) need pin bumps.")
    with tempfile.TemporaryDirectory() as tmpdir:
        for repo, bumps in repo_bumps.items():
            print(f"\n--- Processing {owner}/{repo} ---")
            repo_dir = Path(tmpdir) / repo
            clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
            run("git", "clone", "--depth=1", clone_url, str(repo_dir))

            # Determine default branch (should be main/master)
            default_branch = run(
                "git",
                "-C",
                str(repo_dir),
                "rev-parse",
                "--abbrev-ref",
                "HEAD",
                capture_output=True,
            ).stdout.strip()

            pyproject = repo_dir / "pyproject.toml"
            if not pyproject.exists():
                print(f"  pyproject.toml not found in cloned {repo} — skipping")
                continue

            bump_dict = dict(bumps)
            rewrite_revs(pyproject, bump_dict)

            run("uv", "lock", cwd=str(repo_dir))

            # Commit, push, PR
            run(
                "git", "-C", str(repo_dir), "config", "user.name", "github-actions[bot]"
            )
            run(
                "git",
                "-C",
                str(repo_dir),
                "config",
                "user.email",
                "github-actions[bot]@users.noreply.github.com",
            )
            bump_branch = "pin-bump/sweep"
            run("git", "-C", str(repo_dir), "checkout", "-B", bump_branch)
            run("git", "-C", str(repo_dir), "add", "pyproject.toml", "uv.lock")
            run(
                "git",
                "-C",
                str(repo_dir),
                "commit",
                "-m",
                "chore: bump first-party git pin revs",
            )
            run("git", "-C", str(repo_dir), "push", "--force", "origin", bump_branch)

            # Open or reuse PR
            pr_env = {**os.environ, "GH_TOKEN": token}
            existing = ""
            try:
                existing = run(
                    "gh",
                    "pr",
                    "list",
                    "--head",
                    bump_branch,
                    "--base",
                    default_branch,
                    "--json",
                    "number",
                    "-q",
                    ".[0].number",
                    capture_output=True,
                    env=pr_env,
                ).stdout.strip()
            except subprocess.CalledProcessError:
                pass

            if existing:
                print(f"  PR #{existing} already open — updated by force-push.")
            else:
                run(
                    "gh",
                    "pr",
                    "create",
                    "--title",
                    "chore: bump first-party git pin revs",
                    "--body",
                    (
                        "Automated coherent-set pin bump sweep.\n\n"
                        "Updated pins:\n"
                        + "\n".join(f"- `{pkg}` → `{sha[:8]}`" for pkg, sha in bumps)
                    ),
                    "--base",
                    default_branch,
                    "--head",
                    bump_branch,
                    env=pr_env,
                )
                print(f"  PR created for {owner}/{repo}")

    return 0


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

    args = parser.parse_args()

    if args.mode == "per-repo":
        pyproject = Path(args.pyproject)
        if not pyproject.exists():
            print(f"pyproject.toml not found at {pyproject}", file=sys.stderr)
            sys.exit(1)
        sys.exit(per_repo(pyproject, args.packages))

    elif args.mode == "sweep":
        sys.exit(sweep(args.owner, args.token_env))


if __name__ == "__main__":
    main()
