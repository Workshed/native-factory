#!/usr/bin/env python3
"""Check a host or guest is ready for the Native Factory prototype.

Deliberately a single stdlib-only file with no package, no dependencies and no CLI
framework. It earned its place on day one by turning an opaque Homebrew failure into a
twenty-second diagnosis; it has not earned anything more than this.

    python3 scripts/doctor.py            # host checks
    python3 scripts/doctor.py --guest    # run inside the Tart VM
    python3 scripts/doctor.py --json

Every failure carries a remediation line. An unactionable doctor is just a slower error
message.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"
GLYPH = {PASS: "ok  ", WARN: "warn", FAIL: "FAIL", SKIP: "--  "}

#: The base Xcode image is ~69 GB compressed and ~140 GB on disk.
MIN_FREE_GB = 120

#: Remote-adb behaviour changed after the 2022 releases, and the guest reaches the host's
#: adb server over the Tart NAT.
MIN_PLATFORM_TOOLS = "35.0.0"

#: A 16 GB guest plus an Android emulator needs roughly this much free before starting.
#: On 2026-09-24 macOS killed both -- the VM and the emulator -- under memory pressure,
#: with 42 GB sitting in the compressor. Nothing was lost, because output lives on the
#: host mount, but an hour of build state went with them.
MIN_FREE_MEMORY_GB = 24

ADB_PORT = 5037
TART_NAT_CIDR = "192.168.64.0/24"
TART_TAP = "openai/tools"

# Not \b: there is no word boundary between the "v" and the "2" of `v24.5.0`, so a
# leading \b makes the match start at ".5.0" and report 5.0. Anchor on "not preceded by
# a digit or a dot" instead.
_VERSION = re.compile(r"(?<![\d.])(\d+(?:\.\d+){1,3})")


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""
    version: str | None = None
    fix: str | None = None


@dataclass
class Report:
    where: str
    checks: list[Check] = field(default_factory=list)

    def add(self, check: Check) -> None:
        self.checks.append(check)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def ok(self) -> bool:
        return not self.failures


# -- helpers ------------------------------------------------------------------------


def run(argv: list[str], timeout: float = 20.0) -> tuple[bool, str]:
    """Run a command, never raising. Absence and failure are ordinary results here."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    return proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}".strip()


def version_of(text: str) -> str | None:
    match = _VERSION.search(text or "")
    return match.group(1) if match else None


def at_least(found: str | None, required: str) -> bool:
    """Numeric comparison. An unparseable version is never 'at least'."""
    if not found:
        return False
    left = tuple(int(p) for p in found.split(".") if p.isdigit())
    right = tuple(int(p) for p in required.split(".") if p.isdigit())
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) >= right + (0,) * (width - len(right))


def tool(name: str, binary: str, args: tuple[str, ...] = ("--version",), minimum: str | None = None,
         fix: str | None = None) -> Check:
    path = shutil.which(binary)
    if path is None:
        return Check(name, FAIL, f"{binary} not on PATH", fix=fix or f"install {binary}")
    version = version_of(run([binary, *args])[1])
    if minimum and not at_least(version, minimum):
        return Check(name, FAIL, f"{binary} {version or 'unknown'} < {minimum}", version,
                     fix or f"upgrade {binary} to {minimum}+")
    return Check(name, PASS, path, version)


def android_sdk() -> Path | None:
    import os

    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(var)
        if value and Path(value).is_dir():
            return Path(value)
    default = Path.home() / "Library" / "Android" / "sdk"
    return default if default.is_dir() else None


def adb_path() -> str | None:
    root = android_sdk()
    if root and (root / "platform-tools" / "adb").exists():
        return str(root / "platform-tools" / "adb")
    return shutil.which("adb")


def legacy_android_cli() -> tuple[str, str | None]:
    """Classify `android` on PATH.

    The deprecated 2017 SDK Tools script shares the name of the first-party CLI and
    **exits 0**, so a presence check passes against the wrong binary. Classify by
    behaviour: path layout first, then output text.
    """
    path = shutil.which("android")
    if path is None:
        return "absent", None
    if Path(path).parent.name == "tools":
        return "legacy", path
    text = (run([path, "--version"])[1] + run([path, "--help"])[1]).lower()
    if "deprecated" in text or "no longer available" in text or "sdkmanager and avdmanager" in text:
        return "legacy", path
    return "first-party", path


# -- host -----------------------------------------------------------------------------


