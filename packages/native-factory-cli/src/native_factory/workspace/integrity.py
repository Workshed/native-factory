"""Content hashing for read-only mounts (ADR-0005).

The mount flag is the real control -- Tart enforces `:ro` at the VM boundary. This is the
second line: the host records a digest of `reference/` before handing a VM to a stage that
mounts it read-only, and re-verifies afterwards. A mismatch means the boundary did not hold
and the run's results cannot be trusted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

#: Files that change without anyone meaning them to.
IGNORED_NAMES = frozenset({".DS_Store"})

_CHUNK = 1 << 20


class IntegrityError(Exception):
    """Raised when a read-only tree changed while it was mounted read-only."""


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class TreeDigest:
    digest: str
    file_count: int
    total_bytes: int

    def __str__(self) -> str:
        return f"{self.digest[:12]} ({self.file_count} files, {self.total_bytes} bytes)"


def digest_tree(root: Path) -> TreeDigest:
    """Deterministic digest of a directory tree's contents and layout.

    An absent directory hashes as empty rather than raising, so a stage can be verified
    before the directory it will create exists.
    """
    overall = hashlib.sha256()
    count = 0
    total = 0

    if root.exists():
        paths = sorted(
            (p for p in root.rglob("*") if p.is_file() and p.name not in IGNORED_NAMES),
            key=lambda p: p.relative_to(root).as_posix(),
        )
        for path in paths:
            relative = path.relative_to(root).as_posix()
            size = path.stat().st_size
            overall.update(relative.encode("utf-8"))
            overall.update(b"\0")
            overall.update(_hash_file(path).encode("ascii"))
            overall.update(b"\n")
            count += 1
            total += size

    return TreeDigest(digest=overall.hexdigest(), file_count=count, total_bytes=total)


def verify_unchanged(root: Path, before: TreeDigest, *, label: str) -> None:
    after = digest_tree(root)
    if after.digest != before.digest:
        raise IntegrityError(
            f"{label} changed while mounted read-only.\n"
            f"  before: {before}\n"
            f"  after:  {after}\n"
            f"  path:   {root}\n"
            "  The VM boundary did not hold; this run's results cannot be trusted."
        )
