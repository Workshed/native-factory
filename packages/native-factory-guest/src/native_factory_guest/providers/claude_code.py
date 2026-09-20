"""Claude Code, through the ACP org's adapter.

Claude Code has no native ACP; the adapter is ``@agentclientprotocol/claude-agent-acp``,
built on the Claude Agent SDK (HANDOFF 4.1). It is pre-installed in the golden image at a
pinned version rather than resolved with ``npx -y`` (ADR-0003), so the command is the
installed binary.

Precedence trap (HANDOFF 4.3): inside Claude Code an environment API key beats a
subscription login, and the SDK strips ``ANTHROPIC_API_KEY`` when an OAuth token is
present. ``resolve_secrets`` therefore injects exactly one credential -- passing both
would silently defeat an explicit ``auth: subscription``.
"""

from __future__ import annotations

from native_factory_core.schema.config import AgentAuth
from native_factory_guest.providers.base import Credential, ProviderAdapter


class ClaudeCodeAdapter(ProviderAdapter):
    name = "claude-code"
    title = "Claude Code"
    supported_auth = frozenset({AgentAuth.SUBSCRIPTION, AgentAuth.API_KEY})
    verified = False  # Milestone 2 exercises it

    def acp_command(self) -> list[str]:
        return ["claude-agent-acp"]

    def credentials(self, auth: AgentAuth) -> tuple[Credential, ...]:
        self.check_auth_supported(auth)
        if auth is AgentAuth.SUBSCRIPTION:
            return (
                Credential(
                    "CLAUDE_CODE_OAUTH_TOKEN",
                    "long-lived subscription token from `claude setup-token`",
                ),
            )
        return (Credential("ANTHROPIC_API_KEY", "metered API key; prefer a dedicated one"),)
