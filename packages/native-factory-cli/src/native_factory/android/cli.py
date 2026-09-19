"""Telling the first-party `android` CLI apart from the legacy script of the same name.

HANDOFF section 4.8 specifies the first-party `android` CLI (`android sdk install`,
`android emulator create|start`, `android create --name=...`). An SDK installed before
2018 ships a completely different `tools/android` script with the same name, which prints
a deprecation banner and **exits 0**. A presence check therefore passes against the wrong
binary and `android create` silently does nothing useful.

Measured on the development host on 2026-09-19:

    $ command -v android
    /Users/.../Library/Android/sdk/tools/android
    $ android --help
    The "android" command is deprecated. ... use tools/bin/sdkmanager and avdmanager
    $ echo $?
    0
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from native_factory_core.probe import run, which

#: Phrases the legacy script prints. It exits 0, so the text is the only signal.
_LEGACY_MARKERS = (
    "command is deprecated",
    "no longer available",
    "use android studio",
    "sdkmanager and avdmanager",
)


class AndroidCliKind(StrEnum):
    ABSENT = "absent"
    FIRST_PARTY = "first-party"
    LEGACY = "legacy"


def classify(path: str | None = None) -> tuple[AndroidCliKind, str | None, str | None]:
    """Return (kind, resolved path, version).

    Classification is by behaviour, not by presence: the legacy script exits 0 and is
    indistinguishable from a working tool unless its output is read.
    """
    resolved = path or which("android")
    if resolved is None:
        return AndroidCliKind.ABSENT, None, None

    # A path ending in .../sdk/tools/android is the legacy layout; the first-party CLI is
    # not installed there. Cheap to check and true even if the script is unreadable.
    if Path(resolved).parent.name == "tools":
        return AndroidCliKind.LEGACY, resolved, None

    output = run([resolved, "--version"])
    text = output.text.lower()
    if any(marker in text for marker in _LEGACY_MARKERS):
        return AndroidCliKind.LEGACY, resolved, None

    help_output = run([resolved, "--help"])
    if any(marker in help_output.text.lower() for marker in _LEGACY_MARKERS):
        return AndroidCliKind.LEGACY, resolved, None

    from native_factory_core.probe import extract_version

    return AndroidCliKind.FIRST_PARTY, resolved, extract_version(output.text)


LEGACY_REMEDIATION = (
    "'android' on PATH is the deprecated SDK Tools script, which exits 0 and does nothing.\n"
    "  Remove $ANDROID_HOME/tools from PATH and install the first-party CLI:\n"
    "    https://developer.android.com/tools/agents/android-cli"
)
