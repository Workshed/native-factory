"""``python -m native_factory.config.export_schemas [--check]``.

Thin entry point over ``native_factory_core.schema.export`` so the acceptance test in
docs/implementation-plan.md AT-0 has a stable command to call.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from native_factory_core.schema.export import check_all, write_all


def repo_schemas_dir() -> Path:
    # packages/native-factory-cli/src/native_factory/config/export_schemas.py -> repo root
    return Path(__file__).resolve().parents[5] / "schemas"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or verify the JSON Schemas.")
    parser.add_argument("--check", action="store_true", help="verify instead of writing")
    parser.add_argument("--out", type=Path, default=None, help="output directory")
    args = parser.parse_args(argv)

    out = args.out or repo_schemas_dir()

    if args.check:
        problems = check_all(out)
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)
            print(
                "\nRun: uv run python -m native_factory.config.export_schemas",
                file=sys.stderr,
            )
            return 1
        print(f"ok: schemas in {out} are in sync")
        return 0

    written = write_all(out)
    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
