# Native Factory — Prototype plan

Status: active. Written 2026-09-20, superseding the ten-milestone implementation plan.
See [ADR-0007](adr/0007-prototype-first.md) for why.

**This is an experiment, not a platform.** The objective is one complete
website → iOS + Android workflow. Infrastructure is added when a demonstrated problem
requires it, and not before.

> **The objective is met.** On 2026-09-22 a real website — the Lloyds first-time-buyer
> mortgage affordability calculator — was inspected, explored, and reproduced as a native
> SwiftUI app and a native Compose app, both returning the site's own £247,500 for the
> same inputs. 4/4 Maestro flows on iOS, 2/2 plus 5 unit tests on Android. One feature
> slice of one site: enough to prove the concept, not a general system.

---

## Success criterion

```text
                  Native Factory
                       │
                  OpenHands
                       │
                      ACP
                       │
             ┌─────────┴─────────┐
        Claude Code        GitHub Copilot
             └─────────┬─────────┘
                  same workspace
             ┌─────────┴─────────┐
             ▼                   ▼
           SwiftUI             Compose
```

Changing coding agent must not require changing the website inspection, the project
structure, or the native build process.

## Environment

One Tart macOS guest, created by hand and provisioned with `scripts/setup-guest.sh`.
No golden image, no automatic creation, no automatic destruction.

| In the guest | On the host |
|---|---|
| Xcode + iOS Simulator | Tart |
| Android SDK, JDK, Gradle | **Android Emulator** + `adb` server |
| Git, Node, Playwright, Maestro | the `output/` directory, mounted in |
| OpenHands Agent Canvas | Agent Canvas UI in the browser |
| Claude Code and/or GitHub Copilot CLI | |

**The Android Emulator is on the host, not in the guest.** An ARM64 AVD needs
Hypervisor.framework and fails with `HV_UNSUPPORTED` when nested — this is the one
constraint the prototype cannot simplify away. The guest reaches the host's emulator over
`ADB_SERVER_SOCKET`. See [ADR-0002](adr/0002-android-emulator-outside-the-guest.md).

Authentication uses each agent's normal subscription login, interactively, once. A
persistent VM is what makes that possible — and it works: a conversation ran end to end
with **no `ANTHROPIC_API_KEY` and no `CLAUDE_CODE_OAUTH_TOKEN` set anywhere**. The ACP
subprocess inherits the guest's `HOME` and reads `~/.claude`, because
`acp_isolate_data_dir` defaults to `False`. HANDOFF 4.3 describes the SDK as isolating
`CLAUDE_CONFIG_DIR`; that is true only when that flag is turned on.

## Repository

```text
native-factory/
├── README.md
├── prompts/build-native-apps.md      the provider-agnostic task prompt
├── scripts/
│   ├── doctor.py                     host and guest readiness, stdlib only
│   ├── setup-guest.sh                provision a fresh VM clone
│   ├── inspect-site.ts               Playwright inspection (step 1)
│   └── spikes/                       the two things worth proving early
├── docs/
└── output/                           gitignored; mounted into the guest
    ├── reference/
    ├── ios/
    └── android/
```

## First task — prove the pieces work

Nothing below builds the website → native conversion. Each item either works or it
doesn't, and finding out is the point.

| # | Prove | Notes |
|---|---|---|
| 1 | Tart installs and a macOS guest boots | blocked today on Command Line Tools 16.2 vs Xcode 26.6 |
| 2 | `setup-guest.sh` provisions a fresh clone | re-runnable, so a broken VM is recoverable |
| 3 | `doctor.py --guest` is green inside the VM | |
| 4 | OpenHands Agent Canvas runs, reachable from the host browser | **done** — `scripts/agent-canvas.sh up` |
| 5 | Claude Code authenticates with its subscription login | **done** — `/login`, no API key |
| 6 | Copilot CLI authenticates with its subscription login | fine-grained PAT, *Copilot Requests* permission |
| 7 | Claude Code drives a trivial repo edit through OpenHands ACP | **done 2026-09-22** |
| 8 | Copilot drives the same edit via Custom ACP → `copilot --acp --stdio` | |
| **9** | **An agent creates, builds and runs a trivial Compose app against the host emulator** | plumbing **proven 2026-09-22** without an agent; `scripts/adb-bridge.sh verify` |
| 10 | An agent creates, builds and runs a trivial SwiftUI app | **done 2026-09-22** — plus a Maestro flow |
| 11 | Playwright inspects a website from inside the VM | **done 2026-09-22** — `scripts/inspect-site.ts` |
| 12 | Document the working setup in README.md | |

**Item 9 comes before 10 and 11 deliberately.** It is gated on two unproven things at
once — the emulator plumbing and agent capability — so it is where the prototype is most
likely to fail. `scripts/spikes/s1-android-adb-over-nat.sh` isolates the plumbing half:
it tests the adb CLI, Gradle/AGP, Maestro's bundled dadb and agent-device separately,
because they are four different ADB clients and any of them can ignore
`ADB_SERVER_SOCKET` independently.

Then **stop and report** before building the conversion.

## The workflow, once the pieces work

**Step 1 — Inspect.** `scripts/inspect-site.ts`, a plain Playwright script with no LLM in
the loop, at 393×852 and 412×915. Run it with `scripts/run-in-guest.sh` — see the mount
warning below.

