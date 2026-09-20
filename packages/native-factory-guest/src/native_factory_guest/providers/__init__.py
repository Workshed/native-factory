"""ACP provider adapters.

The registry is a plain dict rather than an enum in core, so adding a provider never
means editing shared code -- which is the only thing that makes the seam real (ADR-0003).
"""

from __future__ import annotations

from native_factory_guest.providers.base import Credential, ProviderAdapter, ProviderError
from native_factory_guest.providers.claude_code import ClaudeCodeAdapter
from native_factory_guest.providers.codex import CodexAdapter
from native_factory_guest.providers.copilot import CopilotAdapter
from native_factory_guest.providers.gemini import GeminiAdapter

_ADAPTERS: tuple[ProviderAdapter, ...] = (
    ClaudeCodeAdapter(),
    CopilotAdapter(),
    CodexAdapter(),
    GeminiAdapter(),
)

REGISTRY: dict[str, ProviderAdapter] = {adapter.name: adapter for adapter in _ADAPTERS}


def get(name: str) -> ProviderAdapter:
    try:
        return REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(REGISTRY))
        raise ProviderError(
            f"unknown agent.provider {name!r}\n  known providers: {known}"
        ) from None


def names() -> list[str]:
    return sorted(REGISTRY)


__all__ = [
    "REGISTRY",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "CopilotAdapter",
    "Credential",
    "GeminiAdapter",
    "ProviderAdapter",
    "ProviderError",
    "get",
    "names",
]
