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
import sys

try:
    import yaml
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "pyyaml"])
    import yaml

_LOCAL_ACTION_PREFIX = "./.github/actions/"
# Absolute prefix for this repo's own composite actions when referenced
# from reusable workflows (which resolve ./  against the *caller* repo,
# not the workflow repo).  The @<sha> suffix is stripped during matching.
_OWN_REPO_ACTION_PREFIX = "damien-robotsix/robotsix-github-workflows/.github/actions/"


def _action_file_exists(actions_dir: str, name: str) -> bool:
    """Return True if ``<actions_dir>/<name>/action.yml`` (or .yaml) exists."""
    base = os.path.join(actions_dir, name)
    return os.path.isfile(os.path.join(base, "action.yml")) or os.path.isfile(
        os.path.join(base, "action.yaml")
    )


def _collect_local_refs_from_doc(doc: object) -> list[str]:
    """Collect every local (or own-repo absolute) action reference from a parsed doc.

    Returns action *names* (e.g. ``"python-setup"``) for both:
    - ``uses: ./.github/actions/<name>``
    - ``uses: damien-robotsix/robotsix-github-workflows/.github/actions/<name>@<sha>``
    """
    refs: list[str] = []
    if not isinstance(doc, dict):
        return refs

    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return refs

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
                name = uses[len(_LOCAL_ACTION_PREFIX) :]
                refs.append(name)
            elif uses.startswith(_OWN_REPO_ACTION_PREFIX):
                # Strip prefix and optional @<sha> suffix
                rest = uses[len(_OWN_REPO_ACTION_PREFIX) :]
                name = rest.split("@", 1)[0]
                refs.append(name)

    return refs


def check(
    *,
    workflow_dir: str = ".github/workflows",
    actions_dir: str = ".github/actions",
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

    for path in workflow_paths:
        with open(path) as fh:
            try:
                doc = yaml.safe_load(fh)
            except yaml.YAMLError as exc:
                errors.append(f"{path}: invalid YAML — {exc}")
                continue

        for name in _collect_local_refs_from_doc(doc):
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
