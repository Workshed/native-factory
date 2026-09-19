"""Small helpers for detecting installed tools.

Shared by the host doctor and the guest doctor so both report the same JSON shape and use
the same version comparison rules.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

_VERSION_RE = re.compile(r"\b(\d+(?:\.\d+){1,3})\b")

DEFAULT_TIMEOUT = 20.0


@dataclass(frozen=True, slots=True)
class Output:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    code: int = 0

    @property
    def text(self) -> str:
        return f"{self.stdout}\n{self.stderr}".strip()


def which(binary: str) -> str | None:
    return shutil.which(binary)


def run(argv: Sequence[str], timeout: float = DEFAULT_TIMEOUT) -> Output:
    """Run a command, never raising. Absence and failure are both ordinary results here."""
    try:
        result = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return Output(ok=False)
    return Output(
        ok=result.returncode == 0,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
        code=result.returncode,
    )


def extract_version(text: str) -> str | None:
    match = _VERSION_RE.search(text or "")
    return match.group(1) if match else None


def version_tuple(version: str | None) -> tuple[int, ...]:
    if not version:
        return ()
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def at_least(found: str | None, required: str) -> bool:
    """True when `found` is >= `required`. An unparseable version is not "at least"."""
    left, right = version_tuple(found), version_tuple(required)
    if not left:
        return False
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) >= right + (0,) * (width - len(right))


def tool_version(binary: str, args: Sequence[str] = ("--version",)) -> str | None:
    """Best-effort version string for a binary on PATH."""
    if which(binary) is None:
        return None
    output = run([binary, *args])
    return extract_version(output.text)
