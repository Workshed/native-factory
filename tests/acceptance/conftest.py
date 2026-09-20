"""Fixtures for acceptance tests that need a real Tart host.

These are marked `vm` and excluded from CI. They run on an Apple Silicon host with Tart
installed and a golden image built:

    uv run pytest -m vm tests/acceptance/milestone1/
"""

from __future__ import annotations

import contextlib
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from native_factory.vm.tart import Tart
from native_factory.workspace.layout import Workspace

GOLDEN_ENV = "NF_TEST_GOLDEN"
DEFAULT_GOLDEN = "nf-golden"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip VM tests unless Tart is present, rather than failing confusingly."""
    if shutil.which("tart"):
        return
    skip = pytest.mark.skip(reason="tart is not installed; VM acceptance tests need a real host")
    for item in items:
        if "vm" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def tart() -> Tart:
    return Tart()


@pytest.fixture(scope="session")
def golden_name() -> str:
    return os.environ.get(GOLDEN_ENV, DEFAULT_GOLDEN)


@pytest.fixture(scope="session")
def golden_image(tart: Tart, golden_name: str) -> str:
    if not tart.exists(golden_name):
        pytest.skip(f"golden image {golden_name!r} not built; run: native-factory vm create")
    return golden_name


@pytest.fixture
def temp_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    """An isolated ~/NativeFactory so acceptance runs never touch the real one."""
    monkeypatch.setenv("NATIVE_FACTORY_HOME", str(tmp_path / "NativeFactory"))
    workspace = Workspace.default()
    workspace.ensure()
    return workspace


@pytest.fixture
def worker(tart: Tart, golden_image: str) -> Iterator[str]:
    """A freshly cloned worker, deleted afterwards even if the test fails."""
    name = "nf-acceptance"
    if tart.exists(name):
        _force_remove(tart, name)
    tart.clone(golden_image, name)
    try:
        yield name
    finally:
        _force_remove(tart, name)


def _force_remove(tart: Tart, name: str) -> None:
    # Teardown must not mask the test's own failure, so every error here is swallowed.
    for action in (tart.stop, tart.delete):
        with contextlib.suppress(Exception):
            action(name)
