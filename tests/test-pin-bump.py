"""Unit and integration tests for scripts/pin-bump.py."""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the pin-bump module (filename contains a hyphen — can't use plain import)
# ---------------------------------------------------------------------------
_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location("pin_bump", _scripts_dir / "pin-bump.py")
assert _spec is not None and _spec.loader is not None
_pin_bump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pin_bump)

# Convenience aliases
parse_git_sources = _pin_bump.parse_git_sources
rewrite_revs = _pin_bump.rewrite_revs
resolve_default_branch_head = _pin_bump.resolve_default_branch_head
per_repo = _pin_bump.per_repo
_collect_fleet_pins = _pin_bump._collect_fleet_pins
_resolve_latest_shas = _pin_bump._resolve_latest_shas
_compute_repo_bumps = _pin_bump._compute_repo_bumps
_apply_pin_bump = _pin_bump._apply_pin_bump
_normalize_git_url = _pin_bump._normalize_git_url
_build_first_party_graph = _pin_bump._build_first_party_graph
_topological_sort = _pin_bump._topological_sort
_get_fleet_dep_bumps = _pin_bump._get_fleet_dep_bumps
sweep = _pin_bump.sweep

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
        check=True,
        capture_output=True,
    )
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    subprocess.run(
        ["git", "-C", str(work_dir), "init"], check=True, capture_output=True
    )
    # Detect the default branch name
    branch = subprocess.run(
        ["git", "-C", str(work_dir), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
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
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work_dir), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work_dir), "remote", "add", "origin", str(repo_dir)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work_dir), "push", "origin", branch],
        check=True,
        capture_output=True,
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
        assert result == {
            "mypkg": {"git": "https://github.com/org/mypkg.git", "rev": sha}
        }

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
            alpha = {{ git = "https://github.com/org/a.git", rev = "{"a" * 40}" }}
            beta  = {{ git = "https://github.com/org/b.git", rev = "{"b" * 40}" }}
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
        assert "[project]" in text
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
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        (work_dir / "README.md").write_text("# dep v2")
        subprocess.run(
            ["git", "-C", str(work_dir), "add", "README.md"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(work_dir), "commit", "-m", "v2"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(work_dir), "push", "origin", branch],
            check=True,
            capture_output=True,
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

        def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
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

        def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args and args[0] == "uv":
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="", stderr=""
                )
            return original_run(*args, **kwargs)

        monkeypatch.setattr(_pin_bump, "run", fake_run)

        exit_code = per_repo(pyproject)
        assert exit_code == 0


# ---------------------------------------------------------------------------
# _compute_repo_bumps
# ---------------------------------------------------------------------------


class TestComputeRepoBumps:
    """Unit tests for the pure helper _compute_repo_bumps."""

    def test_empty_dep_map(self) -> None:
        """Empty dep_map produces empty repo_bumps."""
        assert _compute_repo_bumps({}, {}) == {}

    def test_all_current(self) -> None:
        """When all revs match latest, result is empty."""
        sha = "a" * 40
        dep_map = {"https://example.com/dep.git": [("repo1", "pkg1", sha)]}
        latest_map = {"https://example.com/dep.git": sha}
        assert _compute_repo_bumps(dep_map, latest_map) == {}

    def test_some_stale(self) -> None:
        """Stale pins appear in the result; current ones do not."""
        old = "0" * 40
        new = "f" * 40
        dep_map = {
            "https://example.com/dep.git": [
                ("repo1", "pkg1", old),
                ("repo2", "pkg1", new),
            ]
        }
        latest_map = {"https://example.com/dep.git": new}
        result = _compute_repo_bumps(dep_map, latest_map)
        assert result == {"repo1": [("pkg1", new)]}

    def test_multiple_git_urls(self) -> None:
        """Each git URL is resolved independently."""
        old_a, new_a = "0" * 40, "f" * 40
        old_b, new_b = "1" * 40, "e" * 40
        dep_map = {
            "https://a.git": [("repo1", "alpha", old_a)],
            "https://b.git": [("repo2", "beta", old_b)],
        }
        latest_map = {"https://a.git": new_a, "https://b.git": new_b}
        result = _compute_repo_bumps(dep_map, latest_map)
        assert result == {"repo1": [("alpha", new_a)], "repo2": [("beta", new_b)]}

    def test_multiple_repos_same_git_url(self) -> None:
        """Multiple repos pinned to the same git URL all get the same new SHA."""
        old = "0" * 40
        new = "f" * 40
        dep_map = {
            "https://example.com/dep.git": [
                ("repo1", "pkg1", old),
                ("repo2", "pkg1", old),
                ("repo3", "pkg1", old),
            ]
        }
        latest_map = {"https://example.com/dep.git": new}
        result = _compute_repo_bumps(dep_map, latest_map)
        assert result == {
            "repo1": [("pkg1", new)],
            "repo2": [("pkg1", new)],
            "repo3": [("pkg1", new)],
        }

    def test_mixed_current_and_stale_across_repos(self) -> None:
        """Some repos are current, others stale — only stale appear."""
        old = "0" * 40
        new = "f" * 40
        dep_map = {
            "https://example.com/dep.git": [
                ("repo1", "pkg1", old),
                ("repo2", "pkg1", new),
                ("repo3", "pkg1", old),
            ]
        }
        latest_map = {"https://example.com/dep.git": new}
        result = _compute_repo_bumps(dep_map, latest_map)
        assert result == {"repo1": [("pkg1", new)], "repo3": [("pkg1", new)]}
        assert "repo2" not in result


