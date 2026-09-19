# Native Factory — Implementation Plan

Status: Milestone 1 specified, awaiting approval. Written 2026-09-19.

Milestones 1–10 from `Native Factory — Engineering Brief.md`, with the corrections in
`HANDOFF.md` applied. Read `docs/architecture.md` first. Citations of the form (HANDOFF §4.5)
mark a departure from the brief; **[deviation]** marks a departure from HANDOFF itself.

The brief's instruction holds throughout: **do not attempt the complete factory immediately.**
Each milestone ends in something observable and testable.

---

## Overview

| M | Deliverable | Gate |
|---|---|---|
| 1 | VM bootstrap: CLI skeleton, `doctor`, `vm` lifecycle, golden image, guest doctor, run records — **plus both spikes** | clean host → working guest shell with all tooling |
| 2 | OpenHands agent server + ACP providers in the guest | a coding task edits a repo inside Tart |
| 3 | `native-factory inspect URL` — deterministic crawl | useful, deterministic `reference/` |
| 4 | Reference model + schemas + report | **human approval checkpoint** |
| 5 | iOS proof of concept, one small feature | builds, runs, tests, journey passes |
| 6 | Android proof of concept, same feature | same, on the host emulator |
| 7 | Evaluator | structured parity results |
| 8 | `native-factory build` orchestration | end-to-end on one feature |
| 9 | Disposable workers | clone → run → persist → destroy, ≤ 2 concurrent |
| 10 | Packaging | another developer can install it |

---

## Milestone 1 — VM bootstrap

**Acceptance criterion (brief):** a clean host can create the VM and obtain a shell containing
the required base development tooling.

### 1.1 Scope

1. **Repo scaffolding** — uv workspace, three Python packages (`native-factory-cli`,
   `native-factory-guest`, `native-factory-core`), Apache-2.0, README, CI running
   ruff + pyright + `pytest tests/unit tests/contract`.

2. **Documentation** — `docs/architecture.md`, this file, `docs/vm.md`, initial
   `docs/security.md`, ADRs 0001–0006.

3. **Config schema v0** — `native-factory.yaml` as in the brief, plus HANDOFF §4.11's additions
   (`agent.auth`, `targets.android.emulator`, `xcode.version`, `maestro.version`,
   `vm.base_image` as a pinned **digest**, `vm.cpu`, `vm.memory_mb`) plus `vm.egress: open |
   allowlist` defaulting to `open` (ADR-0006). Pydantic v2 models are the source of truth and
   generate `schemas/project-config.schema.json`; CI asserts the checked-in schema is in sync.

4. **Tart wrapper** — a typed subprocess layer over `clone`, `run`, `exec`, `ip`, `set`, `stop`,
   `delete`, `list`. Only documented commands (HANDOFF §4.4); `tart ssh` and `--headless` do not
   exist and must never appear. Version gate. Error mapping that turns the two-guest ceiling into
   an actionable message. Argv construction is fully unit-tested without a VM.

