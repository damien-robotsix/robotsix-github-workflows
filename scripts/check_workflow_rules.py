#!/usr/bin/env python3
"""Workflow-conventions checker for GitHub Actions workflows.

Enforces the authoring rules declared in this repo's ``AGENT.md`` and is
also exposed to caller repos through ``lint-workflows.yml``
(``run-workflow-rules`` / ``workflow-rules`` inputs).  Each rule has a
toggle name, selected with ``--rules <comma list>`` (``all`` selects every
rule; the default is ``sha-pin,persist-credentials,static-defaults``):

- ``sha-pin`` (**Rule 1**) — every remote ``uses:`` ref is pinned to a 40-char commit
  SHA with a trailing ``# vX[.Y[.Z]]`` version comment.  Local ``./``
  refs are exempt; own-repo composite-action refs
  (``<owner>/<repo>/.github/actions/<name>@<sha>``) must be SHA-pinned
  but carry no version comment (composite actions are not version-tagged).
- ``persist-credentials`` (**Rule 3**) — every ``actions/checkout`` step (workflow job steps and
  composite-action ``runs.steps``) sets ``persist-credentials: false``,
  unless the step carries an explicit ``# zizmor: ignore[artipacked]``
  suppression comment documenting why credentials must persist.
- ``static-defaults`` (**Rule 5**) — ``workflow_call`` input ``default:``
  values are static literals, never ``${{ }}`` expressions.
- ``harden-runner-first`` — the first step of every workflow job is
  ``step-security/harden-runner``.
- ``setup-uv`` — every workflow job whose ``run:`` steps invoke ``uv``
  includes an ``astral-sh/setup-uv`` step.
- ``uv-sync-frozen`` — every ``uv sync`` invocation passes ``--frozen``.

Job-level rules (``harden-runner-first``, ``setup-uv``) expand local
composite actions (``uses: ./.github/actions/<name>``) into the calling
job's steps and skip reusable-workflow jobs (job-level ``uses:``), which
have no steps of their own.

Usage as a standalone script (called from CI workflow / pre-commit)::

    python3 scripts/check_workflow_rules.py
    python3 scripts/check_workflow_rules.py --rules all

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
_LOCAL_ACTION_PREFIX = "./.github/actions/"
_HARDEN_RUNNER = "step-security/harden-runner@"
_SETUP_UV = "astral-sh/setup-uv@"
# Shell command separators used to split a ``run:`` script into commands.
_CMD_SEPARATOR_RE = re.compile(r"&&|\|\||;|\n|\||\$\(|`|\(|\)")
# Leading tokens that may precede the actual command word.
_CMD_PREFIX_RE = re.compile(
    r"^(?:(?:if|then|else|elif|do|while|until|!|exec|time|command)\s+"
    r"|[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*"
)

RULE_SHA_PIN = "sha-pin"
RULE_PERSIST_CREDENTIALS = "persist-credentials"
RULE_STATIC_DEFAULTS = "static-defaults"
RULE_HARDEN_RUNNER_FIRST = "harden-runner-first"
RULE_SETUP_UV = "setup-uv"
RULE_UV_SYNC_FROZEN = "uv-sync-frozen"

ALL_RULES: tuple[str, ...] = (
    RULE_SHA_PIN,
    RULE_PERSIST_CREDENTIALS,
    RULE_STATIC_DEFAULTS,
    RULE_HARDEN_RUNNER_FIRST,
    RULE_SETUP_UV,
    RULE_UV_SYNC_FROZEN,
)
# AGENT.md Rules 1, 3 and 5 — what this repo's own CI / pre-commit enforce.
DEFAULT_RULES: tuple[str, ...] = (
    RULE_SHA_PIN,
    RULE_PERSIST_CREDENTIALS,
    RULE_STATIC_DEFAULTS,
)


def parse_rules(spec: str | None) -> set[str]:
    """Parse a comma/space-separated rule list into a set of rule names.

    Empty / ``None`` selects :data:`DEFAULT_RULES`; ``all`` selects
    :data:`ALL_RULES`.  Raises ``ValueError`` on an unknown rule name.
    """
    if spec is None or not spec.strip():
        return set(DEFAULT_RULES)
    names = {n.strip() for n in re.split(r"[,\s]+", spec) if n.strip()}
    if "all" in names:
        names.discard("all")
        names |= set(ALL_RULES)
    unknown = sorted(names - set(ALL_RULES))
    if unknown:
        raise ValueError(
            f"unknown workflow rule(s): {', '.join(unknown)} "
            f"(valid: {', '.join(ALL_RULES)}, all)"
        )
    return names


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


def _uses_of(step: object) -> str:
    if not isinstance(step, dict):
        return ""
    uses = step.get("uses")
    return uses.strip() if isinstance(uses, str) else ""


def _local_action_name(uses: str, own_repo_prefix: str) -> str | None:
    """Return the composite-action name *uses* refers to in *actions_dir*.

    Handles relative ``./.github/actions/<name>`` refs and absolute own-repo
    ``<owner>/<repo>/.github/actions/<name>@<ref>`` refs; None otherwise.
    """
    if uses.startswith(_LOCAL_ACTION_PREFIX):
        return uses[len(_LOCAL_ACTION_PREFIX) :].strip("/") or None
    if own_repo_prefix and uses.startswith(own_repo_prefix):
        return uses[len(own_repo_prefix) :].split("@", 1)[0].strip("/") or None
    return None


def _load_local_action_steps(actions_dir: str, name: str) -> list | None:
    """Return the ``runs.steps`` of composite action *name*, or None."""
    for fname in ("action.yml", "action.yaml"):
        path = os.path.join(actions_dir, name, fname)
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as fh:
                doc = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError):
            return None
        runs = doc.get("runs") if isinstance(doc, dict) else None
        steps = runs.get("steps") if isinstance(runs, dict) else None
        return steps if isinstance(steps, list) else None
    return None


def _expand_steps(
    steps: list,
    actions_dir: str,
    own_repo_prefix: str,
    _seen: frozenset = frozenset(),
) -> list:
    """Inline local composite actions' steps into *steps* (recursively)."""
    expanded: list = []
    for step in steps:
        expanded.append(step)
        name = _local_action_name(_uses_of(step), own_repo_prefix)
        if name and name not in _seen:
            inner = _load_local_action_steps(actions_dir, name)
            if inner:
                expanded.extend(
                    _expand_steps(inner, actions_dir, own_repo_prefix, _seen | {name})
                )
    return expanded