def host_checks() -> Report:
    report = Report("host")

    machine = platform.machine()
    report.add(
        Check("apple-silicon", PASS if machine == "arm64" else FAIL, machine, machine,
              None if machine == "arm64" else
              "Tart uses Virtualization.framework and the iOS toolchain is arm64-only.")
    )

    macos = platform.mac_ver()[0]
    report.add(Check("macos", PASS if macos else FAIL, f"macOS {macos}" if macos else "not macOS",
                     macos or None, None if macos else "Native Factory runs on macOS hosts only."))

    free_gb = shutil.disk_usage(Path.home()).free / 1024**3
    report.add(
        Check("disk-space", PASS if free_gb >= MIN_FREE_GB else FAIL, f"{free_gb:.0f} GB free",
              f"{free_gb:.0f}GB",
              None if free_gb >= MIN_FREE_GB else
              f"Need ~{MIN_FREE_GB} GB: the Xcode base image is ~69 GB compressed, ~140 GB on disk.")
    )

    report.add(tool("tart", "tart", fix=f"brew install {TART_TAP}/tart {TART_TAP}/tart-guest-agent"))
    report.add(check_memory())

    if shutil.which("brew"):
        installed = run(["brew", "list", "--formula", "tart-guest-agent"])[0]
        report.add(Check("tart-guest-agent", PASS if installed else FAIL,
                         "installed" if installed else "not installed", None,
                         None if installed else
                         f"brew install {TART_TAP}/tart-guest-agent\n"
                         "  Without it `tart exec` has no vsock channel into the guest."))
    else:
        report.add(Check("tart-guest-agent", WARN, "brew unavailable, cannot verify"))

    report.add(tool("node", "node", minimum="22.12",
                    fix="Node 22.12+ is required by Agent Canvas and the Copilot CLI."))

    # Android: the emulator runs on the HOST, never in the macOS guest -- an ARM64 AVD
    # needs Hypervisor.framework and fails with HV_UNSUPPORTED when nested.
    root = android_sdk()
    emulator = str(root / "emulator" / "emulator") if root and (root / "emulator" / "emulator").exists() \
        else shutil.which("emulator")
    report.add(Check("android-emulator", PASS if emulator else FAIL, emulator or "not found", None,
                     None if emulator else
                     "The emulator runs on the host, not in the guest (docs/adr/0002).\n"
                     "  sdkmanager --install emulator"))

    adb = adb_path()
    if adb is None:
        report.add(Check("android-platform-tools", FAIL, "adb not found", None,
                         "sdkmanager --install platform-tools"))
    else:
        pt = None
        for line in run([adb, "version"])[1].splitlines():
            if line.strip().lower().startswith("version"):
                pt = version_of(line)
        good = at_least(pt, MIN_PLATFORM_TOOLS)
        report.add(Check("android-platform-tools", PASS if good else FAIL, adb, pt,
                         None if good else
                         f"Upgrade to {MIN_PLATFORM_TOOLS}+: remote-adb behaviour changed after the\n"
                         "  2022 releases and the guest reaches this server over the Tart NAT.\n"
                         "  sdkmanager --install platform-tools"))

    if emulator:
        avds = [a for a in run([emulator, "-list-avds"])[1].splitlines() if a.strip()]
        report.add(Check("android-avd", PASS if avds else FAIL,
                         f"{len(avds)} AVD(s): {', '.join(avds)}" if avds else "none defined", None,
                         None if avds else "android emulator create --name nf-pixel --api 36"))

    listening = False
    try:
        with socket.create_connection(("127.0.0.1", ADB_PORT), timeout=1.0):
            listening = True
    except OSError:
        pass
    report.add(Check("android-adb-server", PASS if listening else WARN,
                     f"listening on :{ADB_PORT}" if listening else "not running", None,
                     None if listening else
                     "Only needed during Android work. Start one the guest can reach:\n"
                     f"  adb -a -P {ADB_PORT} server nodaemon\n"
                     f"  and firewall {ADB_PORT} to {TART_NAT_CIDR} -- `adb -a` binds 0.0.0.0\n"
                     "  and cannot bind a single interface (docs/adr/0002)."))

    kind, path = legacy_android_cli()
    if kind == "legacy":
        # A warning on the host: nothing here invokes `android`. A failure in the guest,
        # which runs `android create`.
        report.add(Check("android-cli", WARN, f"legacy SDK Tools script at {path}", None,
                         "'android' on PATH is the deprecated script, which exits 0 and does\n"
                         "  nothing. Remove $ANDROID_HOME/tools from PATH.\n"
                         "  https://developer.android.com/tools/agents/android-cli"))
    elif kind == "absent":
        report.add(Check("android-cli", SKIP, "not on PATH (the guest provides it)"))
    else:
        report.add(Check("android-cli", PASS, path or ""))

    return report