# ---------------------------------------------------------------------------
# _resolve_latest_shas
# ---------------------------------------------------------------------------


class TestResolveLatestShas:
    """Tests for _resolve_latest_shas."""

    def test_resolves_each_unique_url_once(self, monkeypatch, capsys) -> None:
        """Each unique git URL is resolved exactly once via
        resolve_default_branch_head."""
        sha_a = "a" * 40
        sha_b = "b" * 40

        calls: list[str] = []

        def fake_resolve(url: str) -> str:
            calls.append(url)
            return sha_a if "a.git" in url else sha_b

        monkeypatch.setattr(_pin_bump, "resolve_default_branch_head", fake_resolve)

        dep_map = {
            "https://example.com/a.git": [
                ("repo1", "alpha", "0" * 40),
                ("repo2", "alpha", "1" * 40),
            ],
            "https://example.com/b.git": [("repo3", "beta", "2" * 40)],
        }
        latest_map, unresolved = _resolve_latest_shas(dep_map)

        assert len(calls) == 2
        assert "https://example.com/a.git" in calls
        assert "https://example.com/b.git" in calls
        assert latest_map == {
            "https://example.com/a.git": sha_a,
            "https://example.com/b.git": sha_b,
        }
        assert unresolved == []


# ---------------------------------------------------------------------------
# _collect_fleet_pins
# ---------------------------------------------------------------------------


