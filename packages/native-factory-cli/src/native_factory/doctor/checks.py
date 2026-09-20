"""Host preflight checks.

Every failure carries a remediation line: an unactionable doctor is just a slower error
message. Checks are pure-ish functions returning CheckResult so they can be unit-tested by
monkeypatching the probe helpers rather than by installing tools.
"""

from __future__ import annotations

import platform
import shutil
from collections.abc import Callable
from pathlib import Path

from native_factory.android import adb, emulator
from native_factory.android.cli import LEGACY_REMEDIATION, AndroidCliKind
from native_factory.android.cli import classify as classify_android_cli
from native_factory_core.probe import at_least, extract_version, run, tool_version, which
from native_factory_core.schema.config import Egress, ProjectConfig
from native_factory_core.schema.run import CheckResult, CheckStatus

#: Two workers plus a ~70 GB OCI cache plus up to ~140 GB sparse per worker. HANDOFF
#: section 4.4 suggests ~200 GB; that is a one-worker floor.
MIN_FREE_GB = 250
COMFORTABLE_FREE_GB = 400

#: Xcode 27 requires macOS 26.6+. Only enforced when the pinned image needs it.
MACOS_FLOOR_FOR_XCODE_27 = "26.6"

TART_TAP = "openai/tools"


def _ok(name: str, detail: str = "", version: str | None = None) -> CheckResult:
    return CheckResult(name=name, status=CheckStatus.PASS, detail=detail, version=version)


def _fail(name: str, detail: str, remediation: str) -> CheckResult:
    return CheckResult(name=name, status=CheckStatus.FAIL, detail=detail, remediation=remediation)


def _warn(name: str, detail: str, remediation: str | None = None) -> CheckResult:
    return CheckResult(name=name, status=CheckStatus.WARN, detail=detail, remediation=remediation)


def _skip(name: str, detail: str) -> CheckResult:
    return CheckResult(name=name, status=CheckStatus.SKIP, detail=detail)


# -- platform ---------------------------------------------------------------------------


def check_apple_silicon() -> CheckResult:
    machine = platform.machine()
    if machine == "arm64":
        return _ok("apple-silicon", platform.processor() or machine, version=machine)
    return _fail(
        "apple-silicon",
        f"architecture is {machine}",
        "Native Factory requires an Apple Silicon Mac: Tart uses Virtualization.framework "
        "and the iOS toolchain is arm64-only.",
    )


def check_macos(required: str | None = None) -> CheckResult:
    version = platform.mac_ver()[0]
    if not version:
        return _fail("macos", "not running macOS", "Native Factory runs on macOS hosts only.")
    if required and not at_least(version, required):
        return _fail(
            "macos",
            f"macOS {version} is older than {required}",
            f"Upgrade to macOS {required}+, or pin an older Xcode in vm.base_image.",
        )
    return _ok("macos", f"macOS {version}", version=version)


def check_disk_space(path: Path | None = None) -> CheckResult:
    target = path or Path.home()
    free_gb = shutil.disk_usage(target).free / 1024**3
    detail = f"{free_gb:.0f} GB free on {target}"
    if free_gb < MIN_FREE_GB:
        return _fail(
            "disk-space",
            detail,
            f"Native Factory needs at least {MIN_FREE_GB} GB: the base Xcode image is "
            "~69 GB compressed and ~140 GB on disk, and each worker clone grows from there.",
        )
    if free_gb < COMFORTABLE_FREE_GB:
        return _warn(
            "disk-space",
            detail,
            f"Below {COMFORTABLE_FREE_GB} GB there is not much room for two concurrent "
            "workers alongside the OCI cache.",
        )
    return _ok("disk-space", detail, version=f"{free_gb:.0f}GB")


# -- tart -------------------------------------------------------------------------------


def check_tart() -> CheckResult:
    path = which("tart")
    if path is None:
        return _fail(
            "tart",
            "not on PATH",
            f"brew install {TART_TAP}/tart {TART_TAP}/tart-guest-agent",
        )
    version = extract_version(run(["tart", "--version"]).text)
    return _ok("tart", path, version=version)


def _brew_formula_installed(formula: str) -> bool | None:
    """True/False when brew can answer, None when brew is unavailable."""
    if which("brew") is None:
        return None
    return run(["brew", "list", "--formula", formula]).ok


def check_tart_guest_agent() -> CheckResult:
    installed = _brew_formula_installed("tart-guest-agent")
    if installed is None:
        return _warn(
            "tart-guest-agent",
            "brew unavailable, cannot verify",
            f"Install with: brew install {TART_TAP}/tart-guest-agent",
        )
    if not installed:
        return _fail(
            "tart-guest-agent",
            "formula not installed",
            f"brew install {TART_TAP}/tart-guest-agent\n"
            "  Without it `tart exec` has no vsock channel into the guest.",
        )
    return _ok("tart-guest-agent", "installed")


def check_softnet(config: ProjectConfig | None) -> CheckResult:
    if config is None or config.vm.egress is not Egress.ALLOWLIST:
        return _skip("softnet", "not required while vm.egress is 'open' (ADR-0006)")
    installed = _brew_formula_installed("softnet")
    if installed is None:
        return _warn(
            "softnet", "brew unavailable, cannot verify", f"brew install {TART_TAP}/softnet"
        )
    if not installed:
        return _fail(
            "softnet",
            "vm.egress is 'allowlist' but softnet is not installed",
            f"brew install {TART_TAP}/softnet",
        )
    return _ok("softnet", "installed")


