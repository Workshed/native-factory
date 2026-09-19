"""`native-factory vm ...` -- golden image and worker lifecycle."""

from __future__ import annotations

import json

import typer

from native_factory.cli.context import (
    Ctx,
    console,
    fail,
    repo_root,
    require_config,
    require_project,
    run_record,
)
from native_factory.doctor.guest import run_guest_doctor
from native_factory.doctor.report import print_report
from native_factory.vm import lifecycle, packer
from native_factory.vm.tart import Tart, TartError
from native_factory_core.schema.config import Stage

app = typer.Typer(no_args_is_help=True, help="Create and drive Tart VMs.")

GUEST_MANIFEST = "/opt/native-factory/manifest.json"


def _tart() -> Tart:
    tart = Tart()
    try:
        tart.require_installed()
    except TartError as exc:
        raise fail(str(exc)) from exc
    return tart


@app.command("create")
def create(
    project: str | None = typer.Option(
        None, "--project", "-p", help="project whose vm.* config to use"
    ),
    name: str | None = typer.Option(None, "--name", help="image name (default: vm.golden_name)"),
    force: bool = typer.Option(False, "--force", help="rebuild even if the image exists"),
) -> None:
    """Build the golden image with Packer.

    A second run is a no-op unless --force. Byte-identical rebuilds are not achievable
    (Packer re-runs Homebrew and npm); reproducibility is the pinned-inputs manifest the
    build writes into the image. See docs/adr and implementation-plan AT-2.
    """
    ctx = Ctx.build(project) if project else Ctx(workspace=Ctx.build(None).workspace)
    config = ctx.config or _default_config()
    image = name or config.vm.golden_name
    tart = _tart()

    if tart.exists(image) and not force:
        console.print(f"image [bold]{image}[/bold] exists, use --force to rebuild")
        raise typer.Exit(0)

    running = lifecycle.running_workers(tart)
    if running:
        raise fail(
            f"workers are running ({', '.join(running)}).\n"
            "  Building the golden image needs a VM slot and macOS allows only two; "
            "stop a worker first."
        )

    try:
        plan = packer.plan_build(repo_root(), config)
    except packer.PackerError as exc:
        raise fail(str(exc)) from exc

    with run_record(ctx, "vm create", vm_name=image) as log:
        log.event(
            "packer.plan",
            image=image,
            base_image=plan.base_image,
            template_sha256=plan.template_hash,
        )
        console.print(f"building [bold]{image}[/bold] from {plan.base_image}")
        console.print("[dim]this takes 60-90 minutes on a first run[/dim]")

        code = packer.run_packer(plan.init_argv(), cwd=repo_root(), on_line=console.out)
        if code != 0:
            raise fail(f"packer init exited {code}")

        code = packer.run_packer(plan.build_argv(), cwd=repo_root(), on_line=console.out)
        if code != 0:
            raise fail(f"packer build exited {code}")

        log.event("packer.done", image=image)

    console.print(f"[green]built[/green] {image}")


@app.command("start")
def start(
    project: str | None = typer.Option(None, "--project", "-p"),
    name: str | None = typer.Option(None, "--name", help="worker VM name"),
    stage: Stage = typer.Option(Stage.IMPLEMENT, "--stage", help="determines the mount policy"),
) -> None:
    """Clone the golden image and run a worker with stage-scoped mounts (ADR-0005)."""
    ctx = Ctx.resolve_single_project(project)
    config = require_config(ctx)
    paths = require_project(ctx)
    tart = _tart()

    with run_record(ctx, "vm start") as log:
        try:
            worker = lifecycle.start_worker(tart, config, paths, stage, name=name)
        except (TartError, lifecycle.LifecycleError) as exc:
            raise fail(str(exc)) from exc
        log.event(
            "vm.started",
            vm_name=worker.name,
            stage=stage.value,
            ip=worker.ip,
            mounts=[m.to_flag() for m in worker.mounts],
        )

    console.print(f"[green]running[/green] {worker.name} ({worker.ip}) stage={stage.value}")
    for mount in worker.mounts:
        access = "ro" if mount.read_only else "rw"
        console.print(f"  [{access}] {mount.guest_path}")