5. **Golden image** — Packer + `packer-plugin-tart` on `macos-tahoe-xcode` pinned **by digest**.
   Adds: uv + Python 3.12 · Playwright + Chromium and WebKit · Maestro (pinned) · agent-device ·
   XcodeBuildMCP · `openhands-sdk`/`-tools`/`-workspace`/`-agent-server` in
   `/opt/native-factory/venv` · `@openhands/agent-canvas` · ACP adapters **pre-installed at
   pinned versions** (ADR-0003, **[deviation]** from HANDOFF §4.1's `npx -y`) · first-party
   `android` CLI · the `native-factory-guest` wheel.
   **Deliberately not installed:** the Android `emulator` package and system images (HANDOFF
   §4.5). `tart set` to 8 CPU / 16384 MB, config-driven. Writes `/opt/native-factory/
   manifest.json`.

6. **`native-factory init <name>`** — **[deviation]** pulled forward from the brief's later
   command set, because `vm start` needs a project directory to mount. Creates
   `~/NativeFactory/projects/<name>/{reference,work/{ios,android},reports,factory}` and a
   `native-factory.yaml` from template. Nothing else from the later set moves.

7. **Host doctor** (HANDOFF §4.12) — Apple Silicon · supported macOS (≥ 26.6 only if the pinned
   image requires Xcode 27) · Tart from the `openai/tools` tap · `tart-guest-agent` · `softnet`
   when `vm.egress: allowlist` · **≥ 250 GB free** (**[deviation]**: HANDOFF §4.4's ~200 GB is a
   one-worker floor; two workers plus a 70 GB OCI cache need more) · and when
   `targets.android.emulator: host`: `emulator` present, **platform-tools ≥ 35**, at least one
   arm64 AVD, adb server reachable from the NAT range. Every failure carries a remediation line.
   `--json` output.

8. **Guest doctor** — ships inside the image; run from the host as `native-factory vm doctor`
   over `tart exec`. Reports versions for Xcode, simulator runtimes, JDK, Android SDK and the
   `android` CLI, Node, Playwright + browsers, Maestro, agent-device, XcodeBuildMCP
   (`xcodebuildmcp-doctor`), agent server health, each ACP adapter, uv/Python.

9. **Run records** — a run ID per invocation, SQLite at `~/NativeFactory/state.db`, one JSONL log
   per run under `reports/`, and a minimal `native-factory status`.

10. **Spike S1 — Android adb over the Tart NAT.** **[deviation]** HANDOFF §4.5 schedules this at
    the start of Milestone 6. It moves here: it needs only a booted guest, the host emulator and
    a prebuilt APK, and this host already has the SDK with four AVDs. Deferring it would build
    M2–M5 on an unverified assumption whose failure reopens the emulator placement, the config
    schema and the M9 concurrency model.

11. **Spike S2 — Linux nested virtualization on M5** (HANDOFF §8 item 1). Informational; gates
    nothing.

### 1.2 Mount design shipped in M1 (ADR-0005)

`vm start --stage <stage>` composes `--dir` flags rather than mounting one directory:

| Stage | `reference` | `work` | `factory` |
|---|---|---|---|
| discovery | `rw` | — | `:ro` |
| implement | `:ro` | `rw` | `:ro` |
| evaluate | `:ro` | `:ro` | `:ro` |

`reports/` is never mounted. The host hashes `reference/` before and after any `:ro` stage and
fails the run on mismatch. The payoff lands at M3/M7, but the mount machinery is M1's.

### 1.3 Acceptance tests

Non-VM tests run in CI. VM tests run as `pytest -m vm tests/acceptance/milestone1/` on a host
with Tart.

#### AT-0 — static gates (CI)

```bash
uv sync
uv run ruff check .
uv run pyright
uv run pytest tests/unit tests/contract
uv run python -m native_factory.config.export_schemas --check   # schemas/ in sync
```

**Pass:** exit 0 on all five.

#### AT-1 — host doctor

```bash
uv run native-factory doctor --json | tee /tmp/doctor.json
jq -e '.status == "ok" and ([.checks[] | select(.status == "fail")] | length == 0)' /tmp/doctor.json
```

**Pass:** exit 0; every host check present with a version string.

Negative tests:

- With `tart` absent from PATH: non-zero exit, and the message names
  `brew install openai/tools/tart`.
- With less than 250 GB free (simulated): non-zero exit naming the figure.
- **Legacy `android` regression** — doctor must **fail**, not pass, when the only `android` on
  PATH is `~/Library/Android/sdk/tools/android`. That is the deprecated 2017 SDK Tools script; it
  shares the name of the first-party CLI HANDOFF §4.8 requires and it **exits 0**, so a
  presence check silently passes against the wrong binary. Doctor asserts on `android --version`
  output shape.

#### AT-2 — golden image build, and no-op rebuild

```bash
uv run native-factory vm create --name nf-golden        # first run, ~60-90 min
tart list | grep -q nf-golden

time uv run native-factory vm create --name nf-golden   # second run
```

**Pass:** the second run exits 0 in under 5 s, prints `image exists, use --force to rebuild`,
and leaves `tart list` unchanged.

```bash
uv run native-factory vm manifest nf-golden > /tmp/m.json
jq -e '.base_image_digest and .template_sha256 and (.tools | length > 10)' /tmp/m.json
```

**Pass:** the manifest records the base image **digest** (not tag), the SHA-256 of the Packer
template and provisioning scripts, and a pinned version for every installed tool.

**[deviation]** HANDOFF §4.13 asks that the second run be "a no-op or identical". Packer + Tart
is neither idempotent nor bit-reproducible — a rebuild re-runs Homebrew and npm, and images
differ by timestamp alone — so "identical" cannot be asserted. The two properties above are what
reproducibility actually means here, and both are checkable.

#### AT-3 — clone, run, mounts, no TCC prompt

```bash
uv run native-factory init demo
uv run native-factory vm start --project demo --name nf-w1 --stage implement
uv run native-factory vm shell --name nf-w1 -- ls "/Volumes/My Shared Files/"
```

**Pass:** `reference`, `work` and `factory` are all listed; the VM runs `--no-graphics`; no TCC
dialog appears.

```bash
uv run native-factory vm shell --name nf-w1 -- \
  sh -c 'touch "/Volumes/My Shared Files/reference/x" 2>&1; echo rc=$?'
```

**Pass:** non-zero rc (read-only file system). This is the ADR-0005 property under test — the
evaluator's inputs must not be writable by the stage being evaluated.

Manual check, once: `native-factory vm shell --name nf-w1` with no command gives a working
interactive `tart exec -it` TTY. `tart ip` + SSH is the documented fallback when the guest agent
is down.

#### AT-4 — guest doctor

```bash
uv run native-factory vm doctor --name nf-w1 --json | tee /tmp/gdoctor.json
jq -e '[.checks[] | select(.status == "fail")] | length == 0' /tmp/gdoctor.json
jq -r '.checks[] | "\(.name) \(.version)"' /tmp/gdoctor.json
```

**Pass:** every tool from §1.1.8 reported with a non-empty version and no failures.

Two specific assertions:

- `android --version` identifies the **first-party** CLI, not the legacy script (as AT-1).
- The Android **`emulator` package is absent**. Its presence is a build error, not a nicety —
  it cannot work in a macOS guest (HANDOFF §4.5) and shipping it invites someone to try.

#### AT-5 — stop, preserve, delete

```bash
uv run native-factory vm stop --name nf-w1
tart list | grep nf-w1          # still present: preserved for inspection
uv run native-factory vm delete --name nf-w1
tart list | grep -qv nf-w1
```

**Pass:** stop leaves the VM inspectable (the brief requires entering a failed VM for
debugging); delete removes it; `factory.preserve_failed_vm` is honoured.

#### AT-6 — the two-guest ceiling is handled, not hit

```bash
uv run native-factory vm start --project demo --name nf-a --stage implement
uv run native-factory vm start --project demo --name nf-b --stage implement
uv run native-factory vm start --project demo --name nf-c --stage implement; echo "rc=$?"
```

**Pass:** the third exits non-zero **before invoking Tart**, naming the two-macOS-guest limit and
listing the running VMs. This is Milestone 9's concurrency contract, asserted at Milestone 1
(HANDOFF §4.4).

#### AT-7 — Spike S1: Android adb over the Tart NAT

The HANDOFF §4.5 decision gate.

Host preparation: upgrade `platform-tools` to ≥ 35 (the installed 33.0.1 predates current
remote-adb behaviour); boot `Pixel_9_API_36`; start a listening adb server
(`adb -a -P 5037 server nodaemon`); load a pf anchor restricting port 5037 to `192.168.64.0/24`
— `adb -a` binds `0.0.0.0` and cannot bind a single interface, so firewalling is the only way to
scope it. In the guest, derive the gateway from the **default route**; do not hardcode
`192.168.64.1`.

Guest environment: `ADB_SERVER_SOCKET=tcp:<gateway>:5037`, `ANDROID_SERIAL=<leased serial>`.

| # | Check | Client under test |
|---|---|---|
| a | `adb devices` lists the host emulator | adb CLI |
| b | `adb install` a prebuilt debug APK; the app launches | adb CLI |
| c | Gradle `installDebug` on a trivial `android create` project succeeds | **AGP / adblib** |
| d | `maestro test` runs one flow; `--format junit --output` written | **Maestro (dadb)** |
| e | `agent-device snapshot` returns an accessibility tree | **agent-device ADB client** |

**Pass:** all five.

**[deviation]** HANDOFF §8 item 2 asks this question only of Maestro's dadb. AGP's adblib path
and agent-device's ADB client make the same `ADB_SERVER_SOCKET` assumption and can fail it
independently; all three are tested.

A partial pass is a decision, not a failure. Record which clients honour the variable, choose a
rung from the architecture's fallback ladder (`docs/architecture.md` §6) — **not** HANDOFF §4.5's
"drop Tart", which is rung 4, not rung 2 — write the outcome into `docs/android.md`, and fix the
`targets.android.emulator` default before Milestone 2 starts.

#### AT-8 — Spike S2: Linux nested virtualization on M5

```bash
tart clone ghcr.io/cirruslabs/ubuntu:latest nf-nested
tart run --nested --no-graphics nf-nested &
tart exec nf-nested sh -c 'ls -l /dev/kvm; grep -r . /sys/module/kvm/parameters/ 2>/dev/null | head'
```

Also assert that Tart **rejects** `--nested` for a macOS guest.

**Pass/fail is informational.** Tart's docs claim M3/M4; M5 is unverified. The result decides
whether `targets.android.emulator: linux-vm` is viable later. Recorded in `docs/vm.md`.

### 1.4 Out of scope for Milestone 1

No OpenHands conversation, no ACP invocation, no Playwright crawl, no Xcode or Gradle project
generation, no evaluation, no `build`. `inspect`, `report`, `plan`, `build` and `test` exist as
CLI stubs that exit with `not implemented until Milestone N`.

### 1.5 Shape

Roughly 3–4 days, dominated by the first golden-image builds (60–90 minutes per iteration, and
there will be several) and by S1. Everything except AT-2 through AT-8 is testable without a VM.

---

## Milestone 2 — OpenHands + coding agent

**Acceptance criterion (brief):** a simple coding task is performed by Claude Code under
OpenHands inside Tart.

- Start the agent server in the guest (`python -m openhands.agent_server --host 0.0.0.0
  --port 8000`), authenticated with `OH_SESSION_API_KEYS_0` / `OH_SECRET_KEY`.
- Connect **Agent Canvas UI from the host browser** (`agent-canvas --frontend-only`, Manage
  Backends → guest URL + key). The UI is for observation; the pipeline never depends on it
  (HANDOFF §4.1).
- Implement the provider adapter interface: `acp_command`, env/secrets, provider-native MCP
  config. Ship `claude-code` first; ship `codex` at the same time as a falsification test that
  the seam is real, even though only Claude Code is exercised.
- Credentials per HANDOFF §4.3: `ANTHROPIC_API_KEY` through `Conversation(secrets={...})` by
  default, `agent.auth: oauth-token` opt-in with the terms caveat documented. Use a dedicated
  rotatable key.
- Prove: a task submitted through the agent server edits a small git repository inside the VM,
  and the change is visible on the host through the mount.

**Resolves** HANDOFF §8 item 3 — whether the Agent Canvas UI path prompts for ACP permissions or
inherits the SDK's auto-approve. Whatever it does, record it in `docs/security.md`; the answer
does not change the model (the VM is the boundary either way), but the documentation must be
accurate.

**Guard:** no Claude-specific logic outside `providers/claude_code.py`. A review checklist item,
and a grep-based CI check for `claude` outside that module and the docs.

---

## Milestone 3 — Website discovery

**Acceptance criterion (brief):** inspection of a small test website produces a useful,
deterministic `reference/` directory.

`native-factory inspect https://example.com`.

- A **Playwright Node library script, no LLM in the loop** (HANDOFF §4.6), in `crawler/`,
  invoked as a subprocess, emitting only validated JSON and files.
- Playwright 1.63 APIs: `page.ariaSnapshot()` / `ariaSnapshotJSON({ mode: 'ai', boxes: true })`
  — `page.accessibility.snapshot()` is **removed**. HAR via `context.tracing.startHar()` or
  `recordHar`.
- Configurable viewport profiles seeded from current device descriptors, plus custom widths for
  breakpoint probing. Breakpoints are **discovered by probing computed styles**, not assumed from
  the site's CSS.
- Per screen/state capture: URL, viewport, screenshot, aria snapshot, semantic DOM information,
  text content, interactive elements, outgoing navigation, network/API activity.
- **Redaction** of cookies, auth headers, tokens, passwords and API keys from every persisted
  artefact, HAR included (HANDOFF §4.2).
- Determinism: a second crawl of the same site produces artefacts that differ only in timestamps
  and volatile content, and the test asserts that.

This is where untrusted input first enters the system. Prompt assembly (M4 onward) must delimit
it as data. Revisit the `vm.egress` default here — ADR-0006 records the argument for flipping it.

---

## Milestone 4 — Reference model

- JSON Schemas for `site`, `route`, `screen`, `journey`, `api`, `feature-spec`, generated from
  pydantic and checked in, with CI enforcing sync.
- Convert discovery artefacts into feature specifications in the brief's shape (`id`, `source`,
  `journeys`, `states`, `acceptance`).
