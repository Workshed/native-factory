"""The shipped project template must validate against the schema."""

from __future__ import annotations

from pathlib import Path

import yaml

from native_factory_core.schema.config import ProjectConfig

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "native-factory.yaml"


def test_template_exists() -> None:
    assert TEMPLATE.exists()


def test_template_validates_once_substituted() -> None:
    text = TEMPLATE.read_text(encoding="utf-8").replace("{{PROJECT_NAME}}", "Example")
    config = ProjectConfig.model_validate(yaml.safe_load(text))
    assert config.project.name == "Example"


def test_template_documents_the_emulator_constraint() -> None:
    # A reader editing this file must not be left to guess why "guest" is absent.
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "cannot run inside the macOS guest" in text
    assert "docs/adr/0002" in text
