"""Guest doctor checks and host-side dispatch."""

from __future__ import annotations

import json
import subprocess

import pytest

from native_factory.doctor.guest import GUEST_ENTRY, run_guest_doctor
from native_factory.vm.tart import Tart, TartError
from native_factory_core.schema.run import CheckStatus, DoctorReport
from native_factory_guest import doctor as guest_doctor


class TestEmulatorAbsence:
    def test_absent_emulator_is_a_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Unusual shape: the check passes when the tool is missing. An ARM64 emulator
        # cannot be accelerated inside a macOS guest, so its presence is a build error.
        monkeypatch.setattr(guest_doctor, "which", lambda _: None)
        result = guest_doctor.check_emulator_absent()
        assert result.status is CheckStatus.PASS
        assert "as intended" in result.detail

    def test_present_emulator_fails_with_the_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guest_doctor, "which", lambda _: "/x/emulator/emulator")
        result = guest_doctor.check_emulator_absent()
        assert result.status is CheckStatus.FAIL
        assert "HV_UNSUPPORTED" in (result.remediation or "")
        assert "ADR-0002" in (result.remediation or "")


class TestGuestAndroidCli:
    def test_legacy_layout_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guest_doctor, "which", lambda _: "/opt/sdk/tools/android")
        assert guest_doctor.check_android_cli().status is CheckStatus.FAIL

    def test_deprecation_text_fails_even_at_exit_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(guest_doctor, "which", lambda _: "/opt/homebrew/bin/android")
        monkeypatch.setattr(
            guest_doctor,
            "run",
            lambda *a, **k: guest_doctor.Output(ok=True, stdout="command is deprecated"),
        )
        assert guest_doctor.check_android_cli().status is CheckStatus.FAIL


class TestAgentServer:
    def test_missing_openhands_is_expected_before_milestone_2(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(guest_doctor, "VENV_PYTHON", tmp_path / "python")
        assert guest_doctor.check_agent_server().status is CheckStatus.SKIP


class FakeTart(Tart):
    def __init__(self, stdout: str = "", stderr: str = "", code: int = 0, raises: bool = False):
        super().__init__()
        self._stdout, self._stderr, self._code, self._raises = stdout, stderr, code, raises

    def exec(self, name, command, *, env=None, check=True):
        if self._raises:
            raise TartError("VM not running")
        return subprocess.CompletedProcess(
            args=list(command), returncode=self._code, stdout=self._stdout, stderr=self._stderr
        )


class TestDispatch:
    def _valid_report(self) -> str:
        report = DoctorReport.of("guest", [])
        return report.model_dump_json()

    def test_parses_a_valid_report(self) -> None:
        report = run_guest_doctor(FakeTart(stdout=self._valid_report()), "nf-w1")
        assert report.where == "guest"
        assert report.ok is True

    def test_unreachable_vm_becomes_a_failed_check_not_an_exception(self) -> None:
        # The caller wants a report either way.
        report = run_guest_doctor(FakeTart(raises=True), "nf-w1")
        assert report.ok is False
        assert report.checks[0].name == "guest-doctor"
        assert "vm start" in (report.checks[0].remediation or "")

    def test_empty_output_suggests_rebuilding_the_image(self) -> None:
        report = run_guest_doctor(FakeTart(stdout="", stderr="not found"), "nf-w1")
        assert report.ok is False
        assert "vm create --force" in (report.checks[0].remediation or "")

    def test_unparseable_output_is_reported_not_raised(self) -> None:
        report = run_guest_doctor(FakeTart(stdout="this is not json"), "nf-w1")
        assert report.ok is False
        assert "could not parse" in report.checks[0].detail

    def test_entry_point_lives_in_the_factory_venv(self) -> None:
        assert GUEST_ENTRY.startswith("/opt/native-factory/venv")


def test_guest_report_is_valid_against_the_schema() -> None:
    report = DoctorReport.of("guest", guest_doctor.guest_checks())
    payload = json.loads(report.model_dump_json())
    assert payload["where"] == "guest"
    assert isinstance(payload["ok"], bool)
    assert len(payload["checks"]) == len(report.checks)
