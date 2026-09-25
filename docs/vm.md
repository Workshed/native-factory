# VMs

How Native Factory uses Tart. Read `docs/architecture.md` §7 first for the reasoning; this
is the operational detail.

## Install

```bash
brew install openai/tools/tart openai/tools/tart-guest-agent
brew install hashicorp/tap/packer            # only needed to build the golden image
```

Two things will trip you up here.

**Packer is not in homebrew-core.** HashiCorp relicensed to BUSL-1.1 in 2023 and their
formulae moved to `hashicorp/tap`; plain `brew install packer` fails with "No available
formula". Using Packer as a build tool does not affect this project's Apache-2.0 licence.

**Homebrew now requires tap trust.** A first install from either tap may stop with
`Refusing to load formula ... from untrusted tap`. Trust the specific formula rather than
the whole tap:

```bash
brew trust --formula openai/tools/softnet
brew trust --formula hashicorp/tap/packer
```

Cirrus Labs joined OpenAI on 2026-04-07, so the tap is `openai/tools`, not `cirruslabs/cli`.
The licence is FSL-1.1-ALv2 — not OSI, but unrestricted for this use, and it converts to
Apache-2.0 after two years. `https://tart.run/licensing/` is stale.

`brew install openai/tools/softnet` is needed only if you set `vm.egress: allowlist`
(ADR-0006), which the prototype does not. `scripts/doctor.py` skips the check otherwise.

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
- A third `tart run` fails with an opaque message, after the clone. Check `tart list`
  first.

## Day-to-day

```bash
tart list                                   # what exists, what is running
tart run --no-graphics --dir=work:$PWD/output nf &
tart exec -it nf /bin/zsh -l                # a shell in the guest
tart ip nf                                  # then ssh admin@<ip> if the agent is down
tart stop nf                                # stops; the VM stays, inspectable
tart delete nf                              # removes it
```

`tart clone` is an APFS copy-on-write clone: near-instant, and the clone grows only as it
diverges. Clone a working VM before doing anything risky to it — Tart has no live
snapshots, so this is the snapshot.

## Mounts

Mounts appear in the guest at `/Volumes/My Shared Files/<name>`. The prototype mounts one
directory:

```bash
tart run --no-graphics --dir=work:$PWD/output nf
```

so `output/reference`, `output/ios` and `output/android` are visible to the agent at
`/Volumes/My Shared Files/work/`, and survive the VM.

Only that directory is exposed. Never the home directory, never host SSH or cloud
credentials.

A read-only mount is `--dir=name:path:ro`. The prototype has no use for one yet; the
earlier design used stage-scoped read-only mounts so an agent could not rewrite the
specification it was judged against, and that concern returns with an evaluator
(superseded ADR-0005).

Touching a mount from `tart exec` triggers a TCC prompt unless SIP is disabled in the
image. The official base and Xcode images disable it, which is a reason to stay on them; a
vanilla-derived custom image is known to hang here.

## Provisioning

Created by hand, then provisioned with `scripts/setup-guest.sh`:

```bash
# Verified 2026-09-20: tag 26.5 and tag latest both resolve to
#   sha256:923c98d32e40ffadb6e6815a9722124b7a57bdf7d7763a708a2b28d1970831bd
# They will diverge. Check before assuming you pulled what you meant to:
#   TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:cirruslabs/macos-tahoe-xcode:pull&service=ghcr.io" | jq -r .token)
#   curl -sI -H "Authorization: Bearer $TOKEN" \
#     -H "Accept: application/vnd.oci.image.manifest.v1+json" \
#     https://ghcr.io/v2/cirruslabs/macos-tahoe-xcode/manifests/26.5 | grep -i docker-content-digest
tart clone ghcr.io/cirruslabs/macos-tahoe-xcode:26.5 nf
tart set nf --cpu 8 --memory 16384
tart run --no-graphics --dir=work:$PWD/output nf &
tart exec -it nf bash -lc '/Volumes/My\ Shared\ Files/work/../scripts/setup-guest.sh'
```

There is no Packer golden image (ADR-0007). The script exists so a broken VM is
recoverable by re-running something, rather than by following prose instructions again
and hoping. `tart clone` of a working VM serves as the snapshot.

**Deliberately not installed in the guest: the Android emulator.** It cannot work there,
and `setup-guest.sh` fails the provision if it finds one. See ADR-0002.

The base image already provides Xcode and platforms, Homebrew, git, node@24, openjdk@17,
Android cmdline-tools, platform-tools, `platforms;android-36`, `build-tools;36.0.0`,
tart-guest-agent, and SIP disabled.

## Disk

| | |
|---|---|
| Xcode base image | ~69 GB compressed pull, ~140 GB on disk |
| OCI cache | ~69 GB, reclaimable with `tart prune` once the VM exists |
| the VM itself | grows from the base as it diverges |

Simulator runtimes dominate: ~16 GB per platform volume, against 4 GB for Xcode.app
itself. `doctor.py` warns below 120 GB free.

## Nested virtualization

Tart supports `--nested` for **Linux guests only**, and throws for any macOS guest. The
documentation claims M3/M4; M5 is unverified, which is what
`scripts/spikes/s2-nested-virtualization.sh` exists to settle.

This matters only because Linux guests are exempt from the two-guest ceiling: if nested
virt works, running the Android emulator inside a Linux guest (`targets.android.emulator:
linux-vm`) becomes worth revisiting. Until the spike runs, `host` is the only supported
placement.

> **Spike result:** not yet run. Record the outcome here.

## Memory

A 16 GB guest plus an Android emulator is a real load on top of an ordinary desktop.
On 2026-09-24 macOS killed **both** under pressure — 108 GB used of 128 GB with 42 GB in
the compressor, and the two biggest processes were ours.

Nothing was lost: `output/` lives on the host mount, so the generated apps, the reference
material and the runs log were all intact. An hour of warm build state was not.

`scripts/doctor.py` now checks this before you start anything, and warns when more memory
is compressed than is available — which is the state that precedes a kill, and is
invisible from "GB free" alone.

If you are tight: `tart set nf --memory 12288` costs some Gradle throughput and buys back
4 GB.

## Troubleshooting

**`tart exec` hangs.** Almost always a TCC prompt on a mount path in an image without SIP
disabled. Use an official base image.

**A third VM will not start.** That is the ceiling, not a bug. Check `tart list`.

**`vm shell` cannot connect.** The guest agent may not be running. Check `tart ip <vm>`
answers, then fall back to SSH.

**The image build fails part way.** Packer leaves the partial VM behind; `tart delete` it
before retrying, or the next `vm create` will refuse the name.