def _iter_step_jobs(doc: dict):
    """Yield ``(job_id, steps)`` for every workflow job that has steps.

    Reusable-workflow jobs (job-level ``uses:``) have no steps and are skipped.
    """
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return
    for job_id, job in jobs.items():
        if not isinstance(job, dict) or "uses" in job:
            continue
        steps = job.get("steps")
        if isinstance(steps, list) and steps:
            yield str(job_id), steps


def _find_job_line(lines: list[str], job_id: str) -> int:
    """Return the 1-indexed line declaring job *job_id* under ``jobs:``."""
    start = next((i for i, ln in enumerate(lines) if re.match(r"^jobs:\s*(#.*)?$", ln)), 0)
    pattern = re.compile(rf"^\s+['\"]?{re.escape(job_id)}['\"]?:\s*(#.*)?$")
    for idx in range(start, len(lines)):
        if pattern.match(lines[idx]):
            return idx + 1
    return start + 1


def _first_step_uses(
    steps: list, actions_dir: str, own_repo_prefix: str
) -> str:
    """Return the ``uses:`` of the first effective step of *steps*.

    When the first step is a local composite action its own first step is
    followed instead (recursively), so a composite that starts with
    harden-runner satisfies the rule.
    """
    seen: set[str] = set()
    uses = _uses_of(steps[0])
    while True:
        name = _local_action_name(uses, own_repo_prefix)
        if not name or name in seen:
            return uses
        seen.add(name)
        inner = _load_local_action_steps(actions_dir, name)
        if not inner:
            return uses
        uses = _uses_of(inner[0])


def _check_harden_runner_first(
    path: str,
    doc: dict,
    lines: list[str],
    actions_dir: str,
    own_repo_prefix: str,
    errors: list[str],
) -> None:
    """harden-runner-first: the first step of every job is harden-runner."""
    for job_id, steps in _iter_step_jobs(doc):
        if _first_step_uses(steps, actions_dir, own_repo_prefix).startswith(_HARDEN_RUNNER):
            continue
        lineno = _find_job_line(lines, job_id)
        errors.append(
            f"{path}:{lineno}: job '{job_id}' does not start with a "
            f"'step-security/harden-runner' step (rule {RULE_HARDEN_RUNNER_FIRST})"
        )


def _shell_commands(run: str) -> list[str]:
    """Split a ``run:`` script into simple commands (best effort).

    Backslash line continuations are joined, comments dropped, and leading
    keywords / ``VAR=value`` assignments stripped so each entry starts with
    its command word.
    """
    script = re.sub(r"\\\n", " ", run)
    script = re.sub(r"(?m)(^|\s)#.*$", r"\1", script)
    commands = []
    for segment in _CMD_SEPARATOR_RE.split(script):
        segment = _CMD_PREFIX_RE.sub("", segment.strip())
        if segment:
            commands.append(segment)
    return commands


