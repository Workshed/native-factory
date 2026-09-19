"""Workspace layout and project slugs."""

from __future__ import annotations

from pathlib import Path

import pytest

from native_factory.workspace.layout import ProjectPaths, Workspace, WorkspaceError, slugify


class TestSlugify:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("demo", "demo"),
            ("My Project", "my-project"),
            ("Example.com", "example-com"),
            ("  spaced  ", "spaced"),
            ("under_score", "under_score"),
        ],
    )
    def test_accepts_reasonable_names(self, given: str, expected: str) -> None:
        assert slugify(given) == expected

    @pytest.mark.parametrize("given", ["", "   ", "...", "../../etc", "/", "a/b", "a..b"])
    def test_rejects_rather_than_mangles(self, given: str) -> None:
        # The slug names a directory that gets mounted into a VM, so a surprise here is a
        # security matter rather than a cosmetic one.
        with pytest.raises(WorkspaceError):
            slugify(given)

    def test_path_like_names_are_refused_not_sanitised(self) -> None:
        # Quietly turning "../../etc" into "etc" would be safe but dishonest: the user
        # should see that their input was not understood.
        with pytest.raises(WorkspaceError, match="looks like a path"):
            slugify("../../etc")


class TestWorkspace:
    def test_default_honours_the_env_override(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("NATIVE_FACTORY_HOME", str(tmp_path / "elsewhere"))
        assert Workspace.default().root == tmp_path / "elsewhere"

    def test_default_is_under_home_without_the_override(self, monkeypatch) -> None:
        monkeypatch.delenv("NATIVE_FACTORY_HOME", raising=False)
        assert Workspace.default().root == Path.home() / "NativeFactory"

    def test_ensure_creates_the_skeleton(self, tmp_path: Path) -> None:
        workspace = Workspace(tmp_path / "nf")
        workspace.ensure()
        assert workspace.projects_dir.is_dir()
        assert workspace.reports.is_dir()
        assert workspace.state_db.parent.is_dir()

    def test_project_paths_are_under_projects_dir(self, tmp_path: Path) -> None:
        workspace = Workspace(tmp_path / "nf")
        project = workspace.project("Demo")
        assert project.root == (workspace.projects_dir / "demo").resolve()

    def test_project_rejects_escaping_names(self, tmp_path: Path) -> None:
        with pytest.raises(WorkspaceError):
            Workspace(tmp_path / "nf").project("../escape")

    def test_projects_lists_existing_directories(self, tmp_path: Path) -> None:
        workspace = Workspace(tmp_path / "nf")
        workspace.ensure()
        for name in ("beta", "alpha"):
            workspace.project(name).create()
        assert [p.name for p in workspace.projects()] == ["alpha", "beta"]

    def test_projects_is_empty_before_ensure(self, tmp_path: Path) -> None:
        assert Workspace(tmp_path / "missing").projects() == []


class TestProjectPaths:
    def test_create_makes_every_directory(self, tmp_path: Path) -> None:
        project = ProjectPaths(tmp_path / "demo")
        project.create()
        for directory in project.directories():
            assert directory.is_dir(), directory

    def test_exists_tracks_the_config_file_not_the_directory(self, tmp_path: Path) -> None:
        project = ProjectPaths(tmp_path / "demo")
        project.create()
        assert project.exists() is False
        project.config_file.write_text("project:\n  name: demo\n", encoding="utf-8")
        assert project.exists() is True

    def test_ios_and_android_live_under_work(self, tmp_path: Path) -> None:
        project = ProjectPaths(tmp_path / "demo")
        assert project.ios.parent == project.work
        assert project.android.parent == project.work
