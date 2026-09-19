"""Console rendering of a doctor report."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text

from native_factory_core.schema.run import CheckStatus, DoctorReport

STYLE = {
    CheckStatus.PASS: ("ok", "green"),
    CheckStatus.WARN: ("warn", "yellow"),
    CheckStatus.FAIL: ("FAIL", "bold red"),
    CheckStatus.SKIP: ("--", "dim"),
}


def print_report(console: Console, report: DoctorReport) -> None:
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("", width=4)
    table.add_column("check", style="bold")
    table.add_column("version")
    table.add_column("detail", overflow="fold")

    for check in report.checks:
        label, style = STYLE[check.status]
        table.add_row(Text(label, style=style), check.name, check.version or "", check.detail)

    console.print(table)

    problems = [c for c in report.checks if c.status in (CheckStatus.FAIL, CheckStatus.WARN)]
    for check in problems:
        if not check.remediation:
            continue
        _, style = STYLE[check.status]
        console.print()
        console.print(Text(check.name, style=style))
        for line in check.remediation.splitlines():
            console.print(f"  {line}")

    failures = len(report.failures())
    warnings = sum(1 for c in report.checks if c.status is CheckStatus.WARN)
    console.print()
    summary = f"{failures} failed, {warnings} warnings, {len(report.checks)} checks"
    console.print(Text(summary, style="bold red" if failures else "green"))
