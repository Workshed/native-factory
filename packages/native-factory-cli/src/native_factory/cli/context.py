"""Shared plumbing for CLI commands: workspace, config resolution, run records."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console

from native_factory.config.loader import CONFIG_FILENAME, ConfigError, load_config
from native_factory.runs.ids import new_run_id
from native_factory.runs.log import RunLog, log_path_for
from native_factory.runs.store import RunStore
from native_factory.workspace.layout import ProjectPaths, Workspace, WorkspaceError
from native_factory_core.schema.config import ProjectConfig
from native_factory_core.schema.run import RunRecord, RunStatus

console = Console()
err_console = Console(stderr=True)


def repo_root() -> Path:
    """The checkout this CLI was installed from, for templates and Packer files."""
    # .../packages/native-factory-cli/src/native_factory/cli/context.py
    return Path(__file__).resolve().parents[5]


def fail(message: str, code: int = 1) -> typer.Exit:
    err_console.print(f"[bold red]error[/bold red] {message}")
    return typer.Exit(code)


@dataclass(slots=True)
class Ctx:
    workspace: Workspace
    project: ProjectPaths | None = None
    config: ProjectConfig | None = None

    @classmethod
    def build(cls, project_name: str | None) -> Ctx:
        workspace = Workspace.default()
        if project_name is None:
            return cls(workspace=workspace)
        try:
            project = workspace.project(project_name)
        except WorkspaceError as exc:
            raise fail(str(exc)) from exc
        try:
            config = load_config(project.config_file)
        except ConfigError as exc:
            raise fail(str(exc)) from exc
        return cls(workspace=workspace, project=project, config=config)

    @classmethod
    def resolve_single_project(cls, project_name: str | None) -> Ctx:
        """Use the named project, or the only one if there is exactly one."""
        if project_name is not None:
            return cls.build(project_name)
        workspace = Workspace.default()
        candidates = [p for p in workspace.projects() if p.exists()]
        if len(candidates) == 1:
            return cls.build(candidates[0].name)
        if not candidates:
            raise fail(
                f"no projects in {workspace.projects_dir}\n  create one: native-factory init <name>"
            )
        names = ", ".join(p.name for p in candidates)
        raise fail(f"several projects exist ({names}); pass --project")

    @property
    def reports_dir(self) -> Path:
        return self.project.reports if self.project else self.workspace.reports

    @property
    def store(self) -> RunStore:
        self.workspace.ensure()
        return RunStore(self.workspace.state_db)


@contextmanager
def run_record(ctx: Ctx, command: str, *, vm_name: str | None = None) -> Iterator[RunLog]:
    """Open a run: a row in state.db and a JSONL log, closed out on the way past."""
    store = ctx.store
    run_id = new_run_id()
    record = RunRecord(
        id=run_id,
        command=command,
        project=ctx.project.name if ctx.project else None,
        vm_name=vm_name,
        provider=ctx.config.agent.provider if ctx.config else None,
    )
    store.start_run(record)
    log = RunLog(log_path_for(ctx.reports_dir, run_id), run_id)
    log.event("run.start", command=command, project=record.project, vm_name=vm_name)
    try:
        yield log
    except BaseException as exc:
        log.event("run.failed", error=str(exc), error_type=type(exc).__name__)
        status = RunStatus.ABORTED if isinstance(exc, KeyboardInterrupt) else RunStatus.FAILED
        store.finish_run(run_id, status, error=str(exc))
        log.close()
        raise
    log.event("run.ok")
    store.finish_run(run_id, RunStatus.OK)
    log.close()


def require_config(ctx: Ctx) -> ProjectConfig:
    if ctx.config is None:
        raise fail(f"this command needs a project; none resolved (looking for {CONFIG_FILENAME})")
    return ctx.config


def require_project(ctx: Ctx) -> ProjectPaths:
    if ctx.project is None:
        raise fail("this command needs a project; pass --project <name>")
    return ctx.project
