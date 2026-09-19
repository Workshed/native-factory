"""Host doctor checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from native_factory.doctor import checks
from native_factory_core.schema.config import ProjectConfig
from native_factory_core.schema.run import CheckStatus, DoctorReport

MINIMAL = {"project": {"name": "demo"}}


class TestPlatform:
    def test_apple_silicon_passes_on_arm64(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(checks.platform, "machine", lambda: "arm64")
        assert checks.check_apple_silicon().status is CheckStatus.PASS

    def test_intel_fails_with_a_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(checks.platform, "machine", lambda: "x86_64")
        result = checks.check_apple_silicon()
        assert result.status is CheckStatus.FAIL
        assert "Virtualization.framework" in (result.remediation or "")

    def test_macos_floor_is_only_applied_when_asked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(checks.platform, "mac_ver", lambda: ("26.5.2", ("", "", ""), "arm64"))
        assert checks.check_macos().status is CheckStatus.PASS
        assert checks.check_macos(required="26.6").status is CheckStatus.FAIL


class TestDiskSpace:
    def _usage(self, free_gb: float):
        class Usage:
            total = 4_000 * 1024**3
            used = 0
            free = int(free_gb * 1024**3)

        return Usage()

    def test_fails_below_the_floor(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(checks.shutil, "disk_usage", lambda _: self._usage(100))
        result = checks.check_disk_space(tmp_path)
        assert result.status is CheckStatus.FAIL
        assert "140 GB on disk" in (result.remediation or "")

    def test_warns_when_tight_for_two_workers(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(checks.shutil, "disk_usage", lambda _: self._usage(300))
        assert checks.check_disk_space(tmp_path).status is CheckStatus.WARN

    def test_passes_with_room(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(checks.shutil, "disk_usage", lambda _: self._usage(2000))
        assert checks.check_disk_space(tmp_path).status is CheckStatus.PASS


class TestTart:
    def test_missing_tart_names_the_tap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(checks, "which", lambda _: None)
        result = checks.check_tart()
        assert result.status is CheckStatus.FAIL
        assert "brew install openai/tools/tart" in (result.remediation or "")

    def test_guest_agent_without_brew_warns_rather_than_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(checks, "which", lambda name: None if name == "brew" else "/bin/x")
        assert checks.check_tart_guest_agent().status is CheckStatus.WARN


class TestSoftnet:
    def test_skipped_while_egress_is_open(self) -> None:
        config = ProjectConfig.model_validate(MINIMAL)
        result = checks.check_softnet(config)
        assert result.status is CheckStatus.SKIP
        assert "ADR-0006" in result.detail

    def test_required_once_egress_is_an_allowlist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(checks, "which", lambda _: "/opt/homebrew/bin/brew")
        monkeypatch.setattr(checks, "run", lambda *a, **k: type("O", (), {"ok": False})())
        config = ProjectConfig.model_validate(
            {**MINIMAL, "vm": {"egress": "allowlist", "egress_allowlist": ["example.com"]}}
        )
        assert checks.check_softnet(config).status is CheckStatus.FAIL


class TestAndroid:
    def test_legacy_cli_fails_the_host_doctor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # AT-1's regression test: a presence check would pass here, because the legacy
        # script exits 0.
        monkeypatch.setattr(
            checks,
            "classify_android_cli",
            lambda: (checks.AndroidCliKind.LEGACY, "/x/sdk/tools/android", None),
        )
        result = checks.check_android_cli()
        assert result.status is CheckStatus.FAIL
        assert "exits 0" in (result.remediation or "")

    def test_absent_cli_is_skipped_because_the_guest_provides_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            checks, "classify_android_cli", lambda: (checks.AndroidCliKind.ABSENT, None, None)
        )
        assert checks.check_android_cli().status is CheckStatus.SKIP

    def test_old_platform_tools_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(checks.adb, "adb_path", lambda: "/x/platform-tools/adb")
        monkeypatch.setattr(
            checks.adb, "adb_version", lambda _: checks.adb.AdbVersion("1.0.41", "33.0.1")
        )
        result = checks.check_platform_tools()
        assert result.status is CheckStatus.FAIL
        assert "35.0.0+" in (result.remediation or "")

    def test_current_platform_tools_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(checks.adb, "adb_path", lambda: "/x/platform-tools/adb")
        monkeypatch.setattr(
            checks.adb, "adb_version", lambda _: checks.adb.AdbVersion("1.0.41", "36.0.0")
        )
        assert checks.check_platform_tools().status is CheckStatus.PASS

    def test_absent_adb_server_warns_because_it_is_stage_specific(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(checks.adb, "server_reachable", lambda *a, **k: False)
        result = checks.check_adb_server()
        assert result.status is CheckStatus.WARN
        assert "192.168.64.0/24" in (result.remediation or "")


class TestAssembly:
    def test_android_checks_are_skipped_when_the_emulator_is_elsewhere(self) -> None:
        config = ProjectConfig.model_validate(
            {**MINIMAL, "targets": {"android": {"enabled": False}}}
        )
        names = {c.name for c in checks.host_checks(config)}
        assert "android-platform-tools" not in names

    def test_android_checks_run_for_the_host_emulator(self) -> None:
        config = ProjectConfig.model_validate(MINIMAL)
        names = {c.name for c in checks.host_checks(config)}
        assert {"android-emulator", "android-platform-tools", "android-avd"} <= names

    def test_report_status_is_the_worst_outcome(self) -> None:
        results = checks.host_checks(ProjectConfig.model_validate(MINIMAL))
        report = DoctorReport.of("host", results)
        worst = CheckStatus.FAIL if report.failures() else report.status
        assert report.status is worst
        assert report.ok is (not report.failures())

    def test_every_failure_carries_a_remediation(self) -> None:
        # An unactionable doctor is just a slower error message.
        for check in checks.host_checks(ProjectConfig.model_validate(MINIMAL)):
            if check.status is CheckStatus.FAIL:
                assert check.remediation, f"{check.name} fails without telling the user what to do"
