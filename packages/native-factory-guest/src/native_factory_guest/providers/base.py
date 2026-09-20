"""The ACP provider seam.

A provider adapter produces exactly three things and nothing else (ADR-0003):

1. ``acp_command`` -- the argv of the ACP adapter binary;
2. the secrets to inject into the conversation;
3. provider-native MCP configuration, when a provider genuinely needs it.

Everything else in the factory is provider-agnostic, and
``scripts/check-provider-isolation.sh`` fails the build if a provider name appears
outside this package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from native_factory_core.schema.config import AgentAuth


class ProviderError(Exception):
    """Raised with a message intended to be shown directly to the user."""


@dataclass(frozen=True, slots=True)
class Credential:
    """One environment variable a provider will accept, and what it is."""

    env_var: str
    description: str


class ProviderAdapter(ABC):
    """Base class for ACP provider adapters."""

    #: Identifier used in `agent.provider`.
    name: str = ""

    #: Human-readable name for messages.
    title: str = ""

    #: Auth modes this adapter can actually produce credentials for.
    supported_auth: frozenset[AgentAuth] = frozenset()

    #: False when support is documentation-derived and has not been exercised.
    verified: bool = False

    @abstractmethod
    def acp_command(self) -> list[str]:
        """Argv for the ACP adapter, pre-installed in the golden image (ADR-0003)."""

    @abstractmethod
    def credentials(self, auth: AgentAuth) -> tuple[Credential, ...]:
        """Accepted environment variables for an auth mode, in precedence order."""

    def mcp_config(self) -> dict[str, object] | None:
        """Provider-native MCP configuration, if any.

        Usually ``None``: the factory drives XcodeBuildMCP and agent-device as plain CLIs
        precisely so no per-provider MCP wiring is needed (ADR-0003).
        """
        return None

    def check_auth_supported(self, auth: AgentAuth) -> None:
        if auth in self.supported_auth:
            return
        supported = ", ".join(sorted(mode.value for mode in self.supported_auth))
        raise ProviderError(
            f"{self.title} does not support agent.auth: {auth.value}\n  supported: {supported}"
        )

    def resolve_secrets(self, auth: AgentAuth, environ: Mapping[str, str]) -> dict[str, str]:
        """Find the credential in the environment and return what to inject.

        Exactly one credential is returned. Passing several invites precedence surprises --
        Claude Code, for instance, lets an API key beat a subscription login, so sending
        both would silently defeat an explicit `auth: subscription` (HANDOFF 4.3).
        """
        self.check_auth_supported(auth)
        candidates = self.credentials(auth)
        for candidate in candidates:
            value = environ.get(candidate.env_var)
            if value:
                return {candidate.env_var: value}

        names = "\n".join(f"    {c.env_var}    {c.description}" for c in candidates)
        raise ProviderError(
            f"no credential found for {self.title} with agent.auth: {auth.value}\n"
            f"  set one of these in the environment before starting a run:\n{names}\n"
            "  Nothing is read from the golden image and nothing is stored on disk."
        )

    def describe(self) -> str:
        modes = ", ".join(sorted(mode.value for mode in self.supported_auth))
        suffix = "" if self.verified else "  (unverified)"
        return f"{self.name:<12} {self.title:<22} auth: {modes}{suffix}"


def format_command(argv: Sequence[str]) -> str:
    return " ".join(argv)