- Readable HTML or Markdown report; `native-factory report`.
- **STOP for human approval.** `factory.require_spec_approval: true` by default;
  `build --approve-spec` exists but the manual gate remains available (brief).
- Decide the concrete shape of the §4.10 parity signal here: which fields of a web aria snapshot
  map to which fields of a native accessibility snapshot, and what counts as a match.

The reference model must be understandable independently of agent conversation history (brief).

---

## Milestone 5 — iOS proof of concept

One deliberately small feature. Not a whole website.

- `scaffold_ios_project` from XcodeBuildMCP (`getsentry/XcodeBuildMCP` 2.7.0 — Sentry acquired it
  in Feb 2026; the old repo path is stale). Override the default `io.sentry.*` bundle prefix.
- **Use the XcodeBuildMCP CLI, not the MCP server** (ADR-0003) — provider-neutral, no per-provider
  MCP config.
- Implement the SwiftUI screen and journey; build; boot the simulator; run tests; run one Maestro
  journey; capture a SnapshotTesting baseline.
- All recorded runs are **factory-invoked** (ADR-0004), not agent-invoked.
- UI inspection during the agent's inner loop is `agent-device`, plus `snapshot_ui` (**not**
  `describe_ui` — renamed).

**Resolves** HANDOFF §8 item 4 (Maestro iOS driver stability on the pinned Xcode/macOS pair — the
XCTest driver has recurring hang issues on new macOS/Xcode combinations, so pin one Xcode and one
Maestro and smoke-test the pair) and item 5 (whether the XcodeBuildMCP iOS template is pinned per
release; pin it manually if not).