**The deterministic crawl only reaches screen one of an interactive flow.** It follows
links; a multi-step form advances by button. That is by design — the plan's answer is
that the agent drives Playwright itself when the capture does not answer a question, and
that works: on the Lloyds mortgage calculator the agent walked 8 interactions across 5
screens to a real result, wrote its own replayable driver, and produced a 17 KB
`journey.md` documenting every question, option, hint, validation message and the
business rule behind the answer.

Two things it did that were not asked for and are worth keeping:

- captured **unanswered and answered states separately**, which is the state inventory a
  native implementation needs;
- listed the site's **instruction-shaped text** ("Please select 'Buy a home'", "Let us
  know your income") in a section of its own, noting that these address the bank's
  customer and were not acted on. That is the untrusted-content boundary holding in
  practice, not just in the prompt. Capture routes, screenshots, page text, links, buttons,
forms and accessibility information into `output/reference/`, plus a readable
`site.md`. No formal schema. The agent can also drive Playwright itself to revisit the
site when the capture doesn't answer a question.

**Step 2 — iOS.** Point the selected agent at `prompts/build-native-apps.md`. Swift,
SwiftUI, native navigation and controls, `xcodebuild` and `simctl`. Edit → build → run →
fix, in small increments. No XcodeBuildMCP unless plain tooling proves inadequate.

**Step 3 — Android.** The same, in Kotlin and Compose, with Gradle and the `android` CLI,
against the host emulator.

**Step 4 — Smoke test.** A handful of Maestro journeys inferred from the website. Not
comprehensive testing.

**Maestro must be told which device to use.** With the adb bridge up, an Android device
is always visible, so Maestro defaults to it — an iOS flow then fails with
`Package ... is not installed` while reporting `Running on Pixel_9_API_36`, which reads
like a packaging problem and is not one. Pass the target explicitly:

```bash
maestro --device <simulator-udid> test .maestro/flow.yaml    # iOS
maestro --device emulator-5554     test .maestro/flow.yaml    # Android
```

The Maestro iOS XCTest driver itself works: HANDOFF 4.9 flags it for hangs on new
macOS/Xcode pairs, and it passed cleanly on Xcode 26.5 / macOS 26.6.2 (5s, including a
tap and an assertion).

### Acceptance

1. Both projects compile.
2. Both applications launch.
3. Core website functionality exists in both.
4. Important user journeys work.
5. Both use genuinely native UI — a WebView wrapper is a failure, however well it works.

## Not building

No CLI, no provider abstraction, no golden image, no automatic VM lifecycle, no database,
no workflow engine, no reference schema, no evaluator, no API mocking, no visual
regression, no worktree orchestration, no GitHub integration, no cloud, no GUI, no
Homebrew packaging.

These are later improvements, not requirements for proving the concept. The previous
attempt at several of them is preserved on the `archive/full-factory-m1` branch.

## What carried over, and why

| Kept | Reason |
|---|---|
| [ADR-0002](adr/0002-android-emulator-outside-the-guest.md) and the S1 spike | The emulator constraint is physics; the prototype needs it unchanged |
| `scripts/doctor.py` | Turned an opaque Homebrew failure into a 20-second diagnosis on day one |
| [`security.md`](security.md) | The VM is the only boundary, and the agent runs with permissions bypassed |
| [`vm.md`](vm.md) | Tart's real command set, the two-guest ceiling, and the install traps |
| The legacy `android` detection | It exits 0, so a presence check passes against the wrong binary |

## The shared mount goes stale — do not run host-edited scripts from it

Measured 2026-09-22, and it cost an hour:

- a **new** file written on the host is read correctly in the guest;
- a **modified** file keeps returning its old content in the guest, indefinitely;
- when the new content is longer, the tail is NUL-filled to the new length, which
  surfaces as `SyntaxError: Unexpected character '\0'` pointing at a line *past the end*
  of the file;
- deleting and recreating the file on the host does **not** clear it.

So editing a script on the host and running it from `/Volumes/My Shared Files/` silently
runs the previous version. `scripts/run-in-guest.sh` pushes the file over
`tart exec -i` on stdin, which bypasses the mount entirely — use it for anything you are
actively editing.

The direction that matters for the workflow is unaffected: the guest writes into
`output/` and reads its own writes, and the host reads the results.

## Known traps, already paid for

- **`brew install packer` fails** — HashiCorp left homebrew-core for `hashicorp/tap`.
  Moot now that there is no Packer, but the same tap-trust prompt applies to
  `openai/tools`.
- **Homebrew requires tap trust** — `brew trust --formula openai/tools/softnet`.
- **`android` on PATH may be the 2017 SDK Tools script**, which prints a deprecation
  notice and **exits 0**.
- **`platform-tools` must be ≥ 35** for remote adb to behave.
- **Version strings need care** — `v24.5.0` parses as `5.0` under a naive `\b`-anchored
  regex, which reported Node 24 as too old.
- **ESM ignores `NODE_PATH`.** A bare `import 'playwright'` cannot see a global install;
  `createRequire` can.
- **Same-site checks must compare hostnames, not origins.** info.cern.ch serves over
  https and links over http, so an origin comparison stopped the crawl at one page.
  `example.com` would never have shown it — test crawlers against a real site.
