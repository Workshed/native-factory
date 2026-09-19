"""Run, command and feature records.

These are the observability contract: `native-factory status` answers "what happened"
from these rows alone, never from an agent transcript (the brief; ADR-0004).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"
    ABORTED = "aborted"


class CheckStatus(StrEnum):
    PASS = "pass"  # noqa: S105  -- a check outcome, not a credential
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


def utcnow() -> datetime:
    return datetime.now(UTC)


class CommandRecord(BaseModel):
    """One factory-invoked command.

    Only factory-invoked commands are recorded. Commands the coding agent runs in its own
    inner loop are deliberately not here -- see ADR-0004.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    argv: list[str]
    exit_code: int | None = None
    duration_ms: int | None = None
    started_at: datetime = Field(default_factory=utcnow)
    stage: str | None = None
    vm_name: str | None = None


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    command: str
    project: str | None = None
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
    vm_name: str | None = None
    image_digest: str | None = None
    provider: str | None = None
    error: str | None = None


class CheckResult(BaseModel):
    """One doctor check. Shared by host and guest doctor so the JSON shape is identical."""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: CheckStatus
    detail: str = ""
    version: str | None = None
    remediation: str | None = None


class DoctorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CheckStatus
    where: str
    checks: list[CheckResult] = Field(default_factory=list)

    @classmethod
    def of(cls, where: str, checks: list[CheckResult]) -> DoctorReport:
        if any(c.status is CheckStatus.FAIL for c in checks):
            overall = CheckStatus.FAIL
        elif any(c.status is CheckStatus.WARN for c in checks):
            overall = CheckStatus.WARN
        else:
            overall = CheckStatus.PASS
        return cls(status=overall, where=where, checks=checks)

    @property
    def ok(self) -> bool:
        return self.status is not CheckStatus.FAIL


class FeatureState(BaseModel):
    """Per-feature state for the vertical slice. Populated from Milestone 8 (the brief)."""

    model_config = ConfigDict(extra="forbid")

    feature: str
    reference_revision: str | None = None
    spec_status: str = "pending"
    ios_status: str = "pending"
    android_status: str = "pending"
    evaluation_status: str = "pending"
    last_failure: str | None = None