The result must remain a normal Xcode project a developer can open and maintain without Native
Factory (brief).

---

## Milestone 6 — Android proof of concept

The same feature in Kotlin/Compose.

**The emulator decision gate was answered at Milestone 1 (AT-7).** This milestone spends its time
on the chosen path rather than discovering it — which is the point of moving the spike.

- Project creation with the first-party `android create --name=<app> --output=<path>` (template
  `empty-activity-agp-9`). No home-grown template (HANDOFF §4.8).
- Watch for the legacy `android` script collision (AT-1) — on a host or image with an old SDK,
  `android` may resolve to the deprecated 2017 tool, which exits 0.
- AGP 9.4 requires Gradle 9.6+ and JDK 17. API 36/37 system images.
- Build, unit tests and Roborazzi run **in the guest** (JVM, no emulator). Install and journeys
  run against the **host** emulator over the AT-7 plumbing.
- Roborazzi 1.74.0 for visual baselines.

The result must remain a normal Android project openable in Android Studio (brief).

---

## Milestone 7 — Evaluation

- An evaluator separate from the implementation worker (brief).
- Inputs: feature spec, website reference artefacts, both implementations, and the
  **factory-recorded** build/unit/Maestro/snapshot results (ADR-0004).
- **Primary parity signal:** native accessibility snapshots (agent-device) against web aria
  snapshots (Playwright) per screen and state (HANDOFF §4.10). Screenshots secondary.
