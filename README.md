# Native Factory

A prototype. It takes a running website as a reference product and has an AI coding agent
build two genuinely native applications from it — Swift/SwiftUI for iOS, Kotlin/Compose
for Android — inside a Tart macOS VM.

Not a transpiler. The website is observed as a product, not read as source. **A WebView
wrapper is a failure of the task**, however well it works.

> **Status: the pieces work; the end-to-end conversion has not been attempted yet.**
> See [`docs/prototype-plan.md`](docs/prototype-plan.md).

## What has actually been demonstrated

All of this is verified on a real machine, not designed on paper.

| | |
|---|---|
| Tart macOS guest, provisioned by script | `scripts/setup-guest.sh`, guest doctor green |
| Claude Code authenticated on a **subscription** | no API key anywhere — see below |
| OpenHands Agent Canvas + ACP driving the agent | agent edited a repo in the VM |
| **Agent built a Compose app** and deployed it | to the emulator on the *host* |
| **Agent built a SwiftUI app** and ran it | on the iOS Simulator, Maestro flow passed |
| Playwright inspection from inside the VM | `scripts/inspect-site.ts` |

Not yet done: the website → native conversion itself, and the GitHub Copilot path.

## How it fits together

```text
              OpenHands Agent Canvas
                       │
                      ACP
             ┌─────────┴─────────┐
        Claude Code        GitHub Copilot CLI
             └─────────┬─────────┘
                  output/
             ┌─────────┴─────────┐
             ▼                   ▼
           SwiftUI             Compose
```

ACP is the abstraction — there is no provider layer of our own. Switching agent changes
nothing about the website inspection, the project structure or the build process.

## Requirements

- Apple Silicon Mac
- [Tart](https://github.com/openai/tart) from the `openai/tools` tap
- ~140 GB free for the VM
- A Claude Code or GitHub Copilot subscription — **no API key needed**

## Getting started

```bash
brew install openai/tools/tart openai/tools/tart-guest-agent
python3 scripts/doctor.py                     # what's missing, and how to fix it

tart clone ghcr.io/cirruslabs/macos-tahoe-xcode:26.5 nf
tart set nf --cpu 8 --memory 16384
tart run --no-graphics \
  --dir=work:$PWD/output \
  --dir=scripts:$PWD/scripts:ro \
  --dir=sources:$PWD/sources:ro nf &

tart exec nf bash -l "/Volumes/My Shared Files/scripts/setup-guest.sh"
tart exec -it nf /bin/zsh -l        # then: claude -> /login   (or copilot -> /login)
python3 scripts/doctor.py --guest   # via tart exec; expect 0 failed
```

Then run a target through the pipeline:

```bash
scripts/agent-canvas.sh up                 # agent UI at http://localhost:8000
scripts/adb-bridge.sh up                   # only for Android work

python3 scripts/console.py                 # http://127.0.0.1:8765
```

Or from the command line:

```bash
scripts/supervise.sh lloyds-mortgage       # runs, halts at the gate, resume by re-running
scripts/supervise.sh lloyds-mortgage approve
scripts/factory.sh   lloyds-mortgage status
```

A target is three files — `target.yaml`, `brief.md`, and whatever driver the explore
stage writes. Prompts are composed from a shared half plus the target's brief, so nothing
is written twice. There is one approval gate, between exploring and building. See
[`docs/workflow.md`](docs/workflow.md).

Switching coding agent is one variable and changes nothing else:

```bash
NF_PROVIDER=copilot scripts/factory.sh <target> build-ios
```

Full setup and the traps: [`docs/vm.md`](docs/vm.md).

## Two things that will catch you out

**The Android emulator runs on your Mac, not in the VM.** An ARM64 emulator needs
Hypervisor.framework and cannot be hardware-accelerated inside a macOS guest — it fails
with `HV_UNSUPPORTED`. Everything else Android stays in the VM, which reaches your
emulator through `scripts/adb-bridge.sh`. Note that **AGP ignores `ADB_SERVER_SOCKET`**,
which is why the bridge forwards `localhost:5037` *inside* the guest rather than setting
an environment variable. [`docs/adr/0002`](docs/adr/0002-android-emulator-outside-the-guest.md)

**The shared mount serves stale content.** Edit a script on the host and run it from
`/Volumes/My Shared Files/` and the guest silently runs the *previous* version; if the
new file is longer, the tail arrives NUL-filled. Use `scripts/run-in-guest.sh`, which
pushes over `tart exec -i` and bypasses the mount.

## Security

**The VM is the only isolation boundary.** OpenHands auto-grants every ACP permission
request and runs the coding agent with permissions bypassed, and scraped website text
travels in the same prompt as your instructions. Read
[`docs/security.md`](docs/security.md) before pointing this at a site you care about.

## Documentation

| | |
|---|---|
| [`docs/workflow.md`](docs/workflow.md) | running a target: stages, the gate, prompt composition |
| [`docs/prototype-plan.md`](docs/prototype-plan.md) | what we are building, in what order, and what is done |
| [`docs/architecture.md`](docs/architecture.md) | how it fits together |
| [`docs/vm.md`](docs/vm.md) | Tart, provisioning, traps |
| [`docs/security.md`](docs/security.md) | what the VM does and does not protect you from |
| [`docs/adr/`](docs/adr/) | decisions, including the ones that were reversed |

`prompts/build-native-apps.md` is the task given to the coding agent. It is deliberately
provider-agnostic.

## History

An earlier attempt built a full factory — CLI, Packer golden image, run database,
provider adapters, 277 tests — before demonstrating that an agent can build a working
native app at all. That was the wrong order.
[ADR-0007](docs/adr/0007-prototype-first.md) records the pivot; the code is preserved on
the `archive/full-factory-m1` branch.

## Licence

Apache-2.0.
