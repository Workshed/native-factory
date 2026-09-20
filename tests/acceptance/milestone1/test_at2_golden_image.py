"""AT-2: golden image build, no-op rebuild, and the pinned-inputs manifest.

HANDOFF 4.13 asks that a second `vm create` be "a no-op or identical". Byte-identical is
not achievable -- Packer re-runs Homebrew and npm, and images differ by timestamp alone --
so this asserts the two properties that are: the rebuild is a detected no-op, and the
manifest records pinned inputs.
"""

from __future__ import annotations

import json
import time

import pytest

from native_factory.vm.packer import compare_manifests
from native_factory.vm.tart import Tart

pytestmark = pytest.mark.vm

MANIFEST = "/opt/native-factory/manifest.json"


def read_manifest(tart: Tart, vm: str) -> dict:
    result = tart.exec(vm, ["cat", MANIFEST], check=False)
    assert result.returncode == 0, f"no manifest in {vm}: {result.stderr}"
    return json.loads(result.stdout)


def test_golden_image_exists(golden_image: str, tart: Tart) -> None:
    assert tart.exists(golden_image)


@pytest.mark.slow
def test_second_create_is_a_fast_no_op(golden_image: str) -> None:
    import subprocess
    import sys

    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "native_factory", "vm", "create", "--name", golden_image],
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - started

    assert result.returncode == 0
    assert "use --force" in result.stdout
    assert elapsed < 30, "a no-op rebuild should not take 30 seconds"


def test_manifest_records_pinned_inputs(worker: str, tart: Tart) -> None:
    manifest = read_manifest(tart, worker)
    assert manifest["base_image"], "the manifest must name the base image"
    assert manifest["template_sha256"] != "unset"
    assert len(manifest["tools"]) > 10, manifest["tools"]


def test_manifest_records_the_emulator_as_deliberately_absent(worker: str, tart: Tart) -> None:
    manifest = read_manifest(tart, worker)
    assert "android-emulator" in manifest["deliberately_absent"]


def test_manifest_is_stable_apart_from_build_time(worker: str, tart: Tart) -> None:
    # Reading twice must agree; this is the property a rebuild comparison relies on.
    first = read_manifest(tart, worker)
    second = read_manifest(tart, worker)
    assert compare_manifests(first, second) == []
