# Native Factory — Prototype plan

Status: active. Written 2026-09-20, superseding the ten-milestone implementation plan.
See [ADR-0007](adr/0007-prototype-first.md) for why.

**This is an experiment, not a platform.** The objective is one complete
website → iOS + Android workflow. Infrastructure is added when a demonstrated problem
requires it, and not before.

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
persistent VM is what makes that possible.

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
| 4 | OpenHands Agent Canvas runs, reachable from the host browser | |
| 5 | Claude Code authenticates with its subscription login | |
| 6 | Copilot CLI authenticates with its subscription login | fine-grained PAT, *Copilot Requests* permission |
| 7 | Claude Code drives a trivial repo edit through OpenHands ACP | |
| 8 | Copilot drives the same edit via Custom ACP → `copilot --acp --stdio` | |
| **9** | **An agent creates, builds and runs a trivial Compose app against the host emulator** | plumbing **proven 2026-09-22** without an agent; `scripts/adb-bridge.sh verify` |
| 10 | An agent creates, builds and runs a trivial SwiftUI app | |
| 11 | Playwright inspects a website from inside the VM | cheapest item here |
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
the loop, at 393×852 and 412×915. Capture routes, screenshots, page text, links, buttons,
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
