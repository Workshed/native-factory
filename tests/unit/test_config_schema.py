"""Configuration schema behaviour."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from native_factory_core.schema.config import (
    AgentAuth,
    Egress,
    EmulatorPlacement,
    ProjectConfig,
    Stage,
)

MINIMAL = {"project": {"name": "Example"}}


def test_minimal_config_fills_documented_defaults() -> None:
    config = ProjectConfig.model_validate(MINIMAL)

    assert config.project.name == "Example"
    assert config.agent.auth is AgentAuth.API_KEY
    assert config.targets.ios.enabled is True
    assert config.targets.android.emulator is EmulatorPlacement.HOST
    assert config.factory.require_spec_approval is True
    assert config.factory.max_retries == 3
    assert config.vm.cpu == 8
    assert config.vm.memory_mb == 16_384


def test_egress_defaults_to_open_per_adr_0006() -> None:
    assert ProjectConfig.model_validate(MINIMAL).vm.egress is Egress.OPEN


def test_allowlist_egress_requires_entries() -> None:
    with pytest.raises(ValidationError, match="egress_allowlist is empty"):
        ProjectConfig.model_validate(
            {**MINIMAL, "vm": {"egress": "allowlist", "egress_allowlist": []}}
        )


def test_allowlist_egress_accepts_entries() -> None:
    config = ProjectConfig.model_validate(
        {**MINIMAL, "vm": {"egress": "allowlist", "egress_allowlist": ["api.anthropic.com"]}}
    )
    assert config.vm.egress is Egress.ALLOWLIST


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProjectConfig.model_validate({**MINIMAL, "factroy": {"max_retries": 1}})


def test_terse_viewport_strings_from_the_brief_are_accepted() -> None:
    config = ProjectConfig.model_validate(
        {**MINIMAL, "discovery": {"viewports": ["375x667", "393x852"]}}
    )
    assert [(v.width, v.height) for v in config.discovery.viewports] == [(375, 667), (393, 852)]


def test_viewport_objects_are_accepted() -> None:
    config = ProjectConfig.model_validate(
        {**MINIMAL, "discovery": {"viewports": [{"name": "tablet", "width": 820, "height": 1180}]}}
    )
    assert config.discovery.viewports[0].name == "tablet"


def test_malformed_viewport_is_rejected() -> None:
    with pytest.raises(ValidationError, match="WIDTHxHEIGHT"):
        ProjectConfig.model_validate({**MINIMAL, "discovery": {"viewports": ["wide"]}})


def test_duplicate_viewport_names_are_rejected() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        ProjectConfig.model_validate(
            {**MINIMAL, "discovery": {"viewports": ["375x667", "375x667"]}}
        )


def test_disabling_both_targets_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one of"):
        ProjectConfig.model_validate(
            {**MINIMAL, "targets": {"ios": {"enabled": False}, "android": {"enabled": False}}}
        )


def test_emulator_placement_has_no_guest_option() -> None:
    # An ARM64 emulator needs Hypervisor.framework and fails with HV_UNSUPPORTED inside a
    # macOS guest. "guest" must not be expressible. See ADR-0002.
    assert "guest" not in {member.value for member in EmulatorPlacement}


def test_needs_host_emulator_tracks_placement() -> None:
    assert ProjectConfig.model_validate(MINIMAL).needs_host_emulator is True

    linux_vm = ProjectConfig.model_validate(
        {**MINIMAL, "targets": {"android": {"emulator": "linux-vm"}}}
    )
    assert linux_vm.needs_host_emulator is False

    ios_only = ProjectConfig.model_validate({**MINIMAL, "targets": {"android": {"enabled": False}}})
    assert ios_only.needs_host_emulator is False


def test_base_image_digest_pinning_is_detectable() -> None:
    tagged = ProjectConfig.model_validate(MINIMAL)
    assert tagged.vm.pinned_by_digest is False

    digested = ProjectConfig.model_validate(
        {**MINIMAL, "vm": {"base_image": "ghcr.io/cirruslabs/macos-tahoe-xcode@sha256:" + "a" * 64}}
    )
    assert digested.vm.pinned_by_digest is True


def test_stage_values_match_the_mount_policy_table() -> None:
    assert {s.value for s in Stage} == {"discovery", "implement", "evaluate"}
