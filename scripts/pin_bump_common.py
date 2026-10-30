"""Shared helpers for ``scripts/pin-bump.py`` and ``scripts/pin_bump_sweep.py``.

Subprocess / ``gh`` wrappers, the transient-error push retry, default-branch
HEAD resolution, ``pyproject.toml`` git-pin parsing and rewriting, and git
URL normalisation.  Used by both the per-repo mode (``pin-bump.py``) and the
fleet sweep mode (``pin_bump_sweep.py``).
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from collections.abc import Callable
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


# Back-off delays (seconds) between push retries on transient server errors.
PUSH_RETRY_DELAYS: tuple[int, ...] = (10, 20, 40)

# Push output patterns that indicate a transient GitHub-side failure worth
# retrying.  Anything else (auth, protected branch, non-fast-forward) fails
# immediately.
_TRANSIENT_PUSH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"remote: Internal Server Error", re.IGNORECASE),
    re.compile(r"remote rejected.*\(Internal Server Error\)", re.IGNORECASE),
    re.compile(r"\bHTTP(?:/[\d.]+)?\s*5\d\d\b", re.IGNORECASE),
    re.compile(r"returned error: 5\d\d\b", re.IGNORECASE),
    re.compile(r"The remote end hung up unexpectedly", re.IGNORECASE),
)

_REQUEST_ID_RE = re.compile(r"\b([0-9A-F]{3,5}(?::[0-9A-F]+){4})\b")


def _is_transient_push_error(output: str) -> bool:
    """Return True when *output* from ``git push`` looks like a transient 5xx."""
    return any(p.search(output) for p in _TRANSIENT_PUSH_PATTERNS)


def _push_with_retry(
    repo_dir: Path,
    branch: str,
    *,
    delays: tuple[int, ...] = PUSH_RETRY_DELAYS,
    sleep: Callable[[float], None] | None = None,
) -> int:
    """Force-push *branch* from *repo_dir*, retrying transient server errors.

    Retries up to ``len(delays)`` times, sleeping ``delays[i]`` seconds
    before retry *i*, only when the push output matches a transient
    GitHub 5xx pattern.  Any other failure raises
    ``subprocess.CalledProcessError`` immediately.  Returns the number of
    retries that were needed (0 when the first push succeeded).
    """
    sleep_fn = sleep if sleep is not None else time.sleep
    cmd = ("git", "-C", str(repo_dir), "push", "--force", "origin", branch)
    attempt = 0
    while True:
        cp = run(*cmd, check=False, capture_output=True)
        output = (cp.stdout or "") + (cp.stderr or "")
        if output:
            print(output, end="" if output.endswith("\n") else "\n")
        if cp.returncode == 0:
            return attempt
        if attempt >= len(delays) or not _is_transient_push_error(output):
            raise subprocess.CalledProcessError(
                cp.returncode, cmd, output=cp.stdout, stderr=cp.stderr
            )
        delay = delays[attempt]
        attempt += 1
        m = _REQUEST_ID_RE.search(output)
        request_id = m.group(1) if m else "unknown"
        print(
            f"  push of {branch} hit a transient server error "
            f"(GitHub request id {request_id}); retry {attempt}/{len(delays)} "
            f"in {delay}s",
            file=sys.stderr,
        )
        sleep_fn(delay)


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


# PEP 508 direct-URL git pin: ``name[extras] @ git+URL@<40-hex>[#frag][; marker]``
_DIRECT_URL_GIT_PIN_RE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*@\s*"
    r"git\+(\S+?)@([0-9a-f]{40})(?=$|[#;\s])"
)


def _iter_dependency_strings(data: dict) -> list[str]:  # type: ignore[type-arg]
    """Return every PEP 508 requirement string from ``[project.dependencies]``,
    ``[project.optional-dependencies]`` and ``[dependency-groups]``."""
    reqs: list[str] = []
    project = data.get("project", {})
    if isinstance(project, dict):
        reqs.extend(
            d for d in project.get("dependencies", []) or [] if isinstance(d, str)
        )
        optional = project.get("optional-dependencies", {}) or {}
        if isinstance(optional, dict):
            for group in optional.values():
                if isinstance(group, list):
                    reqs.extend(d for d in group if isinstance(d, str))
    groups = data.get("dependency-groups", {}) or {}
    if isinstance(groups, dict):
        for group in groups.values():
            if isinstance(group, list):
                # Entries may also be ``{include-group = "..."}`` tables.
                reqs.extend(d for d in group if isinstance(d, str))
    return reqs


def _extract_git_pins(data: dict) -> list[tuple[str, str, str]]:  # type: ignore[type-arg]
    """Return ``[(pkg_name, git_url, rev)]`` for every SHA-pinned git dependency.

    Covers both ``[tool.uv.sources]`` inline tables with a 40-char ``rev``
    and PEP 508 direct-URL requirements of the form
    ``name @ git+URL@<40-hex>`` in ``[project.dependencies]``,
    ``[project.optional-dependencies]`` and ``[dependency-groups]``.
    """
    pins: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    raw = data.get("tool", {}).get("uv", {}).get("sources", {})
    for name, spec in raw.items():
        if isinstance(spec, dict) and "git" in spec:
            rev = spec.get("rev")
            if rev and isinstance(rev, str) and len(rev) == 40:
                pins.append((name, spec["git"], rev))
                seen.add((name, spec["git"], rev))
    for req in _iter_dependency_strings(data):
        m = _DIRECT_URL_GIT_PIN_RE.match(req)
        if m is None:
            continue
        pin = (m.group(1), m.group(2), m.group(3))
        if pin not in seen:
            seen.add(pin)
            pins.append(pin)
    return pins


def parse_git_sources(pyproject_path: Path) -> dict[str, dict[str, str]]:
    """Return ``{pkg_name: {git: url, rev: sha}}`` for every git-sourced entry.

    Includes ``[tool.uv.sources]`` entries whose value is a dict containing
    a ``git`` key and a 40-char ``rev`` (entries without one are unpinned
    and skipped), plus PEP 508 direct-URL pins (``name @ git+URL@<sha>``)
    in ``[project.dependencies]``, ``[project.optional-dependencies]`` and
    ``[dependency-groups]``.
    """
    if tomllib is None:
        raise RuntimeError("tomllib requires Python >= 3.11")

    with pyproject_path.open("rb") as fh:
        data = tomllib.load(fh)

    sources: dict[str, dict[str, str]] = {}
    for name, url, rev in _extract_git_pins(data):
        sources.setdefault(name, {"git": url, "rev": rev})
    return sources


# ---------------------------------------------------------------------------
# Rewriting pyproject.toml
# ---------------------------------------------------------------------------


def rewrite_revs(pyproject_path: Path, bumps: dict[str, str]) -> None:
    """Replace ``rev`` values in *pyproject_path* for the given package names.

    *bumps* maps package name → new SHA.

    Matches ``rev`` lines inside a ``[tool.uv.sources.<name>]``
    inline-table, and quoted PEP 508 direct-URL requirements
    ``"<name> @ git+URL@<40-hex>"`` — both regexes are intentionally narrow
    to avoid accidental replacements in unrelated TOML sections.
    """
    text = pyproject_path.read_text()
    for pkg, new_sha in bumps.items():
        # Match: <pkg> = { git = "...", rev = "<40-hex>" ... }
        pattern = re.compile(
            rf'^(\s*{re.escape(pkg)}\s*=\s*\{{.*?\brev\s*=\s*")[0-9a-f]{{40}}(".*\}}.*)$',
            re.MULTILINE,
        )
        # Match: "<pkg>[extras] @ git+<url>@<40-hex>..." (every occurrence,
        # so the same package pinned in several groups stays coherent)
        direct_pattern = re.compile(
            rf"""(["']\s*{re.escape(pkg)}\s*(?:\[[^\]]*\])?\s*@\s*git\+[^"'\s]*?@)"""
            rf"""[0-9a-f]{{40}}(?=["'#;\s])"""
        )
        found = False
        if pattern.search(text) is not None:
            found = True
            text = pattern.sub(rf"\g<1>{new_sha}\g<2>", text, count=1)
        if direct_pattern.search(text) is not None:
            found = True
            text = direct_pattern.sub(rf"\g<1>{new_sha}", text)
        if not found:
            print(
                f"::warning::Could not locate rev for {pkg} in pyproject.toml — skipping rewrite",
                file=sys.stderr,
            )
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
