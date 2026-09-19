"""Tart argv construction. Pure functions, no VM."""

from __future__ import annotations

from pathlib import Path

import pytest

from native_factory.vm.mounts import Mount
from native_factory.vm.tart import (
    MAX_MACOS_GUESTS,
    TartVmLimitReachedError,
    TartVmNotFoundError,
    classify,
    clone_argv,
    delete_argv,
    exec_argv,
    ip_argv,
    list_argv,
    parse_list_output,
    run_argv,
    set_argv,
    stop_argv,
)


def test_clone() -> None:
    assert clone_argv("ghcr.io/x/y:1", "nf-w1") == ["tart", "clone", "ghcr.io/x/y:1", "nf-w1"]


def test_run_defaults_to_no_graphics_with_the_name_last() -> None:
    assert run_argv("nf-w1") == ["tart", "run", "--no-graphics", "nf-w1"]


def test_run_emits_one_dir_flag_per_mount_in_order() -> None:
    mounts = [
        Mount("reference", Path("/w/reference"), read_only=True),
        Mount("work", Path("/w/work")),
    ]
    assert run_argv("nf-w1", mounts=mounts) == [
        "tart",
        "run",
        "--no-graphics",
        "--dir=reference:/w/reference:ro",
        "--dir=work:/w/work",
        "nf-w1",
    ]


def test_run_with_softnet_allowlist() -> None:
    argv = run_argv("nf-w1", net_softnet=True, softnet_allow=["api.example.com", "pypi.org"])
    assert "--net-softnet" in argv
    assert "--net-softnet-allow=api.example.com,pypi.org" in argv


def test_run_without_softnet_emits_no_network_flags() -> None:
    assert not [flag for flag in run_argv("nf-w1") if "softnet" in flag]


def test_exec_simple() -> None:
    assert exec_argv("nf-w1", ["ls", "-la"]) == ["tart", "exec", "nf-w1", "ls", "-la"]


def test_exec_passes_env_through_usr_bin_env() -> None:
    # `tart exec` has no --env flag; /usr/bin/env is the documented mechanism.
    argv = exec_argv("nf-w1", ["printenv"], env={"B": "2", "A": "1"})
    assert argv == ["tart", "exec", "nf-w1", "/usr/bin/env", "A=1", "B=2", "printenv"]


def test_exec_interactive_flags_precede_the_vm_name() -> None:
    argv = exec_argv("nf-w1", ["/bin/zsh"], interactive=True, tty=True)
    assert argv[:5] == ["tart", "exec", "-i", "-t", "nf-w1"]


def test_exec_requires_a_command() -> None:
    with pytest.raises(ValueError, match="requires a command"):
        exec_argv("nf-w1", [])


def test_set_builds_only_the_requested_properties() -> None:
    assert set_argv("nf-w1", cpu=8, memory_mb=16384) == [
        "tart",
        "set",
        "--cpu",
        "8",
        "--memory",
        "16384",
        "nf-w1",
    ]


def test_set_requires_at_least_one_property() -> None:
    with pytest.raises(ValueError, match="at least one property"):
        set_argv("nf-w1")


def test_trivial_commands() -> None:
    assert stop_argv("a") == ["tart", "stop", "a"]
    assert delete_argv("a") == ["tart", "delete", "a"]
    assert ip_argv("a") == ["tart", "ip", "a"]
    assert list_argv() == ["tart", "list", "--format", "json"]


class TestErrorClassification:
    def test_vm_limit_is_actionable(self) -> None:
        error = classify(["tart", "run", "c"], 1, "Error: maximum number of virtual machines")
        assert isinstance(error, TartVmLimitReachedError)
        assert str(MAX_MACOS_GUESTS) in str(error)
        assert "native-factory vm list" in str(error)

    def test_missing_vm(self) -> None:
        assert isinstance(
            classify(["tart", "ip", "x"], 1, "VM x does not exist"), TartVmNotFoundError
        )

    def test_unknown_error_keeps_the_stderr(self) -> None:
        error = classify(["tart", "run", "x"], 2, "something went sideways")
        assert "something went sideways" in str(error)
        assert error.code == 2


class TestListParsing:
    def test_json(self) -> None:
        payload = (
            '[{"Source":"local","Name":"nf-golden","Disk":90,"Size":42.5,"State":"stopped"},'
            '{"Source":"local","Name":"nf-w1","Disk":90,"Size":1.2,"State":"running"}]'
        )
        vms = parse_list_output(payload)
        assert [vm.name for vm in vms] == ["nf-golden", "nf-w1"]
        assert vms[1].running is True
        assert vms[0].running is False
        assert vms[1].size_gb == 1.2

    def test_table_fallback(self) -> None:
        text = "Source Name      Disk Size State\nlocal  nf-w1     90   1.2  running\n"
        vms = parse_list_output(text)
        assert len(vms) == 1
        assert vms[0].name == "nf-w1"
        assert vms[0].running is True

    def test_empty(self) -> None:
        assert parse_list_output("   ") == []

    def test_absent_os_is_assumed_macos(self) -> None:
        # Over-counting refuses a third VM we might have been able to start, which is the
        # safe direction to be wrong in.
        vms = parse_list_output('[{"Name":"a","Source":"local","State":"running"}]')
        assert vms[0].is_macos is True

    def test_linux_guests_are_not_counted_as_macos(self) -> None:
        vms = parse_list_output('[{"Name":"a","Source":"local","State":"running","OS":"linux"}]')
        assert vms[0].is_macos is False
