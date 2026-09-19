"""The checked-in JSON Schemas must match the pydantic models.

Non-Python consumers (the Node crawler, editor YAML completion) read the generated files,
so drift between them and the models is a broken contract, not a cosmetic problem.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from native_factory.config.export_schemas import repo_schemas_dir
from native_factory_core.schema.export import EXPORTS, check_all

SCHEMAS = repo_schemas_dir()


def test_schemas_are_in_sync_with_the_models() -> None:
    problems = check_all(SCHEMAS)
    assert problems == [], "run: uv run python -m native_factory.config.export_schemas"


@pytest.mark.parametrize("name", sorted(EXPORTS))
def test_each_schema_is_valid_json_with_an_id(name: str) -> None:
    data = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert data["$id"].endswith(f"{name}.schema.json")


def test_project_config_schema_forbids_extra_keys() -> None:
    data = json.loads((SCHEMAS / "project-config.schema.json").read_text(encoding="utf-8"))
    assert data["additionalProperties"] is False


def test_repo_schemas_dir_resolves_to_the_repository() -> None:
    assert SCHEMAS.name == "schemas"
    assert (SCHEMAS.parent / "pyproject.toml").exists()
    assert isinstance(SCHEMAS, Path)
