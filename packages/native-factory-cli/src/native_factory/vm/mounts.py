"""Directory mounts, and the stage-scoped mount policy from ADR-0005.

`reference/` holds the specification the evaluator judges against. The coding agent runs
with auto-approved ACP permissions and an unrestricted shell, and the factory runtime shares
the guest user account with it, so uid separation is not available. Tart's mount flags are
enforced at the VM boundary regardless of uid, so the policy is expressed there: `reference/`
is writable only during discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from native_factory_core.schema.config import Stage

#: Where Tart surfaces `--dir` mounts inside a macOS guest.
GUEST_MOUNT_ROOT = "/Volumes/My Shared Files"


class MountError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Mount:
    """One `--dir=name:path[:ro]` mount."""

    name: str
    path: Path
    read_only: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise MountError("mount name must not be empty")
        # Tart parses --dir on ':', so a colon in either half is unrepresentable.
        if ":" in self.name or "/" in self.name:
            raise MountError(f"mount name {self.name!r} must not contain ':' or '/'")
        if ":" in str(self.path):
            raise MountError(f"mount path {self.path} must not contain ':'")
        if not self.path.is_absolute():
            raise MountError(f"mount path {self.path} must be absolute")

    def to_flag(self) -> str:
        suffix = ":ro" if self.read_only else ""
        return f"--dir={self.name}:{self.path}{suffix}"

    @property
    def guest_path(self) -> str:
        return f"{GUEST_MOUNT_ROOT}/{self.name}"


#: name -> read_only, per stage. A name absent from a stage is not mounted at all.
#:
#: reports/ is deliberately absent everywhere: the host pulls results out over `tart exec`
#: rather than exposing the directory the evaluator writes to.
STAGE_POLICY: dict[Stage, dict[str, bool]] = {
    Stage.DISCOVERY: {"reference": False, "factory": True},
    Stage.IMPLEMENT: {"reference": True, "work": False, "factory": True},
    Stage.EVALUATE: {"reference": True, "work": True, "factory": True},
}

#: Directory name inside the project workspace for each mount name.
_SUBDIR = {"reference": "reference", "work": "work", "factory": "factory"}


def mounts_for_stage(project_dir: Path, stage: Stage) -> list[Mount]:
    """Build the `--dir` set for a stage. See the table in docs/architecture.md section 8."""
    policy = STAGE_POLICY[stage]
    return [
        Mount(name=name, path=project_dir / _SUBDIR[name], read_only=read_only)
        for name, read_only in policy.items()
    ]


def read_only_mount_names(stage: Stage) -> list[str]:
    """Mount names the host should hash before and after the stage (ADR-0005)."""
    return sorted(name for name, read_only in STAGE_POLICY[stage].items() if read_only)
