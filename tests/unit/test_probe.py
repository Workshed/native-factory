"""Version detection and comparison."""

from __future__ import annotations

import pytest

from native_factory_core.probe import at_least, extract_version, run, version_tuple


class TestExtractVersion:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("tart 2.28.1", "2.28.1"),
            ("Android Debug Bridge version 1.0.41", "1.0.41"),
            ("Version 33.0.1-8253317", "33.0.1"),
            ("Xcode 26.6\nBuild version 17F113", "26.6"),
            ("no digits here", None),
            ("", None),
        ],
    )
    def test_finds_the_first_dotted_number(self, text: str, expected: str | None) -> None:
        assert extract_version(text) == expected


class TestAtLeast:
    @pytest.mark.parametrize(
        ("found", "required", "expected"),
        [
            ("35.0.0", "35.0.0", True),
            ("36.0.1", "35.0.0", True),
            ("33.0.1", "35.0.0", False),
            ("17.0.14", "17", True),
            ("11.0.2", "17", False),
            ("26.6", "26.6", True),
            ("26.5", "26.6", False),
            ("22.12.0", "22.12", True),
            ("22.11.0", "22.12", False),
        ],
    )
    def test_compares_numerically_not_lexically(
        self, found: str, required: str, expected: bool
    ) -> None:
        # "9" vs "10" is the classic lexical trap.
        assert at_least(found, required) is expected

    def test_nine_is_not_at_least_ten(self) -> None:
        assert at_least("9.0.0", "10.0.0") is False

    def test_unknown_version_is_never_sufficient(self) -> None:
        assert at_least(None, "1.0") is False
        assert at_least("", "1.0") is False


def test_version_tuple_ignores_non_numeric_parts() -> None:
    assert version_tuple("1.2.3") == (1, 2, 3)
    assert version_tuple(None) == ()


class TestRun:
    def test_captures_output(self) -> None:
        result = run(["echo", "hello"])
        assert result.ok is True
        assert "hello" in result.stdout

    def test_missing_binary_is_a_result_not_an_exception(self) -> None:
        # Absence is an ordinary outcome for a doctor check.
        assert run(["definitely-not-a-real-binary-xyz"]).ok is False

    def test_non_zero_exit_is_captured(self) -> None:
        result = run(["sh", "-c", "exit 3"])
        assert result.ok is False
        assert result.code == 3
