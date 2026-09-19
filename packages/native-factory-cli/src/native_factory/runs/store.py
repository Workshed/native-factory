"""Run state in SQLite.

`native-factory status` answers "what happened" from these rows alone, never from an agent
transcript (the brief). Stdlib sqlite3 only -- the brief rules out a workflow engine until
there is a demonstrated need.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from native_factory_core.schema.run import CommandRecord, FeatureState, RunRecord, RunStatus

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id           TEXT PRIMARY KEY,
    command      TEXT NOT NULL,
    project      TEXT,
    status       TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    vm_name      TEXT,
    image_digest TEXT,
    provider     TEXT,
    error        TEXT
);

CREATE INDEX IF NOT EXISTS runs_started_at ON runs (started_at DESC);
CREATE INDEX IF NOT EXISTS runs_project ON runs (project, started_at DESC);

-- Only factory-invoked commands are recorded here. Commands the coding agent runs in its
-- own inner loop are deliberately absent: evaluation reads recorded runs, not narration
-- (ADR-0004).
CREATE TABLE IF NOT EXISTS commands (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    argv        TEXT NOT NULL,
    exit_code   INTEGER,
    duration_ms INTEGER,
    started_at  TEXT NOT NULL,
    stage       TEXT,
    vm_name     TEXT
);

CREATE INDEX IF NOT EXISTS commands_run ON commands (run_id, id);

CREATE TABLE IF NOT EXISTS features (
    project            TEXT NOT NULL,
    feature            TEXT NOT NULL,
    reference_revision TEXT,
    spec_status        TEXT NOT NULL DEFAULT 'pending',
    ios_status         TEXT NOT NULL DEFAULT 'pending',
    android_status     TEXT NOT NULL DEFAULT 'pending',
    evaluation_status  TEXT NOT NULL DEFAULT 'pending',
    last_failure       TEXT,
    PRIMARY KEY (project, feature)
);

-- Two concurrent workers share one host adb server and one emulator pool, and every ADB
-- client defaults to "the connected device". Leases make the choice explicit (ADR-0002).
CREATE TABLE IF NOT EXISTS device_leases (
    serial      TEXT PRIMARY KEY,
    avd         TEXT,
    run_id      TEXT NOT NULL,
    vm_name     TEXT,
    acquired_at TEXT NOT NULL
);
"""


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class RunStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            with conn:
                yield conn
        finally:
            conn.close()

    # -- runs -------------------------------------------------------------------------

    def start_run(self, record: RunRecord) -> RunRecord:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, command, project, status, started_at, vm_name,"
                " image_digest, provider, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.command,
                    record.project,
                    record.status.value,
                    _iso(record.started_at),
                    record.vm_name,
                    record.image_digest,
                    record.provider,
                    record.error,
                ),
            )
        return record

    def finish_run(
        self,
        run_id: str,
        status: RunStatus,
        *,
        error: str | None = None,
        vm_name: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, ended_at = ?, error = ?,"
                " vm_name = COALESCE(?, vm_name) WHERE id = ?",
                (status.value, datetime.now(UTC).isoformat(), error, vm_name, run_id),
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._row_to_run(row) if row else None

    def recent_runs(self, limit: int = 20, project: str | None = None) -> list[RunRecord]:
        query = "SELECT * FROM runs"
        params: list[object] = []
        if project:
            query += " WHERE project = ?"
            params.append(project)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_run(row) for row in rows]

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            id=row["id"],
            command=row["command"],
            project=row["project"],
            status=RunStatus(row["status"]),
            started_at=_parse(row["started_at"]) or datetime.now(UTC),
            ended_at=_parse(row["ended_at"]),
            vm_name=row["vm_name"],
            image_digest=row["image_digest"],
            provider=row["provider"],
            error=row["error"],
        )

    # -- commands ---------------------------------------------------------------------

    def record_command(self, record: CommandRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO commands (run_id, argv, exit_code, duration_ms, started_at,"
                " stage, vm_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.run_id,
                    json.dumps(record.argv),
                    record.exit_code,
                    record.duration_ms,
                    _iso(record.started_at),
                    record.stage,
                    record.vm_name,
                ),
            )

    def commands_for(self, run_id: str) -> list[CommandRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM commands WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return [
            CommandRecord(
                run_id=row["run_id"],
                argv=json.loads(row["argv"]),
                exit_code=row["exit_code"],
                duration_ms=row["duration_ms"],
                started_at=_parse(row["started_at"]) or datetime.now(UTC),
                stage=row["stage"],
                vm_name=row["vm_name"],
            )
            for row in rows
        ]

    # -- features (populated from Milestone 8) ----------------------------------------

    def upsert_feature(self, project: str, state: FeatureState) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO features (project, feature, reference_revision, spec_status,"
                " ios_status, android_status, evaluation_status, last_failure)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (project, feature) DO UPDATE SET"
                " reference_revision = excluded.reference_revision,"
                " spec_status = excluded.spec_status, ios_status = excluded.ios_status,"
                " android_status = excluded.android_status,"
                " evaluation_status = excluded.evaluation_status,"
                " last_failure = excluded.last_failure",
                (
                    project,
                    state.feature,
                    state.reference_revision,
                    state.spec_status,
                    state.ios_status,
                    state.android_status,
                    state.evaluation_status,
                    state.last_failure,
                ),
            )

    def features(self, project: str) -> list[FeatureState]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM features WHERE project = ? ORDER BY feature", (project,)
            ).fetchall()
        return [
            FeatureState(
                feature=row["feature"],
                reference_revision=row["reference_revision"],
                spec_status=row["spec_status"],
                ios_status=row["ios_status"],
                android_status=row["android_status"],
                evaluation_status=row["evaluation_status"],
                last_failure=row["last_failure"],
            )
            for row in rows
        ]

    # -- device leases (enforced from Milestone 9) ------------------------------------

    def acquire_lease(self, serial: str, run_id: str, *, avd: str, vm_name: str | None) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO device_leases (serial, avd, run_id, vm_name, acquired_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (serial, avd, run_id, vm_name, datetime.now(UTC).isoformat()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def release_lease(self, serial: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM device_leases WHERE serial = ?", (serial,))

    def release_leases_for_run(self, run_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM device_leases WHERE run_id = ?", (run_id,))

    def leases(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT serial, run_id FROM device_leases").fetchall()
        return {row["serial"]: row["run_id"] for row in rows}
