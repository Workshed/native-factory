# Running a target through the pipeline

## The console

```bash
python3 scripts/console.py      # http://127.0.0.1:8765
```

Stdlib only, loopback only, no auth. It holds **no state of its own**: everything it
shows is read from `state.json`, `runs.jsonl`, `targets/` and the filesystem, and every
button shells out to `supervise.sh`. So the CLI and the console are interchangeable, and
the console being down blocks nothing.

What it is for, in one line: **putting `journey.md` and the screenshots next to the
Approve button.** That is the only thing here a terminal cannot do, and it is why a gate
that had been dismissed twice becomes a gate.

It also creates targets, edits `brief.md` (writing the file, showing the diff), renders
the finished apps' screenshots, and links out to Agent Canvas for watching a live agent —
which remains the one thing Canvas does better than we would.

One job at a time, enforced: the two-guest ceiling means concurrent runs would contend on
the VM, the emulator and Canvas.

## The command line

```bash
scripts/supervise.sh <target>              # run, or resume where it stopped
scripts/supervise.sh <target> approve      # release the gate
scripts/supervise.sh <target> reject "…"   # stop, with a reason
scripts/supervise.sh <target> state        # machine-readable current state
scripts/supervise.sh <target> reset        # forget progress; keeps output

scripts/factory.sh <target> <stage>        # one stage, directly
```

`supervise.sh` decides **which** stage runs next; `factory.sh` decides **how** a stage
runs and remains usable on its own. That split matters the first time the supervisor has
a bug.

### It exits at the gate rather than sleeping in it

A supervisor that waits is a process to supervise in turn — a pid to track, something to
restart after a reboot, something to leak. Exiting means state lives entirely in
`state.json`, resuming is just running the command again, and completed stages are
skipped because they are recorded:

```
✓ inspect (done)
✓ gate (approved)
== build-ios
```

The console's Approve button therefore writes a file and re-invokes the supervisor. It
signals nothing.

### Rejection

`reject` records the reason in `state.json` and `runs.jsonl`, then stops and tells you to
edit `targets/<t>/brief.md`. It deliberately does not re-run anything: the brief is the
fix, and re-running against an unchanged brief would mostly reproduce whatever was
rejected.

### The plan is per target

Default: `inspect explore gate build-ios build-android capture test`. Override with
`plan:` in `target.yaml` — `lloyds-locations` omits `explore` because its navigation is
links, so the deterministic crawl already reaches everything. `gate` sits in the plan as
a pseudo-stage so that moving it is a matter of editing a plan rather than editing a
script.

## Stages

| Stage | Does | Produces |
|---|---|---|
| `inspect` | deterministic Playwright crawl, no LLM | `reference/site.md`, per-screen JSON, screenshots |
| `explore` | agent walks the interactive flow | `reference/journey.md`, a replayable driver |
| **gate** | **stop and read** | — |
| `approve` | mark the reference reviewed | `reference/APPROVED` |
| `build-ios` | agent builds | `ios/` + `ios/NOTES.md` |
| `build-android` | agent builds | `android/` + `android/NOTES.md` |
| `source` | sync supplementary source (runs before each build) | `sources/<target>/` |
| `capture` | screenshots of the finished apps | `screenshots/<platform>/` |
| `test` | re-run the committed Maestro flows, excluding `capture.yaml` | pass/fail |
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
  target.yaml            name, url, max_routes; engine/include_path/plan when needed;
                         source_path or source_repo; bundle_id and application_id
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

Nothing else changes: not the crawl, not the prompts, not the project layout, not the
build. That is the ACP seam doing its job.

| Provider | How it is reached |
|---|---|
| `claude-code`, `codex`, `gemini-cli`, `kimi-code`, `opencode`, `pi` | built into OpenHands; named directly |
| `copilot` | **not** built in — the `custom` provider with `copilot --acp --stdio` |

That distinction is invisible from the outside and was wrong here for a while: the runner
passed the provider name straight through as `acp_server`, which works for the six
built-ins and is rejected for Copilot. `provider_settings()` now resolves it.

## Preconditions

`build-*` requires Agent Canvas (`scripts/agent-canvas.sh up`). `build-android` and the
Android half of `test` additionally require the emulator bridge
(`scripts/adb-bridge.sh up`); the runner checks and refuses early rather than failing
halfway through a build.

## What this deliberately is not

No scheduler, no parallel targets, no retries, no database, no evaluator. `runs.jsonl` and
221 lines of bash cover what has actually been needed. When a second target shows that
something here is genuinely missing, add it then.
