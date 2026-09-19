"""Typed wrapper over the `tart` CLI.

Only documented commands are used (HANDOFF section 4.4). Three things people reach for do
not exist and must never appear here: `tart ssh`, a `--headless` flag (that is a Packer
option) and live snapshots. The intended pattern is clone -> run -> delete.

Argv construction is separated from execution so it can be unit-tested without a VM.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from native_factory.vm.mounts import Mount

TART_BINARY = "tart"

#: Tart and Apple's macOS SLA both cap concurrent macOS guests at two. A third
#: `tart run` fails. Linux guests are uncapped.
MAX_MACOS_GUESTS = 2


class TartError(RuntimeError):
    """A `tart` invocation failed."""

    def __init__(self, message: str, *, argv: Sequence[str] = (), stderr: str = "", code: int = 1):
        super().__init__(message)
        self.argv = list(argv)
        self.stderr = stderr
        self.code = code


class TartNotInstalledError(TartError):
    pass


class TartVmNotFoundError(TartError):
    pass


class TartVmLimitReachedError(TartError):
    pass


@dataclass(frozen=True, slots=True)
class VmInfo:
    name: str
    source: str
    state: str
    size_gb: float | None = None
    os: str | None = None

    @property
    def running(self) -> bool:
        return self.state.lower() == "running"

    @property
    def is_macos(self) -> bool:
        # Absent OS information, assume macOS: over-counting refuses a third VM we could
        # perhaps have started, which is the safe direction to be wrong in.
        return self.os is None or self.os.lower() in {"darwin", "macos"}


# --------------------------------------------------------------------------------------
# argv construction (pure)
# --------------------------------------------------------------------------------------


def clone_argv(source: str, name: str) -> list[str]:
    return [TART_BINARY, "clone", source, name]


def run_argv(
    name: str,
    *,
    no_graphics: bool = True,
    mounts: Sequence[Mount] = (),
    net_softnet: bool = False,
    softnet_allow: Sequence[str] = (),
    suspendable: bool = False,
) -> list[str]:
    argv = [TART_BINARY, "run"]
    if no_graphics:
        argv.append("--no-graphics")
    for mount in mounts:
        argv.append(mount.to_flag())
    if net_softnet:
        argv.append("--net-softnet")
        if softnet_allow:
            argv.append(f"--net-softnet-allow={','.join(softnet_allow)}")
    if suspendable:
        argv.append("--suspendable")
    argv.append(name)
    return argv


def exec_argv(
    name: str,
    command: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    interactive: bool = False,
    tty: bool = False,
) -> list[str]:
    """Build a `tart exec` invocation.

    Environment is passed the documented way -- by prefixing `/usr/bin/env K=V` -- because
    `tart exec` has no `--env` flag (HANDOFF section 4.4).
    """
    if not command:
        raise ValueError("tart exec requires a command")
    argv = [TART_BINARY, "exec"]
    if interactive:
        argv.append("-i")
    if tty:
        argv.append("-t")
    argv.append(name)
    if env:
        argv.append("/usr/bin/env")
        argv.extend(f"{key}={value}" for key, value in sorted(env.items()))
    argv.extend(command)
    return argv


def ip_argv(name: str) -> list[str]:
    return [TART_BINARY, "ip", name]


def set_argv(
    name: str,
    *,
    cpu: int | None = None,
    memory_mb: int | None = None,
    disk_size_gb: int | None = None,
) -> list[str]:
    argv = [TART_BINARY, "set"]
    if cpu is not None:
        argv += ["--cpu", str(cpu)]
    if memory_mb is not None:
        argv += ["--memory", str(memory_mb)]
    if disk_size_gb is not None:
        argv += ["--disk-size", str(disk_size_gb)]
    if len(argv) == 2:
        raise ValueError("tart set requires at least one property to set")
    argv.append(name)
    return argv


def stop_argv(name: str) -> list[str]:
    return [TART_BINARY, "stop", name]


def delete_argv(name: str) -> list[str]:
    return [TART_BINARY, "delete", name]


def list_argv() -> list[str]:
    return [TART_BINARY, "list", "--format", "json"]


# --------------------------------------------------------------------------------------
# error classification
# --------------------------------------------------------------------------------------

_LIMIT_MARKERS = (
    "maximum number of virtual machines",
    "too many virtual machines",
    "vm limit",
    "hv_error",
)
_NOT_FOUND_MARKERS = ("does not exist", "not found", "no such vm")


def classify(argv: Sequence[str], code: int, stderr: str) -> TartError:
    text = stderr.lower()
    if any(marker in text for marker in _LIMIT_MARKERS):
        return TartVmLimitReachedError(
            "Tart refused to start another macOS guest.\n"
            f"  macOS permits {MAX_MACOS_GUESTS} VM instances per Mac and Tart enforces it.\n"
            "  Stop a running worker first: native-factory vm list",
            argv=argv,
            stderr=stderr,
            code=code,
        )
    if any(marker in text for marker in _NOT_FOUND_MARKERS):
        return TartVmNotFoundError(
            stderr.strip() or "VM not found", argv=argv, stderr=stderr, code=code
        )
    return TartError(stderr.strip() or f"tart exited {code}", argv=argv, stderr=stderr, code=code)


# --------------------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------------------


def parse_list_output(stdout: str) -> list[VmInfo]:
    """Parse `tart list`, preferring JSON and falling back to the plain table.

    The JSON form is what we ask for; the table parser exists so a Tart release that drops
    or renames `--format json` degrades to a warning rather than breaking the CLI.
    """
    stdout = stdout.strip()
    if not stdout:
        return []

    if stdout.startswith("["):
        rows = json.loads(stdout)
        return [
            VmInfo(
                name=row.get("Name", ""),
                source=row.get("Source", ""),
                state=row.get("State", ""),
                size_gb=_as_float(row.get("Size")),
                os=row.get("OS"),
            )
            for row in rows
            if row.get("Name")
        ]

    lines = stdout.splitlines()
    if len(lines) < 2:
        return []
    header = lines[0].split()
    try:
        name_at = header.index("Name")
        state_at = header.index("State")
    except ValueError:
        return []
    out: list[VmInfo] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) <= max(name_at, state_at):
            continue
        out.append(VmInfo(name=parts[name_at], source=parts[0], state=parts[state_at]))
    return out


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class Tart:
    """Executes `tart`. Inject `runner` in tests to avoid needing a VM."""

    def __init__(self, binary: str = TART_BINARY, timeout: float = 600.0) -> None:
        self.binary = binary
        self.timeout = timeout

    # -- capability -------------------------------------------------------------------

    def installed(self) -> bool:
        return shutil.which(self.binary) is not None

    def require_installed(self) -> None:
        if not self.installed():
            raise TartNotInstalledError(
                "tart is not installed.\n"
                "  brew install openai/tools/tart openai/tools/tart-guest-agent"
            )

    def version(self) -> str:
        return self._check([self.binary, "--version"]).strip()

    # -- commands ---------------------------------------------------------------------

    def list(self) -> list[VmInfo]:
        return parse_list_output(self._check(list_argv()))

    def get(self, name: str) -> VmInfo | None:
        return next((vm for vm in self.list() if vm.name == name), None)

    def exists(self, name: str) -> bool:
        return self.get(name) is not None

    def running_macos_guests(self) -> list[VmInfo]:
        return [vm for vm in self.list() if vm.running and vm.is_macos]

    def clone(self, source: str, name: str) -> None:
        self._check(clone_argv(source, name), timeout=None)

    def configure(self, name: str, **kwargs: int | None) -> None:
        self._check(set_argv(name, **kwargs))

    def stop(self, name: str) -> None:
        self._check(stop_argv(name))

    def delete(self, name: str) -> None:
        self._check(delete_argv(name))

    def ip(self, name: str) -> str:
        return self._check(ip_argv(name)).strip()

    def exec(
        self,
        name: str,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        argv = exec_argv(name, command, env=env)
        result = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout)
        if check and result.returncode != 0:
            raise classify(argv, result.returncode, result.stderr)
        return result

    def exec_interactive(self, name: str, command: Sequence[str] | None = None) -> int:
        """Attach an interactive TTY. Used by `native-factory vm shell`."""
        argv = exec_argv(name, command or ["/bin/zsh", "-l"], interactive=True, tty=True)
        return subprocess.call(argv)

    def run_detached(self, name: str, log_path: Path, **kwargs: object) -> subprocess.Popen[bytes]:
        """Start `tart run` in the background.

        `tart run` blocks for the lifetime of the VM, so the CLI starts it detached and
        waits for the guest to answer instead.
        """
        argv = run_argv(name, **kwargs)  # type: ignore[arg-type]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = log_path.open("ab")
        handle.write(f"\n$ {' '.join(argv)}\n".encode())
        handle.flush()
        return subprocess.Popen(argv, stdout=handle, stderr=handle, stdin=subprocess.DEVNULL)

    # -- internals --------------------------------------------------------------------

    def _check(self, argv: Sequence[str], timeout: float | None = -1.0) -> str:
        self.require_installed()
        effective = self.timeout if timeout == -1.0 else timeout
        try:
            result = subprocess.run(list(argv), capture_output=True, text=True, timeout=effective)
        except FileNotFoundError as exc:
            raise TartNotInstalledError(f"{self.binary} not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise TartError(f"tart timed out after {effective}s", argv=argv) from exc
        if result.returncode != 0:
            raise classify(argv, result.returncode, result.stderr)
        return result.stdout
