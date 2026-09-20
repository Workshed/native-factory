"""The Packer template and its provisioning scripts.

The template itself cannot be validated without Packer and a 90-minute build, so these
check the things that are cheap to get wrong and expensive to discover at minute 85.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from native_factory.vm.packer import compare_manifests, plan_build, template_sha256
from native_factory_core.schema.config import ProjectConfig

REPO = Path(__file__).resolve().parents[2]
PACKER_DIR = REPO / "images" / "packer"
SCRIPTS_DIR = PACKER_DIR / "scripts"
TEMPLATE = PACKER_DIR / "golden.pkr.hcl"
LOCK = REPO / "images" / "versions.lock.json"


def test_template_exists() -> None:
    assert TEMPLATE.exists()


def test_every_script_is_referenced_by_the_template() -> None:
    # An orphaned script is a silently skipped install step.
    referenced = set(re.findall(r"scripts/([\w.-]+\.sh)", TEMPLATE.read_text(encoding="utf-8")))
    on_disk = {p.name for p in SCRIPTS_DIR.glob("*.sh")}
    assert on_disk - referenced == set(), "scripts exist but are never run"
    assert referenced - on_disk == set(), "template references missing scripts"


def test_scripts_run_in_numeric_order() -> None:
    referenced = re.findall(r"scripts/([\w.-]+\.sh)", TEMPLATE.read_text(encoding="utf-8"))
    assert referenced == sorted(referenced), "provisioners are out of order"


@pytest.mark.parametrize("script", sorted(SCRIPTS_DIR.glob("*.sh")), ids=lambda p: p.name)
class TestScripts:
    def test_is_valid_bash(self, script: Path) -> None:
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

    def test_is_executable(self, script: Path) -> None:
        assert script.stat().st_mode & 0o111

    def test_fails_fast(self, script: Path) -> None:
        # Without `set -e` a failed install leaves a broken image that looks built.
        assert "set -euo pipefail" in script.read_text(encoding="utf-8")


def strip_comments(text: str, marker: str = "#") -> str:
    """Drop comment lines. Documenting that a flag does not exist must stay possible."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(marker))


def test_template_uses_the_packer_headless_option_not_a_tart_flag() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "headless" in text
    # `tart run --headless` does not exist; confusing the two is the classic error.
    assert "--headless" not in strip_comments(text)


def test_no_credentials_are_baked_in() -> None:
    # Authentication is injected per conversation at run time, never into the image.
    for path in [TEMPLATE, *SCRIPTS_DIR.glob("*.sh")]:
        text = path.read_text(encoding="utf-8")
        for marker in ("ANTHROPIC_API_KEY=", "OPENAI_API_KEY=", "CLAUDE_CODE_OAUTH_TOKEN="):
            assert marker not in text, f"{path.name} bakes in {marker}"


def test_android_script_asserts_the_emulator_is_absent() -> None:
    text = (SCRIPTS_DIR / "90-android-cli.sh").read_text(encoding="utf-8")
    assert "HV_UNSUPPORTED" in text
    assert "exit 1" in text


def test_acp_adapters_are_installed_not_npx_resolved() -> None:
    # ADR-0003: `npx -y` would resolve at invocation and defeat the pinning.
    text = (SCRIPTS_DIR / "80-acp-adapters.sh").read_text(encoding="utf-8")
    assert "npm install -g" in text
    assert "npx -y" not in strip_comments(text)


class TestVersionsLock:
    def test_is_valid_json(self) -> None:
        assert isinstance(json.loads(LOCK.read_text(encoding="utf-8")), dict)

    def test_declares_the_emulator_absent(self) -> None:
        data = json.loads(LOCK.read_text(encoding="utf-8"))
        assert data["android"]["emulator"] == "DELIBERATELY_ABSENT"

    def test_unverified_pins_are_listed_rather_than_implied(self) -> None:
        # Nothing here has survived a real build yet; the file says so out loud.
        data = json.loads(LOCK.read_text(encoding="utf-8"))
        assert data["verified_against_build"] is None
        assert data["pin_after_first_build"]


class TestTemplateHash:
    def test_is_stable(self) -> None:
        assert template_sha256(PACKER_DIR) == template_sha256(PACKER_DIR)

    def test_changes_when_a_script_changes(self, tmp_path: Path) -> None:
        copy = tmp_path / "packer"
        copy.mkdir()
        (copy / "golden.pkr.hcl").write_text("build {}", encoding="utf-8")
        (copy / "s.sh").write_text("echo one", encoding="utf-8")
        before = template_sha256(copy)
        (copy / "s.sh").write_text("echo two", encoding="utf-8")
        assert template_sha256(copy) != before


class TestBuildPlan:
    def test_passes_pins_and_the_template_hash_to_packer(self) -> None:
        config = ProjectConfig.model_validate({"project": {"name": "demo"}})
        plan = plan_build(REPO, config)
        argv = plan.build_argv()
        assert f"image_name={config.vm.golden_name}" in argv
        assert f"base_image={config.vm.base_image}" in argv
        assert f"template_sha256={plan.template_hash}" in argv
        assert "memory_gb=16" in argv  # 16384 MB, and Packer wants GB

    def test_init_precedes_build_in_the_same_directory(self) -> None:
        config = ProjectConfig.model_validate({"project": {"name": "demo"}})
        plan = plan_build(REPO, config)
        assert plan.init_argv()[:2] == ["packer", "init"]
        assert plan.build_argv()[:2] == ["packer", "build"]


class TestManifestComparison:
    def test_build_time_and_digest_are_allowed_to_differ(self) -> None:
        # These cannot be reproducible; everything else must be.
        left = {"built_at": "a", "image_digest": "x", "tools": {"uv": "1"}}
        right = {"built_at": "b", "image_digest": "y", "tools": {"uv": "1"}}
        assert compare_manifests(left, right) == []

    def test_a_changed_tool_version_is_reported(self) -> None:
        left = {"built_at": "a", "tools": {"uv": "1"}}
        right = {"built_at": "b", "tools": {"uv": "2"}}
        assert compare_manifests(left, right) == ["tools"]
