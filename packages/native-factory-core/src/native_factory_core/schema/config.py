"""Project configuration schema.

Pydantic models are the source of truth; ``schemas/*.schema.json`` is generated from them
and CI asserts the two stay in sync. Shape follows the brief, with the additions required
by HANDOFF section 4.11 (``agent.auth``, ``targets.android.emulator``, ``xcode.version``,
``maestro.version``, ``vm.base_image``, ``vm.cpu``, ``vm.memory_mb``) and ``vm.egress``
from ADR-0006.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_VIEWPORT_RE = re.compile(r"^(\d{2,5})x(\d{2,5})$")


class Strict(BaseModel):
    """Reject unknown keys everywhere: a typo in a config file should fail loudly."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentAuth(StrEnum):
    """How the coding agent authenticates.

    ``subscription`` uses the seat you already pay for -- a long-lived token minted from
    an existing login. ``api-key`` uses metered per-token billing.

    Named for intent rather than mechanism, because the mechanism differs per provider --
    one mints a long-lived token from an existing CLI login, another wants a fine-grained
    personal access token. Which variables each accepts belongs in its adapter, not here.
    See docs/agents.md.
    """

    SUBSCRIPTION = "subscription"
    API_KEY = "api-key"


class EmulatorPlacement(StrEnum):
    """Where the Android Emulator runs. See ADR-0002.

    An ARM64 emulator needs Hypervisor.framework and cannot be nested inside a macOS guest,
    so ``guest`` is deliberately not a value.
    """

    HOST = "host"
    LINUX_VM = "linux-vm"
    HOST_FALLBACK = "host-fallback"


class Egress(StrEnum):
    OPEN = "open"
    ALLOWLIST = "allowlist"


class Stage(StrEnum):
    """Pipeline stage. Determines the mount policy for a worker VM (ADR-0005)."""

    DISCOVERY = "discovery"
    IMPLEMENT = "implement"
    EVALUATE = "evaluate"


class ProjectSection(Strict):
    name: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][\w .-]*$")]


class SourceSection(Strict):
    url: Annotated[str, Field(pattern=r"^https?://")] | None = None


class AgentSection(Strict):
    # The provider is a free-form identifier resolved at runtime against the adapters
    # registered in native_factory_guest.providers. Adding a provider must not require
    # editing a core enum -- that would make the ACP seam a lie (ADR-0003).
    provider: Annotated[str, Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9-]*$")] = (
        "claude-code"  # provider-name-ok: default identifier, not provider logic
    )
    #: Defaults to the subscription seat rather than metered billing. This departs from
    #: HANDOFF 4.3, which recommends defaulting to an API key; the deciding factor was
    #: cost. See docs/agents.md for the trade-off that comes with it.
    auth: AgentAuth = AgentAuth.SUBSCRIPTION


class IosTarget(Strict):
    enabled: bool = True
    bundle_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]*$")] = "com.example.native"


class AndroidTarget(Strict):
    enabled: bool = True
    application_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")] = (
        "com.example.native"
    )
    emulator: EmulatorPlacement = EmulatorPlacement.HOST
    #: AVD names this project may lease, one per concurrent worker (ADR-0002).
    avds: list[str] = Field(default_factory=list)


class TargetsSection(Strict):
    ios: IosTarget = Field(default_factory=IosTarget)
    android: AndroidTarget = Field(default_factory=AndroidTarget)

    @model_validator(mode="after")
    def at_least_one_target(self) -> Self:
        if not self.ios.enabled and not self.android.enabled:
            raise ValueError("at least one of targets.ios or targets.android must be enabled")
        return self


class Viewport(Strict):
    name: str
    width: Annotated[int, Field(ge=240, le=4096)]
    height: Annotated[int, Field(ge=240, le=4096)]

    def __str__(self) -> str:
        return f"{self.width}x{self.height}"