class TestCollectFleetPins:
    """Tests for _collect_fleet_pins."""

    def test_no_repos(self, monkeypatch) -> None:
        """When gh repo list returns no repos, dep_map is empty."""

        def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[:3] == ("gh", "repo", "list"):
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="[]", stderr=""
                )
            return subprocess.run(args, text=True, check=True, **kwargs)  # type: ignore[call-overload,no-any-return]

        monkeypatch.setattr(_pin_bump, "run", fake_run)
        dep_map, skipped, _all_repos = _collect_fleet_pins(
            "test-org", {"GH_TOKEN": "fake"}
        )
        assert dep_map == {}

    def test_repo_without_pyproject(self, monkeypatch) -> None:
        """Repos without pyproject.toml are silently skipped."""

        def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[:3] == ("gh", "repo", "list"):
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout=json.dumps([{"name": "no-pyproject"}]),
                    stderr="",
                )
            return subprocess.run(args, text=True, check=True, **kwargs)  # type: ignore[call-overload,no-any-return]

        def fake_gh(*args: str, **kwargs: object) -> str:
            raise subprocess.CalledProcessError(1, ("gh",) + args)

        monkeypatch.setattr(_pin_bump, "run", fake_run)
        monkeypatch.setattr(_pin_bump, "gh", fake_gh)
        dep_map, skipped, _all_repos = _collect_fleet_pins(
            "test-org", {"GH_TOKEN": "fake"}
        )
        assert dep_map == {}

    def test_repo_with_git_pins(self, monkeypatch) -> None:
        """Git-sourced pins with 40-char revs are collected."""

        sha = "d" * 40
        toml_content = textwrap.dedent(f"""
            [tool.uv.sources]
            mypkg = {{ git = "https://github.com/org/dep.git", rev = "{sha}" }}
        """).lstrip()

        def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[:3] == ("gh", "repo", "list"):
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout=json.dumps([{"name": "myrepo"}]),
                    stderr="",
                )
            return subprocess.run(args, text=True, check=True, **kwargs)  # type: ignore[call-overload,no-any-return]

        def fake_gh(*args: str, **kwargs: object) -> str:
            return base64.b64encode(toml_content.encode()).decode()

        monkeypatch.setattr(_pin_bump, "run", fake_run)
        monkeypatch.setattr(_pin_bump, "gh", fake_gh)
        dep_map, skipped, _all_repos = _collect_fleet_pins(
            "test-org", {"GH_TOKEN": "fake"}
        )

        expected_key = "https://github.com/org/dep.git"
        assert expected_key in dep_map
        assert dep_map[expected_key] == [("myrepo", "mypkg", sha)]

    def test_short_rev_skipped(self, monkeypatch) -> None:
        """Sources with a non-40-char rev (tag/branch) are skipped."""

        toml_content = textwrap.dedent("""
            [tool.uv.sources]
            mypkg = { git = "https://github.com/org/dep.git", rev = "main" }
        """).lstrip()

        def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[:3] == ("gh", "repo", "list"):
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout=json.dumps([{"name": "myrepo"}]),
                    stderr="",
                )
            return subprocess.run(args, text=True, check=True, **kwargs)  # type: ignore[call-overload,no-any-return]

        def fake_gh(*args: str, **kwargs: object) -> str:
            return base64.b64encode(toml_content.encode()).decode()

        monkeypatch.setattr(_pin_bump, "run", fake_run)
        monkeypatch.setattr(_pin_bump, "gh", fake_gh)
        dep_map, skipped, _all_repos = _collect_fleet_pins(
            "test-org", {"GH_TOKEN": "fake"}
        )
        assert dep_map == {}

    def test_multiple_repos(self, monkeypatch) -> None:
        """Multiple repos are all enumerated."""
        sha_a, sha_b = "a" * 40, "b" * 40

        # We need different TOML per repo — track which repo is being fetched
        repo_tomls = {
            "repo1": textwrap.dedent(f"""
                [tool.uv.sources]
                alpha = {{ git = "https://github.com/org/dep.git", rev = "{sha_a}" }}
            """).lstrip(),
            "repo2": textwrap.dedent(f"""
                [tool.uv.sources]
                beta = {{ git = "https://github.com/org/dep.git", rev = "{sha_b}" }}
            """).lstrip(),
        }
        fetch_order: list[str] = []

        def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[:3] == ("gh", "repo", "list"):
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout=json.dumps([{"name": "repo1"}, {"name": "repo2"}]),
                    stderr="",
                )
            return subprocess.run(args, text=True, check=True, **kwargs)  # type: ignore[call-overload,no-any-return]

        def fake_gh(*args: str, **kwargs: object) -> str:
            # args[1] = "repos/<owner>/<repo>/contents/pyproject.toml"
            repo = args[1].split("/")[2]
            fetch_order.append(repo)
            return base64.b64encode(repo_tomls[repo].encode()).decode()

        monkeypatch.setattr(_pin_bump, "run", fake_run)
        monkeypatch.setattr(_pin_bump, "gh", fake_gh)
        dep_map, skipped, _all_repos = _collect_fleet_pins(
            "test-org", {"GH_TOKEN": "fake"}
        )

        assert len(fetch_order) == 2
        key = "https://github.com/org/dep.git"
        assert key in dep_map
        # Two pins collected across two repos
        assert len(dep_map[key]) == 2
        assert ("repo1", "alpha", sha_a) in dep_map[key]
        assert ("repo2", "beta", sha_b) in dep_map[key]


# ---------------------------------------------------------------------------
# _normalize_git_url
# ---------------------------------------------------------------------------


