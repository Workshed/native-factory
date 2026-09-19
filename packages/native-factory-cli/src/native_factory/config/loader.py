"""Load and validate ``native-factory.yaml``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from native_factory_core.schema.config import ProjectConfig

CONFIG_FILENAME = "native-factory.yaml"


class ConfigError(Exception):
    """Raised with a message intended to be shown directly to the user."""


def _format_validation_error(path: Path, error: ValidationError) -> str:
    lines = [f"{path} is not valid:"]
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "(root)"
        lines.append(f"  {location}: {item['msg']}")
    return "\n".join(lines)


def load_config(path: Path) -> ProjectConfig:
    if not path.exists():
        raise ConfigError(f"no config at {path}\n  create one with: native-factory init <name>")
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML:\n  {exc}") from exc

    if raw is None:
        raise ConfigError(f"{path} is empty")
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")

    try:
        return ProjectConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(path, exc)) from exc


def dump_config(config: ProjectConfig) -> str:
    data = config.model_dump(mode="json", exclude_defaults=True)
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
