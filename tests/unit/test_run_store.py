"""Run records in SQLite."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from native_factory.runs.ids import new_run_id
from native_factory.runs.store import RunStore
from native_factory_core.schema.run import CommandRecord, FeatureState, RunRecord, RunStatus


def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "state.db")


class TestRunIds:
    def test_is_sortable_and_unique(self) -> None:
        early = new_run_id(datetime(2026, 1, 1, tzinfo=UTC))
        late = new_run_id(datetime(2026, 6, 1, tzinfo=UTC))
        assert early < late
        assert new_run_id() != new_run_id()

    def test_is_filename_safe(self) -> None:
        assert not set(new_run_id()) & set('/\\:*?"<>| ')


class TestRuns:
    def test_start_and_fetch(self, tmp_path: Path) -> None:
        db = store(tmp_path)
        record = db.start_run(RunRecord(id=new_run_id(), command="doctor"))
        fetched = db.get_run(record.id)
        assert fetched is not None
        assert fetched.command == "doctor"
        assert fetched.status is RunStatus.RUNNING
        assert fetched.ended_at is None

    def test_finish_sets_status_and_end_time(self, tmp_path: Path) -> None:
        db = store(tmp_path)
        record = db.start_run(RunRecord(id=new_run_id(), command="vm create"))
        db.finish_run(record.id, RunStatus.OK)
        fetched = db.get_run(record.id)
        assert fetched is not None
        assert fetched.status is RunStatus.OK
        assert fetched.ended_at is not None

    def test_failure_keeps_the_error(self, tmp_path: Path) -> None:
        db = store(tmp_path)
        record = db.start_run(RunRecord(id=new_run_id(), command="vm start"))
        db.finish_run(record.id, RunStatus.FAILED, error="tart refused a third guest")
        fetched = db.get_run(record.id)
        assert fetched is not None
        assert fetched.error == "tart refused a third guest"

    def test_unknown_run_is_none(self, tmp_path: Path) -> None:
        assert store(tmp_path).get_run("run_nope") is None

    def test_recent_runs_are_newest_first_and_filterable(self, tmp_path: Path) -> None:
        db = store(tmp_path)
        for index, project in enumerate(["a", "b", "a"]):
            db.start_run(
                RunRecord(
                    id=f"run_{index}",
                    command="inspect",
                    project=project,
                    started_at=datetime(2026, 1, index + 1, tzinfo=UTC),
                )
            )
        assert [r.id for r in db.recent_runs()] == ["run_2", "run_1", "run_0"]
        assert [r.id for r in db.recent_runs(project="a")] == ["run_2", "run_0"]
        assert len(db.recent_runs(limit=1)) == 1


class TestCommands:
    def test_recorded_in_order_with_argv_preserved(self, tmp_path: Path) -> None:
        db = store(tmp_path)
        run = db.start_run(RunRecord(id=new_run_id(), command="vm doctor"))
        for argv in (["tart", "list"], ["tart", "exec", "nf-w1", "sw_vers"]):
            db.record_command(CommandRecord(run_id=run.id, argv=argv, exit_code=0))

        recorded = db.commands_for(run.id)
        assert [c.argv for c in recorded] == [
            ["tart", "list"],
            ["tart", "exec", "nf-w1", "sw_vers"],
        ]

    def test_cascade_delete_follows_the_run(self, tmp_path: Path) -> None:
        db = store(tmp_path)
        run = db.start_run(RunRecord(id=new_run_id(), command="x"))
        db.record_command(CommandRecord(run_id=run.id, argv=["tart", "list"]))
        # Reaching into _connect deliberately: this exercises the FK cascade itself.
        with db._connect() as conn:
            conn.execute("DELETE FROM runs WHERE id = ?", (run.id,))
        assert db.commands_for(run.id) == []


class TestFeatures:
    def test_upsert_replaces_rather_than_duplicates(self, tmp_path: Path) -> None:
        db = store(tmp_path)
        db.upsert_feature("demo", FeatureState(feature="login"))
        db.upsert_feature("demo", FeatureState(feature="login", ios_status="built"))

        features = db.features("demo")
        assert len(features) == 1
        assert features[0].ios_status == "built"
        assert features[0].android_status == "pending"

    def test_scoped_per_project(self, tmp_path: Path) -> None:
        db = store(tmp_path)
        db.upsert_feature("a", FeatureState(feature="login"))
        db.upsert_feature("b", FeatureState(feature="login"))
        assert len(db.features("a")) == 1


class TestDeviceLeases:
    def test_a_serial_can_be_leased_once(self, tmp_path: Path) -> None:
        # Two workers share one host adb server; without this they both grab the same
        # emulator (ADR-0002).
        db = store(tmp_path)
        assert db.acquire_lease("emulator-5554", "run_a", avd="Pixel_9", vm_name="nf-a") is True
        assert db.acquire_lease("emulator-5554", "run_b", avd="Pixel_9", vm_name="nf-b") is False

    def test_release_frees_the_serial(self, tmp_path: Path) -> None:
        db = store(tmp_path)
        db.acquire_lease("emulator-5554", "run_a", avd="Pixel_9", vm_name=None)
        db.release_lease("emulator-5554")
        assert db.acquire_lease("emulator-5554", "run_b", avd="Pixel_9", vm_name=None) is True

    def test_releasing_a_run_frees_all_its_devices(self, tmp_path: Path) -> None:
        db = store(tmp_path)
        db.acquire_lease("emulator-5554", "run_a", avd="A", vm_name=None)
        db.acquire_lease("emulator-5556", "run_a", avd="B", vm_name=None)
        db.release_leases_for_run("run_a")
        assert db.leases() == {}


def test_store_is_reopenable(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    RunStore(path).start_run(RunRecord(id="run_x", command="doctor"))
    assert RunStore(path).get_run("run_x") is not None
