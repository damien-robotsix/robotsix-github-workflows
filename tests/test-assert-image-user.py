"""Tests for scripts/assert_image_user.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the assert_image_user module
# ---------------------------------------------------------------------------
_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "assert_image_user", _scripts_dir / "assert_image_user.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

main = _module.main
normalize_user = _module.normalize_user


def _write(path: Path, config: object) -> Path:
    path.write_text(json.dumps(config) if not isinstance(config, str) else config)
    return path


# ---------------------------------------------------------------------------
# normalize_user
# ---------------------------------------------------------------------------


class TestNormalizeUser:
    def test_root_equivalents_canonicalise(self) -> None:
        assert normalize_user("root") == ""
        assert normalize_user("0") == ""
        assert normalize_user("") == ""
        assert normalize_user("  root  ") == ""

    def test_non_root_preserved(self) -> None:
        assert normalize_user("app") == "app"
        assert normalize_user(" 1000 ") == "1000"

    def test_none_preserved(self) -> None:
        assert normalize_user(None) is None


# ---------------------------------------------------------------------------
# main() integration tests
# ---------------------------------------------------------------------------


class TestMain:
    def test_matching_non_root_user_passes(self, tmp_path: Path) -> None:
        base = _write(tmp_path / "base.json", {"config": {"User": "app"}})
        hardened = _write(tmp_path / "hard.json", {"config": {"User": "app"}})
        rc = main(
            ["--base-config", str(base), "--hardened-config", str(hardened)]
        )
        assert rc == 0

    def test_matching_root_variants_pass(self, tmp_path: Path) -> None:
        # Base empty-root vs hardened "root" are equivalent.
        base = _write(tmp_path / "base.json", {"config": {"User": ""}})
        hardened = _write(tmp_path / "hard.json", {"config": {"User": "root"}})
        rc = main(
            ["--base-config", str(base), "--hardened-config", str(hardened)]
        )
        assert rc == 0

    def test_mismatch_fails(self, tmp_path: Path, capsys) -> None:
        # Hardened lost the restore line and runs as root; base ran as app.
        base = _write(tmp_path / "base.json", {"config": {"User": "app"}})
        hardened = _write(tmp_path / "hard.json", {"config": {"User": "root"}})
        rc = main(
            ["--base-config", str(base), "--hardened-config", str(hardened)]
        )
        assert rc == 1
        assert "does not match" in capsys.readouterr().err

    def test_unknown_base_user_fails(self, tmp_path: Path) -> None:
        base = _write(tmp_path / "base.json", "{not valid json")
        hardened = _write(tmp_path / "hard.json", {"config": {"User": "app"}})
        rc = main(
            ["--base-config", str(base), "--hardened-config", str(hardened)]
        )
        assert rc == 2

    def test_unknown_hardened_user_fails(self, tmp_path: Path) -> None:
        base = _write(tmp_path / "base.json", {"config": {"User": "app"}})
        hardened = _write(tmp_path / "hard.json", {"config": {}})
        rc = main(
            ["--base-config", str(base), "--hardened-config", str(hardened)]
        )
        assert rc == 2
