"""Guest preflight checks.

Runs inside the Tart worker and prints the same JSON shape as the host doctor, so
`native-factory vm doctor` can dispatch over `tart exec` and render the result identically.

Two checks are assertions about the image rather than about tooling:

* the first-party `android` CLI must be present and must not be the legacy script;
* the Android ``emulator`` package must be **absent**. It cannot work in a macOS guest --
  an ARM64 AVD needs Hypervisor.framework and fails with HV_UNSUPPORTED when nested -- so
  shipping it would only invite someone to try (ADR-0002).
"""

from __future__ import annotations

from pathlib import Path

from native_factory_core.probe import Output, at_least, extract_version, run, which
from native_factory_core.schema.run import CheckResult, CheckStatus, DoctorReport

#: Where the Packer layer installs the factory's own Python environment.
FACTORY_PREFIX = Path("/opt/native-factory")
VENV_PYTHON = FACTORY_PREFIX / "venv" / "bin" / "python"
MANIFEST = FACTORY_PREFIX / "manifest.json"

AGENT_SERVER_PORT = 8000


def _result(
    name: str,
    status: CheckStatus,
    detail: str = "",
    version: str | None = None,
    remediation: str | None = None,
) -> CheckResult:
    return CheckResult(
        name=name, status=status, detail=detail, version=version, remediation=remediation
    )


def _binary(
    name: str,
    binary: str,
    args: tuple[str, ...] = ("--version",),
    *,
    minimum: str | None = None,
) -> CheckResult:
    path = which(binary)
    if path is None:
        return _result(
            name,
            CheckStatus.FAIL,
            f"{binary} not on PATH",
            remediation=f"The golden image should provide {binary}; rebuild with "
            "`native-factory vm create --force`.",
        )
    version = extract_version(run([binary, *args]).text)
    if minimum and not at_least(version, minimum):
        return _result(
            name,
            CheckStatus.FAIL,
            f"{binary} {version or 'unknown'} is older than {minimum}",
            version=version,
            remediation=f"Pin {binary} >= {minimum} in images/versions.lock.json and rebuild.",
        )
    return _result(name, CheckStatus.PASS, path, version=version)


# -- Apple toolchain ----------------------------------------------------------------------


def check_xcode() -> CheckResult:
    output: Output = run(["xcodebuild", "-version"])
    if not output.ok:
        return _result(
            "xcode",
            CheckStatus.FAIL,
            output.text or "xcodebuild unavailable",
            remediation="Accept the licence in the image build: sudo xcodebuild -license accept",
        )
    return _result(
        "xcode", CheckStatus.PASS, output.text.splitlines()[0], extract_version(output.text)
    )


def check_simulator_runtimes() -> CheckResult:
    output = run(["xcrun", "simctl", "list", "runtimes", "-j"])
    if not output.ok:
        return _result(
            "ios-simulator-runtimes",
            CheckStatus.FAIL,
            output.text or "simctl failed",
            remediation="xcodebuild -downloadPlatform iOS",
        )
    count = output.stdout.count('"identifier"')
    if count == 0:
        return _result(
            "ios-simulator-runtimes",
            CheckStatus.FAIL,
            "no runtimes installed",
            remediation="xcodebuild -downloadPlatform iOS",
        )
    return _result("ios-simulator-runtimes", CheckStatus.PASS, f"{count} runtime(s)")


# -- Android ------------------------------------------------------------------------------


def check_android_cli() -> CheckResult:
    """First-party CLI, not the legacy SDK Tools script of the same name."""
    path = which("android")
    if path is None:
        return _result(
            "android-cli",
            CheckStatus.FAIL,
            "not on PATH",
            remediation="The image must install the first-party android CLI: "
            "https://developer.android.com/tools/agents/android-cli",
        )
    if Path(path).parent.name == "tools":
        return _result(
            "android-cli",
            CheckStatus.FAIL,
            f"legacy SDK Tools script at {path}",
            remediation="Remove $ANDROID_HOME/tools from PATH in the image.",
        )
    output = run([path, "--version"])
    if "deprecated" in output.text.lower():
        return _result(
            "android-cli",
            CheckStatus.FAIL,
            "the `android` on PATH is the deprecated script (it exits 0)",
            remediation="Remove $ANDROID_HOME/tools from PATH in the image.",
        )
    return _result("android-cli", CheckStatus.PASS, path, extract_version(output.text))


