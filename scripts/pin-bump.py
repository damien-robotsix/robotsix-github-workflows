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
import base64
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
# URL normalisation
# ---------------------------------------------------------------------------


def _normalize_git_url(url: str) -> str:
    """Normalize a git URL to a canonical HTTPS form for comparison.

    Handles both SSH (``git@github.com:org/repo.git``) and HTTPS URLs.
    Strips trailing ``.git`` suffix and trailing slashes.
    """
    url = url.strip()
    # SSH → HTTPS: git@github.com:org/repo.git → https://github.com/org/repo
    ssh_match = re.match(r"git@([^:]+):(.+?)(?:\.git)?$", url)
    if ssh_match:
        return f"https://{ssh_match.group(1)}/{ssh_match.group(2)}"
    # HTTPS: strip .git suffix and trailing slash
    url = url.removesuffix(".git")
    return url.rstrip("/")


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
# Sweep (coherent-set) mode — helpers
# ---------------------------------------------------------------------------


def _collect_fleet_pins(
    owner: str, env: dict[str, str]
) -> tuple[dict[str, list[tuple[str, str, str]]], list[str], list[str]]:
    """Enumerate fleet repos and collect all git-sourced pins.

    Returns ``(dep_map, skipped_repos, all_fleet_repos)`` where *dep_map*
    maps ``git_url → [(repo_name, pkg_name, current_rev)]``,
    *skipped_repos* lists repos that have no git-sourced pins, and
    *all_fleet_repos* is the complete list of fleet repo names.
    """
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

    dep_map: dict[str, list[tuple[str, str, str]]] = {}
    skipped_repos: list[str] = []

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
            skipped_repos.append(repo)
            continue  # no pyproject.toml — skip

        toml_text = base64.b64decode(content).decode()
        try:
            data = tomllib.loads(toml_text)
        except Exception:
            print(f"    Failed to parse pyproject.toml for {repo} — skipping")
            skipped_repos.append(repo)
            continue

        raw = data.get("tool", {}).get("uv", {}).get("sources", {})
        has_git_pin = False
        for pkg, spec in raw.items():
            if isinstance(spec, dict) and "git" in spec:
                rev = spec.get("rev")
                if rev and isinstance(rev, str) and len(rev) == 40:
                    has_git_pin = True
                    dep_map.setdefault(spec["git"], []).append((repo, pkg, rev))
        if not has_git_pin:
            skipped_repos.append(repo)

    return dep_map, skipped_repos, repo_names


