"""Unit and integration tests for scripts/pin-bump.py."""

from __future__ import annotations

import importlib.util
import subprocess
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the pin-bump module (filename contains a hyphen — can't use plain import)
# ---------------------------------------------------------------------------
_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "pin_bump", _scripts_dir / "pin-bump.py"
)
assert _spec is not None and _spec.loader is not None
_pin_bump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pin_bump)

# Convenience aliases
parse_git_sources = _pin_bump.parse_git_sources
rewrite_revs = _pin_bump.rewrite_revs
resolve_default_branch_head = _pin_bump.resolve_default_branch_head
per_repo = _pin_bump.per_repo

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_pyproject(tmp_path: Path) -> Path:
    """Return a temporary directory that we'll write pyproject.toml into."""
    return tmp_path / "pyproject.toml"


def _write_toml(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip())


def _create_bare_repo(tmp_path: Path) -> tuple[Path, str]:
    """Create a bare git repo with one commit on its default branch.

    Returns (path_to_bare_repo, head_sha).
    """
    repo_dir = tmp_path / "dep.git"
    repo_dir.mkdir()
    subprocess.run(
        ["git", "-C", str(repo_dir), "init", "--bare"],
        check=True, capture_output=True,
    )
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    subprocess.run(
        ["git", "-C", str(work_dir), "init"], check=True, capture_output=True
    )
    # Detect the default branch name
    branch = subprocess.run(
        ["git", "-C", str(work_dir), "branch", "--show-current"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    (work_dir / "README.md").write_text("# test")
    subprocess.run(
        ["git", "-C", str(work_dir), "config", "user.email", "test@test.test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(work_dir), "config", "user.name", "Test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(work_dir), "add", "README.md"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work_dir), "commit", "-m", "init"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work_dir), "remote", "add", "origin", str(repo_dir)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work_dir), "push", "origin", branch],
        check=True, capture_output=True,
    )
    head = resolve_default_branch_head(f"file://{repo_dir}")
    return repo_dir, head


# ---------------------------------------------------------------------------
# parse_git_sources
# ---------------------------------------------------------------------------


class TestParseGitSources:
    def test_empty_sources(self, tmp_pyproject: Path) -> None:
        """TOML without [tool.uv.sources] returns empty dict."""
        _write_toml(
            tmp_pyproject,
            """
            [project]
            name = "test"
            """,
        )
        assert parse_git_sources(tmp_pyproject) == {}

    def test_git_source_with_rev(self, tmp_pyproject: Path) -> None:
        """Valid git source with 40-char rev is included."""
        sha = "a" * 40
        _write_toml(
            tmp_pyproject,
            f"""
            [tool.uv.sources]
            mypkg = {{ git = "https://github.com/org/mypkg.git", rev = "{sha}" }}
            """,
        )
        result = parse_git_sources(tmp_pyproject)
        assert result == {"mypkg": {"git": "https://github.com/org/mypkg.git", "rev": sha}}

    def test_git_source_without_rev_skipped(self, tmp_pyproject: Path) -> None:
        """Git source without rev is skipped."""
        _write_toml(
            tmp_pyproject,
            """
            [tool.uv.sources]
            mypkg = { git = "https://github.com/org/mypkg.git" }
            """,
        )
        assert parse_git_sources(tmp_pyproject) == {}

    def test_git_source_with_short_rev_skipped(self, tmp_pyproject: Path) -> None:
        """Git source with a non-40-char rev is skipped (tag, branch, short sha)."""
        _write_toml(
            tmp_pyproject,
            """
            [tool.uv.sources]
            mypkg = { git = "https://github.com/org/mypkg.git", rev = "v1.0" }
            """,
        )
        assert parse_git_sources(tmp_pyproject) == {}

    def test_non_git_sources_skipped(self, tmp_pyproject: Path) -> None:
        """Non-git sources (e.g. path) are skipped."""
        _write_toml(
            tmp_pyproject,
            """
            [tool.uv.sources]
            mypkg = { path = "../mypkg", editable = true }
            otherpkg = "https://example.com/otherpkg"
            """,
        )
        assert parse_git_sources(tmp_pyproject) == {}

    def test_multiple_git_sources(self, tmp_pyproject: Path) -> None:
        """Multiple git sources are all parsed."""
        sha_a, sha_b, sha_c = "a" * 40, "b" * 40, "c" * 40
        _write_toml(
            tmp_pyproject,
            f"""
            [tool.uv.sources]
            alpha = {{ git = "https://github.com/org/alpha.git", rev = "{sha_a}" }}
            beta  = {{ git = "https://github.com/org/beta.git",  rev = "{sha_b}" }}
            gamma = {{ git = "https://github.com/org/gamma.git", rev = "{sha_c}" }}
            """,
        )
        result = parse_git_sources(tmp_pyproject)
        assert len(result) == 3
        assert result["alpha"]["git"] == "https://github.com/org/alpha.git"
        assert result["beta"]["git"] == "https://github.com/org/beta.git"
        assert result["gamma"]["git"] == "https://github.com/org/gamma.git"

    def test_mixed_sources(self, tmp_pyproject: Path) -> None:
        """Only git sources with 40-char revs are included; others skipped."""
        sha_d = "d" * 40
        _write_toml(
            tmp_pyproject,
            f"""
            [tool.uv.sources]
            pinned   = {{ git = "https://github.com/org/pinned.git",   rev = "{sha_d}" }}
            unpinned = {{ git = "https://github.com/org/unpinned.git" }}
            tagged   = {{ git = "https://github.com/org/tagged.git",   rev = "v2" }}
            pathdep  = {{ path = "../local" }}
            """,
        )
        result = parse_git_sources(tmp_pyproject)
        assert list(result.keys()) == ["pinned"]
        assert result["pinned"]["rev"] == sha_d


