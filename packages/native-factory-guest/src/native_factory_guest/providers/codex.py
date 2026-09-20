"""OpenAI Codex, through ``@agentclientprotocol/codex-acp`` (HANDOFF 4.1).

Only API-key auth is declared. Codex may well support a ChatGPT subscription sign-in, but
that has not been verified here, and declaring an auth mode that then fails at run time
inside a VM is worse than declaring none.
"""

from __future__ import annotations

from native_factory_core.schema.config import AgentAuth
from native_factory_guest.providers.base import Credential, ProviderAdapter


class CodexAdapter(ProviderAdapter):
    name = "codex"
    title = "OpenAI Codex"
    supported_auth = frozenset({AgentAuth.API_KEY})
    verified = False

    def acp_command(self) -> list[str]:
        return ["codex-acp"]

    def credentials(self, auth: AgentAuth) -> tuple[Credential, ...]:
        self.check_auth_supported(auth)
        return (Credential("OPENAI_API_KEY", "metered API key"),)
