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

    def test_missing_user(self) -> None:
        assert extract_user({"config": {}}) == ""
        assert extract_user({"Entrypoint": ["/bin/x"]}) == ""

    def test_none_and_wrong_type(self) -> None:
        assert extract_user(None) == ""
        assert extract_user("nonsense") == ""
        assert extract_user(["a", "b"]) == ""

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

    def test_malformed_config_defaults_to_root(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text("{not valid json")
        out = tmp_path / "Dockerfile"
        rc = main(
            ["--base-ref", "base:tag", "--config", str(cfg), "--out", str(out)]
        )
        assert rc == 0
        text = out.read_text()
        assert text.count("USER ") == 1  # stays root, no restore line

    def test_missing_config_is_ok(self, tmp_path: Path, capsys) -> None:
        rc = main(["--base-ref", "base:tag"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "FROM base:tag" in captured.out
