"""Fleet sweep (coherent-set) mode of ``scripts/pin-bump.py``.

Enumerates every non-archived, non-fork repository owned by an owner,
collects all git-sourced pins, resolves each unique dependency URL **once**,
and then clones + updates + opens a PR for every affected repository in
first-party topological order.

The orchestration runs in named phases: collect → resolve → plan → order →
apply → summarise.  ``pin-bump.py sweep`` is the CLI entry point.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pin_bump_common as common

if sys.version_info >= (3, 11):
    import tomllib
else:
    tomllib = None  # type: ignore[assignment]

# ``git_url → [(repo_name, pkg_name, current_rev)]``
DepMap = dict[str, list[tuple[str, str, str]]]

# Branch the sweep force-pushes its pin bumps to in every target repo.
SWEEP_BRANCH = "pin-bump/sweep"
SWEEP_COMMIT_MESSAGE = "chore: bump first-party git pin revs"

# "<owner>/<repo>" → number of push retries needed by _apply_pin_bump.
_push_retry_counts: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Phase 1 — collect
# ---------------------------------------------------------------------------


def _list_fleet_repos(owner: str, env: dict[str, str]) -> list[str]:
    """Return the names of every non-archived, non-fork repo owned by *owner*."""
    print(f"Enumerating non-archived, non-fork repos owned by {owner} …")
    repo_list_json = common.run(
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
    return repo_names


def _fetch_repo_pins(
    owner: str, repo: str, env: dict[str, str]
) -> list[tuple[str, str, str]] | None:
    """Return the git pins of *repo*'s ``pyproject.toml``.

    Returns ``None`` when the file is missing or cannot be parsed.
    """
    if tomllib is None:
        raise RuntimeError("tomllib requires Python >= 3.11")
    print(f"  Fetching pyproject.toml from {owner}/{repo} …")
    try:
        content = common.gh(
            "api",
            f"repos/{owner}/{repo}/contents/pyproject.toml",
            "--jq",
            ".content",
            env=env,
        )
    except subprocess.CalledProcessError:
        return None  # no pyproject.toml — skip

    toml_text = base64.b64decode(content).decode()
    try:
        data = tomllib.loads(toml_text)
    except Exception:
        print(f"    Failed to parse pyproject.toml for {repo} — skipping")
        return None
    return common._extract_git_pins(data)


def _collect_fleet_pins(
    owner: str, env: dict[str, str]
) -> tuple[DepMap, list[str], list[str]]:
    """Enumerate fleet repos and collect all git-sourced pins.

    Both ``[tool.uv.sources]`` git pins and PEP 508 direct-URL git pins
    (``name @ git+URL@<sha>``) are collected.

    Returns ``(dep_map, skipped_repos, all_fleet_repos)`` where *dep_map*
    maps ``git_url → [(repo_name, pkg_name, current_rev)]``,
    *skipped_repos* lists repos that have no git-sourced pins, and
    *all_fleet_repos* is the complete list of fleet repo names.
    """
    repo_names = _list_fleet_repos(owner, env)

    dep_map: DepMap = {}
    skipped_repos: list[str] = []
    for repo in repo_names:
        pins = _fetch_repo_pins(owner, repo, env)
        if not pins:
            skipped_repos.append(repo)
            continue
        for pkg, git_url, rev in pins:
            dep_map.setdefault(git_url, []).append((repo, pkg, rev))

    return dep_map, skipped_repos, repo_names


# ---------------------------------------------------------------------------
# Phase 2 — resolve / plan
# ---------------------------------------------------------------------------


def _resolve_latest_shas(
    dep_map: DepMap,
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
            latest_map[git_url] = common.resolve_default_branch_head(git_url)
            print(f"  {git_url}: {latest_map[git_url][:8]}")
        except Exception as exc:
            print(f"  FAILED {git_url}: {exc}", file=sys.stderr)
            unresolved.append((git_url, str(exc)))
    return latest_map, unresolved


def _compute_repo_bumps(
    dep_map: DepMap,
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
# Phase 3 — order (first-party dependency graph & topological sort)
# ---------------------------------------------------------------------------


def _build_first_party_graph(
    dep_map: DepMap,
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
        fleet_urls[common._normalize_git_url(canonical)] = repo_name

    graph: dict[str, set[str]] = {}
    for git_url, pins in dep_map.items():
        normalized = common._normalize_git_url(git_url)
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
    dep_map: DepMap,
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
        dep_url_norm = common._normalize_git_url(
            f"https://github.com/{owner}/{dep_repo}.git"
        )
        for git_url, pins in dep_map.items():
            if common._normalize_git_url(git_url) == dep_url_norm:
                for pin_repo, pkg_name, current_rev in pins:
                    if pin_repo == repo and current_rev != new_sha:
                        bumps.append((pkg_name, new_sha))
                # No break: the same dependency may be listed under several
                # raw URLs (e.g. ``…/repo.git`` and ``…/repo``).
    return bumps


# ---------------------------------------------------------------------------
# Phase 4 — apply (per-repo clone → rewrite → lock → push → PR)
# ---------------------------------------------------------------------------


def _git(repo_dir: Path, *args: str, capture: bool = False) -> str:
    """Run ``git -C <repo_dir> <args>`` and return stripped stdout if captured."""
    if capture:
        cp = common.run("git", "-C", str(repo_dir), *args, capture_output=True)
        return cp.stdout.strip()  # type: ignore[no-any-return]
    common.run("git", "-C", str(repo_dir), *args)
    return ""


def _clone_repo(owner: str, repo: str, token: str, repo_dir: Path) -> str:
    """Shallow-clone *owner/repo* into *repo_dir*; return its default branch."""
    clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    common.run("git", "clone", "--depth=1", clone_url, str(repo_dir))
    # Determine default branch (should be main/master)
    return _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD", capture=True)


def _commit_and_push(owner: str, repo: str, repo_dir: Path) -> str:
    """Commit the rewritten pins on the sweep branch, push it, return its SHA."""
    _git(repo_dir, "config", "user.name", "github-actions[bot]")
    _git(
        repo_dir,
        "config",
        "user.email",
        "github-actions[bot]@users.noreply.github.com",
    )
    _git(repo_dir, "checkout", "-B", SWEEP_BRANCH)
    _git(repo_dir, "add", "pyproject.toml", "uv.lock")
    _git(repo_dir, "commit", "-m", SWEEP_COMMIT_MESSAGE)
    retries = common._push_with_retry(repo_dir, SWEEP_BRANCH)
    _push_retry_counts[f"{owner}/{repo}"] = retries

    # Capture the pushed commit SHA so dependents can pin to it
    return _git(repo_dir, "rev-parse", "HEAD", capture=True)


def _find_open_pr(owner: str, repo: str, base: str, pr_env: dict[str, str]) -> str:
    """Return the number of the open sweep PR in *owner/repo*, or ``""``."""
    try:
        return common.run(  # type: ignore[no-any-return]
            "gh",
            "pr",
            "list",
            # Explicit --repo: every git call above targets the clone with
            # `-C`, but gh resolves the repository from the CWD, which is the
            # workflow's own checkout, not this repo's clone.
            "--repo",
            f"{owner}/{repo}",
            "--head",
            SWEEP_BRANCH,
            "--base",
            base,
            "--json",
            "number",
            "-q",
            ".[0].number",
            capture_output=True,
            env=pr_env,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def _open_or_reuse_pr(
    owner: str,
    repo: str,
    bumps: list[tuple[str, str]],
    token: str,
    base: str,
) -> None:
    """Open the sweep PR, or reuse the open one (already updated by the push)."""
    pr_env = {**os.environ, "GH_TOKEN": token}
    existing = _find_open_pr(owner, repo, base, pr_env)
    if existing:
        print(f"  PR #{existing} already open — updated by force-push.")
        return
    common.run(
        "gh",
        "pr",
        "create",
        "--repo",
        f"{owner}/{repo}",
        "--title",
        SWEEP_COMMIT_MESSAGE,
        "--body",
        (
            "Automated coherent-set pin bump sweep.\n\n"
            "Updated pins:\n"
            + "\n".join(f"- `{pkg}` → `{sha[:8]}`" for pkg, sha in bumps)
        ),
        "--base",
        base,
        "--head",
        SWEEP_BRANCH,
        env=pr_env,
    )
    print(f"  PR created for {owner}/{repo}")


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
    default_branch = _clone_repo(owner, repo, token, repo_dir)

    pyproject = repo_dir / "pyproject.toml"
    if not pyproject.exists():
        print(f"  pyproject.toml not found in cloned {repo} — skipping")
        return None

    common.rewrite_revs(pyproject, dict(bumps))
    common.run("uv", "lock", cwd=str(repo_dir))

    pushed_sha = _commit_and_push(owner, repo, repo_dir)
    _open_or_reuse_pr(owner, repo, bumps, token, default_branch)
    return pushed_sha


# ---------------------------------------------------------------------------
# Phase 5 — summarise
# ---------------------------------------------------------------------------


def _summary_section(title: str, items: list[str]) -> list[str]:
    """Return markdown lines for one summary section (``(none)`` when empty)."""
    if not items:
        return [f"### {title}", "(none)", ""]
    return [f"### {title} ({len(items)})", *(f"- {item}" for item in items), ""]


def _planned_section(
    owner: str, planned: dict[str, list[tuple[str, str]]]
) -> list[str]:
    """Return markdown lines for the dry-run "Planned bumps" section."""
    lines = [f"### Planned bumps — dry run ({len(planned)})"]
    if planned:
        for r in sorted(planned):
            pins = ", ".join(f"`{pkg}` → `{sha[:8]}`" for pkg, sha in planned[r])
            lines.append(f"- {owner}/{r}: {pins}")
    else:
        lines.append("(none)")
    lines.append("")
    return lines


def _write_sweep_summary(
    owner: str,
    bumped: list[str],
    failed: list[tuple[str, str]],
    skipped: list[str],
    unresolved_urls: list[tuple[str, str]],
    skipped_cycles: list[tuple[str, str]] | None = None,
    planned: dict[str, list[tuple[str, str]]] | None = None,
    bumped_notes: dict[str, str] | None = None,
) -> None:
    """Write the sweep summary to stdout and ``$GITHUB_STEP_SUMMARY``.

    *planned* (dry-run only) maps repo → ``[(pkg, new_sha)]`` bumps that
    would be applied.  *bumped_notes* maps a bumped repo to a short note
    (e.g. ``retried 1×``) appended to its summary line.
    """
    notes = bumped_notes or {}
    lines: list[str] = ["## Pin Bump Sweep Summary", ""]
    if planned is not None:
        lines += _planned_section(owner, planned)
    lines += _summary_section(
        "Bumped",
        [f"{owner}/{r}" + (f" ({notes[r]})" if r in notes else "") for r in bumped],
    )
    lines += _summary_section("Failed", [f"{owner}/{r}: {why}" for r, why in failed])
    lines += _summary_section(
        "Skipped — dependency cycles",
        [f"{owner}/{r}: {why}" for r, why in skipped_cycles or []],
    )
    lines += _summary_section(
        "Skipped — no git pins", [f"{owner}/{r}" for r in skipped]
    )
    lines += _summary_section(
        "Unresolved dependencies", [f"{url}: {why}" for url, why in unresolved_urls]
    )

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
# Orchestrator
# ---------------------------------------------------------------------------


@dataclass
class _SweepOutcome:
    """Mutable per-repo results accumulated while applying bumps."""

    bumped: list[str] = field(default_factory=list)
    bumped_notes: dict[str, str] = field(default_factory=dict)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped_cycles: list[tuple[str, str]] = field(default_factory=list)
    # Commit SHA pushed to each repo's PR branch so that dependents can pin
    # to it for coherent transitive resolution.
    pushed_shas: dict[str, str] = field(default_factory=dict)
    failed_or_skipped: set[str] = field(default_factory=set)


def _sweep_token(token_env: str) -> str:
    """Return the sweep token from *token_env*, or raise if it is unset."""
    token = os.environ.get(token_env)
    if not token:
        raise RuntimeError(
            f"Environment variable {token_env} is not set. "
            "The sweep needs a token with repo + workflow scope across all fleet repos."
        )
    return token


def _report_dry_run(owner: str, repo_bumps: dict[str, list[tuple[str, str]]]) -> None:
    """Print the bumps a dry run would apply."""
    print(f"\nDry run — {len(repo_bumps)} repo(s) would get pin bumps:")
    for repo in sorted(repo_bumps):
        for pkg, sha in repo_bumps[repo]:
            print(f"  {owner}/{repo}: {pkg} → {sha[:8]}")


def _report_cycles(graph: dict[str, set[str]], cycle_repos: set[str]) -> None:
    """Warn about repos skipped because of first-party dependency cycles."""
    if not cycle_repos:
        return
    print(
        f"\nWarning: {len(cycle_repos)} repo(s) in first-party "
        "dependency cycles — will be skipped:"
    )
    for repo in sorted(cycle_repos):
        cycle_deps = graph.get(repo, set()) & cycle_repos
        print(f"  {repo} ↔ {', '.join(sorted(cycle_deps))}")


def _bump_one_repo(
    owner: str,
    repo: str,
    bumps: list[tuple[str, str]],
    token: str,
    tmpdir: str,
    outcome: _SweepOutcome,
) -> None:
    """Apply *bumps* to *repo* and record the result in *outcome*."""
    try:
        pushed_sha = _apply_pin_bump(owner, repo, bumps, token, tmpdir)
        if pushed_sha is not None:
            outcome.pushed_shas[repo] = pushed_sha
        outcome.bumped.append(repo)
        retries = _push_retry_counts.pop(f"{owner}/{repo}", 0)
        if retries:
            outcome.bumped_notes[repo] = f"retried {retries}×"
    except Exception as exc:
        outcome.failed.append((repo, str(exc)))
        outcome.failed_or_skipped.add(repo)
        print(f"\n  FAILED {owner}/{repo}: {exc}", file=sys.stderr)


def _apply_in_order(
    owner: str,
    token: str,
    sorted_repos: list[str],
    graph: dict[str, set[str]],
    repo_bumps: dict[str, list[tuple[str, str]]],
    dep_map: DepMap,
    outcome: _SweepOutcome,
) -> None:
    """Apply bumps to *sorted_repos* in topological order — leaves first."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for repo in sorted_repos:
            # If any fleet dep was not successfully processed, skip this
            # repo to avoid conflicting transitive pins.
            deps = graph.get(repo, set())
            unprocessed_deps = deps & outcome.failed_or_skipped
            if unprocessed_deps:
                dep_names = ", ".join(sorted(unprocessed_deps))
                msg = (
                    f"Skipped: depends on {dep_names} which could not be "
                    f"bumped in this sweep"
                )
                outcome.skipped_cycles.append((repo, msg))
                outcome.failed_or_skipped.add(repo)
                print(f"\n  SKIP {owner}/{repo}: {msg}")
                continue

            # Start with bumps from stale default-branch pins, then override
            # with fleet dep bumps — when a first-party dep was already
            # pushed in this sweep, pin to its PR branch SHA so transitive
            # resolution stays coherent.  This takes precedence over the
            # default-branch HEAD computed by _compute_repo_bumps.
            bumps_dict = dict(repo_bumps.get(repo, []))
            fleet_bumps = _get_fleet_dep_bumps(
                repo, deps, outcome.pushed_shas, dep_map, owner
            )
            bumps_dict.update(fleet_bumps)
            if bumps_dict:
                _bump_one_repo(
                    owner, repo, list(bumps_dict.items()), token, tmpdir, outcome
                )


