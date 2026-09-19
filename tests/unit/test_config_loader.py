"""Loading ``native-factory.yaml`` from disk."""

from __future__ import annotations

from pathlib import Path

import pytest

from native_factory.config.loader import ConfigError, dump_config, load_config
from native_factory_core.schema.config import ProjectConfig


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "native-factory.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_a_valid_file(tmp_path: Path) -> None:
    path = write(tmp_path, "project:\n  name: Example\n")
    assert load_config(path).project.name == "Example"


def test_missing_file_suggests_init(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="native-factory init"):
        load_config(tmp_path / "absent.yaml")


def test_invalid_yaml_is_reported_as_yaml(tmp_path: Path) -> None:
    path = write(tmp_path, "project:\n  name: [unclosed\n")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(path)


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="is empty"):
        load_config(write(tmp_path, "\n"))


def test_non_mapping_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="mapping at the top level"):
        load_config(write(tmp_path, "- one\n- two\n"))


def test_validation_errors_name_the_offending_path(tmp_path: Path) -> None:
    path = write(tmp_path, "project:\n  name: Example\nvm:\n  cpu: 1\n")
    with pytest.raises(ConfigError, match=r"vm\.cpu"):
        load_config(path)


def test_dump_round_trips(tmp_path: Path) -> None:
    config = ProjectConfig.model_validate(
        {"project": {"name": "Example"}, "source": {"url": "https://example.com"}}
    )
    path = write(tmp_path, dump_config(config))
    assert load_config(path) == config