def check_packer() -> CheckResult:
    path = which("packer")
    if path is None:
        return _warn(
            "packer",
            "not on PATH",
            "Needed only by `native-factory vm create`: brew install packer",
        )
    version = extract_version(run(["packer", "version"]).text)
    plugins = run(["packer", "plugins", "installed"])
    if plugins.ok and "tart" not in plugins.text.lower():
        return _warn(
            "packer",
            f"packer {version} without the tart plugin",
            "The plugin installs on first `packer init images/packer`.",
        )
    return _ok("packer", path, version=version)


# -- host python ------------------------------------------------------------------------


def check_uv() -> CheckResult:
    version = tool_version("uv")
    if version is None:
        return _fail("uv", "not on PATH", "curl -LsSf https://astral.sh/uv/install.sh | sh")
    return _ok("uv", "installed", version=version)


def check_python() -> CheckResult:
    version = platform.python_version()
    if not at_least(version, "3.12"):
        return _fail(
            "python",
            f"running {version}",
            "Native Factory requires Python 3.12+. uv manages this: uv sync",
        )
    return _ok("python", f"Python {version}", version=version)


# -- android (host emulator path) ---------------------------------------------------------


def check_android_cli() -> CheckResult:
    """The legacy `android` script shares the name of the first-party CLI and exits 0.

    A **warning** on the host, a **failure** in the guest. The host never invokes `android`
    -- it only runs the emulator and adb (ADR-0002) -- so a legacy shadow here is a stale
    SDK worth reporting, not a reason to block an otherwise ready machine. The guest does
    run `android create`, so `native_factory_guest.doctor` fails on it.
    """
    kind, path, version = classify_android_cli()
    if kind is AndroidCliKind.ABSENT:
        return _skip("android-cli", "no `android` on PATH (the guest image provides it)")
    if kind is AndroidCliKind.LEGACY:
        return _warn("android-cli", f"legacy SDK Tools script at {path}", LEGACY_REMEDIATION)
    return _ok("android-cli", path or "", version=version)


def check_android_emulator() -> CheckResult:
    path = emulator.emulator_path()
    if path is None:
        return _fail(
            "android-emulator",
            "emulator not found",
            "The emulator runs on the host, not in the guest (ADR-0002). Install it with:\n"
            "  sdkmanager --install emulator  (or Android Studio > SDK Tools)",
        )
    return _ok("android-emulator", path)


def check_platform_tools() -> CheckResult:
    path = adb.adb_path()
    if path is None:
        return _fail(
            "android-platform-tools",
            "adb not found",
            "sdkmanager --install platform-tools",
        )
    version = adb.adb_version(path).platform_tools
    if not at_least(version, adb.MIN_PLATFORM_TOOLS):
        return _fail(
            "android-platform-tools",
            f"platform-tools {version or 'unknown'} at {path}",
            f"Upgrade to {adb.MIN_PLATFORM_TOOLS}+: remote-adb behaviour changed after the "
            "2022 releases and the guest reaches this server over the Tart NAT.\n"
            "  sdkmanager --install platform-tools",
        )
    return _ok("android-platform-tools", path, version=version)


def check_arm64_avd() -> CheckResult:
    avds = emulator.list_avds()
    if not avds:
        return _fail(
            "android-avd",
            "no AVDs defined",
            "Create one: android emulator create --name nf-pixel --api 36",
        )
    arm64 = [a.name for a in avds if a.is_arm64]
    if not arm64:
        names = ", ".join(a.name for a in avds)
        return _warn(
            "android-avd",
            f"no AVD detected as arm64 among: {names}",
            "An x86 image cannot be hardware-accelerated on Apple Silicon. If these are "
            "arm64, the ABI could not be read from config.ini and this is cosmetic.",
        )
    return _ok("android-avd", f"{len(arm64)} arm64 AVD(s): {', '.join(arm64)}")


def check_adb_server() -> CheckResult:
    if adb.server_reachable():
        return _ok("android-adb-server", f"listening on :{adb.DEFAULT_ADB_PORT}")
    return _warn(
        "android-adb-server",
        "no adb server listening",
        "Only needed during Android stages. Start one reachable from the guest:\n"
        f"  adb -a -P {adb.DEFAULT_ADB_PORT} server nodaemon\n"
        f"  and firewall {adb.DEFAULT_ADB_PORT} to {adb.TART_NAT_CIDR} (ADR-0002).",
    )


# -- assembly ----------------------------------------------------------------------------


def host_checks(config: ProjectConfig | None = None) -> list[CheckResult]:
    checks: list[Callable[[], CheckResult]] = [
        check_apple_silicon,
        check_macos,
        check_disk_space,
        check_tart,
        check_tart_guest_agent,
        check_packer,
        check_uv,
        check_python,
        check_android_cli,
    ]
    results = [check() for check in checks]
    results.append(check_softnet(config))

    if config is None or config.needs_host_emulator:
        results += [
            check_android_emulator(),
            check_platform_tools(),
            check_arm64_avd(),
            check_adb_server(),
        ]
    else:
        results.append(_skip("android-emulator", "targets.android.emulator is not 'host'"))

    return results