- Structured, machine-readable output in the brief's shape (Behaviour / iOS / Android / Parity),
  with a readable rendering.
- Intentional native deviations from the website are documented explicitly and excluded from
  parity failures (brief).
- Bounded retry: `factory.max_retries`, no unlimited loop.
- `reference/` is mounted `:ro` for this stage and the host verifies its hash (ADR-0005).

---

## Milestone 8 — Orchestration

Only now `native-factory build`.

- Coordinates the established stages over the vertical slice: discover → spec → approve →
  implement iOS → implement Android → record → evaluate → next.
- Feature state in SQLite: `feature`, `reference_revision`, `spec_status`, `ios_status`,
  `android_status`, `evaluation_status`, `last_failure` (brief).
- Configurable retry limits; git commits at meaningful factory stages; isolated branches or
  worktrees per worker. **Never push, never open remote PRs.** A local run works with no GitHub
  repository (brief).

---

## Milestone 9 — Disposable workers

Automate clone → run → persist → destroy, preserving failed workers when configured.

**The concurrency ceiling is two macOS guests** (HANDOFF §4.4). Designed in, not discovered:

- At most **two features in flight**. The scheduler enforces it; AT-6 already asserts the CLI
  refuses a third before invoking Tart.
- The golden image cannot be rebuilt while two workers run — `vm create` checks and says so.
- Linux guests are uncapped, which is the only reason `emulator: linux-vm` is interesting later.

