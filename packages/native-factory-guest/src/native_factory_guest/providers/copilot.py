"""GitHub Copilot CLI.

Copilot is **not** a built-in OpenHands provider; it is reached through the Custom
provider with the CLI's own native ACP server (HANDOFF 4.1).

Verified against GitHub's documentation on 2026-09-20:

* install ``npm install -g @github/copilot`` (Node 22+), or
  ``brew install --cask copilot-cli``
* ACP server ``copilot --acp --stdio``
* subscription auth uses a **fine-grained personal access token** with the
  *Copilot Requests* permission, read from ``COPILOT_GITHUB_TOKEN``, ``GH_TOKEN`` or
  ``GITHUB_TOKEN``, in that order of precedence.

BYOK exists (``COPILOT_PROVIDER_*`` / ``COPILOT_PROVIDERS_CONFIG``) and is deliberately
not wired: it reintroduces metered per-token billing, which is the thing subscription
auth is chosen to avoid.
"""

from __future__ import annotations

from native_factory_core.schema.config import AgentAuth
from native_factory_guest.providers.base import Credential, ProviderAdapter, ProviderError


class CopilotAdapter(ProviderAdapter):
    name = "copilot"
    title = "GitHub Copilot CLI"
    supported_auth = frozenset({AgentAuth.SUBSCRIPTION})
    verified = False  # documentation-derived; Milestone 2 exercises it

    def acp_command(self) -> list[str]:
        # --stdio is the default transport, stated explicitly so the intent survives a
        # future change of default.
        return ["copilot", "--acp", "--stdio"]

    def credentials(self, auth: AgentAuth) -> tuple[Credential, ...]:
        self.check_auth_supported(auth)
        return (
            Credential(
                "COPILOT_GITHUB_TOKEN",
                "fine-grained PAT with the 'Copilot Requests' permission (preferred)",
            ),
            Credential("GH_TOKEN", "GitHub CLI token, if it carries Copilot Requests"),
            Credential("GITHUB_TOKEN", "generic GitHub token, lowest precedence"),
        )

    def check_auth_supported(self, auth: AgentAuth) -> None:
        if auth is AgentAuth.API_KEY:
            raise ProviderError(
                "GitHub Copilot does not use an API key in this factory.\n"
                "  Its bring-your-own-key mode (COPILOT_PROVIDER_*) exists but is not\n"
                "  wired, because it reintroduces the metered billing that\n"
                "  agent.auth: subscription is chosen to avoid.\n"
                "  Use agent.auth: subscription with a fine-grained PAT."
            )
        super().check_auth_supported(auth)
