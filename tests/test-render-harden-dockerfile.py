"""Tests for scripts/render_harden_dockerfile.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the render_harden_dockerfile module
# ---------------------------------------------------------------------------
_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "render_harden_dockerfile", _scripts_dir / "render_harden_dockerfile.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

extract_user = _module.extract_user
render = _module.render
main = _module.main


# ---------------------------------------------------------------------------
# extract_user unit tests
# ---------------------------------------------------------------------------


class TestExtractUser:
    def test_docker_inspect_config_shape(self) -> None:
        assert extract_user({"User": "app", "Entrypoint": ["/bin/x"]}) == "app"

    def test_oci_image_config_shape(self) -> None:
        assert extract_user({"config": {"User": "1000"}, "os": "linux"}) == "1000"

    def test_empty_user_is_root(self) -> None:
        assert extract_user({"User": ""}) == ""
        assert extract_user({"config": {"User": ""}}) == ""

    def test_missing_user_is_unknown(self) -> None:
        # No ``User`` key anywhere => undeterminable, NOT a silent root default.
        # OCI config without the optional User key = root (BuildKit omits it).
        assert extract_user({"config": {}}) == ""
        assert (
            extract_user(
                {
                    "created": "2026-10-21T12:50:00Z",
                    "architecture": "amd64",
                    "os": "linux",
                    "config": {
                        "Entrypoint": ["/usr/bin/tini", "-s", "--", "/app/entrypoint.sh"],
                        "Env": ["PATH=/usr/local/bin"],
                        "ExposedPorts": {"8077/tcp": {}},
                        "WorkingDir": "/app",
                    },
                    "rootfs": {"type": "layers", "diff_ids": []},
                }
            )
            == ""
        )
        assert extract_user({"Entrypoint": ["/bin/x"]}) is None

    def test_none_and_wrong_type_are_unknown(self) -> None:
        assert extract_user(None) is None
        assert extract_user("nonsense") is None
        assert extract_user(["a", "b"]) is None

    def test_platform_map_prefers_amd64(self) -> None:
        cfg = {
            "linux/arm64": {"config": {"User": "arm-user"}},
            "linux/amd64": {"config": {"User": "amd-user"}},
        }
        assert extract_user(cfg) == "amd-user"

    def test_platform_map_falls_back_to_any(self) -> None:
        cfg = {"linux/arm64": {"config": {"User": "arm-user"}}}
        assert extract_user(cfg) == "arm-user"

    def test_whitespace_is_stripped(self) -> None:
        assert extract_user({"User": "  app  "}) == "app"


# ---------------------------------------------------------------------------
# render unit tests
# ---------------------------------------------------------------------------


class TestRender:
    def test_contains_from_and_root_and_upgrade(self) -> None:
        out = render("ghcr.io/o/r@sha256:abc", "")
        assert "FROM ghcr.io/o/r@sha256:abc" in out
        assert "USER root" in out
        assert "apt-get" in out and "upgrade" in out
        assert out.endswith("\n")

    def test_root_user_has_no_trailing_user_line(self) -> None:
        for user in ("", "root", "0"):
            out = render("base:tag", user)
            # Only the single "USER root" line, no restore line.
            assert out.count("USER ") == 1
            assert "USER root" in out

    def test_non_root_user_is_restored_last(self) -> None:
        out = render("base:tag", "appuser")
        lines = [ln for ln in out.splitlines() if ln.startswith("USER ")]
        assert lines[0] == "USER root"
        assert lines[-1] == "USER appuser"

    def test_no_apt_omits_upgrade(self) -> None:
        out = render("base:tag", "appuser", apt=False)
        assert "apt-get" not in out
        # USER restore still present.
        assert "USER appuser" in out

    def test_strips_pip_by_default_before_user_restore(self) -> None:
        out = render("base:tag", "appuser")
        assert "-m pip --version" in out
        assert "-m pip uninstall -y pip" in out
        # Conditional: guarded on a python3 interpreter that has pip.
        assert "command -v python3" in out
        assert "/usr/local/bin/python3" in out
        # Runs as root, before the original USER is restored.
        assert out.index("pip uninstall") < out.index("USER appuser")
        assert out.index("apt-get") < out.index("pip uninstall")

    def test_strip_pip_false_omits_pip_layer(self) -> None:
        out = render("base:tag", "appuser", strip_pip=False)
        assert "pip" not in out
        assert "apt-get" in out
        assert "USER appuser" in out

    def test_pip_strip_run_is_valid_shell(self, tmp_path: Path) -> None:
        import subprocess

        body = _module._PIP_STRIP_RUN.removeprefix("RUN ").replace("\\\n", "\n")
        script = tmp_path / "strip.sh"
        script.write_text(body + "\n")
        subprocess.run(["sh", "-n", str(script)], check=True)

    def test_empty_base_ref_raises(self) -> None:
        for bad in ("", "   "):
            try:
                render(bad, "")
            except ValueError:
                pass
            else:  # pragma: no cover
                raise AssertionError("expected ValueError for empty base_ref")


# ---------------------------------------------------------------------------
# main() / CLI integration tests
# ---------------------------------------------------------------------------


class TestMain:
    def test_writes_out_file_with_config(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"config": {"User": "svc"}}))
        out = tmp_path / "Dockerfile"
        rc = main(
            [
                "--base-ref",
                "ghcr.io/o/r@sha256:deadbeef",
                "--config",
                str(cfg),
                "--out",
                str(out),
            ]
        )
        assert rc == 0
        text = out.read_text()
        assert "FROM ghcr.io/o/r@sha256:deadbeef" in text
        assert text.rstrip().endswith("USER svc")
        assert "pip uninstall" in text

    def test_no_strip_pip_flag(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"config": {"User": "svc"}}))
        out = tmp_path / "Dockerfile"
        rc = main(
            [
                "--base-ref",
                "base:tag",
                "--config",
                str(cfg),
                "--out",
                str(out),
                "--no-strip-pip",
            ]
        )
        assert rc == 0
        assert "pip" not in out.read_text()

    def test_non_root_base_restores_user(self, tmp_path: Path) -> None:
        # A base that genuinely runs as a non-root user => USER line emitted.
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"config": {"User": "app"}}))
        out = tmp_path / "Dockerfile"
        rc = main(
            ["--base-ref", "base:tag", "--config", str(cfg), "--out", str(out)]
        )
        assert rc == 0
        assert out.read_text().rstrip().endswith("USER app")

    def test_genuine_root_base_has_no_restore_line(self, tmp_path: Path) -> None:
        # ``User`` present but root => no restore line, and NO failure.
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"config": {"User": "root"}}))
        out = tmp_path / "Dockerfile"
        rc = main(
            ["--base-ref", "base:tag", "--config", str(cfg), "--out", str(out)]
        )
        assert rc == 0
        assert out.read_text().count("USER ") == 1  # only the hardening root

    def test_unparseable_config_fails_loud(self, tmp_path: Path, capsys) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text("{not valid json")
        out = tmp_path / "Dockerfile"
        rc = main(
            ["--base-ref", "base:tag", "--config", str(cfg), "--out", str(out)]
        )
        assert rc != 0  # no silent rootful Dockerfile
        assert not out.exists()
        assert "could not determine" in capsys.readouterr().err

    def test_empty_config_fails_loud(self, tmp_path: Path, capsys) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text("   ")
        out = tmp_path / "Dockerfile"
        rc = main(
            ["--base-ref", "base:tag", "--config", str(cfg), "--out", str(out)]
        )
        assert rc != 0
        assert not out.exists()

    def test_config_without_user_fails_loud(self, tmp_path: Path) -> None:
        # A docker-inspect (top-level) shape with no User is undeterminable;
        # an OCI ``config`` object without User is root, see
        # TestExtractUser.test_missing_user_is_unknown.
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"Entrypoint": ["/bin/x"]}))
        out = tmp_path / "Dockerfile"
        rc = main(
            ["--base-ref", "base:tag", "--config", str(cfg), "--out", str(out)]
        )
        assert rc != 0
        assert not out.exists()

    def test_missing_config_fails_loud(self) -> None:
        # No --config at all is "user unknown" too: fail rather than root.
        assert main(["--base-ref", "base:tag"]) != 0

    def test_allow_unknown_user_opts_in_to_root(
        self, tmp_path: Path
    ) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text("{not valid json")
        out = tmp_path / "Dockerfile"
        rc = main(
            [
                "--base-ref",
                "base:tag",
                "--config",
                str(cfg),
                "--out",
                str(out),
                "--allow-unknown-user",
            ]
        )
        assert rc == 0
        assert out.read_text().count("USER ") == 1  # explicit root opt-in
