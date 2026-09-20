"""Structured JSONL logging alongside readable console output (the brief).

One file per run. The console is for the human watching; the JSONL is what survives, and
what `native-factory status` and later the evaluator read.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

#: Keys whose values are replaced before anything is written. The VM boundary is the real
#: control (docs/architecture.md section 9); this stops the obvious accidents.
REDACTED_KEYS = frozenset(
    {
        "api_key",
        "anthropic_api_key",  # provider-name-ok: env var name, not provider logic
        "openai_api_key",
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
        "oauth_token",
    }
)
REDACTION = "[redacted]"


def redact(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: (REDACTION if key.lower() in REDACTED_KEYS else redact(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact(item) for item in payload]
    return payload


class RunLog:
    """Append-only JSONL log for one run."""

    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        #: Set by a command that completed but whose verdict was negative -- a doctor
        #: report with failures, say. The command did not crash, but the run did not
        #: succeed, and `status` should not claim otherwise.
        self.failure: str | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8")

    def event(self, event: str, **fields: Any) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "run_id": self.run_id,
            "event": event,
            **redact(fields),
        }
        self._handle.write(json.dumps(record, default=str) + "\n")
        self._handle.flush()

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def read_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


@contextmanager
def timed(log: RunLog, event: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Log `<event>.start` / `<event>.end` with a duration, and `<event>.error` on failure."""
    extra: dict[str, Any] = {}
    started = datetime.now(UTC)
    log.event(f"{event}.start", **fields)
    try:
        yield extra
    except BaseException as exc:
        log.event(
            f"{event}.error",
            error=str(exc),
            error_type=type(exc).__name__,
            duration_ms=_ms_since(started),
            **fields,
            **extra,
        )
        raise
    log.event(f"{event}.end", duration_ms=_ms_since(started), **fields, **extra)


def _ms_since(started: datetime) -> int:
    return int((datetime.now(UTC) - started).total_seconds() * 1000)


def log_path_for(reports_dir: Path, run_id: str) -> Path:
    return reports_dir / "runs" / f"{run_id}.jsonl"


def is_ci() -> bool:
    return os.environ.get("CI", "").lower() in {"1", "true", "yes"}
