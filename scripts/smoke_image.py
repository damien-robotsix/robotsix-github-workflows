#!/usr/bin/env python3
"""Smoke-test a freshly built Docker image by executing it once.

The reusable Docker publish/scan workflows build an image, run Trivy and
layer a security-hardening wrapper on top -- but nothing in that pipeline
ever *executes* the image.  An image can therefore build cleanly, scan
green and still be completely unbootable: e.g. ``requires-python`` is
raised to ``>=3.14`` while the Dockerfile builds on the 3.12 uv image, uv
downloads a managed 3.14 into the builder, and the venv copied into the
runtime stage ends up with a dangling python symlink + shebangs::

    exec /app/.venv/bin/uvicorn: no such file or directory

This module is the fleet-wide guard for that class of bug.  It runs the
built image once, cheaply, and fails the job when the container process
cannot even ``exec``.

Two modes
---------
*derived probe* (default)
    With no ``--command``, derive the executable from the image's own
    ``Entrypoint``/``Cmd`` (the first token) and run
    ``docker run --rm --entrypoint <cmd[0]> <image> --help``.  Only an
    *exec failure* (docker exit 125/126/127) fails the job -- a program
    that starts but returns non-zero for ``--help`` still proves the
    image can boot.

*explicit command*
    With ``--command "python -c 'import mypkg'"``, run that command inside
    the container via ``sh -c`` (entrypoint reset).  Here *any* non-zero
    exit fails the job, because the caller chose a meaningful check.

This lives in ``scripts/`` as an importable module (AGENT.md Rule 6) so the
workflow invokes ``python3 scripts/smoke_image.py`` and the unit tests
exercise the exact same logic -- the workflow cannot drift from what is
tested.  It is wired into the shared workflows through the ``docker-smoke``
composite action because a reusable workflow's ``run:`` steps execute in
the CALLER's workspace, where this script does not exist.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Docker exit codes that mean the container process could not be *executed*
# at all (as opposed to running and returning a non-zero status).  These are
# the signature of the class of bug this guard exists to catch:
#   125  docker run itself failed (bad flag, image not found)
#   126  the entrypoint was found but is not executable
#   127  the entrypoint could not be found
#        (`exec /app/.venv/bin/uvicorn: no such file or directory`)
_EXEC_FAILURE_CODES = frozenset({125, 126, 127})


def _config_dict(config: Any) -> dict[str, Any]:
    """Return the dict carrying ``Entrypoint``/``Cmd`` across inspect shapes.

    Tolerant of the several JSON shapes the workflow may feed in (mirrors
    ``render_harden_dockerfile.extract_user``):

    * ``docker inspect --format '{{json .Config}}'`` ->
      ``{"Entrypoint": [...], "Cmd": [...], ...}`` (keys at top level).
    * ``docker buildx imagetools inspect --format '{{json .Image}}'`` ->
      an OCI image config ``{"config": {"Entrypoint": [...]}, ...}``.
    * a per-platform map ``{"linux/amd64": {"config": {...}}, ...}`` (an
      image index / manifest list).

    Anything unrecognised yields ``{}`` so the caller treats the image as
    having no derivable command and skips -- a safe, build-passing default.
    """
    if not isinstance(config, dict):
        return {}
    nested = config.get("config")
    if isinstance(nested, dict) and ("Entrypoint" in nested or "Cmd" in nested):
        return nested
    if "Entrypoint" in config or "Cmd" in config:
        return config
    # Image index / manifest list keyed by platform. Prefer linux/amd64,
    # then fall back to any platform entry that declares a command.
    ordered_keys = ["linux/amd64", *config.keys()]
    for key in ordered_keys:
        value = config.get(key)
        if isinstance(value, dict):
            found = _config_dict(value)
            if found:
                return found
    return {}


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def extract_argv(config: Any) -> list[str]:
    """Return the image's ``Entrypoint + Cmd`` as a flat argv list."""
    section = _config_dict(config)
    return _as_str_list(section.get("Entrypoint")) + _as_str_list(section.get("Cmd"))


def derive_executable(config: Any) -> str:
    """Return the first token of the image's ``Entrypoint``/``Cmd``, or ``""``."""
    argv = extract_argv(config)
    return argv[0].strip() if argv else ""


def build_docker_args(
    image: str, *, executable: str = "", command: str = ""
) -> list[str]:
    """Build the ``docker run`` argv for a smoke test.

    When ``command`` is given it runs inside the container via ``sh -c``
    (entrypoint reset).  Otherwise the derived ``executable`` is exec'd with
    ``--help``.  Raises ``ValueError`` when neither a command nor an
    executable is available.
    """
    ref = (image or "").strip()
    if not ref:
        raise ValueError("image must be a non-empty reference")

    cmd = (command or "").strip()
    if cmd:
        # Reset the entrypoint so the smoke command is interpreted by the
        # shell rather than appended to the image's own entrypoint.
        return ["docker", "run", "--rm", "--entrypoint", "sh", ref, "-c", cmd]

    exe = (executable or "").strip()
    if exe:
        # Default probe: exec the image's own entrypoint/CMD binary with
        # ``--help`` so we only verify the process can start.
        return ["docker", "run", "--rm", "--entrypoint", exe, ref, "--help"]

    raise ValueError(
        "no smoke command: provide --command or an image with an Entrypoint/Cmd"
    )


def should_fail(exit_code: int, *, probe: bool) -> bool:
    """Return True when ``exit_code`` should fail the job.

    For the derived ``--help`` probe, only an exec failure (125/126/127)
    fails -- a program that starts but returns non-zero for ``--help`` still
    proved the image can boot.  For an explicit command, any non-zero exit
    fails.
    """
    if probe:
        return exit_code in _EXEC_FAILURE_CODES
    return exit_code != 0


def _default_runner(args: list[str]) -> int:
    return subprocess.run(args, check=False).returncode


def _load_config(path: str | None) -> Any:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # A malformed inspect output must not crash the smoke step; treat it
        # as "no derivable command" and skip.
        return None


def main(
    argv: list[str] | None = None,
    *,
    runner: Callable[[list[str]], int] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        required=True,
        help="Image reference to smoke-test (tag or name@digest).",
    )
    parser.add_argument(
        "--config",
        default="",
        help="Path to the image config JSON (docker inspect .Config or "
        "buildx imagetools inspect .Image output). Used to derive the "
        "default --help probe. Optional.",
    )
    parser.add_argument(
        "--command",
        default="",
        help="Smoke command run inside the container via `sh -c`. When "
        "omitted, the derived --help probe is used.",
    )
    args = parser.parse_args(argv)

    run_fn = runner or _default_runner
    command = (args.command or "").strip()

    if command:
        probe = False
        docker_args = build_docker_args(args.image, command=command)
    else:
        executable = derive_executable(_load_config(args.config))
        if not executable:
            print(
                "::warning::smoke test skipped: image has no Entrypoint/Cmd to "
                "probe and no smoke command was provided.",
                file=sys.stderr,
            )
            return 0
        probe = True
        docker_args = build_docker_args(args.image, executable=executable)

    printable = " ".join(shlex.quote(a) for a in docker_args)
    print(f"Smoke-testing image: {printable}")

    exit_code = run_fn(docker_args)

    if should_fail(exit_code, probe=probe):
        print(
            f"::error::smoke test failed: `{printable}` exited {exit_code} -- "
            "the image's entrypoint could not be executed.",
            file=sys.stderr,
        )
        return 1

    print(f"Smoke test passed (exit {exit_code}).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
