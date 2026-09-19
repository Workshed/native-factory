"""Cross-cutting invariant 3: only documented Tart commands.

`tart ssh` and a `tart run --headless` flag do not exist -- headless is a Packer option and
SSH is reached through `tart ip` -- and Tart has no live snapshots. These are easy to write
from memory and fail only at runtime against a real VM, so they are checked here.

Docstrings and comments are excluded: documenting that these do not exist is exactly how a
future contributor avoids reaching for them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = sorted((REPO / "packages").rglob("*.py"))

FORBIDDEN = {
    r'"ssh"': "tart ssh does not exist; use tart ip and a real ssh client",
    r'"--headless"': "--headless is a Packer option, not a tart run flag; use --no-graphics",
    r'"snapshot"': "Tart has no live snapshots; the pattern is clone -> run -> delete",
}


def docstring_lines(tree: ast.Module) -> set[int]:
    """Line numbers occupied by docstrings."""
    covered: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
            and first.end_lineno is not None
        ):
            covered.update(range(first.lineno, first.end_lineno + 1))
    return covered


def test_sources_exist() -> None:
    assert SOURCES, "no Python sources found to check"


def test_no_forbidden_tart_usage() -> None:
    offences: list[str] = []
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        if "tart" not in text.lower():
            continue
        skip = docstring_lines(ast.parse(text))
        for line_no, line in enumerate(text.splitlines(), start=1):
            if line_no in skip or line.lstrip().startswith("#"):
                continue
            code = line.split("#", 1)[0]
            for pattern, why in FORBIDDEN.items():
                if re.search(pattern, code):
                    offences.append(
                        f"{path.relative_to(REPO)}:{line_no}: {why}\n    {line.strip()}"
                    )
    assert not offences, "\n".join(offences)


def test_the_check_would_catch_a_real_offence(tmp_path: Path) -> None:
    # A guard that passes vacuously is worse than no guard.
    sample = '"""Docstring mentioning --headless is fine."""\nargv = ["tart", "ssh", name]\n'
    tree = ast.parse(sample)
    skip = docstring_lines(tree)
    hits = [
        line
        for line_no, line in enumerate(sample.splitlines(), start=1)
        if line_no not in skip and re.search(r'"ssh"', line)
    ]
    assert hits == ['argv = ["tart", "ssh", name]']
    assert 1 in skip