# ---------------------------------------------------------------------------
# rewrite_revs
# ---------------------------------------------------------------------------


class TestRewriteRevs:
    def test_single_bump(self, tmp_pyproject: Path) -> None:
        """A single package rev is updated."""
        old_sha = "0" * 40
        new_sha = "f" * 40
        _write_toml(
            tmp_pyproject,
            f"""
            [tool.uv.sources]
            mypkg = {{ git = "https://github.com/org/mypkg.git", rev = "{old_sha}" }}
            """,
        )
        rewrite_revs(tmp_pyproject, {"mypkg": new_sha})
        result = parse_git_sources(tmp_pyproject)
        assert result["mypkg"]["rev"] == new_sha

    def test_multiple_bumps(self, tmp_pyproject: Path) -> None:
        """Multiple packages are all updated."""
        _write_toml(
            tmp_pyproject,
            f"""
            [tool.uv.sources]
            alpha = {{ git = "https://github.com/org/a.git", rev = "{"a"*40}" }}
            beta  = {{ git = "https://github.com/org/b.git", rev = "{"b"*40}" }}
            """,
        )
        rewrite_revs(tmp_pyproject, {"alpha": "f" * 40, "beta": "e" * 40})
        result = parse_git_sources(tmp_pyproject)
        assert result["alpha"]["rev"] == "f" * 40
        assert result["beta"]["rev"] == "e" * 40

    def test_only_matches_inline_table_format(self, tmp_pyproject: Path) -> None:
        """Only revs in inline-table format under [tool.uv.sources] are matched."""
        old_sha = "0" * 40
        new_sha = "f" * 40
        _write_toml(
            tmp_pyproject,
            f"""
            [tool.uv.sources]
            mypkg = {{ git = "https://github.com/org/mypkg.git", rev = "{old_sha}" }}

            # This is a different TOML section — should NOT be matched
            [other]
            mypkg = {{ git = "https://evil.com/mypkg.git", rev = "{old_sha}" }}
            """,
        )
        rewrite_revs(tmp_pyproject, {"mypkg": new_sha})
        text = tmp_pyproject.read_text()
        # The first occurrence (in [tool.uv.sources]) should be updated
        assert new_sha in text
        # The second occurrence (in [other]) should still have the old SHA
        assert text.count(new_sha) == 1

    def test_preserves_surrounding_content(self, tmp_pyproject: Path) -> None:
        """Non-rev content around the source line is preserved."""
        old_sha = "0" * 40
        new_sha = "f" * 40
        _write_toml(
            tmp_pyproject,
            f"""
            [project]
            name = "test"
            version = "1.0"

            [tool.uv.sources]
            mypkg = {{ git = "https://github.com/org/mypkg.git", rev = "{old_sha}", subdirectory = "pkg" }}
            """,
        )
        rewrite_revs(tmp_pyproject, {"mypkg": new_sha})
        text = tmp_pyproject.read_text()
        assert '[project]' in text
        assert 'name = "test"' in text
        assert 'subdirectory = "pkg"' in text
        assert new_sha in text

    def test_no_match_does_not_crash(self, tmp_pyproject: Path, capsys) -> None:
        """When a package is not found, a warning is printed but no crash."""
        _write_toml(
            tmp_pyproject,
            """
            [tool.uv.sources]
            mypkg = { git = "https://github.com/org/mypkg.git", rev = "0000000000000000000000000000000000000000" }
            """,
        )
        rewrite_revs(tmp_pyproject, {"nonexistent": "f" * 40})
        captured = capsys.readouterr()
        assert "Could not locate rev for nonexistent" in captured.err
        # Original file should remain unchanged (mypkg still has old SHA)
        assert "0000000000000000000000000000000000000000" in tmp_pyproject.read_text()