def _resolve_latest_shas(
    dep_map: dict[str, list[tuple[str, str, str]]],
) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Resolve the latest HEAD SHA for each unique git URL.

    Returns ``(latest_map, unresolved)`` where *unresolved* lists
    ``(git_url, error_message)`` for each URL that could not be
    resolved.
    """
    print(f"\nResolving latest SHAs for {len(dep_map)} unique git URLs …")
    latest_map: dict[str, str] = {}
    unresolved: list[tuple[str, str]] = []
    for git_url in dep_map:
        try:
            latest_map[git_url] = resolve_default_branch_head(git_url)
            print(f"  {git_url}: {latest_map[git_url][:8]}")
        except Exception as exc:
            print(f"  FAILED {git_url}: {exc}", file=sys.stderr)
            unresolved.append((git_url, str(exc)))
    return latest_map, unresolved


def _compute_repo_bumps(
    dep_map: dict[str, list[tuple[str, str, str]]],
    latest_map: dict[str, str],
) -> dict[str, list[tuple[str, str]]]:
    """Determine which repos need pin bumps.

    Returns ``{repo_name: [(pkg, new_sha)]}`` for repos with stale pins.

    Git URLs that could not be resolved are silently skipped (their pins
    are not bumped).
    """
    repo_bumps: dict[str, list[tuple[str, str]]] = {}
    for git_url, pins in dep_map.items():
        new_sha = latest_map.get(git_url)
        if new_sha is None:
            continue  # resolution failed — skip this dependency
        for repo, pkg, current_rev in pins:
            if current_rev != new_sha:
                repo_bumps.setdefault(repo, []).append((pkg, new_sha))
    return repo_bumps


# ---------------------------------------------------------------------------
# First-party dependency graph & topological ordering
# ---------------------------------------------------------------------------


def _build_first_party_graph(
    dep_map: dict[str, list[tuple[str, str, str]]],
    all_fleet_repos: list[str],
    owner: str,
) -> dict[str, set[str]]:
    """Build first-party dependency graph from collected pins.

    Returns ``{repo_name: set of fleet repo names it pins}``.  Only
    includes edges where the pinned git URL matches a fleet repo.
    """
    # Map normalized git URL → fleet repo name
    fleet_urls: dict[str, str] = {}
    for repo_name in all_fleet_repos:
        canonical = f"https://github.com/{owner}/{repo_name}.git"
        fleet_urls[_normalize_git_url(canonical)] = repo_name

    graph: dict[str, set[str]] = {}
    for git_url, pins in dep_map.items():
        normalized = _normalize_git_url(git_url)
        dep_repo = fleet_urls.get(normalized)
        if dep_repo is None:
            continue
        for repo_name, _pkg_name, _rev in pins:
            if repo_name != dep_repo:  # no self-loops
                graph.setdefault(repo_name, set()).add(dep_repo)

    return graph


def _topological_sort(
    graph: dict[str, set[str]],
    repos: set[str],
) -> tuple[list[str], set[str]]:
    """Topologically sort *repos* by first-party dependencies.

    Returns ``(sorted_repos, cycle_repos)`` where *cycle_repos* is the
    set of repos involved in dependency cycles (and therefore excluded
    from *sorted_repos*).  Leaves (no in-set dependencies) come first.
    """
    # In-degree: number of in-set dependencies each repo has
    in_degree: dict[str, int] = {}
    for repo in repos:
        in_degree[repo] = len(graph.get(repo, set()) & repos)

    # Kahn's algorithm with deterministic ordering
    queue = sorted(r for r in repos if in_degree.get(r, 0) == 0)
    sorted_repos: list[str] = []

    while queue:
        repo = queue.pop(0)
        sorted_repos.append(repo)
        for other in sorted(repos):
            if repo in graph.get(other, set()):
                in_degree[other] -= 1
                if in_degree[other] == 0:
                    queue.append(other)
                    queue.sort()

    cycle_repos = repos - set(sorted_repos)
    return sorted_repos, cycle_repos


def _get_fleet_dep_bumps(
    repo: str,
    fleet_deps: set[str],
    pushed_shas: dict[str, str],
    dep_map: dict[str, list[tuple[str, str, str]]],
    owner: str,
) -> list[tuple[str, str]]:
    """Return additional pin bumps for fleet deps already pushed in this sweep.

    When a first-party dependency was bumped earlier in the sweep, its new
    commit lives on the ``pin-bump/sweep`` PR branch.  Dependents must pin
    that exact commit so their transitive resolution stays coherent.
    """
    bumps: list[tuple[str, str]] = []
    for dep_repo in fleet_deps:
        if dep_repo not in pushed_shas:
            continue
        new_sha = pushed_shas[dep_repo]
        dep_url_norm = _normalize_git_url(f"https://github.com/{owner}/{dep_repo}.git")
        for git_url, pins in dep_map.items():
            if _normalize_git_url(git_url) == dep_url_norm:
                for pin_repo, pkg_name, current_rev in pins:
                    if pin_repo == repo and current_rev != new_sha:
                        bumps.append((pkg_name, new_sha))
                break
    return bumps


def _apply_pin_bump(
    owner: str,
    repo: str,
    bumps: list[tuple[str, str]],
    token: str,
    tmpdir: str,
) -> str | None:
    """Clone a repo, rewrite pin revs, lock, commit, push, and open a PR.

    Returns the commit SHA of the pushed branch, or ``None`` if the
    repo was skipped (e.g. missing ``pyproject.toml``).
    """
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
        return None

    bump_dict = dict(bumps)
    rewrite_revs(pyproject, bump_dict)

    run("uv", "lock", cwd=str(repo_dir))

    # Commit, push, PR
    run("git", "-C", str(repo_dir), "config", "user.name", "github-actions[bot]")
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

    # Capture the pushed commit SHA so dependents can pin to it
    pushed_sha = run(
        "git", "-C", str(repo_dir), "rev-parse", "HEAD", capture_output=True
    ).stdout.strip()

    # Open or reuse PR
    pr_env = {**os.environ, "GH_TOKEN": token}
    existing = ""
    try:
        existing = run(
            "gh",
            "pr",
            "list",
            # Explicit --repo: every git call above targets the clone with
            # `-C`, but gh resolves the repository from the CWD, which is the
            # workflow's own checkout, not this repo's clone.
            "--repo",
            f"{owner}/{repo}",
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
            "--repo",
            f"{owner}/{repo}",
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

    return pushed_sha


def _write_sweep_summary(
    owner: str,
    bumped: list[str],
    failed: list[tuple[str, str]],
    skipped: list[str],
    unresolved_urls: list[tuple[str, str]],
    skipped_cycles: list[tuple[str, str]] | None = None,
) -> None:
    """Write the sweep summary to stdout and ``$GITHUB_STEP_SUMMARY``."""
    lines: list[str] = []
    lines.append("## Pin Bump Sweep Summary")
    lines.append("")

    if bumped:
        lines.append(f"### Bumped ({len(bumped)})")
        for r in bumped:
            lines.append(f"- {owner}/{r}")
        lines.append("")
    else:
        lines.append("### Bumped")
        lines.append("(none)")
        lines.append("")

    if failed:
        lines.append(f"### Failed ({len(failed)})")
        for r, reason in failed:
            lines.append(f"- {owner}/{r}: {reason}")
        lines.append("")
    else:
        lines.append("### Failed")
        lines.append("(none)")
        lines.append("")

    if skipped_cycles:
        lines.append(f"### Skipped — dependency cycles ({len(skipped_cycles)})")
        for r, reason in skipped_cycles:
            lines.append(f"- {owner}/{r}: {reason}")
        lines.append("")
    else:
        lines.append("### Skipped — dependency cycles")
        lines.append("(none)")
        lines.append("")

    if skipped:
        lines.append(f"### Skipped — no git pins ({len(skipped)})")
        for r in skipped:
            lines.append(f"- {owner}/{r}")
        lines.append("")
    else:
        lines.append("### Skipped — no git pins")
        lines.append("(none)")
        lines.append("")

    if unresolved_urls:
        lines.append(f"### Unresolved dependencies ({len(unresolved_urls)})")
        for url, reason in unresolved_urls:
            lines.append(f"- {url}: {reason}")
        lines.append("")
    else:
        lines.append("### Unresolved dependencies")
        lines.append("(none)")
        lines.append("")

    markdown = "\n".join(lines)

    # Print to stdout (also visible in raw logs)
    print("\n=== Sweep summary ===")
    print(markdown)

    # Append to GITHUB_STEP_SUMMARY for the job summary page
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as fh:
            fh.write(markdown + "\n")


# ---------------------------------------------------------------------------
# Sweep (coherent-set) mode — orchestrator
# ---------------------------------------------------------------------------


def sweep(owner: str, token_env: str) -> int:
    """Enumerate fleet repos, resolve pins once, open PRs for affected repos.

    Repos are processed in topological order so that a dependent always
    pins a commit whose own first-party pins already match.  Repos
    involved in dependency cycles are skipped with an explicit message.
    """
    token = os.environ.get(token_env)
    if not token:
        raise RuntimeError(
            f"Environment variable {token_env} is not set. "
            "The sweep needs a token with repo + workflow scope across all fleet repos."
        )

    env = {**os.environ, "GH_TOKEN": token}

    dep_map, skipped_repos, all_fleet_repos = _collect_fleet_pins(owner, env)
    if not dep_map:
        print("No git-sourced pins found across fleet.")
        if skipped_repos:
            print(f"Skipped {len(skipped_repos)} repo(s) with no git pins:")
            for r in skipped_repos:
                print(f"  - {owner}/{r}")
        _write_sweep_summary(owner, [], [], skipped_repos, [], [])
        return 0

    latest_map, unresolved_urls = _resolve_latest_shas(dep_map)

    repo_bumps = _compute_repo_bumps(dep_map, latest_map)
    if not repo_bumps:
        print("All fleet pins are already current.")
        _write_sweep_summary(owner, [], [], skipped_repos, unresolved_urls, [])
        return 0

    # Build first-party dependency graph and topologically sort so that
    # leaves (repos that don't pin other fleet repos) are bumped first.
    first_party_graph = _build_first_party_graph(dep_map, all_fleet_repos, owner)
    repos_needing_bumps = set(repo_bumps.keys())
    sorted_repos, cycle_repos = _topological_sort(
        first_party_graph, repos_needing_bumps
    )

    if cycle_repos:
        print(
            f"\nWarning: {len(cycle_repos)} repo(s) in first-party "
            "dependency cycles — will be skipped:"
        )
        for repo in sorted(cycle_repos):
            cycle_deps = first_party_graph.get(repo, set()) & cycle_repos
            print(f"  {repo} ↔ {', '.join(sorted(cycle_deps))}")

    print(f"\n{len(repo_bumps)} repo(s) need pin bumps.")
    bumped: list[str] = []
    failed: list[tuple[str, str]] = []
    skipped_cycles: list[tuple[str, str]] = []
    # Track the commit SHA pushed to each repo's PR branch so that
    # dependents can pin to it for coherent transitive resolution.
    pushed_shas: dict[str, str] = {}
    failed_or_skipped: set[str] = set(cycle_repos)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Process in topological order — leaves first
        for repo in sorted_repos:
            # If any fleet dep was not successfully processed, skip this
            # repo to avoid conflicting transitive pins.
            deps = first_party_graph.get(repo, set())
            unprocessed_deps = deps & failed_or_skipped
            if unprocessed_deps:
                dep_names = ", ".join(sorted(unprocessed_deps))
                msg = (
                    f"Skipped: depends on {dep_names} which could not be "
                    f"bumped in this sweep"
                )
                skipped_cycles.append((repo, msg))
                failed_or_skipped.add(repo)
                print(f"\n  SKIP {owner}/{repo}: {msg}")
                continue

            # Start with bumps from stale default-branch pins
            bumps_dict = dict(repo_bumps.get(repo, []))

            # Override with fleet dep bumps — when a first-party dep was
            # already pushed in this sweep, pin to its PR branch SHA so
            # transitive resolution stays coherent.  This takes precedence
            # over the default-branch HEAD computed by _compute_repo_bumps.
            fleet_bumps = _get_fleet_dep_bumps(repo, deps, pushed_shas, dep_map, owner)
            for pkg, sha in fleet_bumps:
                bumps_dict[pkg] = sha

            bumps = list(bumps_dict.items())

            if not bumps:
                continue

            try:
                pushed_sha = _apply_pin_bump(owner, repo, bumps, token, tmpdir)
                if pushed_sha is not None:
                    pushed_shas[repo] = pushed_sha
                bumped.append(repo)
            except Exception as exc:
                failed.append((repo, str(exc)))
                failed_or_skipped.add(repo)
                print(f"\n  FAILED {owner}/{repo}: {exc}", file=sys.stderr)

    _write_sweep_summary(
        owner, bumped, failed, skipped_repos, unresolved_urls, skipped_cycles
    )
    return 1 if failed else 0


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
