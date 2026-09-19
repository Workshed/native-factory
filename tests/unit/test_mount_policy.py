"""Mount construction and the ADR-0005 stage policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from native_factory.vm.mounts import (
    GUEST_MOUNT_ROOT,
    STAGE_POLICY,
    Mount,
    MountError,
    mounts_for_stage,
    read_only_mount_names,
)
from native_factory_core.schema.config import Stage

PROJECT = Path("/Users/x/NativeFactory/projects/demo")


class TestMount:
    def test_read_write_flag(self) -> None:
        assert Mount("work", Path("/a/b")).to_flag() == "--dir=work:/a/b"

    def test_read_only_flag(self) -> None:
        assert (
            Mount("reference", Path("/a/b"), read_only=True).to_flag() == "--dir=reference:/a/b:ro"
        )

    def test_guest_path(self) -> None:
        assert Mount("work", Path("/a/b")).guest_path == f"{GUEST_MOUNT_ROOT}/work"

    @pytest.mark.parametrize("name", ["", "a:b", "a/b"])
    def test_invalid_names_rejected(self, name: str) -> None:
        # Tart splits --dir on ':', so these are unrepresentable rather than merely odd.
        with pytest.raises(MountError):
            Mount(name, Path("/a"))

    def test_relative_path_rejected(self) -> None:
        with pytest.raises(MountError, match="must be absolute"):
            Mount("work", Path("relative/path"))

    def test_colon_in_path_rejected(self) -> None:
        with pytest.raises(MountError, match="must not contain"):
            Mount("work", Path("/a:b"))


class TestStagePolicy:
    def test_discovery_may_write_reference_and_has_no_work_dir(self) -> None:
        mounts = {m.name: m for m in mounts_for_stage(PROJECT, Stage.DISCOVERY)}
        assert mounts["reference"].read_only is False
        assert "work" not in mounts

    def test_implement_gets_read_only_reference_and_writable_work(self) -> None:
        mounts = {m.name: m for m in mounts_for_stage(PROJECT, Stage.IMPLEMENT)}
        assert mounts["reference"].read_only is True
        assert mounts["work"].read_only is False

    def test_evaluate_is_read_only_throughout(self) -> None:
        mounts = mounts_for_stage(PROJECT, Stage.EVALUATE)
        assert all(m.read_only for m in mounts)

    def test_config_is_read_only_in_every_stage(self) -> None:
        for stage in Stage:
            factory = next(m for m in mounts_for_stage(PROJECT, stage) if m.name == "factory")
            assert factory.read_only is True, stage

    def test_reports_is_never_mounted(self) -> None:
        # The host pulls results out over `tart exec`; the directory the evaluator writes
        # to is not exposed to the guest at all.
        for stage in Stage:
            assert "reports" not in {m.name for m in mounts_for_stage(PROJECT, stage)}

    def test_reference_is_writable_in_exactly_one_stage(self) -> None:
        writable = [s for s in Stage if STAGE_POLICY[s].get("reference") is False]
        assert writable == [Stage.DISCOVERY]

    def test_paths_are_under_the_project_directory(self) -> None:
        for mount in mounts_for_stage(PROJECT, Stage.IMPLEMENT):
            assert mount.path.is_relative_to(PROJECT)

    def test_every_stage_has_a_policy(self) -> None:
        assert set(STAGE_POLICY) == set(Stage)

    def test_read_only_names_drive_the_integrity_check(self) -> None:
        assert read_only_mount_names(Stage.DISCOVERY) == ["factory"]
        assert read_only_mount_names(Stage.IMPLEMENT) == ["factory", "reference"]
        assert read_only_mount_names(Stage.EVALUATE) == ["factory", "reference", "work"]
