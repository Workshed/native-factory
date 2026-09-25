# Running a target through the pipeline

```bash
scripts/factory.sh <target> <stage> [--yes]
scripts/factory.sh lloyds-mortgage all
```

## Stages

| Stage | Does | Produces |
|---|---|---|
| `inspect` | deterministic Playwright crawl, no LLM | `reference/site.md`, per-screen JSON, screenshots |
| `explore` | agent walks the interactive flow | `reference/journey.md`, a replayable driver |
| **gate** | **stop and read** | — |
| `approve` | mark the reference reviewed | `reference/APPROVED` |
| `build-ios` | agent builds | `ios/` + `ios/NOTES.md` |
| `build-android` | agent builds | `android/` + `android/NOTES.md` |
| `capture` | screenshots of the finished apps | `screenshots/<platform>/` |
| `test` | re-run the committed Maestro flows | pass/fail |
| `status` | what has run, from `runs.jsonl` | |

`all` runs the lot, stopping at the gate. `--yes` approves automatically — for batches,
once you trust the target.

**`explore` is optional.** It exists for flows that advance by button, where a link-
following crawl reaches screen one and stops. A content site whose navigation is links
needs only `inspect` — the second target produced ten usable screens that way and no
`journey.md`. Run `explore` when `site.md` plainly stops short of the thing you care
about.

## Why only one gate

`journey.md` costs the agent about half an hour and a human about two minutes to read. A
build costs an hour and is hard to redirect once it is wrong. That asymmetry is the entire
argument, and it only applies in one place. Gates before writing code, before running, or
per-iteration would cost attention and catch nothing — the build either compiles and
passes its flows or it does not, and that is cheaper to observe than to supervise.

What the gate is actually for: *did it walk the right branch of the flow, and did it find
the rule behind the result?* Both are obvious in two minutes of reading and invisible from
a build log.

## Layout

```text
targets/<t>/
  target.yaml            name, url, max_routes, and engine/include_path when needed
  brief.md               the target-specific half of the prompt
  walk.ts                the driver the explore stage produced
  journey-actions.json   its declarative action list

prompts/
  explore.md             shared: how to drive Playwright, what to capture, untrusted content
  build-native-apps.md   shared: parity not pixels, no WebView, incremental method
  platform-ios.md        shared
  platform-android.md    shared

output/<t>/
  reference/  ios/  android/  runs.jsonl
```

## Prompt composition

Nothing is written per target twice:

```text
prompts/<stage>.md  +  targets/<t>/brief.md  +  prompts/platform-<p>.md
```

Measured on the first real target, about 60% of each prompt was the shared half. The
per-target brief carries scope, the business rule, branding constraints, and which
deviations are wanted deliberately.

## Screenshots

`capture` runs each app's own `.maestro/capture.yaml` — a flow the build agent writes
alongside the app, so it follows the real navigation and stays correct as the app
changes. Builds made before that was asked for fall back to launching the app and taking
a single shot, so the stage is useful on existing output rather than only on new builds.

## Each target's output is a git repository

`output/<t>/` is `git init`-ed on first use, and every stage that changes files commits,
with its conversation id in the message.

This answers "how do I get at the code" with a tool you already have, and three things
fall out for free: **diffs between runs** when a site changes and the target is rebuilt,
provenance in the commit trail, and no file browser to write. Build products —
`build/`, `.gradle/`, `DerivedData/`, `local.properties` — are ignored.

```bash
git -C output/<t> log --oneline
git -C output/<t> show --stat HEAD
```

The parent repository ignores `output/` entirely, so these repositories are independent
and stay unpushed.

## Provenance

Every stage appends to `output/<t>/runs.jsonl`: timestamp, stage, conversation id, the
first 16 hex of the prompt's SHA-256, and the outcome. That answers "which conversation
produced this, from which prompt" — the question that was unanswerable when runs were
hand-typed `curl` calls.

```bash
scripts/factory.sh lloyds-mortgage status
```

## Switching coding agent

```bash
NF_PROVIDER=copilot scripts/factory.sh <target> build-ios
```

Any key from OpenHands' ACP provider registry. Nothing else changes: not the crawl, not
the prompts, not the project layout, not the build. That is the ACP seam doing its job.

## Preconditions

`build-*` requires Agent Canvas (`scripts/agent-canvas.sh up`). `build-android` and the
Android half of `test` additionally require the emulator bridge
(`scripts/adb-bridge.sh up`); the runner checks and refuses early rather than failing
halfway through a build.

## What this deliberately is not

No scheduler, no parallel targets, no retries, no database, no evaluator. `runs.jsonl` and
221 lines of bash cover what has actually been needed. When a second target shows that
something here is genuinely missing, add it then.