def _default_viewports() -> list[Viewport]:
    # Seeded from the brief; real breakpoints are discovered by probing, not assumed
    # (docs/architecture.md section 14).
    return [
        Viewport(name="iphone_small", width=375, height=667),
        Viewport(name="iphone", width=393, height=852),
        Viewport(name="android", width=412, height=915),
    ]


class DiscoverySection(Strict):
    viewports: list[Viewport] = Field(default_factory=_default_viewports)
    max_routes: Annotated[int, Field(ge=1, le=10_000)] = 50

    @field_validator("viewports", mode="before")
    @classmethod
    def accept_wxh_strings(cls, value: Any) -> Any:
        """Accept the brief's terse ``- 393x852`` form alongside full objects."""
        if not isinstance(value, list):
            return value
        out: list[Any] = []
        for item in value:
            if isinstance(item, str):
                match = _VIEWPORT_RE.match(item.strip())
                if match is None:
                    raise ValueError(f"viewport {item!r} is not of the form WIDTHxHEIGHT")
                width, height = match.groups()
                out.append(
                    {"name": f"{width}x{height}", "width": int(width), "height": int(height)}
                )
            else:
                out.append(item)
        return out

    @model_validator(mode="after")
    def viewport_names_unique(self) -> Self:
        names = [v.name for v in self.viewports]
        if len(names) != len(set(names)):
            raise ValueError("discovery.viewports names must be unique")
        if not names:
            raise ValueError("discovery.viewports must not be empty")
        return self


class FactorySection(Strict):
    require_spec_approval: bool = True
    max_retries: Annotated[int, Field(ge=0, le=20)] = 3
    preserve_failed_vm: bool = True


class VmSection(Strict):
    #: Pinned by digest, never by tag. HANDOFF section 4.4 documents
    #: sequoia-xcode:latest resolving to 16.4 while 26.x tags exist -- tags lie.
    base_image: str = "ghcr.io/cirruslabs/macos-tahoe-xcode:26.5"
    golden_name: str = "nf-golden"
    cpu: Annotated[int, Field(ge=2, le=64)] = 8
    memory_mb: Annotated[int, Field(ge=4096, le=262_144)] = 16_384
    disk_size_gb: Annotated[int, Field(ge=60, le=2048)] = 160
    egress: Egress = Egress.OPEN
    #: Hosts permitted when egress is ``allowlist``. Unused when ``open`` (ADR-0006).
    egress_allowlist: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def allowlist_requires_entries(self) -> Self:
        if self.egress is Egress.ALLOWLIST and not self.egress_allowlist:
            raise ValueError("vm.egress is 'allowlist' but vm.egress_allowlist is empty")
        return self

    @property
    def pinned_by_digest(self) -> bool:
        return "@sha256:" in self.base_image


class ToolchainSection(Strict):
    """Versions that must be pinned together and smoke-tested as a pair.

    The Maestro iOS XCTest driver has recurring hang issues on new macOS/Xcode
    combinations (HANDOFF section 4.9), so Xcode and Maestro are pinned side by side.
    """

    xcode_version: str = "26.5"
    maestro_version: str = "2.10.0"


class ProjectConfig(Strict):
    """The contents of a project's ``native-factory.yaml``."""

    project: ProjectSection
    source: SourceSection = Field(default_factory=SourceSection)
    agent: AgentSection = Field(default_factory=AgentSection)
    targets: TargetsSection = Field(default_factory=TargetsSection)
    discovery: DiscoverySection = Field(default_factory=DiscoverySection)
    factory: FactorySection = Field(default_factory=FactorySection)
    vm: VmSection = Field(default_factory=VmSection)
    toolchain: ToolchainSection = Field(default_factory=ToolchainSection)

    @property
    def needs_host_emulator(self) -> bool:
        return self.targets.android.enabled and self.targets.android.emulator in (
            EmulatorPlacement.HOST,
            EmulatorPlacement.HOST_FALLBACK,
        )
