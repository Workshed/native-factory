"""Dispatching the guest doctor from the host over `tart exec`."""

from __future__ import annotations

import json

from native_factory.vm.tart import Tart, TartError
from native_factory_core.schema.run import CheckResult, CheckStatus, DoctorReport

#: Installed by the Packer layer into the factory environment.
GUEST_ENTRY = "/opt/native-factory/venv/bin/native-factory-guest"


def _unavailable(detail: str, remediation: str) -> DoctorReport:
    return DoctorReport.of(
        "guest",
        [
            CheckResult(
                name="guest-doctor",
                status=CheckStatus.FAIL,
                detail=detail,
                remediation=remediation,
            )
        ],
    )


def run_guest_doctor(tart: Tart, vm_name: str) -> DoctorReport:
    """Run the guest doctor and parse its JSON.

    A guest that cannot be reached, or that returns something unparseable, is reported as
    a failed check rather than raised: the caller wants a report either way.
    """
    try:
        result = tart.exec(vm_name, [GUEST_ENTRY, "doctor", "--json"], check=False)
    except TartError as exc:
        return _unavailable(
            str(exc),
            f"Is the VM running? native-factory vm start --project <name>\n"
            f"  Then: native-factory vm shell --name {vm_name}",
        )

    stdout = result.stdout.strip()
    if not stdout:
        return _unavailable(
            result.stderr.strip() or f"{GUEST_ENTRY} produced no output",
            "The golden image may predate the guest runtime; rebuild with "
            "`native-factory vm create --force`.",
        )

    try:
        return DoctorReport.model_validate(json.loads(stdout))
    except (json.JSONDecodeError, ValueError) as exc:
        return _unavailable(
            f"could not parse guest doctor output: {exc}",
            f"Run it by hand: native-factory vm shell --name {vm_name} -- {GUEST_ENTRY} doctor",
        )
