"""AT-3: clone, run, stage-scoped mounts, and the read-only guarantee (ADR-0005).

The last test here is the one that matters: `reference/` must be genuinely unwritable from
inside the guest during an implement stage, because the evaluator judges against it and
the agent runs with an unrestricted shell.
"""

from __future__ import annotations

import pytest

from native_factory.vm.lifecycle import start_worker
from native_factory.vm.mounts import GUEST_MOUNT_ROOT
from native_factory.vm.tart import Tart
from native_factory.workspace.layout import Workspace
from native_factory_core.schema.config import ProjectConfig, Stage

pytestmark = pytest.mark.vm


@pytest.fixture
def started_worker(
    tart: Tart, golden_image: str, temp_workspace: Workspace, worker: str
) -> tuple[str, ProjectConfig]:
    config = ProjectConfig.model_validate(
        {"project": {"name": "acceptance"}, "vm": {"golden_name": golden_image}}
    )
    project = temp_workspace.project("acceptance")
    project.create()
    (project.reference / "site.yaml").write_text("name: acceptance\n", encoding="utf-8")
    start_worker(tart, config, project, Stage.IMPLEMENT, name=worker)
    return worker, config


def test_all_three_mounts_are_visible(started_worker, tart: Tart) -> None:
    vm, _ = started_worker
    result = tart.exec(vm, ["ls", GUEST_MOUNT_ROOT])
    listing = result.stdout.split()
    assert {"reference", "work", "factory"} <= set(listing), listing


def test_reference_is_read_only_during_implement(started_worker, tart: Tart) -> None:
    # The ADR-0005 property under test. A writable reference/ means the agent can edit the
    # acceptance criteria it is graded on.
    vm, _ = started_worker
    result = tart.exec(
        vm,
        ["sh", "-c", f'touch "{GUEST_MOUNT_ROOT}/reference/tamper" 2>&1; echo rc=$?'],
        check=False,
    )
    assert "rc=0" not in result.stdout, "reference/ was writable during an implement stage"


def test_work_is_writable_during_implement(started_worker, tart: Tart) -> None:
    vm, _ = started_worker
    result = tart.exec(
        vm, ["sh", "-c", f'touch "{GUEST_MOUNT_ROOT}/work/ok" && echo written'], check=False
    )
    assert "written" in result.stdout


def test_config_mount_is_read_only(started_worker, tart: Tart) -> None:
    vm, _ = started_worker
    result = tart.exec(
        vm,
        ["sh", "-c", f'touch "{GUEST_MOUNT_ROOT}/factory/tamper" 2>&1; echo rc=$?'],
        check=False,
    )
    assert "rc=0" not in result.stdout


def test_reports_is_not_mounted(started_worker, tart: Tart) -> None:
    # The host pulls results out; the directory the evaluator writes to is never exposed.
    vm, _ = started_worker
    result = tart.exec(vm, ["ls", GUEST_MOUNT_ROOT])
    assert "reports" not in result.stdout.split()


def test_tart_exec_does_not_trigger_a_tcc_prompt(started_worker, tart: Tart) -> None:
    # A TCC prompt would hang here rather than fail. SIP is disabled in the official base
    # images, which is why the build stays on them (HANDOFF 4.4).
    vm, _ = started_worker
    result = tart.exec(vm, ["ls", f"{GUEST_MOUNT_ROOT}/reference"], check=False)
    assert result.returncode == 0, "listing a mount hung or failed: TCC prompt?"
