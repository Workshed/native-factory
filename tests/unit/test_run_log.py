"""Structured run logging."""

from __future__ import annotations

from pathlib import Path

import pytest

from native_factory.runs.log import RunLog, log_path_for, redact, timed


class TestRedaction:
    def test_known_keys_are_replaced(self) -> None:
        assert redact({"api_key": "sk-123"})["api_key"] == "[redacted]"

    def test_is_case_insensitive(self) -> None:
        assert redact({"Authorization": "Bearer x"})["Authorization"] == "[redacted]"

    def test_recurses_into_nested_structures(self) -> None:
        payload = {"env": [{"token": "t"}, {"safe": "keep"}]}
        result = redact(payload)
        assert result["env"][0]["token"] == "[redacted]"
        assert result["env"][1]["safe"] == "keep"

    def test_leaves_ordinary_values_alone(self) -> None:
        assert redact({"argv": ["tart", "list"], "exit_code": 0}) == {
            "argv": ["tart", "list"],
            "exit_code": 0,
        }


class TestRunLog:
    def test_events_are_one_json_object_per_line(self, tmp_path: Path) -> None:
        with RunLog(tmp_path / "r.jsonl", "run_1") as log:
            log.event("vm.start", vm="nf-w1")
            log.event("vm.stop", vm="nf-w1")

        events = RunLog(tmp_path / "r.jsonl", "run_1").read_events()
        assert [e["event"] for e in events] == ["vm.start", "vm.stop"]
        assert all(e["run_id"] == "run_1" for e in events)
        assert all("ts" in e for e in events)

    def test_secrets_never_reach_the_file(self, tmp_path: Path) -> None:
        path = tmp_path / "r.jsonl"
        with RunLog(path, "run_1") as log:
            log.event("agent.start", api_key="sk-secret-value")
        assert "sk-secret-value" not in path.read_text(encoding="utf-8")

    def test_appends_rather_than_truncates(self, tmp_path: Path) -> None:
        path = tmp_path / "r.jsonl"
        with RunLog(path, "run_1") as log:
            log.event("one")
        with RunLog(path, "run_1") as log:
            log.event("two")
        assert len(RunLog(path, "run_1").read_events()) == 2

    def test_reading_a_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert RunLog(tmp_path / "absent.jsonl", "r").read_events() == []


class TestTimed:
    def test_emits_start_and_end_with_a_duration(self, tmp_path: Path) -> None:
        with RunLog(tmp_path / "r.jsonl", "run_1") as log:
            with timed(log, "build", target="ios"):
                pass
            events = log.read_events()

        assert [e["event"] for e in events] == ["build.start", "build.end"]
        assert events[1]["duration_ms"] >= 0
        assert events[1]["target"] == "ios"

    def test_failure_is_recorded_and_re_raised(self, tmp_path: Path) -> None:
        log = RunLog(tmp_path / "r.jsonl", "run_1")
        with pytest.raises(RuntimeError, match="boom"), timed(log, "build"):
            raise RuntimeError("boom")
        log.close()

        events = log.read_events()
        assert [e["event"] for e in events] == ["build.start", "build.error"]
        assert events[1]["error_type"] == "RuntimeError"

    def test_extra_fields_set_inside_the_block_reach_the_end_event(self, tmp_path: Path) -> None:
        with RunLog(tmp_path / "r.jsonl", "run_1") as log:
            with timed(log, "clone") as extra:
                extra["image"] = "nf-golden"
            assert log.read_events()[-1]["image"] == "nf-golden"


def test_log_path_groups_runs_together(tmp_path: Path) -> None:
    assert log_path_for(tmp_path, "run_1") == tmp_path / "runs" / "run_1.jsonl"