class TestNormalizeGitUrl:
    """Tests for _normalize_git_url."""

    def test_ssh_url(self) -> None:
        assert (
            _normalize_git_url("git@github.com:org/repo.git")
            == "https://github.com/org/repo"
        )

    def test_https_with_git_suffix(self) -> None:
        assert (
            _normalize_git_url("https://github.com/org/repo.git")
            == "https://github.com/org/repo"
        )

    def test_https_without_git_suffix(self) -> None:
        assert (
            _normalize_git_url("https://github.com/org/repo")
            == "https://github.com/org/repo"
        )

    def test_trailing_slash(self) -> None:
        assert (
            _normalize_git_url("https://github.com/org/repo/")
            == "https://github.com/org/repo"
        )

    def test_ssh_without_git_suffix(self) -> None:
        assert (
            _normalize_git_url("git@github.com:org/repo")
            == "https://github.com/org/repo"
        )


# ---------------------------------------------------------------------------
# _build_first_party_graph
# ---------------------------------------------------------------------------


class TestBuildFirstPartyGraph:
    """Tests for _build_first_party_graph."""

    def test_no_fleet_deps(self) -> None:
        """When no pins match fleet repos, graph is empty."""
        dep_map = {"https://github.com/external/dep.git": [("repo1", "pkg1", "a" * 40)]}
        graph = _build_first_party_graph(dep_map, ["repo1"], "org")
        assert graph == {}

    def test_fleet_dep(self) -> None:
        """When a repo pins a fleet repo, an edge is created."""
        dep_map = {
            "https://github.com/org/dep-repo.git": [("repo1", "dep-repo", "a" * 40)]
        }
        graph = _build_first_party_graph(dep_map, ["repo1", "dep-repo"], "org")
        assert graph == {"repo1": {"dep-repo"}}

    def test_self_loop_excluded(self) -> None:
        """A repo pinning itself is excluded."""
        dep_map = {"https://github.com/org/repo1.git": [("repo1", "repo1", "a" * 40)]}
        graph = _build_first_party_graph(dep_map, ["repo1"], "org")
        assert graph == {}

    def test_ssh_url_matches_https_fleet_repo(self) -> None:
        """SSH-format pin URL matches an HTTPS fleet repo."""
        dep_map = {"git@github.com:org/dep-repo.git": [("repo1", "dep-repo", "a" * 40)]}
        graph = _build_first_party_graph(dep_map, ["repo1", "dep-repo"], "org")
        assert graph == {"repo1": {"dep-repo"}}

    def test_multiple_deps(self) -> None:
        """A repo with multiple fleet deps has multiple edges."""
        dep_map = {
            "https://github.com/org/dep-a.git": [("repo1", "dep-a", "a" * 40)],
            "https://github.com/org/dep-b.git": [("repo1", "dep-b", "b" * 40)],
        }
        graph = _build_first_party_graph(dep_map, ["repo1", "dep-a", "dep-b"], "org")
        assert graph == {"repo1": {"dep-a", "dep-b"}}


# ---------------------------------------------------------------------------
# _topological_sort
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    """Tests for _topological_sort."""

    def test_no_dependencies(self) -> None:
        """Repos with no deps are all leaves."""
        graph: dict[str, set[str]] = {}
        repos = {"a", "b", "c"}
        sorted_repos, cycle_repos = _topological_sort(graph, repos)
        assert cycle_repos == set()
        assert set(sorted_repos) == repos

    def test_linear_chain(self) -> None:
        """A → B → C: C first, then B, then A."""
        graph = {"a": {"b"}, "b": {"c"}}
        sorted_repos, cycle_repos = _topological_sort(graph, {"a", "b", "c"})
        assert cycle_repos == set()
        assert sorted_repos.index("c") < sorted_repos.index("b")
        assert sorted_repos.index("b") < sorted_repos.index("a")

    def test_diamond(self) -> None:
        """A depends on B and C; B depends on C. C first."""
        graph = {"a": {"b", "c"}, "b": {"c"}}
        sorted_repos, cycle_repos = _topological_sort(graph, {"a", "b", "c"})
        assert cycle_repos == set()
        assert sorted_repos.index("c") < sorted_repos.index("b")
        assert sorted_repos.index("c") < sorted_repos.index("a")

    def test_cycle_detected(self) -> None:
        """A ↔ B cycle: both are in cycle_repos."""
        graph = {"a": {"b"}, "b": {"a"}}
        sorted_repos, cycle_repos = _topological_sort(graph, {"a", "b"})
        assert cycle_repos == {"a", "b"}
        assert sorted_repos == []

    def test_partial_cycle(self) -> None:
        """A → B ↔ C: A depends on B which is in a cycle, so all three
        are unsortable."""
        graph = {"a": {"b"}, "b": {"c"}, "c": {"b"}}
        sorted_repos, cycle_repos = _topological_sort(graph, {"a", "b", "c"})
        assert cycle_repos == {"a", "b", "c"}
        assert sorted_repos == []

    def test_deterministic_order(self) -> None:
        """Same input always produces the same output."""
        graph = {"a": {"c"}, "b": {"c"}}
        repos = {"a", "b", "c"}
        result1 = _topological_sort(graph, repos)
        result2 = _topological_sort(graph, repos)
        assert result1 == result2

    def test_dep_outside_set_ignored(self) -> None:
        """Dependencies not in the repos set are ignored."""
        graph = {"a": {"b", "external"}}
        sorted_repos, cycle_repos = _topological_sort(graph, {"a", "b"})
        assert cycle_repos == set()
        # b has no in-set deps, so it's a leaf
        assert sorted_repos.index("b") < sorted_repos.index("a")


