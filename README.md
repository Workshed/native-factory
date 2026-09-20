# Native Factory

A prototype. It takes a running website as a reference product and has an AI coding agent
build two genuinely native applications from it — Swift/SwiftUI for iOS, Kotlin/Compose
for Android — inside a Tart macOS VM.

> **Status: prototype, not yet working end to end.** The goal is one complete
> website → iOS + Android workflow, not a platform. See
> [`docs/prototype-plan.md`](docs/prototype-plan.md).

Not a transpiler. The website is observed as a product, not read as source. **A WebView
wrapper is a failure of the task**, however well it works.

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
- A Claude Code or GitHub Copilot subscription

## Getting started

```bash
brew install openai/tools/tart openai/tools/tart-guest-agent
python3 scripts/doctor.py                     # what's missing, and how to fix it

tart clone ghcr.io/cirruslabs/macos-tahoe-xcode:26.5 nf
tart set nf --cpu 8 --memory 16384
tart run --no-graphics --dir=work:$PWD/output nf &
tart exec -it nf /bin/zsh -l                  # then run scripts/setup-guest.sh
```

Full setup, including the traps: [`docs/vm.md`](docs/vm.md).

## The Android emulator runs on your Mac, not in the VM

The one thing that cannot be simplified. An ARM64 emulator needs Hypervisor.framework and
cannot be hardware-accelerated inside a macOS guest — it fails with `HV_UNSUPPORTED`.
Everything else Android — SDK, Gradle, unit tests — stays in the VM, which reaches your
emulator over a remote adb server.

[`docs/adr/0002`](docs/adr/0002-android-emulator-outside-the-guest.md) has the reasoning
and the fallbacks. `scripts/spikes/s1-android-adb-over-nat.sh` tests whether the plumbing
actually works, one ADB client at a time.

## Security

**The VM is the only isolation boundary.** OpenHands auto-grants every ACP permission
request and runs the coding agent with permissions bypassed, and scraped website text
travels in the same prompt as your instructions. Read
[`docs/security.md`](docs/security.md) before pointing this at a site you care about.

## Documentation

| | |
|---|---|
| [`docs/prototype-plan.md`](docs/prototype-plan.md) | what we are building and in what order |
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