def check_emulator_absent() -> CheckResult:
    """The Android emulator must NOT be in the guest image.

    A pass here is the absence of a tool, which is unusual enough to be worth stating:
    an ARM64 emulator cannot be hardware-accelerated inside a macOS guest, so its presence
    is a build error rather than a bonus (ADR-0002).
    """
    path = which("emulator")
    if path is None:
        return _result(
            "android-emulator-absent",
            CheckStatus.PASS,
            "not installed, as intended (the emulator runs on the host)",
        )
    return _result(
        "android-emulator-absent",
        CheckStatus.FAIL,
        f"emulator present at {path}",
        remediation="Remove the emulator package from the image. It cannot work here: an "
        "ARM64 AVD needs Hypervisor.framework and fails with HV_UNSUPPORTED when nested. "
        "See ADR-0002.",
    )


# -- factory tooling -------------------------------------------------------------------


def check_playwright_browsers() -> CheckResult:
    output = run(["npx", "--no-install", "playwright", "--version"])
    if not output.ok:
        return _result(
            "playwright",
            CheckStatus.FAIL,
            "playwright not installed",
            remediation="npm i -g playwright && playwright install --with-deps",
        )
    cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    if not cache.exists() or not any(cache.iterdir()):
        return _result(
            "playwright",
            CheckStatus.FAIL,
            "playwright installed but no browsers downloaded",
            version=extract_version(output.text),
            remediation="playwright install chromium webkit",
        )
    browsers = sorted(p.name for p in cache.iterdir() if p.is_dir())
    return _result(
        "playwright", CheckStatus.PASS, ", ".join(browsers), extract_version(output.text)
    )


def check_xcodebuildmcp() -> CheckResult:
    if which("xcodebuildmcp") is None:
        return _result(
            "xcodebuildmcp",
            CheckStatus.FAIL,
            "not on PATH",
            remediation="npm i -g xcodebuildmcp@<pinned>",
        )
    # The project ships its own doctor; prefer its verdict over a version string.
    output = run(["xcodebuildmcp-doctor"], timeout=90)
    status = CheckStatus.PASS if output.ok else CheckStatus.WARN
    version = extract_version(run(["xcodebuildmcp", "--version"]).text)
    return _result(
        "xcodebuildmcp",
        status,
        "xcodebuildmcp-doctor passed" if output.ok else "xcodebuildmcp-doctor reported problems",
        version=version,
        remediation=None if output.ok else output.text[:400],
    )


def check_factory_venv() -> CheckResult:
    if not VENV_PYTHON.exists():
        return _result(
            "factory-venv",
            CheckStatus.FAIL,
            f"{VENV_PYTHON} missing",
            remediation="The image build did not create the factory environment; rebuild.",
        )
    version = extract_version(run([str(VENV_PYTHON), "--version"]).text)
    return _result("factory-venv", CheckStatus.PASS, str(VENV_PYTHON), version)


def check_manifest() -> CheckResult:
    """The image manifest is what makes 'reproducible' checkable (ADR-0003 / AT-2)."""
    if not MANIFEST.exists():
        return _result(
            "image-manifest",
            CheckStatus.FAIL,
            f"{MANIFEST} missing",
            remediation="Rebuild the golden image; 99-manifest.sh writes this file.",
        )
    return _result("image-manifest", CheckStatus.PASS, str(MANIFEST))


def check_agent_server() -> CheckResult:
    """Milestone 2 installs the stack; at Milestone 1 its absence is expected."""
    if not VENV_PYTHON.exists():
        return _result("agent-server", CheckStatus.SKIP, "factory venv missing")
    probe = run([str(VENV_PYTHON), "-c", "import openhands.sdk; print(openhands.sdk.__name__)"])
    if not probe.ok:
        return _result(
            "agent-server",
            CheckStatus.SKIP,
            "openhands-sdk not installed (expected until Milestone 2)",
        )
    return _result("agent-server", CheckStatus.PASS, "openhands-sdk importable")


# -- assembly ----------------------------------------------------------------------------


def guest_checks() -> list[CheckResult]:
    return [
        check_xcode(),
        check_simulator_runtimes(),
        _binary("xcode-cli-tools", "xcrun", ("--version",)),
        _binary("git", "git"),
        _binary("jdk", "java", ("-version",), minimum="17"),
        _binary("gradle", "gradle", ("--version",)),
        _binary("adb", "adb", ("version",)),
        check_android_cli(),
        check_emulator_absent(),
        _binary("node", "node", minimum="22.12"),
        check_playwright_browsers(),
        _binary("maestro", "maestro", ("--version",)),
        _binary("agent-device", "agent-device", ("--version",)),
        check_xcodebuildmcp(),
        _binary("uv", "uv"),
        check_factory_venv(),
        check_manifest(),
        check_agent_server(),
    ]


def report() -> DoctorReport:
    return DoctorReport.of("guest", guest_checks())