# ---------------------------------------------------------------------------
# _get_fleet_dep_bumps
# ---------------------------------------------------------------------------


class TestGetFleetDepBumps:
    """Tests for _get_fleet_dep_bumps."""

    def test_no_pushed_deps(self) -> None:
        """When no fleet deps were pushed, no bumps returned."""
        bumps = _get_fleet_dep_bumps("repo1", {"dep-repo"}, {}, {}, "org")
        assert bumps == []

    def test_pushed_dep_creates_bump(self) -> None:
        """When a fleet dep was pushed, its pin is bumped."""
        dep_map = {
            "https://github.com/org/dep-repo.git": [("repo1", "dep-repo", "a" * 40)]
        }
        pushed_shas = {"dep-repo": "b" * 40}
        bumps = _get_fleet_dep_bumps("repo1", {"dep-repo"}, pushed_shas, dep_map, "org")
        assert bumps == [("dep-repo", "b" * 40)]

    def test_already_current_rev_skipped(self) -> None:
        """When the current rev matches the pushed SHA, no bump."""
        sha = "a" * 40
        dep_map = {"https://github.com/org/dep-repo.git": [("repo1", "dep-repo", sha)]}
        pushed_shas = {"dep-repo": sha}
        bumps = _get_fleet_dep_bumps("repo1", {"dep-repo"}, pushed_shas, dep_map, "org")
        assert bumps == []

    def test_only_matching_repo(self) -> None:
        """Only bumps for the specified repo, not other repos."""
        dep_map = {
            "https://github.com/org/dep-repo.git": [
                ("repo1", "dep-repo", "a" * 40),
                ("repo2", "dep-repo", "c" * 40),
            ]
        }
        pushed_shas = {"dep-repo": "b" * 40}
        bumps = _get_fleet_dep_bumps("repo1", {"dep-repo"}, pushed_shas, dep_map, "org")
        assert bumps == [("dep-repo", "b" * 40)]

    def test_dep_not_in_pushed_shas(self) -> None:
        """Fleet dep not in pushed_shas produces no bump."""
        dep_map = {
            "https://github.com/org/dep-repo.git": [("repo1", "dep-repo", "a" * 40)]
        }
        bumps = _get_fleet_dep_bumps("repo1", {"dep-repo"}, {}, dep_map, "org")
        assert bumps == []


# ---------------------------------------------------------------------------
# _apply_pin_bump
# ---------------------------------------------------------------------------


