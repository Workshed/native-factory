# ADR-0004 — The factory runs the recorded builds and tests; the agent edits code

Date: 2026-09-19 · Status: **superseded by [ADR-0007](0007-prototype-first.md)** · **Deviation from both source documents**

> Superseded on 2026-09-20 by the prototype-first pivot. Kept because the reasoning
> still applies if the factory shape returns at v2. See ADR-0007 for what changed and why.

## Context

The brief requires machine-readable evaluation and that a user "understand what happened without
reading an LLM transcript". Neither the brief nor HANDOFF states who actually invokes the builds
and tests. If the coding agent does, the factory receives only the agent's prose about the run —
exit codes, JUnit XML and parsed diagnostics are lost, and evaluation degrades to trusting a
narrator that is also the author.

## Decision

| | Owner |
|---|---|
| Editing source files | Agent |
| Running builds/tests freely for its own feedback | Agent — unrecorded, unlimited |
| The **recorded** build, test, journey and snapshot runs | **Factory runtime** |

The factory runtime invokes these directly and captures argv, exit code, stdout/stderr and
structured output: `xcodebuild` / `xcrun simctl` (via the XcodeBuildMCP CLI), Gradle
(`assembleDebug`, `testDebugUnitTest`, `installDebug`), `maestro test --format junit --output`,
and the SnapshotTesting / Roborazzi runs.

Only factory-recorded results enter the evaluator, the run record and `native-factory status`.
Agent narration is logged, never scored.

## Consequences

- The evaluator's inputs are trustworthy independently of the agent's honesty or competence.
- `native-factory status` can answer "what happened" from `state.db` alone.
- The agent keeps a fast inner loop; nothing here slows it down.
- The factory needs its own thin wrappers for each build tool — implemented under
  `native_factory_guest/tools/`.
