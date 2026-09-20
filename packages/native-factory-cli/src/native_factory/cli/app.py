"""`native-factory` -- the host CLI."""

from __future__ import annotations

import typer

from native_factory.cli import vm_cmd
from native_factory.cli.context import Ctx, console, fail, repo_root, run_record
from native_factory.config.loader import CONFIG_FILENAME
from native_factory.doctor.checks import host_checks
from native_factory.doctor.report import print_report
from native_factory_core.schema.run import DoctorReport, RunStatus

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Turn a website into native iOS and Android apps, in disposable Tart VMs.",
)
app.add_typer(vm_cmd.app, name="vm")

#: Commands whose milestone has not landed. Listed so `--help` shows the shape of the
#: finished CLI rather than pretending these do not exist.
STUBS = {
    "inspect": (3, "crawl a website into reference/"),
    "report": (4, "render the reference model for human approval"),
    "plan": (4, "turn discovery artefacts into feature specifications"),
    "build": (8, "run the full per-feature pipeline"),
    "test": (7, "run recorded builds, journeys and evaluation"),
}


@app.command()
def doctor(
    project: str | None = typer.Option(
        None, "--project", "-p", help="check against this project's config"
    ),
    json_output: bool = typer.Option(False, "--json", help="emit machine-readable JSON"),
) -> None:
    """Check the host is ready. Every failure carries a remediation line."""
    ctx = Ctx.build(project) if project else Ctx(workspace=Ctx.build(None).workspace)

    # Recorded like any other run: "was the host green before that failure?" is a
    # question `status` should be able to answer.
    with run_record(ctx, "doctor") as log:
        report = DoctorReport.of("host", host_checks(ctx.config))
        log.event(
            "doctor.result",
            status=report.status.value,
            failed=[c.name for c in report.failures()],
            checks=len(report.checks),
        )
        if not report.ok:
            failed = ", ".join(c.name for c in report.failures())
            log.failure = f"host not ready: {failed}"

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        print_report(console, report)

    raise typer.Exit(0 if report.ok else 1)


@app.command()
def init(
    name: str = typer.Argument(..., help="project name"),
    url: str | None = typer.Option(None, "--url", help="the reference website"),
    force: bool = typer.Option(False, "--force", help="overwrite an existing config"),
) -> None:
    """Create a project workspace and config.

    Pulled forward from the brief's later command set because `vm start` needs a project
    directory to mount.
    """
    workspace = Ctx.build(None).workspace
    workspace.ensure()

    try:
        project = workspace.project(name)
    except Exception as exc:  # WorkspaceError, already user-facing
        raise fail(str(exc)) from exc

    if project.exists() and not force:
        raise fail(f"{project.config_file} already exists (use --force to overwrite)")

    template = repo_root() / "templates" / CONFIG_FILENAME
    if not template.exists():
        raise fail(f"template missing at {template}")

    project.create()
    content = template.read_text(encoding="utf-8").replace("{{PROJECT_NAME}}", name)
    if url:
        content = content.replace("url: https://example.com", f"url: {url}")
    project.config_file.write_text(content, encoding="utf-8")

    console.print(f"[green]created[/green] {project.root}")
    for directory in project.directories():
        console.print(f"  {directory.relative_to(project.root)}/")
    console.print(
        f"\nedit {project.config_file}, then: native-factory vm start --project {project.name}"
    )


@app.command()
def status(
    project: str | None = typer.Option(None, "--project", "-p"),
    limit: int = typer.Option(10, "--limit", "-n"),
) -> None:
    """What happened, from the run records -- never from an agent transcript."""
    ctx = Ctx.build(project) if project else Ctx(workspace=Ctx.build(None).workspace)
    runs = ctx.store.recent_runs(limit=limit, project=project)

    if not runs:
        console.print("no runs recorded yet")
        return

    style = {
        RunStatus.OK: "green",
        RunStatus.FAILED: "bold red",
        RunStatus.RUNNING: "yellow",
        RunStatus.ABORTED: "dim",
    }
    for run in runs:
        when = run.started_at.strftime("%Y-%m-%d %H:%M")
        colour = style.get(run.status, "white")
        project_label = f" [{run.project}]" if run.project else ""
        console.print(
            f"  [{colour}]{run.status.value:<8}[/{colour}] {when}  {run.command}{project_label}"
        )
        if run.error:
            console.print(f"           [dim]{run.error.splitlines()[0]}[/dim]")


def _register_stubs() -> None:
    for command, (milestone, summary) in STUBS.items():

        def make(cmd: str = command, ms: int = milestone, why: str = summary) -> None:
            def stub() -> None:
                raise fail(f"`{cmd}` ({why}) lands in Milestone {ms}", code=2)

            stub.__doc__ = f"[Milestone {ms}] {why}"
            app.command(cmd)(stub)

        make()


_register_stubs()