def _is_uv(command: str, subcommand: str | None = None) -> bool:
    words = command.split()
    if not words or words[0] != "uv":
        return False
    return subcommand is None or (len(words) > 1 and words[1] == subcommand)


def _run_uses_uv(step: object) -> bool:
    if not isinstance(step, dict):
        return False
    run = step.get("run")
    return isinstance(run, str) and any(_is_uv(c) for c in _shell_commands(run))


def _check_setup_uv(
    path: str,
    doc: dict,
    lines: list[str],
    actions_dir: str,
    own_repo_prefix: str,
    errors: list[str],
) -> None:
    """setup-uv: jobs that run ``uv`` include an astral-sh/setup-uv step."""
    for job_id, steps in _iter_step_jobs(doc):
        expanded = _expand_steps(steps, actions_dir, own_repo_prefix)
        if not any(_run_uses_uv(s) for s in expanded):
            continue
        if any(_uses_of(s).startswith(_SETUP_UV) for s in expanded):
            continue
        lineno = _find_job_line(lines, job_id)
        errors.append(
            f"{path}:{lineno}: job '{job_id}' runs 'uv' but has no "
            f"'astral-sh/setup-uv' step (rule {RULE_SETUP_UV})"
        )


def _check_uv_sync_frozen(
    path: str, doc: dict, lines: list[str], errors: list[str]
) -> None:
    """uv-sync-frozen: every ``uv sync`` invocation passes ``--frozen``."""
    search_from = 0
    for step in _iter_steps(doc):
        if not isinstance(step, dict):
            continue
        run = step.get("run")
        if not isinstance(run, str):
            continue
        for command in _shell_commands(run):
            if not _is_uv(command, "sync"):
                continue
            lineno = _find_line(lines, "uv sync", search_from)
            search_from = lineno
            if "--frozen" not in command.split():
                errors.append(
                    f"{path}:{lineno}: 'uv sync' without '--frozen' "
                    f"(rule {RULE_UV_SYNC_FROZEN})"
                )


def check(
    *,
    workflow_dir: str = ".github/workflows",
    actions_dir: str = ".github/actions",
    rules: set[str] | frozenset[str] | tuple[str, ...] | list[str] | None = None,
) -> int:
    """Validate the selected *rules* across workflows and composite actions.

    *rules* defaults to :data:`DEFAULT_RULES` (AGENT.md Rules 1, 3 and 5).
    Returns 0 when no violations are found, 1 otherwise.
    """
    selected = set(DEFAULT_RULES) if rules is None else set(rules)
    unknown = sorted(selected - set(ALL_RULES))
    if unknown:
        raise ValueError(f"unknown workflow rule(s): {', '.join(unknown)}")

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

        if RULE_SHA_PIN in selected:
            _check_uses_lines(path, lines, own_repo_prefix, errors)

        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            errors.append(f"{path}:1: invalid YAML — {exc}")
            continue
        if not isinstance(doc, dict):
            continue

        is_workflow = path in workflows
        if is_workflow and RULE_STATIC_DEFAULTS in selected:
            _check_workflow_call_defaults(path, doc, lines, errors)
        if RULE_PERSIST_CREDENTIALS in selected:
            _check_checkout_credentials(path, doc, lines, errors)
        if is_workflow and RULE_HARDEN_RUNNER_FIRST in selected:
            _check_harden_runner_first(
                path, doc, lines, actions_dir, own_repo_prefix, errors
            )
        if is_workflow and RULE_SETUP_UV in selected:
            _check_setup_uv(path, doc, lines, actions_dir, own_repo_prefix, errors)
        if RULE_UV_SYNC_FROZEN in selected:
            _check_uv_sync_frozen(path, doc, lines, errors)

    if errors:
        for msg in errors:
            print(f"::error::{msg}", file=sys.stderr)
        return 1

    names = ", ".join(r for r in ALL_RULES if r in selected) or "none"
    print(
        "::notice::All workflows and composite actions comply with the "
        f"selected workflow rules ({names})."
    )
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
        "--rules",
        default=os.environ.get("WORKFLOW_RULES", ""),
        help=(
            "Comma-separated rules to enforce, or 'all' "
            f"(valid: {', '.join(ALL_RULES)}; default: {','.join(DEFAULT_RULES)}; "
            "env: WORKFLOW_RULES)."
        ),
    )
    args = parser.parse_args()
    try:
        selected_rules = parse_rules(args.rules)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(2)
    sys.exit(
        check(
            workflow_dir=args.workflow_dir,
            actions_dir=args.actions_dir,
            rules=selected_rules,
        )
    )
