"""Plain-text rendering of a doctor report.

Lives in core with no rendering dependencies so the guest can print a readable report
without the host CLI's rich stack.
"""

from __future__ import annotations

from native_factory_core.schema.run import CheckStatus, DoctorReport

GLYPH = {
    CheckStatus.PASS: "ok  ",
    CheckStatus.WARN: "warn",
    CheckStatus.FAIL: "FAIL",
    CheckStatus.SKIP: "--  ",
}


def render_report(report: DoctorReport) -> str:
    lines = [f"native-factory doctor ({report.where})", ""]
    width = max((len(c.name) for c in report.checks), default=0)

    for check in report.checks:
        detail = check.detail
        if check.version:
            detail = f"{check.version}  {detail}".strip()
        lines.append(f"  {GLYPH[check.status]}  {check.name.ljust(width)}  {detail}".rstrip())

    failures = [c for c in report.checks if c.status is CheckStatus.FAIL]
    warnings = [c for c in report.checks if c.status is CheckStatus.WARN]

    for check in failures + warnings:
        if check.remediation:
            lines.append("")
            lines.append(f"{check.name}:")
            lines += [f"  {line}" for line in check.remediation.splitlines()]

    lines += ["", f"{len(failures)} failed, {len(warnings)} warnings, {len(report.checks)} checks"]
    return "\n".join(lines)
