"""`native-factory-guest` -- the in-guest entry point.

Installed into the golden image and invoked by the host over `tart exec`.
"""

from __future__ import annotations

import typer

from native_factory_core.render import render_report
from native_factory_guest import doctor as guest_doctor

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Native Factory in-guest runtime.",
)


@app.command()
def doctor(
    json_output: bool = typer.Option(False, "--json", help="emit machine-readable JSON"),
) -> None:
    """Check the guest toolchain."""
    report = guest_doctor.report()
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_report(report))
    raise typer.Exit(0 if report.ok else 1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
