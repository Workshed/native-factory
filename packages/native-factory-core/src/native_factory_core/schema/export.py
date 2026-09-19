"""Generate ``schemas/*.schema.json`` from the pydantic models.

The generated files are checked in so that non-Python consumers (the Node crawler, editors
offering YAML completion, future tooling) have a contract without importing Python. CI runs
``--check`` to assert they have not drifted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from native_factory_core.schema.config import ProjectConfig
from native_factory_core.schema.run import CommandRecord, DoctorReport, FeatureState, RunRecord

#: Generated filename -> model. Milestones 3 and 4 add site/screen/feature-spec/evaluation.
EXPORTS: dict[str, type[BaseModel]] = {
    "project-config": ProjectConfig,
    "run-record": RunRecord,
    "command-record": CommandRecord,
    "doctor-report": DoctorReport,
    "feature-state": FeatureState,
}

_BANNER = "Generated from pydantic models by native_factory_core.schema.export -- do not edit."


def schema_for(model: type[BaseModel], name: str) -> dict[str, Any]:
    schema = model.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://native-factory.dev/schemas/{name}.schema.json"
    schema["description"] = f"{schema.get('description', '').strip()}\n\n{_BANNER}".strip()
    return schema


def render(name: str, model: type[BaseModel]) -> str:
    return json.dumps(schema_for(model, name), indent=2, sort_keys=True) + "\n"


def write_all(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in EXPORTS.items():
        path = out_dir / f"{name}.schema.json"
        path.write_text(render(name, model), encoding="utf-8")
        written.append(path)
    return written


def check_all(out_dir: Path) -> list[str]:
    """Return a list of human-readable drift descriptions; empty means in sync."""
    problems: list[str] = []
    for name, model in EXPORTS.items():
        path = out_dir / f"{name}.schema.json"
        expected = render(name, model)
        if not path.exists():
            problems.append(f"{path} is missing")
        elif path.read_text(encoding="utf-8") != expected:
            problems.append(f"{path} is out of date")
    return problems