**Device leases** (architecture §6). One AVD per worker, serial pinned per run via
`ANDROID_SERIAL`, leases held in `state.db` with acquire/release and crash recovery. Without
this, two workers sharing one host adb server collide on every `install`, Maestro run and
agent-device call. **[deviation]** HANDOFF §4.5 does not address multi-worker device arbitration.

Automatic destruction stays conservative: a successful worker is destroyed, a failed one is
preserved when `factory.preserve_failed_vm` is set, and the brief's requirement to enter a failed
VM for debugging is preserved.

---

## Milestone 10 — Packaging

Only now: Homebrew tap, signed binaries, downloadable base images, public documentation, CI for
Native Factory itself. `uv tool install` covers distribution until then (architecture §11).

---

## Cross-cutting: what must stay true

Checked at every milestone.

1. **No Claude-specific logic outside the provider adapter.** CI grep + review.
2. **Recorded results come from factory-invoked commands**, never from agent narration
   (ADR-0004).
3. **Only documented Tart commands.** No `tart ssh`, no `--headless`, no live snapshots.
4. **Every pin is a pin.** Base image by digest; tool versions in `versions.lock.json`; no
   `npx -y`, no `:latest` (HANDOFF §4.4 documents `sequoia-xcode:latest` resolving to 16.4 while
   26.x tags exist — tags lie).
5. **The VM is the only isolation boundary** (architecture §9). Any change that weakens the mount
   policy or the egress setting is a security change and needs an ADR.
