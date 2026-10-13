"""Tests for scripts/smoke_image.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the smoke_image module
# ---------------------------------------------------------------------------
_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "smoke_image", _scripts_dir / "smoke_image.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

extract_argv = _module.extract_argv
derive_executable = _module.derive_executable
build_docker_args = _module.build_docker_args
should_fail = _module.should_fail
main = _module.main


# ---------------------------------------------------------------------------
# extract_argv / derive_executable unit tests
# ---------------------------------------------------------------------------


class TestExtractArgv:
    def test_docker_inspect_config_shape(self) -> None:
        cfg = {"Entrypoint": ["/app/.venv/bin/uvicorn"], "Cmd": ["--port", "80"]}
        assert extract_argv(cfg) == ["/app/.venv/bin/uvicorn", "--port", "80"]

    def test_oci_image_config_shape(self) -> None:
        cfg = {"config": {"Entrypoint": ["python"], "Cmd": ["-m", "app"]}, "os": "linux"}
        assert extract_argv(cfg) == ["python", "-m", "app"]

    def test_cmd_only(self) -> None:
        assert extract_argv({"Cmd": ["uvicorn", "app:app"]}) == ["uvicorn", "app:app"]

    def test_entrypoint_only(self) -> None:
        assert extract_argv({"config": {"Entrypoint": ["/bin/svc"]}}) == ["/bin/svc"]

    def test_platform_map_prefers_amd64(self) -> None:
        cfg = {
            "linux/arm64": {"config": {"Cmd": ["arm-bin"]}},
            "linux/amd64": {"config": {"Cmd": ["amd-bin"]}},
        }
        assert extract_argv(cfg) == ["amd-bin"]

    def test_platform_map_falls_back_to_any(self) -> None:
        cfg = {"linux/arm64": {"config": {"Cmd": ["arm-bin"]}}}
        assert extract_argv(cfg) == ["arm-bin"]

    def test_none_and_wrong_type(self) -> None:
        assert extract_argv(None) == []
        assert extract_argv("nonsense") == []
        assert extract_argv(["a", "b"]) == []

    def test_missing_entrypoint_and_cmd(self) -> None:
        assert extract_argv({"User": "app"}) == []
        assert extract_argv({"config": {"User": "app"}}) == []

    def test_non_list_values_ignored(self) -> None:
        assert extract_argv({"Entrypoint": "oops", "Cmd": None}) == []


class TestDeriveExecutable:
    def test_first_token_of_entrypoint(self) -> None:
        cfg = {"Entrypoint": ["/app/.venv/bin/uvicorn"], "Cmd": ["--port", "80"]}
        assert derive_executable(cfg) == "/app/.venv/bin/uvicorn"

    def test_first_token_of_cmd_when_no_entrypoint(self) -> None:
        assert derive_executable({"Cmd": ["python", "-m", "app"]}) == "python"

    def test_empty_when_nothing(self) -> None:
        assert derive_executable({}) == ""
        assert derive_executable(None) == ""


# ---------------------------------------------------------------------------
# build_docker_args unit tests
# ---------------------------------------------------------------------------


class TestBuildDockerArgs:
    def test_default_probe_uses_entrypoint_and_help(self) -> None:
        args = build_docker_args("img:tag", executable="uvicorn")
        assert args == [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "uvicorn",
            "img:tag",
            "--help",
        ]

    def test_command_runs_via_sh(self) -> None:
        args = build_docker_args("img:tag", command='python -c "import pkg"')
        assert args == [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "sh",
            "img:tag",
            "-c",
            'python -c "import pkg"',
        ]

    def test_command_takes_precedence_over_executable(self) -> None:
        args = build_docker_args("img:tag", executable="uvicorn", command="true")
        assert "sh" in args and "-c" in args and "true" in args
        assert "--help" not in args

    def test_empty_image_raises(self) -> None:
        for bad in ("", "   "):
            try:
                build_docker_args(bad, executable="x")
            except ValueError:
                pass
            else:  # pragma: no cover
                raise AssertionError("expected ValueError for empty image")

    def test_no_command_and_no_executable_raises(self) -> None:
        try:
            build_docker_args("img:tag")
        except ValueError:
            pass
        else:  # pragma: no cover
            raise AssertionError("expected ValueError when nothing to run")


# ---------------------------------------------------------------------------
# should_fail unit tests
# ---------------------------------------------------------------------------


class TestShouldFail:
    def test_probe_fails_only_on_exec_failure_codes(self) -> None:
        for code in (125, 126, 127):
            assert should_fail(code, probe=True) is True

    def test_probe_tolerates_other_nonzero(self) -> None:
        # e.g. the binary ran but `--help` returned a usage error.
        for code in (0, 1, 2):
            assert should_fail(code, probe=True) is False

    def test_command_fails_on_any_nonzero(self) -> None:
        assert should_fail(0, probe=False) is False
        for code in (1, 2, 127):
            assert should_fail(code, probe=False) is True


# ---------------------------------------------------------------------------
# main() integration tests (with an injected runner — no real docker)
# ---------------------------------------------------------------------------


class _Runner:
    def __init__(self, code: int) -> None:
        self.code = code
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> int:
        self.calls.append(args)
        return self.code


class TestMain:
    def _config_file(self, tmp_path: Path, payload: object) -> str:
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps(payload))
        return str(cfg)

    def test_derived_probe_passes(self, tmp_path: Path) -> None:
        cfg = self._config_file(tmp_path, {"Cmd": ["uvicorn", "app:app"]})
        runner = _Runner(0)
        rc = main(["--image", "img:tag", "--config", cfg], runner=runner)
        assert rc == 0
        assert runner.calls == [
            ["docker", "run", "--rm", "--entrypoint", "uvicorn", "img:tag", "--help"]
        ]

    def test_derived_probe_fails_on_exec_failure(self, tmp_path: Path) -> None:
        cfg = self._config_file(
            tmp_path, {"config": {"Cmd": ["/app/.venv/bin/uvicorn"]}}
        )
        runner = _Runner(127)  # exec: no such file or directory
        rc = main(["--image", "img:tag", "--config", cfg], runner=runner)
        assert rc == 1

    def test_derived_probe_tolerates_usage_error(self, tmp_path: Path) -> None:
        cfg = self._config_file(tmp_path, {"Cmd": ["mytool"]})
        runner = _Runner(2)  # ran, but --help unsupported
        rc = main(["--image", "img:tag", "--config", cfg], runner=runner)
        assert rc == 0

    def test_explicit_command_passes(self, tmp_path: Path) -> None:
        runner = _Runner(0)
        rc = main(
            ["--image", "img:tag", "--command", 'python -c "import pkg"'],
            runner=runner,
        )
        assert rc == 0
        assert runner.calls[0][:5] == ["docker", "run", "--rm", "--entrypoint", "sh"]

    def test_explicit_command_fails_on_nonzero(self, tmp_path: Path) -> None:
        runner = _Runner(1)  # import failed
        rc = main(
            ["--image", "img:tag", "--command", 'python -c "import pkg"'],
            runner=runner,
        )
        assert rc == 1

    def test_skips_when_no_command_and_no_derivable_cmd(self, tmp_path: Path) -> None:
        cfg = self._config_file(tmp_path, {"User": "app"})
        runner = _Runner(0)
        rc = main(["--image", "img:tag", "--config", cfg], runner=runner)
        assert rc == 0
        assert runner.calls == []  # never invoked docker

    def test_skips_when_config_missing(self, tmp_path: Path) -> None:
        runner = _Runner(0)
        rc = main(
            ["--image", "img:tag", "--config", str(tmp_path / "absent.json")],
            runner=runner,
        )
        assert rc == 0
        assert runner.calls == []

    def test_malformed_config_skips(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text("{not valid json")
        runner = _Runner(0)
        rc = main(["--image", "img:tag", "--config", str(cfg)], runner=runner)
        assert rc == 0
        assert runner.calls == []
