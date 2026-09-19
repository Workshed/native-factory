"""Building the golden image with Packer.

Reproducibility here means *pinned inputs with a verifiable manifest*, not byte-identical
images: Packer re-runs Homebrew and npm, and two images differ by timestamp alone. The
image records its base digest, tool versions and the SHA-256 of the template and scripts,
and two builds from the same versions.lock.json must produce equal manifests apart from
build time and image digest.

HANDOFF section 4.13 asks that a second `vm create` be "a no-op or identical"; only the
no-op half is achievable, and it is implemented here.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from native_factory_core.schema.config import ProjectConfig

PACKER_BINARY = "packer"


class PackerError(Exception):
    """Raised with a message intended to be shown directly to the user."""


def template_dir(repo_root: Path) -> Path:
    return repo_root / "images" / "packer"


def versions_lock(repo_root: Path) -> Path:
    return repo_root / "images" / "versions.lock.json"


def template_sha256(directory: Path) -> str:
    """Hash the template and every provisioning script, in path order."""
    digest = hashlib.sha256()
    files = sorted(
        (p for p in directory.rglob("*") if p.is_file() and p.suffix in {".hcl", ".sh"}),
        key=lambda p: p.relative_to(directory).as_posix(),
    )
    if not files:
        raise PackerError(f"no Packer template found under {directory}")
    for path in files:
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class BuildPlan:
    directory: Path
    image_name: str
    base_image: str
    cpu: int
    memory_mb: int
    disk_size_gb: int
    template_hash: str

    def init_argv(self) -> list[str]:
        return [PACKER_BINARY, "init", str(self.directory)]

    def build_argv(self) -> list[str]:
        return [
            PACKER_BINARY,
            "build",
            "-var",
            f"image_name={self.image_name}",
            "-var",
            f"base_image={self.base_image}",
            "-var",
            f"cpu_count={self.cpu}",
            "-var",
            f"memory_gb={self.memory_mb // 1024}",
            "-var",
            f"disk_size_gb={self.disk_size_gb}",
            "-var",
            f"template_sha256={self.template_hash}",
            str(self.directory),
        ]


def plan_build(repo_root: Path, config: ProjectConfig) -> BuildPlan:
    directory = template_dir(repo_root)
    return BuildPlan(
        directory=directory,
        image_name=config.vm.golden_name,
        base_image=config.vm.base_image,
        cpu=config.vm.cpu,
        memory_mb=config.vm.memory_mb,
        disk_size_gb=config.vm.disk_size_gb,
        template_hash=template_sha256(directory),
    )


def run_packer(argv: Sequence[str], cwd: Path, on_line: object = None) -> int:
    """Stream Packer output; an image build is long enough that silence is alarming."""
    process = subprocess.Popen(
        list(argv),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if process.stdout is not None:
        for line in process.stdout:
            if callable(on_line):
                on_line(line.rstrip())
    return process.wait()


def load_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        raise PackerError(f"no image manifest at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def compare_manifests(left: dict[str, object], right: dict[str, object]) -> list[str]:
    """Fields that differ, ignoring the ones that cannot be reproducible.

    Build time and the resulting image digest always differ; everything else must not.
    """
    volatile = {"built_at", "image_digest", "build_host"}
    keys = (set(left) | set(right)) - volatile
    return sorted(key for key in keys if left.get(key) != right.get(key))
