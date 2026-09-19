"""Host adb: locating it, checking its version, and reaching the Tart NAT (ADR-0002)."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path

from native_factory_core.probe import Output, extract_version, run, which

#: Remote-adb behaviour has changed since the 2022 releases; the spike and the emulator
#: path both assume current behaviour.
MIN_PLATFORM_TOOLS = "35.0.0"

DEFAULT_ADB_PORT = 5037

#: Tart's vmnet subnet on macOS. Used only for the firewall rule; the guest derives the
#: gateway from its own default route rather than assuming this.
TART_NAT_CIDR = "192.168.64.0/24"


def sdk_root() -> Path | None:
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(variable)
        if value and Path(value).is_dir():
            return Path(value)
    default = Path.home() / "Library" / "Android" / "sdk"
    return default if default.is_dir() else None


def adb_path() -> str | None:
    root = sdk_root()
    if root is not None:
        candidate = root / "platform-tools" / "adb"
        if candidate.exists():
            return str(candidate)
    return which("adb")


@dataclass(frozen=True, slots=True)
class AdbVersion:
    bridge: str | None
    platform_tools: str | None


def adb_version(path: str | None = None) -> AdbVersion:
    """Parse `adb version`.

    Two numbers matter and only one is interesting: the bridge protocol version has been
    1.0.41 for years, while the second line carries the platform-tools revision.
    """
    binary = path or adb_path()
    if binary is None:
        return AdbVersion(None, None)
    output = run([binary, "version"])
    bridge = platform_tools = None
    for line in output.text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("android debug bridge"):
            bridge = extract_version(stripped)
        elif stripped.lower().startswith("version"):
            platform_tools = extract_version(stripped)
    return AdbVersion(bridge, platform_tools)


def server_argv(port: int = DEFAULT_ADB_PORT, *, listen_all: bool = True) -> list[str]:
    """Argv for a foreground adb server reachable from the guest.

    `-a` makes the server listen on all interfaces. adb cannot bind a single interface, so
    scoping it to the Tart NAT is a firewall job, not a flag (ADR-0002).
    """
    binary = adb_path() or "adb"
    argv = [binary]
    if listen_all:
        argv.append("-a")
    argv += ["-P", str(port), "server", "nodaemon"]
    return argv


def server_reachable(
    host: str = "127.0.0.1", port: int = DEFAULT_ADB_PORT, timeout: float = 1.0
) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def devices(path: str | None = None) -> list[str]:
    binary = path or adb_path()
    if binary is None:
        return []
    output: Output = run([binary, "devices"])
    serials: list[str] = []
    for line in output.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


def guest_env(
    gateway: str, port: int = DEFAULT_ADB_PORT, serial: str | None = None
) -> dict[str, str]:
    """Environment a guest needs to drive the host's emulator.

    ANDROID_SERIAL pins the leased device: every ADB client otherwise defaults to "the
    connected device", and two workers share one server (ADR-0002).
    """
    env = {"ADB_SERVER_SOCKET": f"tcp:{gateway}:{port}"}
    if serial:
        env["ANDROID_SERIAL"] = serial
    return env


def pf_anchor_rule(cidr: str = TART_NAT_CIDR, port: int = DEFAULT_ADB_PORT) -> str:
    """The packet-filter rule that scopes the adb server to the Tart NAT.

    `adb -a` binds 0.0.0.0 and has no interface option, so without this the server is
    reachable from every network the Mac is on.
    """
    return (
        f"block in proto tcp from any to any port {port}\n"
        f"pass in proto tcp from {cidr} to any port {port}\n"
    )
