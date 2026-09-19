"""Worker VM lifecycle: clone -> run -> work -> stop -> delete or preserve.

Tart has no live snapshots; clone/run/delete is the intended pattern (HANDOFF 4.4).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from native_factory.config.loader import dump_config
from native_factory.vm.mounts import Mount, mounts_for_stage
from native_factory.vm.tart import MAX_MACOS_GUESTS, Tart, TartError, TartVmLimitReachedError
from native_factory.workspace.layout import ProjectPaths
from native_factory_core.schema.config import Egress, ProjectConfig, Stage

WORKER_PREFIX = "nf-"
READY_TIMEOUT = 300.0
READY_POLL = 2.0


class LifecycleError(Exception):
    """Raised with a message intended to be shown directly to the user."""


def worker_name(project: str) -> str:
    return f"{WORKER_PREFIX}{project}"


@dataclass(frozen=True, slots=True)
class Worker:
    name: str
    stage: Stage
    mounts: tuple[Mount, ...]
    ip: str | None = None


def ensure_capacity(tart: Tart, *, about_to_start: str | None = None) -> None:
    """Refuse a third macOS guest before invoking Tart.

    Tart would fail anyway, but its error is opaque and arrives after a clone. Checking
    first turns the two-guest ceiling into an explanation (AT-6).
    """
    running = [vm for vm in tart.running_macos_guests() if vm.name != about_to_start]
    if len(running) < MAX_MACOS_GUESTS:
        return
    names = ", ".join(vm.name for vm in running)
    raise TartVmLimitReachedError(
        f"{len(running)} macOS guests are already running: {names}\n"
        f"  macOS permits {MAX_MACOS_GUESTS} VM instances per Mac and Tart enforces it, so "
        "at most two features can be in flight.\n"
        "  Stop one first: native-factory vm stop --name <name>"
    )


def write_effective_config(project: ProjectPaths, config: ProjectConfig) -> Path:
    """Materialise the resolved config into the read-only `factory` mount."""
    project.factory.mkdir(parents=True, exist_ok=True)
    path = project.factory / "config.yaml"
    path.write_text(dump_config(config), encoding="utf-8")
    return path


def clone_worker(tart: Tart, config: ProjectConfig, name: str) -> None:
    golden = config.vm.golden_name
    if not tart.exists(golden):
        raise LifecycleError(
            f"golden image {golden!r} does not exist\n  Build it first: native-factory vm create"
        )
    if tart.exists(name):
        raise LifecycleError(
            f"a VM named {name!r} already exists\n"
            f"  Reuse it, or remove it: native-factory vm delete --name {name}"
        )
    tart.clone(golden, name)
    tart.configure(name, cpu=config.vm.cpu, memory_mb=config.vm.memory_mb)


def start_worker(
    tart: Tart,
    config: ProjectConfig,
    project: ProjectPaths,
    stage: Stage,
    *,
    name: str | None = None,
    log_path: Path | None = None,
    timeout: float = READY_TIMEOUT,
) -> Worker:
    vm_name = name or worker_name(project.name)
    ensure_capacity(tart, about_to_start=vm_name)

    write_effective_config(project, config)
    project.create()

    if not tart.exists(vm_name):
        clone_worker(tart, config, vm_name)

    mounts = mounts_for_stage(project.root, stage)
    for mount in mounts:
        mount.path.mkdir(parents=True, exist_ok=True)

    softnet = config.vm.egress is Egress.ALLOWLIST
    tart.run_detached(
        vm_name,
        log_path or (project.reports / "vm" / f"{vm_name}.log"),
        mounts=mounts,
        net_softnet=softnet,
        softnet_allow=config.vm.egress_allowlist if softnet else (),
    )

    ip = wait_ready(tart, vm_name, timeout=timeout)
    return Worker(name=vm_name, stage=stage, mounts=tuple(mounts), ip=ip)


def wait_ready(tart: Tart, name: str, timeout: float = READY_TIMEOUT) -> str:
    """Wait for the guest to answer `tart ip`.

    `tart run` blocks for the VM's lifetime, so readiness is observed from outside rather
    than awaited from the process.
    """
    deadline = time.monotonic() + timeout
    last: str = ""
    while time.monotonic() < deadline:
        try:
            ip = tart.ip(name)
            if ip:
                return ip
        except TartError as exc:
            last = str(exc)
        time.sleep(READY_POLL)
    raise LifecycleError(
        f"{name} did not become reachable within {timeout:.0f}s\n"
        f"  {last}\n"
        "  Check the VM log under <project>/reports/vm/."
    )


def stop_worker(tart: Tart, name: str) -> None:
    tart.stop(name)


def delete_worker(tart: Tart, name: str, *, preserve: bool) -> bool:
    """Delete the worker unless preservation is configured. Returns True when deleted.

    The brief requires that a failed VM can be entered for debugging, so destruction stays
    conservative and opt-out.
    """
    if preserve:
        return False
    tart.delete(name)
    return True


def running_workers(tart: Tart) -> list[str]:
    return [vm.name for vm in tart.running_macos_guests() if vm.name.startswith(WORKER_PREFIX)]
