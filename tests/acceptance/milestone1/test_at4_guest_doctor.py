"""AT-4: the guest doctor reports every tool with a version."""

from __future__ import annotations

import pytest

from native_factory.doctor.guest import run_guest_doctor
from native_factory.vm.tart import Tart
from native_factory_core.schema.run import CheckStatus

pytestmark = pytest.mark.vm

EXPECTED = {
    "xcode",
    "ios-simulator-runtimes",
    "git",
    "jdk",
    "adb",
    "android-cli",
    "android-emulator-absent",
    "node",
    "playwright",
    "maestro",
    "agent-device",
    "xcodebuildmcp",
    "uv",
    "factory-venv",
    "image-manifest",
}


@pytest.fixture
def report(tart: Tart, worker: str):
    return run_guest_doctor(tart, worker)


def test_every_expected_tool_is_checked(report) -> None:
    assert {c.name for c in report.checks} >= EXPECTED


def test_no_check_fails(report) -> None:
    failures = [f"{c.name}: {c.detail}" for c in report.failures()]
    assert not failures, "\n".join(failures)


def test_passing_checks_carry_a_version_or_a_detail(report) -> None:
    for check in report.checks:
        if check.status is CheckStatus.PASS:
            assert check.version or check.detail, f"{check.name} passed with nothing to show"


def test_android_cli_is_the_first_party_tool(report) -> None:
    # Not the legacy SDK Tools script, which shares the name and exits 0 (HANDOFF 4.8).
    check = next(c for c in report.checks if c.name == "android-cli")
    assert check.status is CheckStatus.PASS
    assert "tools/android" not in check.detail


def test_the_emulator_is_absent_from_the_image(report) -> None:
    # Its presence is a build error: an ARM64 AVD cannot be accelerated in a macOS guest.
    check = next(c for c in report.checks if c.name == "android-emulator-absent")
    assert check.status is CheckStatus.PASS
