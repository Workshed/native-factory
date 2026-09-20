# ADR-0006 — Egress filtering: allow-list considered, default deferred

Date: 2026-09-19 · Status: accepted (user decision) — the argument below is recorded, not acted on

## Context

`docs/architecture.md` §9 establishes that the Tart VM is the **only** isolation boundary:
OpenHands auto-grants every ACP permission request and launches Claude Code in
`bypassPermissions` (Codex in `agent-full-access`) (HANDOFF §4.2). From Milestone 3, untrusted
website text enters the same prompt string as trusted instructions, because `ACPAgent` offers no
structural channel (ADR-0003).

A prompt-injected agent therefore has an unrestricted shell, the workspace, and the provider API
key in its process environment — `Conversation(secrets={...})` masks the key in *logs*, not from
the agent. With open egress, there is no barrier to exfiltration.

HANDOFF §4.2 treats `--net-softnet` with an allow-list as optional, "when egress control is
needed".

## Options considered

**A. Allow-list on by default from Milestone 3.** M1/M2 keep open egress (no untrusted input
exists yet). From M3, `vm.egress: allowlist` becomes the default, permitting the target site's
origin, provider API endpoints, and package registries. Costs a softnet dependency and an
allow-list that must be maintained as builds pull new hosts — Gradle distributions, Maven
mirrors, CocoaPods, npm, Homebrew bottles, Xcode toolchain downloads.

**B. Opt-in, as HANDOFF §4.2 says.** Egress stays open unless configured. Simpler; no softnet
dependency; no mysterious build failures from a blocked mirror. Accepts that a prompt-injected
agent can exfiltrate the API key and the workspace.

## Decision

**B — opt-in**, per the user's decision and HANDOFF §4.2.

The implementing agent's recommendation was A, on the grounds that the M3 combination of
untrusted input, auto-approved permissions and an in-environment API key is exactly the case
egress filtering exists for. That recommendation is recorded here rather than reopened.

## Consequences and mitigations

- The prototype runs with open egress. `tart run --net-softnet` is the mechanism if and
  when this is revisited.
- `scripts/doctor.py` does not check for `softnet`, since nothing requires it yet.
- **Mandatory mitigation:** use a dedicated, rotatable factory API key — never the user's
  primary key. Documented in `docs/security.md`.
- The residual risk is written into `docs/security.md` in plain language so a user opting into
  autonomy knows what they are accepting.
- Revisit at Milestone 3, when the risk first becomes live rather than theoretical.