def check_memory() -> Check:
    """Free memory, as macOS actually reports it.

    vm_stat's "free" pages alone are misleading on macOS -- it keeps very little strictly
    free and reclaims from the inactive and purgeable pools on demand. Counting those in
    matches what is really available to a starting VM.
    """
    ok, out = run(["vm_stat"])
    if not ok:
        return Check("memory", SKIP, "vm_stat unavailable")

    page = 16384
    stats = {}
    for line in out.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            digits = v.strip().rstrip(".")
            if digits.isdigit():
                stats[k.strip()] = int(digits)
        if "page size of" in line:
            for token in line.split():
                if token.isdigit():
                    page = int(token)

    available = sum(
        stats.get(k, 0)
        for k in ("Pages free", "Pages inactive", "Pages purgeable", "Pages speculative")
    ) * page / 1024**3
    compressed = stats.get("Pages occupied by compressor", 0) * page / 1024**3
    detail = f"{available:.0f} GB available, {compressed:.0f} GB compressed"

    if available < MIN_FREE_MEMORY_GB:
        return Check("memory", FAIL, detail, f"{available:.0f}GB",
                     f"A 16 GB guest plus an Android emulator wants ~{MIN_FREE_MEMORY_GB} GB free.\n"
                     "  macOS has killed both under pressure before. Quit what you can, or\n"
                     "  lower vm.memory: tart set nf --memory 12288")
    if compressed > available:
        return Check("memory", WARN, detail, f"{available:.0f}GB",
                     "More memory is compressed than is available; the machine is already\n"
                     "  working hard. Starting a VM and an emulator now may get them killed.")
    return Check("memory", PASS, detail, f"{available:.0f}GB")


# -- guest ----------------------------------------------------------------------------


def guest_checks() -> Report:
    report = Report("guest")

    ok, text = run(["xcodebuild", "-version"])
    report.add(Check("xcode", PASS if ok else FAIL, text.splitlines()[0] if ok else "unavailable",
                     version_of(text), None if ok else "sudo xcodebuild -license accept"))

    ok, text = run(["xcrun", "simctl", "list", "runtimes", "-j"])
    count = text.count('"identifier"') if ok else 0
    report.add(Check("ios-simulator-runtimes", PASS if count else FAIL, f"{count} runtime(s)",
                     None, None if count else "xcodebuild -downloadPlatform iOS"))

    report.add(tool("git", "git"))
    report.add(tool("jdk", "java", ("-version",), minimum="17"))
    report.add(tool("node", "node", minimum="22.12"))
    report.add(tool("adb", "adb", ("version",)))
    report.add(tool("maestro", "maestro", fix="curl -Ls https://get.maestro.mobile.dev | bash"))

    ok, text = run(["npx", "--no-install", "playwright", "--version"])
    report.add(Check("playwright", PASS if ok else FAIL, "installed" if ok else "not installed",
                     version_of(text), None if ok else
                     "npm i -g playwright && playwright install chromium webkit"))

    # At least one ACP-capable coding agent must be present.
    agents = {name: shutil.which(binary) for name, binary in
              (("claude-code", "claude"), ("copilot", "copilot"))}
    present = {n: p for n, p in agents.items() if p}
    report.add(Check("coding-agent", PASS if present else FAIL,
                     ", ".join(sorted(present)) if present else "none found", None,
                     None if present else
                     "Install at least one:\n"
                     "  npm i -g @github/copilot        then: copilot  -> /login\n"
                     "  https://code.claude.com/docs    then: claude   -> /login"))

    kind, path = legacy_android_cli()
    report.add(Check("android-cli", PASS if kind == "first-party" else FAIL,
                     path or "not on PATH", None,
                     None if kind == "first-party" else
                     "The guest runs `android create`, so it needs the first-party CLI.\n"
                     "  Remove $ANDROID_HOME/tools from PATH; that script exits 0 and does nothing."))

    # A pass here is the ABSENCE of a tool, which is unusual enough to state: an ARM64
    # emulator cannot be accelerated inside a macOS guest, so its presence is a mistake.
    emulator = shutil.which("emulator")
    report.add(Check("android-emulator-absent", PASS if not emulator else FAIL,
                     "absent, as intended (it runs on the host)" if not emulator
                     else f"present at {emulator}", None,
                     None if not emulator else
                     "Remove it. An ARM64 AVD needs Hypervisor.framework and fails with\n"
                     "  HV_UNSUPPORTED when nested. See docs/adr/0002."))

    return report


# -- output ----------------------------------------------------------------------------


def render(report: Report) -> str:
    lines = [f"native-factory doctor ({report.where})", ""]
    width = max((len(c.name) for c in report.checks), default=0)
    for check in report.checks:
        detail = f"{check.version}  {check.detail}".strip() if check.version else check.detail
        lines.append(f"  {GLYPH[check.status]}  {check.name.ljust(width)}  {detail}".rstrip())
    for check in report.checks:
        if check.fix and check.status in (FAIL, WARN):
            lines += ["", f"{check.name}:"] + [f"  {ln}" for ln in check.fix.splitlines()]
    warns = sum(1 for c in report.checks if c.status == WARN)
    lines += ["", f"{len(report.failures)} failed, {warns} warnings, {len(report.checks)} checks"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--guest", action="store_true", help="run the in-VM checks")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    report = guest_checks() if args.guest else host_checks()

    if args.as_json:
        print(json.dumps({
            "where": report.where,
            "ok": report.ok,
            "checks": [vars(c) for c in report.checks],
        }, indent=2))
    else:
        print(render(report))

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
