#!/usr/bin/env python3
"""Assert a hardened image runs as the same ``USER`` as its base image.

Fail-closed companion to ``render_harden_dockerfile.py``.  The hardening layer
runs ``apt`` as ``root`` and is then supposed to restore the base image's
original ``USER``.  If a parsing regression (a buildx format change, an
unexpected multi-arch shape, a transient empty inspect) dropped the restore
line, the published image would silently run as ``root`` with an otherwise
green build and a green Trivy gate.

This script verifies the *outcome* rather than trusting the parse: it compares
the published (hardened) image's ``User`` against the Stage-1 base image's
``User`` (both obtained via ``docker buildx imagetools inspect --format
'{{json .Image}}'``) and exits non-zero on mismatch.

It lives in ``scripts/`` as an importable module (AGENT.md Rule 6) so the
shared ``docker-release.yml`` workflow invokes it through a composite action
and the unit tests exercise the exact same logic.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

# Reuse the shape-tolerant parser from the render script.  When run as a
# script, the scripts/ directory is on ``sys.path`` so a direct import works;
# fall back to loading by path for callers (e.g. tests) that import this
# module out of tree.
try:  # pragma: no cover - exercised implicitly by the workflow
    from render_harden_dockerfile import extract_user
except ImportError:  # pragma: no cover - import-path fallback
    _spec = importlib.util.spec_from_file_location(
        "render_harden_dockerfile",
        Path(__file__).resolve().parent / "render_harden_dockerfile.py",
    )
    assert _spec is not None and _spec.loader is not None
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    extract_user = _module.extract_user


def normalize_user(user: str | None) -> str | None:
    """Canonicalise root-equivalent users to ``""``.

    ``""``, ``"root"`` and ``"0"`` all describe the same (root) runtime user,
    so they compare equal.  ``None`` (undeterminable) is preserved so the
    caller can fail loud rather than treat it as root.
    """
    if user is None:
        return None
    stripped = user.strip()
    return "" if stripped in ("root", "0") else stripped


def _load_config(path: str) -> Any:
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-config",
        required=True,
        help="Path to the base image's JSON config (imagetools inspect .Image).",
    )
    parser.add_argument(
        "--hardened-config",
        required=True,
        help="Path to the hardened image's JSON config (imagetools inspect "
        ".Image).",
    )
    args = parser.parse_args(argv)

    base_user = extract_user(_load_config(args.base_config))
    hardened_user = extract_user(_load_config(args.hardened_config))

    if base_user is None:
        print(
            "error: could not determine the base image's USER from "
            f"--base-config ({args.base_config!r}); cannot verify the "
            "hardened image did not escalate to root.",
            file=sys.stderr,
        )
        return 2
    if hardened_user is None:
        print(
            "error: could not determine the hardened image's USER from "
            f"--hardened-config ({args.hardened_config!r}); cannot verify it "
            "did not escalate to root.",
            file=sys.stderr,
        )
        return 2

    if normalize_user(base_user) != normalize_user(hardened_user):
        print(
            "error: hardened image USER "
            f"({hardened_user!r}) does not match base image USER "
            f"({base_user!r}); the hardening layer did not restore the "
            "original user. Refusing to publish a privilege-escalated image.",
            file=sys.stderr,
        )
        return 1

    print(
        f"ok: hardened image runs as the base image USER ({base_user!r})."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
