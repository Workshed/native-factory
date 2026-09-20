# ADR-0003 — ACP is the provider boundary; prefer CLIs over MCP servers

Date: 2026-09-19 · Status: **superseded by [ADR-0007](0007-prototype-first.md)**

> Superseded on 2026-09-20 by the prototype-first pivot. Kept because the reasoning
> still applies if the factory shape returns at v2. See ADR-0007 for what changed and why.

## Context

The architecture must permit swapping Claude Code for Codex, Gemini or GitHub Copilot without
touching the product-discovery or mobile-build pipeline (brief). `openhands.sdk.agent.ACPAgent`
is that seam — but it accepts no `tools`, `mcp_config`, `condenser` or `critic` (HANDOFF §4.1),
so every MCP server must be wired through provider-native configuration files that differ per
provider (`.mcp.json` for Claude Code, `config.toml` for Codex).

## Decision

1. **A provider adapter produces exactly three things:** `acp_command`, environment/secrets, and
   provider-native MCP config written into the workspace. Nothing else in the codebase names a
   provider.

2. **Prefer plain CLIs over MCP servers for everything in the pipeline.** HANDOFF §4.9 makes this
   argument for agent-device; it applies at least as strongly to XcodeBuildMCP, whose bare command
   is itself a CLI (HANDOFF §4.7). Using CLIs collapses the per-provider adapter surface to
   approximately zero. MCP servers are reserved for interactive Agent Canvas sessions where a
   human is driving.

3. **Pre-install ACP adapters at pinned versions.** HANDOFF §4.1 gives them as
   `npx -y @agentclientprotocol/claude-agent-acp`. `npx -y` resolves and downloads at invocation,
   making a "reproducible" golden image depend on npm reachability and on whatever version is
   latest at run time. The image installs each adapter globally at a pinned version recorded in
   the manifest; `acp_command` points at the installed binary.

## Consequences

- Adding a provider is one module and one config entry.
- Repository context reaches the agent only as prompt text via `agent_context` — there is no
  structural channel, which is also why trusted instructions and untrusted content share one
  string (see ADR-0006 and `docs/architecture.md` §9).
- Claude Code has no native ACP; the adapter is maintained by the ACP org on the Claude Agent
  SDK. GitHub Copilot is not a built-in OpenHands provider and uses the Custom provider path.
- CI greps for provider names outside `providers/` and the docs.
- A headless ACP client using the Python `agent-client-protocol` package is a named fallback if
  OpenHands ever blocks the pipeline. It is not built speculatively.
