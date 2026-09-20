# ADR-0005 — Mounts are stage-scoped; `reference/` is read-only outside discovery

Date: 2026-09-19 · Status: **superseded by [ADR-0007](0007-prototype-first.md)** · **Addresses a gap in HANDOFF §4.2**

> Superseded on 2026-09-20 by the prototype-first pivot. Kept because the reasoning
> still applies if the factory shape returns at v2. See ADR-0007 for what changed and why.

## Context

HANDOFF §4.2 mounts `~/NativeFactory/projects/<name>` read-write and keeps only config
read-only. But `reference/` holds the specification the evaluator judges against, and §4.2
simultaneously establishes that the agent runs with auto-approved ACP permissions and an
unrestricted shell in `bypassPermissions`. Under that combination, a prompt-injected agent can
edit the acceptance criteria it is being graded on, and the reports that record the verdict.

The factory runtime shares the guest user account with the ACP agent (the runtime is
guest-resident by decision), so uid separation is not available. Tart's mount flags, however,
are enforced at the VM boundary and hold regardless of uid.

## Decision

`vm start --stage <stage>` composes `--dir` flags per stage rather than mounting one directory:

| Stage | `reference` | `work` (ios/, android/) | `factory` (config) |
|---|---|---|---|
| discovery | `rw` | — | `:ro` |
| implement | `:ro` | `rw` | `:ro` |
| evaluate | `:ro` | `:ro` | `:ro` |

`reports/` is never mounted; the host pulls results out over `tart exec`.

Additionally, the host hashes `reference/` before handing a VM to any stage that mounts it `:ro`
and re-verifies afterwards. A mismatch fails the run loudly.

## Consequences

- The evaluator's inputs cannot be rewritten by the stage being evaluated, even under full
  agent compromise.
- `vm start` grows a `--stage` argument in Milestone 1, before the stages that need it exist.
  This is deliberate: retrofitting a mount policy after M3 and M7 depend on the loose one is
  considerably harder.
- Acceptance test AT-3 asserts the read-only flag actually holds by attempting a write.
