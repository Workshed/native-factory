"""The ACP provider seam."""

from __future__ import annotations

import pytest

from native_factory_core.schema.config import AgentAuth, ProjectConfig
from native_factory_guest import providers
from native_factory_guest.providers import ProviderError


class TestRegistry:
    def test_known_providers(self) -> None:
        assert providers.names() == ["claude-code", "codex", "copilot", "gemini"]

    def test_unknown_provider_lists_the_known_ones(self) -> None:
        with pytest.raises(ProviderError, match="known providers"):
            providers.get("nope")

    def test_config_provider_default_resolves(self) -> None:
        config = ProjectConfig.model_validate({"project": {"name": "demo"}})
        assert providers.get(config.agent.provider) is not None

    @pytest.mark.parametrize("name", providers.names())
    def test_every_adapter_declares_its_contract(self, name: str) -> None:
        adapter = providers.get(name)
        assert adapter.name == name
        assert adapter.title
        assert adapter.supported_auth, f"{name} supports no auth mode"
        assert adapter.acp_command(), f"{name} has no ACP command"

    @pytest.mark.parametrize("name", providers.names())
    def test_no_adapter_claims_to_be_verified_yet(self, name: str) -> None:
        # Milestone 2 is where providers are actually exercised. Until then, claiming
        # verification would be a lie told by a green test suite.
        assert providers.get(name).verified is False


class TestCopilot:
    """GitHub Copilot: subscription seat, no metered key."""

    @pytest.fixture
    def adapter(self):
        return providers.get("copilot")

    def test_uses_the_native_acp_server(self, adapter) -> None:
        assert adapter.acp_command() == ["copilot", "--acp", "--stdio"]

    def test_supports_subscription_auth(self, adapter) -> None:
        assert AgentAuth.SUBSCRIPTION in adapter.supported_auth

    def test_refuses_api_key_auth_and_explains_why(self, adapter) -> None:
        # BYOK exists (COPILOT_PROVIDER_*) but reintroduces the metered billing that
        # subscription auth is chosen to avoid.
        with pytest.raises(ProviderError, match="metered billing"):
            adapter.check_auth_supported(AgentAuth.API_KEY)

    def test_token_precedence_matches_githubs(self, adapter) -> None:
        order = [c.env_var for c in adapter.credentials(AgentAuth.SUBSCRIPTION)]
        assert order == ["COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"]

    def test_highest_precedence_credential_wins(self, adapter) -> None:
        env = {"GITHUB_TOKEN": "low", "COPILOT_GITHUB_TOKEN": "high", "GH_TOKEN": "mid"}
        assert adapter.resolve_secrets(AgentAuth.SUBSCRIPTION, env) == {
            "COPILOT_GITHUB_TOKEN": "high"
        }

    def test_falls_through_to_lower_precedence(self, adapter) -> None:
        assert adapter.resolve_secrets(AgentAuth.SUBSCRIPTION, {"GH_TOKEN": "x"}) == {
            "GH_TOKEN": "x"
        }

    def test_missing_credential_names_every_accepted_variable(self, adapter) -> None:
        with pytest.raises(ProviderError) as caught:
            adapter.resolve_secrets(AgentAuth.SUBSCRIPTION, {})
        message = str(caught.value)
        for variable in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
            assert variable in message
        assert "Copilot Requests" in message


class TestClaudeCodePrecedenceTrap:
    @pytest.fixture
    def adapter(self):
        return providers.get("claude-code")

    def test_subscription_injects_only_the_subscription_token(self, adapter) -> None:
        # Inside Claude Code an environment API key beats a subscription login, so
        # injecting both would silently defeat an explicit auth: subscription
        # (HANDOFF 4.3). Exactly one credential goes in.
        env = {"ANTHROPIC_API_KEY": "sk-metered", "CLAUDE_CODE_OAUTH_TOKEN": "sub"}
        secrets = adapter.resolve_secrets(AgentAuth.SUBSCRIPTION, env)
        assert secrets == {"CLAUDE_CODE_OAUTH_TOKEN": "sub"}
        assert "ANTHROPIC_API_KEY" not in secrets

    def test_api_key_mode_injects_only_the_api_key(self, adapter) -> None:
        env = {"ANTHROPIC_API_KEY": "sk-metered", "CLAUDE_CODE_OAUTH_TOKEN": "sub"}
        assert adapter.resolve_secrets(AgentAuth.API_KEY, env) == {
            "ANTHROPIC_API_KEY": "sk-metered"
        }


class TestUnsupportedCombinations:
    def test_codex_rejects_subscription_rather_than_guessing(self) -> None:
        # Declaring an auth mode that then fails at run time inside a VM is worse than
        # declaring none.
        with pytest.raises(ProviderError, match="does not support"):
            providers.get("codex").resolve_secrets(AgentAuth.SUBSCRIPTION, {})


class TestMcpConfig:
    @pytest.mark.parametrize("name", providers.names())
    def test_no_provider_needs_mcp_wiring(self, name: str) -> None:
        # The factory drives XcodeBuildMCP and agent-device as plain CLIs precisely so
        # the per-provider MCP surface stays empty (ADR-0003).
        assert providers.get(name).mcp_config() is None
