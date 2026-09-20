"""AT-5: stop, preserve, delete. AT-6: the two-guest ceiling."""

from __future__ import annotations

import pytest

from native_factory.vm.lifecycle import delete_worker, ensure_capacity, stop_worker
from native_factory.vm.tart import MAX_MACOS_GUESTS, Tart, TartVmLimitReachedError, VmInfo

pytestmark = pytest.mark.vm


class TestLifecycle:
    def test_stop_leaves_the_vm_inspectable(self, tart: Tart, worker: str) -> None:
        # The brief requires being able to enter a failed VM for debugging.
        stop_worker(tart, worker)
        assert tart.exists(worker)

    def test_preserve_blocks_deletion(self, tart: Tart, worker: str) -> None:
        assert delete_worker(tart, worker, preserve=True) is False
        assert tart.exists(worker)

    def test_delete_removes_it(self, tart: Tart, worker: str) -> None:
        assert delete_worker(tart, worker, preserve=False) is True
        assert not tart.exists(worker)


class TestTwoGuestCeiling:
    """AT-6. Asserted without booting three VMs: the point is that we refuse first."""

    def test_capacity_check_passes_below_the_limit(self, tart: Tart) -> None:
        ensure_capacity(tart)

    def test_a_third_guest_is_refused_before_tart_is_invoked(
        self, tart: Tart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        running = [
            VmInfo(name=f"nf-{i}", source="local", state="running", os="darwin")
            for i in range(MAX_MACOS_GUESTS)
        ]
        monkeypatch.setattr(tart, "running_macos_guests", lambda: running)

        with pytest.raises(TartVmLimitReachedError) as caught:
            ensure_capacity(tart, about_to_start="nf-third")

        message = str(caught.value)
        assert str(MAX_MACOS_GUESTS) in message
        assert "nf-0" in message and "nf-1" in message
        assert "vm stop" in message

    def test_restarting_an_existing_worker_is_not_counted_against_it(
        self, tart: Tart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        running = [
            VmInfo(name="nf-a", source="local", state="running", os="darwin"),
            VmInfo(name="nf-b", source="local", state="running", os="darwin"),
        ]
        monkeypatch.setattr(tart, "running_macos_guests", lambda: running)
        ensure_capacity(tart, about_to_start="nf-b")

    def test_linux_guests_do_not_count(self, tart: Tart, monkeypatch: pytest.MonkeyPatch) -> None:
        running = [
            VmInfo(name="linux-1", source="local", state="running", os="linux"),
            VmInfo(name="linux-2", source="local", state="running", os="linux"),
            VmInfo(name="nf-a", source="local", state="running", os="darwin"),
        ]
        monkeypatch.setattr(
            tart, "running_macos_guests", lambda: [v for v in running if v.is_macos]
        )
        ensure_capacity(tart, about_to_start="nf-b")