6. **Untrusted website content is delimited as data** in every prompt that carries it.
7. **No unlimited autonomous loops.** Every retry path has a configured bound.
8. **Nothing is pushed anywhere** without explicit user action.

---

## Appendix A — Proposed repository structure

```text
native-factory/
├── README.md  LICENSE(Apache-2.0)  CONTRIBUTING.md  SECURITY.md
├── pyproject.toml  uv.lock  .python-version(3.12)     # uv workspace root
├── docs/
│   ├── architecture.md  implementation-plan.md  security.md  vm.md
│   ├── discovery.md  reference-model.md  agents.md  ios.md  android.md
│   ├── testing.md  troubleshooting.md
│   └── adr/0001…0006-*.md
├── packages/
│   ├── native-factory-cli/          # HOST — src/native_factory/
│   │   ├── cli/                     #   typer app: doctor, vm, init, inspect, report,
│   │   │                            #   plan, build, test, status
│   │   ├── config/                  #   pydantic models → schemas/, loader, defaults
│   │   ├── vm/                      #   tart.py (typed subprocess wrapper), lifecycle.py,
│   │   │                            #   packer.py, mounts.py (stage-scoped ro/rw, ADR-0005)
│   │   ├── doctor/                  #   host checks + guest dispatch over `tart exec`
│   │   ├── workspace/               #   ~/NativeFactory layout, reference/ integrity hashing
│   │   ├── android/                 #   host emulator, adb server, device leases (ADR-0002)
│   │   └── runs/                    #   run ids, SQLite store, JSONL structured logging
│   ├── native-factory-guest/        # GUEST — src/native_factory_guest/
│   │   ├── serve.py                 #   agent server bootstrap + health
│   │   ├── providers/               #   base.py, claude_code.py, codex.py, gemini.py,
│   │   │                            #   copilot.py → acp_command + env + native MCP config
│   │   ├── pipeline/                #   inspect, spec, implement, evaluate stages
│   │   ├── prompts/                 #   trusted templates + untrusted-content framing
│   │   ├── tools/                   #   xcodebuild.py simctl.py gradle.py adb.py
│   │   │                            #   maestro.py agent_device.py  (ADR-0004)
│   │   └── doctor.py                #   guest checks, --json
│   └── native-factory-core/         # SHARED — src/native_factory_core/
│       ├── schema/                  #   pydantic models mirrored to JSON Schema
│       └── artefacts/               #   reference/ + reports/ IO, redaction
├── crawler/                         # NODE — Playwright discovery crawl (architecture §14)
│   ├── package.json  package-lock.json
│   └── src/  crawl.ts viewports.ts redact.ts emit.ts    # JSON contract only
├── schemas/                         # generated from pydantic, checked in, CI-verified in sync
│   └── project-config · site · screen · feature-spec · evaluation · run-record  .schema.json
├── images/
│   ├── packer/golden.pkr.hcl  variables.pkr.hcl
│   ├── packer/scripts/            10-uv-python … 90-android-cli, 99-manifest.sh
│   └── versions.lock.json           # every pin, including the base image digest
├── templates/                       # native-factory.yaml template, generated-project .gitignore
├── tests/
│   ├── unit/                        # pure Python, no VM, runs in CI
│   ├── contract/                    # golden-file: tart argv construction, config parse, schema
│   └── acceptance/milestone1/       # @pytest.mark.vm — real Tart, not in CI
├── scripts/
└── .github/workflows/ci.yml         # ruff + pyright + pytest unit,contract
```

Stack: uv workspace · typer + rich · pydantic v2 · pytest · ruff · pyright · stdlib `sqlite3` ·
stdlib logging with a JSON formatter. No distributed workflow engine (brief).

Three Python packages rather than one, because the host and the guest have disjoint dependency
sets: the guest needs the whole `openhands-sdk` stack and the host must not, and the guest wheel
is built into the golden image independently of the host CLI's release cycle. `native-factory-core`
holds what both need — schemas and artefact IO — and depends on neither.
