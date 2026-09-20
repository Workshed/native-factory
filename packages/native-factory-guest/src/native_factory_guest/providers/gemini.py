"""Google Gemini CLI in ACP mode (HANDOFF 4.1)."""

from __future__ import annotations

from native_factory_core.schema.config import AgentAuth
from native_factory_guest.providers.base import Credential, ProviderAdapter


class GeminiAdapter(ProviderAdapter):
    name = "gemini"
    title = "Google Gemini CLI"
    supported_auth = frozenset({AgentAuth.API_KEY})
    verified = False

    def acp_command(self) -> list[str]:
        return ["gemini", "--acp"]

    def credentials(self, auth: AgentAuth) -> tuple[Credential, ...]:
        self.check_auth_supported(auth)
        return (
            Credential("GEMINI_API_KEY", "metered API key"),
            Credential("GOOGLE_API_KEY", "alternative variable name"),
        )
