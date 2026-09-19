"""Telling the first-party `android` CLI from the legacy script of the same name.

This is not hypothetical: the development host has the legacy script on PATH, it exits 0,
and a naive presence check passes against it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from native_factory.android import cli
from native_factory_core.probe import Output


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch):
    responses: dict[tuple[str, ...], Output] = {}

    def runner(argv, timeout=20.0):
        return responses.get(tuple(argv), Output(ok=False))

    monkeypatch.setattr(cli, "run", runner)
    return responses


def test_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "which", lambda _: None)
    kind, path, _version = cli.classify()
    assert kind is cli.AndroidCliKind.ABSENT
    assert path is None


def test_legacy_detected_by_path_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    # .../sdk/tools/android is the pre-2018 layout; the first-party CLI is never there.
    legacy = "/Users/x/Library/Android/sdk/tools/android"
    monkeypatch.setattr(cli, "which", lambda _: legacy)
    kind, path, _ = cli.classify()
    assert kind is cli.AndroidCliKind.LEGACY
    assert path == legacy


def test_legacy_detected_by_output_despite_exit_zero(
    monkeypatch: pytest.MonkeyPatch, fake_run: dict
) -> None:
    # The real trap: the script exits 0, so only its text distinguishes it.
    elsewhere = "/usr/local/bin/android"
    monkeypatch.setattr(cli, "which", lambda _: elsewhere)
    fake_run[(elsewhere, "--version")] = Output(
        ok=True, stdout='The "android" command is deprecated.\nUse Android Studio.'
    )
    kind, _, _ = cli.classify()
    assert kind is cli.AndroidCliKind.LEGACY


def test_legacy_detected_from_help_when_version_is_silent(
    monkeypatch: pytest.MonkeyPatch, fake_run: dict
) -> None:
    elsewhere = "/usr/local/bin/android"
    monkeypatch.setattr(cli, "which", lambda _: elsewhere)
    fake_run[(elsewhere, "--version")] = Output(ok=True, stdout="")
    fake_run[(elsewhere, "--help")] = Output(
        ok=True, stdout="use tools/bin/sdkmanager and avdmanager"
    )
    assert cli.classify()[0] is cli.AndroidCliKind.LEGACY


def test_first_party_is_accepted(monkeypatch: pytest.MonkeyPatch, fake_run: dict) -> None:
    modern = "/opt/homebrew/bin/android"
    monkeypatch.setattr(cli, "which", lambda _: modern)
    fake_run[(modern, "--version")] = Output(ok=True, stdout="android 1.4.0")
    kind, path, version = cli.classify()
    assert kind is cli.AndroidCliKind.FIRST_PARTY
    assert path == modern
    assert version == "1.4.0"


def test_explicit_path_overrides_lookup(monkeypatch: pytest.MonkeyPatch, fake_run: dict) -> None:
    monkeypatch.setattr(cli, "which", lambda _: "/should/not/be/used")
    given = "/somewhere/tools/android"
    assert cli.classify(given)[0] is cli.AndroidCliKind.LEGACY
    assert Path(given).parent.name == "tools"


def test_remediation_names_the_real_cause() -> None:
    assert "exits 0" in cli.LEGACY_REMEDIATION
    assert "android-cli" in cli.LEGACY_REMEDIATION
