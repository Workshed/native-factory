# VMs

How Native Factory uses Tart. Read `docs/architecture.md` §7 first for the reasoning; this
is the operational detail.

## Install

```bash
brew install openai/tools/tart openai/tools/tart-guest-agent
```

Cirrus Labs joined OpenAI on 2026-04-07, so the tap is `openai/tools`, not `cirruslabs/cli`.
The licence is FSL-1.1-ALv2 — not OSI, but unrestricted for this use, and it converts to
Apache-2.0 after two years. `https://tart.run/licensing/` is stale.

`brew install openai/tools/softnet` is needed only if you set `vm.egress: allowlist`
(ADR-0006). `native-factory doctor` skips the check otherwise.

## Commands used, and commands that do not exist

Native Factory uses only these: `clone`, `run`, `exec [-i] [-t]`, `ip`, `set`, `stop`,
`suspend`, `delete`, `list`.

Three things people reach for **do not exist**:

| Not a thing | What to use |
|---|---|
| `tart ssh` | `tart ip <vm>`, then a real ssh client (`admin`/`admin` in the official images) |
| `tart run --headless` | `--no-graphics`. `headless` is a *Packer* option |
| live snapshots | clone → run → delete; that is the intended pattern |

`tests/contract/test_forbidden_tart_usage.py` greps the sources for these, because they are
easy to write from memory and fail only at runtime against a real VM.

Environment for `tart exec` goes through `/usr/bin/env K=V cmd`; there is no `--env` flag.

## The two-guest ceiling

**A third `tart run` of a macOS guest fails.** Apple's macOS SLA §2.B(iii) independently
caps development/test use at two VM instances per Mac. Linux guests are uncapped.

Consequences, designed in from Milestone 1:

- At most **two features in flight** (Milestone 9's scheduler enforces this).
- The golden image cannot be rebuilt while two workers run; `vm create` checks and says so.
- `native-factory vm start` refuses a third worker **before invoking Tart**, naming the
  limit and listing what is running. Tart would fail anyway, but only after a clone and
  with an opaque message.

## Lifecycle

```text
golden image ──clone──▶ worker ──run──▶ work ──stop──▶ delete  (success)
                                                    └──▶ preserve (failure, if configured)
```

`tart clone` is an APFS copy-on-write clone: near-instant, and the clone's disk grows only
as it diverges.

```bash
native-factory vm create                                   # build the golden image
native-factory vm start --project demo --stage implement   # clone + run a worker
native-factory vm shell                                    # interactive tart exec -it
native-factory vm doctor                                   # guest toolchain report
native-factory vm stop  --name nf-demo                     # stop, leave inspectable
native-factory vm delete --name nf-demo
```

`vm stop` deliberately leaves the VM in place: the brief requires being able to enter a
failed VM for debugging. `factory.preserve_failed_vm` keeps `vm delete` from removing one;
`--force` overrides.

`vm shell` prefers `tart exec -it`. If the guest agent is not answering, fall back to
`ssh admin@$(tart ip <vm>)`.

## Mounts

Mounts appear in the guest at `/Volumes/My Shared Files/<name>`. Which ones, and whether
they are writable, depends on the stage (ADR-0005):

| Stage | `reference` | `work` | `factory` |
|---|---|---|---|
| `discovery` | rw | — | ro |
| `implement` | ro | rw | ro |
| `evaluate` | ro | ro | ro |

`reports/` is never mounted; the host pulls results out over `tart exec`.

Touching a mount from `tart exec` triggers a TCC prompt unless SIP is disabled in the
image. The official base and Xcode images disable it, which is a reason to stay on them; a
vanilla-derived custom image is known to hang here.

## The golden image

Built by Packer from `images/packer/golden.pkr.hcl` over
`ghcr.io/cirruslabs/macos-tahoe-xcode`, pinned by **digest**. Tags lie: HANDOFF §4.4
records `sequoia-xcode:latest` resolving to 16.4 while 26.x tags exist.

Already in the base: Xcode and platforms, Homebrew, git, node@24, mise, openjdk@17, Android
cmdline-tools, platform-tools, `platforms;android-36`, `build-tools;36.0.0`, NDK, tuist,
fastlane, `tart-guest-agent`, SIP disabled.

Added by the factory layer: uv + Python 3.12, Playwright + Chromium/WebKit, Maestro,
agent-device, XcodeBuildMCP, the OpenHands stack in `/opt/native-factory/venv`, pinned ACP
adapters, the first-party `android` CLI, and the `native-factory-guest` wheel.

**Deliberately absent: the Android `emulator` package and system images.** They cannot work
here (ADR-0002); `90-android-cli.sh` fails the build if the emulator is present, and the
guest doctor asserts its absence.

### What "reproducible" means here

Packer + Tart is neither idempotent nor bit-reproducible: a rebuild re-runs Homebrew and
npm, and images differ by timestamp alone. So reproducibility is **pinned inputs plus a
verifiable manifest**, not byte equality:

- `/opt/native-factory/manifest.json` records the base image digest, every installed tool
  version, the macOS version, and the SHA-256 of the template and provisioning scripts.
- Two builds from the same `images/versions.lock.json` must produce equal manifests apart
  from `built_at` and the image digest.
- A second `native-factory vm create` is a detected no-op; `--force` rebuilds.

```bash
native-factory vm manifest nf-golden
```

`images/versions.lock.json` marks which pins have not yet survived a real build
(`verified_against_build`, `pin_after_first_build`). Read the manifest after the first
successful build and feed the resolved versions back into the lock file.

## Disk

| | |
|---|---|
| Xcode base image | ~69 GB compressed pull, ~140 GB on disk |
| plain base image | ~27 GB / ~50 GB |
| OCI cache | budget ~70 GB |
| each worker | sparse clone, grows with divergence |

`doctor` fails below **250 GB** free and warns below 400 GB. HANDOFF §4.4 suggests ~200 GB;
that is a one-worker figure and leaves nothing for two workers plus the cache.

## Nested virtualization

Tart supports `--nested` for **Linux guests only**, and throws for any macOS guest. The
documentation claims M3/M4; M5 is unverified, which is what
`scripts/spikes/s2-nested-virtualization.sh` exists to settle.

This matters only because Linux guests are exempt from the two-guest ceiling: if nested
virt works, running the Android emulator inside a Linux guest (`targets.android.emulator:
linux-vm`) becomes worth revisiting. Until the spike runs, `host` is the only supported
placement.

> **Spike result:** not yet run. Record the outcome here.

## Troubleshooting

**`tart exec` hangs.** Almost always a TCC prompt on a mount path in an image without SIP
disabled. Use an official base image.

**A third VM will not start.** That is the ceiling, not a bug. `native-factory vm list`.

**`vm shell` cannot connect.** The guest agent may not be running. Check `tart ip <vm>`
answers, then fall back to SSH.

**The image build fails part way.** Packer leaves the partial VM behind; `tart delete` it
before retrying, or the next `vm create` will refuse the name.