class TestApplyPinBump:
    """Tests for _apply_pin_bump."""

    def _make_apply_mocks(
        self, tmp_path: Path, monkeypatch, *, existing_pr: bool = False
    ) -> tuple[list[str], list[str]]:
        """Set up mocks for _apply_pin_bump and return command/gh_call logs.

        Returns (subprocess_calls, gh_pr_calls).
        """
        subprocess_calls: list[tuple[str, ...]] = []
        gh_calls: list[tuple[str, ...]] = []

        def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            subprocess_calls.append(args)
            if args[0] == "git" and args[1] == "clone":
                # Create the fake cloned repo directory
                dest = Path(args[-1])
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "pyproject.toml").write_text(
                    textwrap.dedent("""
                        [tool.uv.sources]
                        mypkg = { git = "https://github.com/org/dep.git", rev = "0000000000000000000000000000000000000000" }
                    """).lstrip()
                )
            if args[0] == "git" and args[1] == "-C" and "rev-parse" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="main\n", stderr=""
                )
            if args[0] == "gh" and args[1] == "pr":
                gh_calls.append(args)
                if args[2] == "list":
                    if existing_pr:
                        return subprocess.CompletedProcess(
                            args=args, returncode=0, stdout="42\n", stderr=""
                        )
                    raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(_pin_bump, "run", fake_run)
        return subprocess_calls, gh_calls

    def test_creates_new_pr(self, tmp_path: Path, monkeypatch) -> None:
        """When no existing PR for the bump branch, a new PR is created."""
        subprocess_calls, gh_calls = self._make_apply_mocks(
            tmp_path, monkeypatch, existing_pr=False
        )

        bumps = [("mypkg", "f" * 40)]
        _apply_pin_bump("test-org", "myrepo", bumps, "fake-token", str(tmp_path))

        # Verify git clone happened
        clone_calls = [c for c in subprocess_calls if c[0] == "git" and c[1] == "clone"]
        assert len(clone_calls) == 1
        assert clone_calls[0][-1] == str(tmp_path / "myrepo")

        # Verify branch name
        checkout_calls = [
            c for c in subprocess_calls if c[0] == "git" and "checkout" in c
        ]
        assert any("pin-bump/sweep" in c for c in checkout_calls)

        # Verify PR was created (not just list)
        pr_create = [c for c in gh_calls if "create" in c]
        assert len(pr_create) == 1

    def test_reuses_existing_pr(self, tmp_path: Path, monkeypatch) -> None:
        """When a PR already exists for the bump branch, no new PR is created."""
        subprocess_calls, gh_calls = self._make_apply_mocks(
            tmp_path, monkeypatch, existing_pr=True
        )

        bumps = [("mypkg", "f" * 40)]
        _apply_pin_bump("test-org", "myrepo", bumps, "fake-token", str(tmp_path))

        # PR list was called, but create was not
        pr_list = [c for c in gh_calls if "list" in c]
        pr_create = [c for c in gh_calls if "create" in c]
        assert len(pr_list) == 1
        assert len(pr_create) == 0

    def test_skips_when_no_pyproject_after_clone(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """When pyproject.toml is missing from the cloned repo, skip quietly."""

        def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[0] == "git" and args[1] == "clone":
                dest = Path(args[-1])
                dest.mkdir(parents=True, exist_ok=True)
                # deliberately NOT creating pyproject.toml
            if args[0] == "git" and args[1] == "-C" and "rev-parse" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="main\n", stderr=""
                )
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(_pin_bump, "run", fake_run)

        bumps = [("mypkg", "f" * 40)]
        _apply_pin_bump("test-org", "myrepo", bumps, "fake-token", str(tmp_path))

        captured = capsys.readouterr()
        assert "pyproject.toml not found" in captured.out


# ---------------------------------------------------------------------------
# sweep (orchestrator)
# ---------------------------------------------------------------------------