def sweep(owner: str, token_env: str, dry_run: bool = False) -> int:
    """Enumerate fleet repos, resolve pins once, open PRs for affected repos.

    With *dry_run*, stop after computing the stale pins: report the planned
    bumps in the summary without cloning, pushing or opening PRs.

    Repos are processed in topological order so that a dependent always
    pins a commit whose own first-party pins already match.  Repos
    involved in dependency cycles are skipped with an explicit message.
    """
    token = _sweep_token(token_env)
    env = {**os.environ, "GH_TOKEN": token}
    planned_empty: dict[str, list[tuple[str, str]]] | None = {} if dry_run else None

    dep_map, skipped_repos, all_fleet_repos = _collect_fleet_pins(owner, env)
    if not dep_map:
        print("No git-sourced pins found across fleet.")
        if skipped_repos:
            print(f"Skipped {len(skipped_repos)} repo(s) with no git pins:")
            for r in skipped_repos:
                print(f"  - {owner}/{r}")
        _write_sweep_summary(owner, [], [], skipped_repos, [], [], planned_empty)
        return 0

    latest_map, unresolved_urls = _resolve_latest_shas(dep_map)
    repo_bumps = _compute_repo_bumps(dep_map, latest_map)
    if not repo_bumps or dry_run:
        if not repo_bumps:
            print("All fleet pins are already current.")
        else:
            _report_dry_run(owner, repo_bumps)
        planned = repo_bumps if dry_run else None
        _write_sweep_summary(owner, [], [], skipped_repos, unresolved_urls, [], planned)
        return 0

    # Build first-party dependency graph and topologically sort so that
    # leaves (repos that don't pin other fleet repos) are bumped first.
    graph = _build_first_party_graph(dep_map, all_fleet_repos, owner)
    sorted_repos, cycle_repos = _topological_sort(graph, set(repo_bumps))
    _report_cycles(graph, cycle_repos)

    print(f"\n{len(repo_bumps)} repo(s) need pin bumps.")
    outcome = _SweepOutcome(failed_or_skipped=set(cycle_repos))
    _apply_in_order(owner, token, sorted_repos, graph, repo_bumps, dep_map, outcome)

    _write_sweep_summary(
        owner,
        outcome.bumped,
        outcome.failed,
        skipped_repos,
        unresolved_urls,
        outcome.skipped_cycles,
        bumped_notes=outcome.bumped_notes,
    )
    return 1 if outcome.failed else 0