# ---------------------------------------------------------------------------
# resolve_default_branch_head
# ---------------------------------------------------------------------------


class TestResolveDefaultBranchHead:
    def test_resolves_head_of_local_repo(self, tmp_path: Path) -> None:
        """Create a local bare repo and verify HEAD is resolved."""
        _repo_dir, head = _create_bare_repo(tmp_path)
        assert len(head) == 40
        assert all(c in "0123456789abcdef" for c in head)

    def test_invalid_url_raises(self) -> None:
        """A bogus URL causes a subprocess error (git ls-remote fails)."""
        with pytest.raises(subprocess.CalledProcessError):
            resolve_default_branch_head("https://invalid.example/nonexistent.git")


# ---------------------------------------------------------------------------
# Integration: per_repo
# ---------------------------------------------------------------------------


class TestPerRepoIntegration:
    def test_no_git_sources_returns_zero(self, tmp_path: Path) -> None:
        """per_repo on a pyproject.toml with no git sources returns 0."""
        pyproject = tmp_path / "pyproject.toml"
        _write_toml(
            pyproject,
            """
            [project]
            name = "test"
            """,
        )
        exit_code = per_repo(pyproject)
        assert exit_code == 0

    def test_per_repo_with_local_dep(self, tmp_path: Path, monkeypatch) -> None:
        """End-to-end: create a local git dep, pin it, bump it.

        Creates a bare repo as the "dependency", writes a pyproject.toml
        that references it as a git source with a stale rev, then runs
        per_repo and verifies the rev is bumped and exit code is 2.
        """
        # 1. Create bare repo and get its first HEAD
        dep_bare, first_head = _create_bare_repo(tmp_path)

        # 2. Create a second commit (will become the "latest")
        work_dir = tmp_path / "work"
        branch = subprocess.run(
            ["git", "-C", str(work_dir), "branch", "--show-current"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        (work_dir / "README.md").write_text("# dep v2")
        subprocess.run(
            ["git", "-C", str(work_dir), "add", "README.md"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(work_dir), "commit", "-m", "v2"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(work_dir), "push", "origin", branch],
            check=True, capture_output=True,
        )
        latest_head = resolve_default_branch_head(f"file://{dep_bare}")
        assert first_head != latest_head

        # 3. Write a pyproject.toml with a stale pin (first_head)
        pyproject = tmp_path / "pyproject.toml"
        _write_toml(
            pyproject,
            f"""
            [project]
            name = "consumer"
            version = "0.1.0"
            requires-python = ">=3.11"

            [tool.uv.sources]
            mydep = {{ git = "file://{dep_bare}", rev = "{first_head}" }}
            """,
        )

        # 4. Monkeypatch run() to skip "uv lock"
        original_run = _pin_bump.run

        def fake_run(
            *args: str, **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if args and args[0] == "uv":
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="", stderr=""
                )
            return original_run(*args, **kwargs)

        monkeypatch.setattr(_pin_bump, "run", fake_run)

        # 5. Run per_repo — should detect the bump and return 2
        exit_code = per_repo(pyproject)
        assert exit_code == 2

        # 6. Verify the pyproject.toml was rewritten with the latest SHA
        updated_sources = parse_git_sources(pyproject)
        assert updated_sources["mydep"]["rev"] == latest_head

    def test_per_repo_current_pins_returns_zero(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """per_repo on a pyproject.toml where all pins are current returns 0."""
        dep_bare, head = _create_bare_repo(tmp_path)

        pyproject = tmp_path / "pyproject.toml"
        _write_toml(
            pyproject,
            f"""
            [project]
            name = "consumer"
            version = "0.1.0"
            requires-python = ">=3.11"

            [tool.uv.sources]
            mydep = {{ git = "file://{dep_bare}", rev = "{head}" }}
            """,
        )

        # Monkeypatch run() to skip uv lock
        original_run = _pin_bump.run

        def fake_run(
            *args: str, **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if args and args[0] == "uv":
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="", stderr=""
                )
            return original_run(*args, **kwargs)

        monkeypatch.setattr(_pin_bump, "run", fake_run)

        exit_code = per_repo(pyproject)
        assert exit_code == 0
