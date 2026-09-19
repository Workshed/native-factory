"""Run identifiers."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

PREFIX = "run"


def new_run_id(now: datetime | None = None) -> str:
    """Sortable, collision-resistant, and readable in a directory listing."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{PREFIX}_{stamp}_{secrets.token_hex(3)}"