class TestSweep:
    """Integration tests for the sweep() orchestrator."""

    def test_no_git_pins_returns_zero(self, monkeypatch) -> None:
        """When no repos have git-sourced pins, sweep returns 0."""

        def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[:3] == ("gh", "repo", "list"):
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout=json.dumps([{"name": "repo1"}]),
                    stderr="",
                )
            return subprocess.run(args, text=True, check=True, **kwargs)  # type: ignore[call-overload,no-any-return]

        def fake_gh(*args: str, **kwargs: object) -> str:
            # Return a pyproject.toml with no git sources
            toml = textwrap.dedent("""
                [project]
                name = "no-git-pins"
            """).lstrip()
            return base64.b64encode(toml.encode()).decode()

        monkeypatch.setattr(_pin_bump, "run", fake_run)
        monkeypatch.setattr(_pin_bump, "gh", fake_gh)
        monkeypatch.setenv("SWEEP_TOKEN", "fake-token")

        exit_code = sweep("test-org", "SWEEP_TOKEN")
        assert exit_code == 0

    def test_all_pins_current_returns_zero(self, tmp_path: Path, monkeypatch) -> None:
        """When all fleet pins are already current, sweep returns 0."""
        # Create a bare repo to resolve a real SHA
        dep_bare, head = _create_bare_repo(tmp_path)

        toml_content = textwrap.dedent(f"""
            [tool.uv.sources]
            mypkg = {{ git = "file://{dep_bare}", rev = "{head}" }}
        """).lstrip()

        def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[:3] == ("gh", "repo", "list"):
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout=json.dumps([{"name": "consumer"}]),
                    stderr="",
                )
            # Let resolve_default_branch_head use real git
            if args[0] == "git" and args[1] == "ls-remote":
                return subprocess.run(args, text=True, check=True, **kwargs)  # type: ignore[call-overload,no-any-return]
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="", stderr=""
            )

        def fake_gh(*args: str, **kwargs: object) -> str:
            return base64.b64encode(toml_content.encode()).decode()

        monkeypatch.setattr(_pin_bump, "run", fake_run)
        monkeypatch.setattr(_pin_bump, "gh", fake_gh)
        monkeypatch.setenv("SWEEP_TOKEN", "fake-token")

        exit_code = sweep("test-org", "SWEEP_TOKEN")
        assert exit_code == 0

    def test_stale_pins_trigger_bumps(self, tmp_path: Path, monkeypatch) -> None:
        """When pins are stale, sweep detects bumps and processes repos."""
        # Create a bare repo and get its HEAD
        dep_bare, head = _create_bare_repo(tmp_path)

        # Use a different (stale) rev in the pyproject
        stale_rev = "0" * 40

        toml_content = textwrap.dedent(f"""
            [tool.uv.sources]
            mypkg = {{ git = "file://{dep_bare}", rev = "{stale_rev}" }}
        """).lstrip()

        subprocess_calls: list[tuple[str, ...]] = []

        def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            subprocess_calls.append(args)
            if args[:3] == ("gh", "repo", "list"):
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout=json.dumps([{"name": "consumer"}]),
                    stderr="",
                )
            if args[0] == "git" and args[1] == "ls-remote":
                return subprocess.run(args, text=True, check=True, **kwargs)  # type: ignore[call-overload,no-any-return]
            if args[0] == "git" and args[1] == "clone":
                dest = Path(args[-1])
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "pyproject.toml").write_text(toml_content)
            if args[0] == "git" and args[1] == "-C" and "rev-parse" in args:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="main\n", stderr=""
                )
            if args[0] == "gh" and args[1] == "pr" and args[2] == "list":
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="", stderr=""
            )

        def fake_gh(*args: str, **kwargs: object) -> str:
            return base64.b64encode(toml_content.encode()).decode()

        monkeypatch.setattr(_pin_bump, "run", fake_run)
        monkeypatch.setattr(_pin_bump, "gh", fake_gh)
        monkeypatch.setenv("SWEEP_TOKEN", "fake-token")

        exit_code = sweep("test-org", "SWEEP_TOKEN")
        assert exit_code == 0

        # Verify clone happened (meaning a bump was detected)
        clone_calls = [c for c in subprocess_calls if c[0] == "git" and c[1] == "clone"]
        assert len(clone_calls) == 1

        # Verify PR was created
        pr_create = [
            c
            for c in subprocess_calls
            if c[0] == "gh" and c[1] == "pr" and "create" in c
        ]
        assert len(pr_create) == 1

    def test_topological_ordering(self, tmp_path: Path, monkeypatch) -> None:
        """Leaf repo is bumped before its dependent; dependent pins the
        leaf's PR-branch SHA for coherent transitive resolution."""
        dep_bare, head = _create_bare_repo(tmp_path)
        stale = "0" * 40

        # Fleet: board (leaf — pins modules), mail (pins board + modules)
        dep_map = {
            f"file://{dep_bare}": [
                ("board", "modules", stale),
                ("mail", "modules", stale),
            ],
            "https://github.com/test-org/board.git": [
                ("mail", "board", stale),
            ],
        }
        all_fleet_repos = ["board", "mail"]

        monkeypatch.setattr(
            _pin_bump,
            "_collect_fleet_pins",
            lambda *a, **kw: (dep_map, [], all_fleet_repos),
        )
        monkeypatch.setattr(
            _pin_bump,
            "_resolve_latest_shas",
            lambda dm: ({f"file://{dep_bare}": head}, []),
        )

        call_order: list[str] = []
        bumps_per_repo: dict[str, list[tuple[str, str]]] = {}

        def fake_apply(
            owner: str,
            repo: str,
            bumps: list[tuple[str, str]],
            token: str,
            tmpdir: str,
        ) -> str:
            call_order.append(repo)
            bumps_per_repo[repo] = bumps
            return f"{repo}_pr_sha"

        monkeypatch.setattr(_pin_bump, "_apply_pin_bump", fake_apply)
        monkeypatch.setenv("SWEEP_TOKEN", "fake-token")

        exit_code = sweep("test-org", "SWEEP_TOKEN")
        assert exit_code == 0

        # board (leaf) processed before mail (dependent)
        assert call_order == ["board", "mail"]

        # mail's bumps: modules → HEAD, board → board's PR-branch SHA
        mail_bumps = dict(bumps_per_repo["mail"])
        assert mail_bumps["modules"] == head
        assert mail_bumps["board"] == "board_pr_sha"

    def test_cycle_repos_skipped(self, monkeypatch) -> None:
        """Repos in a first-party dependency cycle are skipped."""
        stale = "0" * 40
        new = "f" * 40

        dep_map = {
            "https://github.com/test-org/b.git": [("a", "b", stale)],
            "https://github.com/test-org/a.git": [("b", "a", stale)],
        }
        all_fleet_repos = ["a", "b"]

        monkeypatch.setattr(
            _pin_bump,
            "_collect_fleet_pins",
            lambda *a, **kw: (dep_map, [], all_fleet_repos),
        )
        monkeypatch.setattr(
            _pin_bump,
            "_resolve_latest_shas",
            lambda dm: (
                {
                    "https://github.com/test-org/b.git": new,
                    "https://github.com/test-org/a.git": new,
                },
                [],
            ),
        )

        apply_calls: list[str] = []

        def fake_apply(
            owner: str,
            repo: str,
            bumps: list[tuple[str, str]],
            token: str,
            tmpdir: str,
        ) -> str:
            apply_calls.append(repo)
            return "sha"

        monkeypatch.setattr(_pin_bump, "_apply_pin_bump", fake_apply)
        monkeypatch.setenv("SWEEP_TOKEN", "fake-token")

        exit_code = sweep("test-org", "SWEEP_TOKEN")
        assert exit_code == 0

        # Neither repo was processed (both in cycle)
        assert apply_calls == []

    def test_cascading_skip_on_dep_failure(self, monkeypatch) -> None:
        """When a leaf repo fails, its dependents are skipped."""
        stale = "0" * 40
        new = "f" * 40

        dep_map = {
            "https://github.com/test-org/dep.git": [
                ("leaf", "dep", stale),
                ("consumer", "dep", stale),
            ],
            "https://github.com/test-org/leaf.git": [
                ("consumer", "leaf", stale),
            ],
        }
        all_fleet_repos = ["leaf", "consumer"]

        monkeypatch.setattr(
            _pin_bump,
            "_collect_fleet_pins",
            lambda *a, **kw: (dep_map, [], all_fleet_repos),
        )
        monkeypatch.setattr(
            _pin_bump,
            "_resolve_latest_shas",
            lambda dm: (
                {
                    "https://github.com/test-org/dep.git": new,
                    "https://github.com/test-org/leaf.git": new,
                },
                [],
            ),
        )

        apply_calls: list[str] = []

        def fake_apply(
            owner: str,
            repo: str,
            bumps: list[tuple[str, str]],
            token: str,
            tmpdir: str,
        ) -> str:
            apply_calls.append(repo)
            if repo == "leaf":
                raise RuntimeError("lock failed")
            return "sha"

        monkeypatch.setattr(_pin_bump, "_apply_pin_bump", fake_apply)
        monkeypatch.setenv("SWEEP_TOKEN", "fake-token")

        exit_code = sweep("test-org", "SWEEP_TOKEN")
        assert exit_code == 1  # failed

        # leaf was attempted but failed; consumer was skipped
        assert "leaf" in apply_calls
        assert "consumer" not in apply_calls
