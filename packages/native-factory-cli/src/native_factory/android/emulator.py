"""Host Android Emulator discovery.

The emulator runs on the host, never in the macOS guest: an ARM64 AVD needs
Hypervisor.framework and fails with HV_UNSUPPORTED when nested (ADR-0002).
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

from native_factory.android.adb import sdk_root
from native_factory_core.probe import run, which

ARM64_ABIS = ("arm64-v8a", "arm64", "aarch64")


def emulator_path() -> str | None:
    root = sdk_root()
    if root is not None:
        candidate = root / "emulator" / "emulator"
        if candidate.exists():
            return str(candidate)
    return which("emulator")


def avd_home() -> Path:
    return Path.home() / ".android" / "avd"


@dataclass(frozen=True, slots=True)
class Avd:
    name: str
    abi: str | None = None

    @property
    def is_arm64(self) -> bool:
        if self.abi is None:
            return False
        return any(token in self.abi.lower() for token in ARM64_ABIS)


def _avd_abi(name: str) -> str | None:
    config = avd_home() / f"{name}.avd" / "config.ini"
    if not config.exists():
        return None
    parser = configparser.ConfigParser()
    # AVD config.ini is a bare key=value file with no section header.
    try:
        parser.read_string("[avd]\n" + config.read_text(encoding="utf-8", errors="replace"))
    except configparser.Error:
        return None
    section = parser["avd"]
    return section.get("abi.type") or section.get("hw.cpu.arch")


def list_avds(path: str | None = None) -> list[Avd]:
    binary = path or emulator_path()
    if binary is None:
        return []
    output = run([binary, "-list-avds"])
    names = [line.strip() for line in output.stdout.splitlines() if line.strip()]
    return [Avd(name=name, abi=_avd_abi(name)) for name in names]


def start_argv(avd: str, *, window: bool = False, port: int | None = None) -> list[str]:
    """Headless-by-default emulator launch (HANDOFF section 4.5)."""
    argv = [emulator_path() or "emulator", "-avd", avd, "-no-audio", "-no-boot-anim"]
    if not window:
        argv += ["-no-window", "-gpu", "swiftshader_indirect"]
    if port is not None:
        argv += ["-port", str(port)]
    return argv
