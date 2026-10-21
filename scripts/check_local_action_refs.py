#!/usr/bin/env python3
"""Local composite-action reference validator for GitHub Actions workflows.

Ensures that every ``uses: ./.github/actions/<name>`` step in the
repository's workflow files points to an existing composite action
(``.github/actions/<name>/action.yml`` or ``action.yaml``).  Optionally
also fails when a composite action is not referenced by any workflow
(no orphaned composite actions).

This covers the gap left by actionlint (which intentionally dropped its
missing-local-action check) and ``mpalmer/action-validator`` (which only
validates YAML schema, not filesystem existence).

Usage as a standalone script (called from CI workflow)::

    python3 scripts/check_local_action_refs.py --check-orphans

Usage as an importable module (called from tests)::

    from scripts.check_local_action_refs import check
    exit_code = check(check_orphans=True)
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys

try:
    import yaml
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "pyyaml"])
    import yaml

_LOCAL_ACTION_PREFIX = "./.github/actions/"
# Path segment that follows ``<owner>/<repo>`` in an absolute reference to
# this repo's own composite actions.
_OWN_REPO_ACTIONS_SUFFIX = "/.github/actions/"
# Fallback ``<owner>/<repo>`` used only when GITHUB_REPOSITORY is not set
# (local runs / unit tests).  This is the single place the repo slug is
# defined; do not re-hardcode it elsewhere.
_DEFAULT_OWN_REPO = "damien-robotsix/robotsix-github-workflows"


def _own_repo_action_prefix(repository: str | None = None) -> str:
    """Return the absolute ``uses:`` prefix for this repo's own composite actions.

    Reusable workflows reference their own composite actions with an
    absolute ``<owner>/<repo>/.github/actions/<name>@<sha>`` ref because a
    relative ``./`` path resolves against the *caller* repo, not the
    workflow repo.  The ``<owner>/<repo>`` slug is derived from the live
    ``GITHUB_REPOSITORY`` runtime context (always set inside GitHub
    Actions), falling back to :data:`_DEFAULT_OWN_REPO` outside CI.  Because
    the prefix comes from the same context the workflows run in, resolution
    can never drift from the workflows' actual own-repo action refs.
    """
    repo = repository or os.environ.get("GITHUB_REPOSITORY") or _DEFAULT_OWN_REPO
    return f"{repo}{_OWN_REPO_ACTIONS_SUFFIX}"


def _action_file_exists(actions_dir: str, name: str) -> bool:
    """Return True if ``<actions_dir>/<name>/action.yml`` (or .yaml) exists."""
    base = os.path.join(actions_dir, name)
    return os.path.isfile(os.path.join(base, "action.yml")) or os.path.isfile(
        os.path.join(base, "action.yaml")
    )


def _iter_action_refs(doc: object, own_repo_prefix: str):
    """Yield ``(name, sha)`` for every local/own-repo action ref in a doc.

    ``sha`` is ``None`` for relative ``./.github/actions/<name>`` refs and
    the pinned 40-char commit sha for own-repo absolute
    ``<owner>/<repo>/.github/actions/<name>@<sha>`` refs (``None`` when the
    absolute ref carries no ``@<sha>`` suffix).
    """
    if not isinstance(doc, dict):
        return

    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return

    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses")
            if not isinstance(uses, str):
                continue
            if uses.startswith(_LOCAL_ACTION_PREFIX):
                yield uses[len(_LOCAL_ACTION_PREFIX) :], None
            elif uses.startswith(own_repo_prefix):
                # Strip prefix and split the optional @<sha> suffix.
                rest = uses[len(own_repo_prefix) :]
                name, _, sha = rest.partition("@")
                yield name, (sha or None)


def _collect_local_refs_from_doc(
    doc: object, own_repo_prefix: str | None = None
) -> list[str]:
    """Collect every local (or own-repo absolute) action reference from a parsed doc.

    Returns action *names* (e.g. ``"python-setup"``) for both:
    - ``uses: ./.github/actions/<name>``
    - ``uses: <owner>/<repo>/.github/actions/<name>@<sha>``

    The own-repo absolute prefix is derived from the runtime context via
    :func:`_own_repo_action_prefix` unless supplied explicitly by the
    caller (computed once per :func:`check` run).
    """
    if own_repo_prefix is None:
        own_repo_prefix = _own_repo_action_prefix()

    return [name for name, _sha in _iter_action_refs(doc, own_repo_prefix)]


def _verify_action_at_sha(
    name: str, sha: str, *, actions_dir_rel: str = ".github/actions", repo_root: str = "."
) -> str | None:
    """Verify the composite action ``name`` exists in git at ``sha``.

    Reproduces the failure mode that a working-tree-only check misses: an
    own-repo absolute ``uses:`` pinned to a sha that does *not* contain the
    action's ``action.yml`` fails at ``Set up job`` for the first consumer
    whose pin moves past it.  Checks ``git cat-file -e
    <sha>:.github/actions/<name>/action.yml`` (falling back to
    ``action.yaml``), fetching the sha first (``git fetch --depth=1 origin
    <sha>``) when the checkout is shallow and the object is absent.

    Returns ``None`` when the action file exists at the sha, or an error
    string (naming the action and the sha) otherwise.
    """

    def _sha_present() -> bool:
        return (
            subprocess.run(
                ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                cwd=repo_root,
                capture_output=True,
            ).returncode
            == 0
        )

    if not _sha_present():
        fetched = subprocess.run(
            ["git", "fetch", "--depth=1", "origin", sha],
            cwd=repo_root,
            capture_output=True,
        )
        if fetched.returncode != 0 or not _sha_present():
            return f"action '{name}' pinned to sha {sha} which could not be fetched"

    for filename in ("action.yml", "action.yaml"):
        path = f"{actions_dir_rel}/{name}/{filename}"
        if (
            subprocess.run(
                ["git", "cat-file", "-e", f"{sha}:{path}"],
                cwd=repo_root,
                capture_output=True,
            ).returncode
            == 0
        ):
            return None

    return (
        f"action '{name}' does not exist at sha {sha} "
        f"({actions_dir_rel}/{name}/action.yml or action.yaml); the pinned "
        f"sha must be one that contains the action"
    )


def check(
    *,
    workflow_dir: str = ".github/workflows",
    actions_dir: str = ".github/actions",
    actions_dir_rel: str = ".github/actions",
    repo_root: str = ".",
    check_orphans: bool = False,
) -> int:
    """Validate local composite-action references across all workflow files.

    Returns 0 when all references resolve (and, when *check_orphans* is
    set, no action is orphaned), 1 when violations are found.
    """
    if not os.path.isdir(workflow_dir):
        print(f"::notice::{workflow_dir} not found; nothing to check.")
        return 0

    workflow_paths = sorted(
        glob.glob(f"{workflow_dir}/*.yml") + glob.glob(f"{workflow_dir}/*.yaml")
    )
    if not workflow_paths:
        print(f"::notice::No workflow files found in {workflow_dir}; nothing to check.")
        return 0

    errors: list[str] = []
    referenced: set[str] = set()
    own_repo_prefix = _own_repo_action_prefix()

    for path in workflow_paths:
        with open(path) as fh:
            try:
                doc = yaml.safe_load(fh)
            except yaml.YAMLError as exc:
                errors.append(f"{path}: invalid YAML — {exc}")
                continue

        for name, sha in _iter_action_refs(doc, own_repo_prefix):
            if not name or "/" in name:
                errors.append(f"{path}: invalid local action reference '{name}'")
                continue

            referenced.add(name)
            if not _action_file_exists(actions_dir, name):
                errors.append(
                    f"{path}: references action '{name}' but "
                    f"{actions_dir}/{name}/action.yml (or action.yaml) "
                    f"does not exist"
                )

            # Own-repo absolute refs carry a pinned sha; the working-tree
            # check above cannot catch a sha that predates the action
            # (ghwf #211). Verify the action file exists AT THAT SHA.
            if sha:
                sha_error = _verify_action_at_sha(
                    name,
                    sha,
                    actions_dir_rel=actions_dir_rel,
                    repo_root=repo_root,
                )
                if sha_error is not None:
                    errors.append(f"{path}: {sha_error}")

    if check_orphans and os.path.isdir(actions_dir):
        for entry in sorted(os.listdir(actions_dir)):
            entry_path = os.path.join(actions_dir, entry)
            if not os.path.isdir(entry_path):
                continue
            if _action_file_exists(actions_dir, entry) and entry not in referenced:
                errors.append(
                    f"{actions_dir}/{entry}/action.yml (or action.yaml) is "
                    f"not referenced by any workflow"
                )

    if errors:
        for msg in errors:
            print(f"::error::{msg}", file=sys.stderr)
        return 1

    print("::notice::All local composite action references resolve.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory containing workflow files (default: %(default)s).",
    )
    parser.add_argument(
        "--actions-dir",
        default=".github/actions",
        help="Directory containing composite actions (default: %(default)s).",
    )
    parser.add_argument(
        "--check-orphans",
        action="store_true",
        help=(
            "Also fail when a composite action is not referenced by any "
            "workflow (no orphaned composite actions)."
        ),
    )
    args = parser.parse_args()
    sys.exit(
        check(
            workflow_dir=args.workflow_dir,
            actions_dir=args.actions_dir,
            check_orphans=args.check_orphans,
        )
    )
