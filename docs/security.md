# Security

Read this before pointing Native Factory at anything you care about.

## The one-line threat model

**The inspected website is untrusted input, and the coding agent that reads it has an
unrestricted shell.**

## The agent framework does not sandbox the agent

This is easy to assume and wrong:

- **OpenHands auto-grants every ACP permission request.** There is no human-in-the-loop
  prompt.
- It launches **Claude Code in `bypassPermissions`** and **Codex in `agent-full-access`**.
- Playwright MCP's own README says it is **"not a security boundary"**. Its origin filters
  and secret masking are conveniences, not controls.

**The Tart VM and the mount allow-list are the only isolation.** Everything else in this
document is defence in depth on top of that single boundary. If you disable the VM — by
running the factory outside Tart, for instance — you have no boundary at all.

## Prompt injection

Trusted factory instructions and untrusted observed website content travel in the **same
prompt string**. This is not a shortcut: `ACPAgent` accepts no `tools`, `mcp_config`,
`condenser` or `critic`, so repository context and skills reach the agent only as prompt
text via `agent_context`. There is no structural channel to separate them into.

What reduces the exposure:

1. **Discovery has no LLM in the loop.** The crawl is a deterministic Playwright script;
   interpretation happens afterwards, over stored artefacts. The injection surface is the
   interpretation step, and its input is on disk and auditable.
2. **Observed content is delimited as data** in every prompt that carries it, with
   instructions that content inside the delimiters is evidence to be described, never
   directives to be followed.
3. **The evaluator reads `reference/` read-only** (below).
4. **Code obtained from the inspected website is never executed.**

None of these is a guarantee. A determined injection against an agent with a shell is
contained by the VM or not at all.

## Mounts

Only the project directory is exposed. Never the home directory, never host SSH or cloud
credentials.

Mount flags are enforced by Tart at the VM boundary, which is what makes them useful here:
the factory runtime shares the guest user account with the agent, so file permissions
would not separate them, but the read-only flag holds regardless of uid.

| Stage | `reference` | `work` | `factory` |
|---|---|---|---|
| `discovery` | rw | — | ro |
| `implement` | ro | rw | ro |
| `evaluate` | ro | ro | ro |

`reference/` holds the specification the evaluator judges against. Without the stage-scoped
policy it would sit in the same read-write mount as the generated code, and a
prompt-injected agent could edit the acceptance criteria it is being graded on. `reports/`
is never mounted at all; the host pulls results out.

As a second line, the host hashes `reference/` before and after any stage that mounts it
read-only and fails the run loudly on a mismatch — a mismatch means the boundary did not
hold and the run's results cannot be trusted. See ADR-0005.

## Credentials

**Use a dedicated, rotatable API key. Never your primary one.**

Nothing is baked into the golden image. Authentication is injected per conversation:

| Mode | Source |
|---|---|
| `agent.auth: api-key` (default) | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` via `Conversation(secrets={...})` |
| `agent.auth: oauth-token` | `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` |

The OAuth path is opt-in and carries a caveat: Anthropic's Agent SDK terms restrict
third-party products offering claude.ai login. Precedence inside Claude Code is that an
environment API key beats subscription login, `--bare` ignores the OAuth token, and the SDK
strips `ANTHROPIC_API_KEY` when an OAuth token is present. The SDK isolates Claude
configuration with `CLAUDE_CONFIG_DIR`.

**What `secrets={...}` does and does not do.** It masks the value in logs. It does **not**
hide it from the agent: the ACP subprocess receives it in its environment, and `env` is one
shell command away for an agent running with permissions bypassed. Treat any key you give
the factory as exposed to whatever the agent reads.

Native Factory's own JSONL logs additionally redact credential-shaped keys before writing.

## Network egress

`vm.egress: open | allowlist`, implemented with `tart run --net-softnet`.

**The default is `open`.** This is a deliberate decision, recorded with its counter-argument
in [ADR-0006](adr/0006-egress-allowlist-considered-deferred.md).

The residual risk, stated plainly: from Milestone 3 onward, a prompt-injected agent has an
unrestricted shell, the workspace, the provider API key in its environment, and an open
path to the internet. Open egress is what turns a local compromise into exfiltration.

Mitigations available today:

- A dedicated, rotatable factory key (above), so the blast radius is one key.
- `vm.egress: allowlist` with `vm.egress_allowlist`, for anyone who wants it now. The
  allow-list needs the target site's origin, the provider API endpoint, and the package
  registries a build reaches (npm, Maven Central, Gradle distributions, CocoaPods,
  Homebrew). Expect to extend it when a build fails oddly.

## Discovery artefacts

Redacted from everything persisted, HAR files included: cookies, authentication headers,
tokens, passwords, API keys. Captured credentials are never replayed.

## Git

Local only. Native Factory never pushes and never opens remote pull requests. A run works
with no GitHub repository at all. Remote integration, if it ever exists, will be opt-in.

## Reporting a vulnerability

The project is pre-alpha and not yet published. Once it is, this section will carry a
disclosure address.
