"""The host-side workspace.

VMs are disposable; project output is not. Only the project directory is ever exposed to a
guest -- never the home directory, and never host SSH or cloud credentials (the brief).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT_ENV = "NATIVE_FACTORY_HOME"
DEFAULT_ROOT_NAME = "NativeFactory"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class WorkspaceError(Exception):
    """Raised with a message intended to be shown directly to the user."""


def slugify(name: str) -> str:
    """Directory-safe project slug.

    Rejects rather than silently mangles: the slug names a directory that gets mounted into
    a VM, so surprises here are a security matter, not a cosmetic one. Anything that looks
    like a path is refused outright -- quietly turning "../../etc" into "etc" would be
    safe but dishonest, and the user should see that their input was not understood.
    """
    if any(token in name for token in ("/", "\\", "..", "\0")):
        raise WorkspaceError(
            f"project name {name!r} looks like a path\n"
            "  use letters, digits, hyphens or underscores"
        )
    slug = re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower()).strip("-")
    if not _SLUG_RE.match(slug):
        raise WorkspaceError(
            f"cannot derive a directory name from project name {name!r}\n"
            "  use letters, digits, hyphens or underscores"
        )
    return slug


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """Layout of one project directory. Mirrors the table in docs/architecture.md section 8."""

    root: Path

    @property
    def config_file(self) -> Path:
        return self.root / "native-factory.yaml"

    @property
    def reference(self) -> Path:
        return self.root / "reference"

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def ios(self) -> Path:
        return self.work / "ios"

    @property
    def android(self) -> Path:
        return self.work / "android"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def factory(self) -> Path:
        return self.root / "factory"

    @property
    def name(self) -> str:
        return self.root.name

    def directories(self) -> list[Path]:
        return [self.reference, self.work, self.ios, self.android, self.reports, self.factory]

    def exists(self) -> bool:
        return self.config_file.exists()

    def create(self) -> None:
        for directory in self.directories():
            directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class Workspace:
    root: Path

    @classmethod
    def default(cls) -> Workspace:
        override = os.environ.get(DEFAULT_ROOT_ENV)
        return cls(Path(override).expanduser() if override else Path.home() / DEFAULT_ROOT_NAME)

    @property
    def projects_dir(self) -> Path:
        return self.root / "projects"

    @property
    def state_db(self) -> Path:
        return self.root / "state.db"

    @property
    def reports(self) -> Path:
        """Reports for commands that belong to no project (doctor, vm create)."""
        return self.root / "reports"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def ensure(self) -> None:
        for directory in (self.root, self.projects_dir, self.reports, self.logs):
            directory.mkdir(parents=True, exist_ok=True)

    def project(self, name: str) -> ProjectPaths:
        slug = slugify(name)
        candidate = (self.projects_dir / slug).resolve()
        # slugify already forbids separators; this is the belt to its braces, because the
        # result is handed to `tart run --dir`.
        if not candidate.is_relative_to(self.projects_dir.resolve()):
            raise WorkspaceError(f"project path {candidate} escapes {self.projects_dir}")
        return ProjectPaths(candidate)

    def projects(self) -> list[ProjectPaths]:
        if not self.projects_dir.exists():
            return []
        return sorted(
            (ProjectPaths(p) for p in self.projects_dir.iterdir() if p.is_dir()),
            key=lambda p: p.name,
        )