@app.command("shell")
def shell(
    name: str | None = typer.Option(None, "--name"),
    project: str | None = typer.Option(None, "--project", "-p"),
    command: list[str] | None = typer.Argument(None, help="command to run instead of a shell"),
) -> None:
    """Interactive `tart exec -it` shell, or a one-shot command after `--`."""
    tart = _tart()
    vm_name = name or _only_running_worker(tart)
    if command:
        result = tart.exec(vm_name, command, check=False)
        if result.stdout:
            typer.echo(result.stdout, nl=False)
        if result.stderr:
            typer.echo(result.stderr, nl=False, err=True)
        raise typer.Exit(result.returncode)
    raise typer.Exit(tart.exec_interactive(vm_name))


@app.command("stop")
def stop(name: str | None = typer.Option(None, "--name")) -> None:
    """Stop a worker. The VM is left in place so a failed run can be inspected."""
    tart = _tart()
    vm_name = name or _only_running_worker(tart)
    try:
        lifecycle.stop_worker(tart, vm_name)
    except TartError as exc:
        raise fail(str(exc)) from exc
    console.print(f"[green]stopped[/green] {vm_name} (still present; `vm delete` to remove)")


@app.command("delete")
def delete(
    name: str = typer.Option(..., "--name"),
    force: bool = typer.Option(False, "--force", help="ignore factory.preserve_failed_vm"),
    project: str | None = typer.Option(None, "--project", "-p"),
) -> None:
    """Delete a worker VM."""
    tart = _tart()
    preserve = False
    if project:
        preserve = require_config(Ctx.build(project)).factory.preserve_failed_vm and not force
    try:
        deleted = lifecycle.delete_worker(tart, name, preserve=preserve)
    except TartError as exc:
        raise fail(str(exc)) from exc
    if deleted:
        console.print(f"[green]deleted[/green] {name}")
    else:
        console.print(f"kept {name} (factory.preserve_failed_vm); --force to delete anyway")


@app.command("list")
def list_vms() -> None:
    """List local VMs."""
    tart = _tart()
    try:
        vms = tart.list()
    except TartError as exc:
        raise fail(str(exc)) from exc
    if not vms:
        console.print("no VMs")
        return
    for vm in vms:
        marker = "[green]running[/green]" if vm.running else "[dim]stopped[/dim]"
        console.print(f"  {marker}  {vm.name}")


@app.command("doctor")
def vm_doctor(
    name: str | None = typer.Option(None, "--name"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Run the guest doctor inside a worker over `tart exec`."""
    tart = _tart()
    vm_name = name or _only_running_worker(tart)
    report = run_guest_doctor(tart, vm_name)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        print_report(console, report)
    raise typer.Exit(0 if report.ok else 1)


@app.command("manifest")
def manifest(
    name: str = typer.Argument(..., help="VM to read /opt/native-factory/manifest.json from"),
) -> None:
    """Print an image's pinned-inputs manifest (AT-2)."""
    tart = _tart()
    result = tart.exec(name, ["cat", GUEST_MANIFEST], check=False)
    if result.returncode != 0:
        raise fail(
            f"no manifest in {name}: {result.stderr.strip() or GUEST_MANIFEST + ' missing'}\n"
            "  Images built before the manifest layer will not have one; rebuild."
        )
    try:
        typer.echo(json.dumps(json.loads(result.stdout), indent=2, sort_keys=True))
    except json.JSONDecodeError as exc:
        raise fail(f"manifest in {name} is not valid JSON: {exc}") from exc


def _only_running_worker(tart: Tart) -> str:
    workers = lifecycle.running_workers(tart)
    if len(workers) == 1:
        return workers[0]
    if not workers:
        raise fail("no running workers; start one: native-factory vm start --project <name>")
    raise fail(f"several workers are running ({', '.join(workers)}); pass --name")


def _default_config():
    from native_factory_core.schema.config import ProjectConfig

    return ProjectConfig.model_validate({"project": {"name": "default"}})


__all__ = ["app"]
