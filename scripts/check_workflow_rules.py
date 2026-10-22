#!/usr/bin/env python3
"""AGENT.md workflow-rule checker for this workflow library.

Enforces the repo-specific authoring rules declared in ``AGENT.md`` that
no other repo-owned check covers:

- **Rule 1** — every remote ``uses:`` ref is pinned to a 40-char commit
  SHA with a trailing ``# vX[.Y[.Z]]`` version comment.  Local ``./``
  refs are exempt; own-repo composite-action refs
  (``<owner>/<repo>/.github/actions/<name>@<sha>``) must be SHA-pinned
  but carry no version comment (composite actions are not version-tagged).
- **Rule 3** — every ``actions/checkout`` step (workflow job steps and
  composite-action ``runs.steps``) sets ``persist-credentials: false``,
  unless the step carries an explicit ``# zizmor: ignore[artipacked]``
  suppression comment documenting why credentials must persist.
- **Rule 5** — ``workflow_call`` input ``default:`` values are static
  literals, never ``${{ }}`` expressions.

Usage as a standalone script (called from CI workflow / pre-commit)::

    python3 scripts/check_workflow_rules.py

Usage as an importable module (called from tests)::

    from scripts.check_workflow_rules import check
    exit_code = check(workflow_dir=".github/workflows", actions_dir=".github/actions")
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "pyyaml"])
    import yaml

# Reuse the single definition of the own-repo slug / env lookup.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_local_action_refs import _own_repo_action_prefix  # noqa: E402

_USES_RE = re.compile(r"^\s*-?\s*uses:\s*(\S+)")
_SHA_RE = re.compile(r"@[0-9a-f]{40}\b")
_VERSION_COMMENT_RE = re.compile(r"#\s*v\d+(\.\d+)*")
_STEP_START_RE = re.compile(r"^\s*-\s")
_ARTIPACKED_IGNORE = "zizmor: ignore[artipacked]"


def _collect_files(workflow_dir: str, actions_dir: str) -> tuple[list[str], list[str]]:
    workflows = sorted(
        glob.glob(os.path.join(workflow_dir, "*.yml"))
        + glob.glob(os.path.join(workflow_dir, "*.yaml"))
    )
    actions = sorted(
        glob.glob(os.path.join(actions_dir, "*", "action.yml"))
        + glob.glob(os.path.join(actions_dir, "*", "action.yaml"))
    )
    return workflows, actions


def _check_uses_lines(
    path: str, lines: list[str], own_repo_prefix: str, errors: list[str]
) -> None:
    """Rule 1: SHA pin + trailing version comment (line-based)."""
    for lineno, line in enumerate(lines, start=1):
        match = _USES_RE.match(line)
        if not match:
            continue
        ref = match.group(1).strip("'\"")
        if ref.startswith("./"):
            continue
        if ref.startswith("docker://"):
            print(f"::notice::{path}:{lineno}: skipping docker:// ref '{ref}'")
            continue
        if not _SHA_RE.search(ref):
            errors.append(
                f"{path}:{lineno}: 'uses: {ref}' is not pinned to a 40-char "
                f"commit SHA (AGENT.md Rule 1)"
            )
            continue
        if ref.startswith(own_repo_prefix):
            continue
        comment = line[match.end() :]
        if not _VERSION_COMMENT_RE.search(comment):
            errors.append(
                f"{path}:{lineno}: 'uses: {ref}' lacks a trailing '# vX.Y.Z' "
                f"version comment (AGENT.md Rule 1)"
            )


def _find_line(lines: list[str], pattern: str, start: int = 0) -> int:
    """Return the 1-indexed line of the first line containing *pattern*."""
    for idx in range(start, len(lines)):
        if pattern in lines[idx]:
            return idx + 1
    return 1


def _check_workflow_call_defaults(
    path: str, doc: dict, lines: list[str], errors: list[str]
) -> None:
    """Rule 5: workflow_call input defaults must be static literals."""
    triggers = doc.get("on", doc.get(True))
    if not isinstance(triggers, dict):
        return
    wc = triggers.get("workflow_call")
    if not isinstance(wc, dict):
        return
    inputs = wc.get("inputs")
    if not isinstance(inputs, dict):
        return
    for name, spec in inputs.items():
        if not isinstance(spec, dict):
            continue
        default = spec.get("default")
        if isinstance(default, str) and "${{" in default:
            name_line = _find_line(lines, f"{name}:")
            lineno = _find_line(lines, "default:", name_line - 1)
            errors.append(
                f"{path}:{lineno}: workflow_call input '{name}' default "
                f"contains a '${{{{ }}}}' expression; defaults must be static "
                f"literals (AGENT.md Rule 5)"
            )


def _step_suppresses_artipacked(lines: list[str], uses_lineno: int) -> bool:
    """Return True when the step owning *uses_lineno* carries a zizmor
    ``ignore[artipacked]`` suppression comment.

    A few checkout steps intentionally keep persisted credentials (e.g. a
    later push step needs the minted token); they document this with the
    same ``# zizmor: ignore[artipacked]`` marker zizmor honours.  The marker
    is searched from the step's ``- `` start line through the ``uses:`` line.
    """
    idx = uses_lineno - 1
    while idx >= 0:
        line = lines[idx]
        if _ARTIPACKED_IGNORE in line:
            return True
        if _STEP_START_RE.match(line):
            return False
        idx -= 1
    return False


def _iter_steps(doc: dict):
    jobs = doc.get("jobs")
    if isinstance(jobs, dict):
        for job in jobs.values():
            if not isinstance(job, dict):
                continue
            steps = job.get("steps")
            if isinstance(steps, list):
                yield from steps
    runs = doc.get("runs")
    if isinstance(runs, dict):
        steps = runs.get("steps")
        if isinstance(steps, list):
            yield from steps


def _check_checkout_credentials(
    path: str, doc: dict, lines: list[str], errors: list[str]
) -> None:
    """Rule 3: every actions/checkout step sets persist-credentials: false."""
    search_from = 0
    for step in _iter_steps(doc):
        if not isinstance(step, dict):
            continue
        uses = step.get("uses")
        if not isinstance(uses, str) or not uses.startswith("actions/checkout@"):
            continue
        lineno = _find_line(lines, uses, search_from)
        search_from = lineno
        if _step_suppresses_artipacked(lines, lineno):
            continue
        with_ = step.get("with")
        if not isinstance(with_, dict) or with_.get("persist-credentials") is not False:
            errors.append(
                f"{path}:{lineno}: actions/checkout step does not set "
                f"'persist-credentials: false' (AGENT.md Rule 3)"
            )


def check(
    *,
    workflow_dir: str = ".github/workflows",
    actions_dir: str = ".github/actions",
) -> int:
    """Validate AGENT.md Rules 1, 3 and 5 across workflows and composite actions.

    Returns 0 when no violations are found, 1 otherwise.
    """
    workflows, actions = _collect_files(workflow_dir, actions_dir)
    if not workflows and not actions:
        print("::notice::No workflow or composite-action files found; nothing to check.")
        return 0

    errors: list[str] = []
    own_repo_prefix = _own_repo_action_prefix()

    for path in workflows + actions:
        with open(path) as fh:
            text = fh.read()
        lines = text.splitlines()

        _check_uses_lines(path, lines, own_repo_prefix, errors)

        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            errors.append(f"{path}:1: invalid YAML — {exc}")
            continue
        if not isinstance(doc, dict):
            continue

        if path in workflows:
            _check_workflow_call_defaults(path, doc, lines, errors)
        _check_checkout_credentials(path, doc, lines, errors)

    if errors:
        for msg in errors:
            print(f"::error::{msg}", file=sys.stderr)
        return 1

    print("::notice::All workflows and composite actions comply with AGENT.md Rules 1, 3 and 5.")
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
    args = parser.parse_args()
    sys.exit(check(workflow_dir=args.workflow_dir, actions_dir=args.actions_dir))
