"""AT-1: host doctor.

Runnable without Tart, so it is not marked `vm`.
"""

from __future__ import annotations

import json
import subprocess
import sys

from native_factory.doctor.checks import host_checks
from native_factory_core.schema.run import CheckStatus, DoctorReport


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "native_factory", *args], capture_output=True, text=True
    )


def test_doctor_emits_parseable_json() -> None:
    result = run_cli("doctor", "--json")
    payload = json.loads(result.stdout)
    assert payload["where"] == "host"
    assert isinstance(payload["ok"], bool)
    assert payload["checks"]


def test_exit_code_tracks_the_verdict() -> None:
    result = run_cli("doctor", "--json")
    payload = json.loads(result.stdout)
    assert (result.returncode == 0) is payload["ok"]


def test_every_check_reports_a_name_and_a_status() -> None:
    payload = json.loads(run_cli("doctor", "--json").stdout)
    for check in payload["checks"]:
        assert check["name"]
        assert check["status"] in {"pass", "fail", "warn", "skip"}


def test_every_failure_is_actionable() -> None:
    # AT-1: "Make failures actionable" (the brief). An unactionable doctor is just a
    # slower error message.
    for check in host_checks():
        if check.status is CheckStatus.FAIL:
            assert check.remediation, f"{check.name} fails without a remediation"


def test_missing_tart_names_the_tap(monkeypatch) -> None:
    from native_factory.doctor import checks

    monkeypatch.setattr(checks, "which", lambda _: None)
    result = checks.check_tart()
    assert result.status is CheckStatus.FAIL
    assert "brew install openai/tools/tart" in (result.remediation or "")


def test_report_status_is_the_worst_check() -> None:
    report = DoctorReport.of("host", host_checks())
    if report.failures():
        assert report.status is CheckStatus.FAIL
        assert report.ok is False
