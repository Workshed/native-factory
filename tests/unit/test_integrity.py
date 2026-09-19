"""Read-only tree digests (ADR-0005)."""

from __future__ import annotations

from pathlib import Path

import pytest

from native_factory.workspace.integrity import (
    IntegrityError,
    digest_tree,
    verify_unchanged,
)


def populate(root: Path) -> Path:
    (root / "screens").mkdir(parents=True, exist_ok=True)
    (root / "site.yaml").write_text("name: demo\n", encoding="utf-8")
    (root / "screens" / "home.json").write_text('{"id": "home"}', encoding="utf-8")
    return root


def test_absent_directory_hashes_as_empty(tmp_path: Path) -> None:
    result = digest_tree(tmp_path / "nope")
    assert result.file_count == 0
    assert result.total_bytes == 0


def test_digest_is_stable_across_calls(tmp_path: Path) -> None:
    populate(tmp_path)
    assert digest_tree(tmp_path).digest == digest_tree(tmp_path).digest


def test_digest_counts_files_and_bytes(tmp_path: Path) -> None:
    populate(tmp_path)
    result = digest_tree(tmp_path)
    assert result.file_count == 2
    assert result.total_bytes > 0


def test_content_change_is_detected(tmp_path: Path) -> None:
    populate(tmp_path)
    before = digest_tree(tmp_path)
    (tmp_path / "site.yaml").write_text("name: tampered\n", encoding="utf-8")
    assert digest_tree(tmp_path).digest != before.digest


def test_rename_is_detected_even_at_equal_content(tmp_path: Path) -> None:
    # Layout is part of the digest: swapping two identical files still changes the tree.
    populate(tmp_path)
    before = digest_tree(tmp_path)
    (tmp_path / "site.yaml").rename(tmp_path / "site-renamed.yaml")
    assert digest_tree(tmp_path).digest != before.digest


def test_addition_and_deletion_are_detected(tmp_path: Path) -> None:
    populate(tmp_path)
    before = digest_tree(tmp_path)
    (tmp_path / "extra.txt").write_text("x", encoding="utf-8")
    after_add = digest_tree(tmp_path)
    assert after_add.digest != before.digest

    (tmp_path / "extra.txt").unlink()
    assert digest_tree(tmp_path).digest == before.digest


def test_ds_store_is_ignored(tmp_path: Path) -> None:
    populate(tmp_path)
    before = digest_tree(tmp_path)
    (tmp_path / ".DS_Store").write_bytes(b"\x00finder")
    assert digest_tree(tmp_path).digest == before.digest


def test_verify_unchanged_passes_when_untouched(tmp_path: Path) -> None:
    populate(tmp_path)
    verify_unchanged(tmp_path, digest_tree(tmp_path), label="reference/")


def test_verify_unchanged_explains_the_consequence(tmp_path: Path) -> None:
    populate(tmp_path)
    before = digest_tree(tmp_path)
    (tmp_path / "site.yaml").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(IntegrityError) as caught:
        verify_unchanged(tmp_path, before, label="reference/")

    message = str(caught.value)
    assert "mounted read-only" in message
    assert "cannot be trusted" in message
    assert str(tmp_path) in message
