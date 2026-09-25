# Design: the console

A single-user web front end for running targets end to end. **Design only — nothing here
is built.**

## The problem, stated honestly

The pipeline works. Its interface is a person typing `scripts/factory.sh` and reading the
output, which so far has meant *me*, in a chat window. Two consequences:

- **The gate has never gated anything.** `runs.jsonl` shows two approvals; both were
  mine, neither preceded by a human reading `journey.md`. A human-in-the-loop approved by
  an agent is not a loop.
- **There is no screenshot capture.** `grep screenshot scripts/factory.sh` → 0. Every
  screenshot so far was taken by hand, ad hoc, and pasted into a conversation.

So this is not only a presentation problem. One of the five things wanted — *see the
finished app* — has no underlying capability yet.

## What it must do

1. Submit a job: a running site, optionally some source, a brief.
2. Show progress across stages, not just within one agent conversation.
3. **Pause at the gate and wait for a person**, with the material to judge on screen.
4. Show screenshots of the finished apps.
5. Give access to the generated code.

## Non-goals

No multi-user, no accounts, no database, no scheduling, no retry orchestration, no
real-time agent streaming (Agent Canvas already does that better than we would). Not a
service — a **build server for one person**.

Two facts set that altitude and should not be designed away: jobs take hours, and macOS
permits **two** VM guests per host. Concurrency is measured in single digits forever.

---

## Input model

Always a running site. Source is supplementary — it is read for API shapes and business
rules, never translated. That matches the brief's stance and the thing we have twice
confirmed in practice: the product is what the site *does*, not what its code says.

```yaml
name: Mortgage Calculator

site:
  url: http://localhost:3000        # real, staging, or local dev server
  engine: webkit                    # optional; chromium unless it is blocked
  include_path: /careers            # optional
  max_routes: 14

source:                             # optional, for APIs and business logic
  path: ../some-checkout            # mounted read-only
  # or: repo: https://github.com/org/repo   (public; private needs a token — see below)

targets:
  ios:     { bundle_id: com.example.app }
  android: { application_id: com.example.app }
```

`bundle_id` and `application_id` are here because both builds so far *guessed* them —
`uk.co.otaku-dev.MortgageCalculator` from git config, `com.example.ourlocations` from the
app name.

### localhost needs the same trick as adb

A dev server on the host's `localhost` is unreachable from the guest. We have solved this
exact problem once already, for the Android emulator: **bind a forwarder to the vmnet
interface** and let the guest reach it there.

```text
host   dev server on 127.0.0.1:3000
       socat  192.168.64.1:3000 -> 127.0.0.1:3000
guest  crawls http://192.168.64.1:3000
```

The runner detects a loopback URL, brings the forwarder up, and rewrites the URL for the
guest. The user changes nothing about how they run their dev server — notably they do not
have to rebind it to `0.0.0.0`, which is the obvious alternative and worse, because it
exposes their work to the network to solve a VM problem.

### Source

`path:` mounts the checkout **read-only** as a third `--dir`. Read-only is the point: it
is reference material, and the agent has no business editing it.

`repo:` clones inside the guest. Public repositories only to begin with. Private ones need
a token in the VM, and that is the credential-exposure question from `docs/security.md`
again — an agent with a bypassed shell can read any token we inject. Defer it; "clone it
yourself and give me a `path:`" is a complete answer in the meantime.

---

## Architecture

Three pieces, each of which stays useful on its own.

```text
   browser
      │  HTTP (LAN, shared token)
┌─────▼──────────────────────────────────────────────┐
│ console                                            │
│   read   state.json, runs.jsonl, the filesystem    │
│   write  queue entries, APPROVED markers           │
│   serve  screenshots, journey.md, git              │
└─────┬──────────────────────────────────────────────┘
      │ spawns
┌─────▼─────────┐        ┌──────────────────────────┐
│ supervisor    │───────▶│ scripts/factory.sh       │
│ which stage   │        │ how to run a stage       │
│ next; halts   │        │ (unchanged; still a CLI) │
│ at the gate   │        └──────────────────────────┘
└───────────────┘
```

**`factory.sh` stays the execution layer and stays usable alone.** The supervisor decides
*which* stage runs next; `factory.sh` decides *how* a stage runs. Keeping that split means
the CLI keeps working with no console running, which matters the first time the console
has a bug.

### State

| File | Role |
|---|---|
| `output/<t>/runs.jsonl` | append-only history — exists today |
| `output/<t>/state.json` | current stage and status — new, small |

History could be replayed to derive "currently running X since T", but a five-line current
state file is simpler than a reducer, and it is what the console polls.

### Queue

One worker, jobs serialised. Even with the two-guest ceiling, two concurrent jobs would
contend on a single emulator AVD and a single Agent Canvas. If that ever changes, the
device-lease design in ADR-0002 is the answer, and it is already written down.

---

## The gate becomes a state

Today `stage_gate` prints and exits 3, which assumes a human at a terminal.

```text
explore finishes
   → state: awaiting-approval, since <t>
   → supervisor sleeps; the job is not failed, not running, just waiting
   → console shows journey.md rendered, the captured screenshots, Approve / Reject
   → Approve  writes reference/APPROVED   → supervisor continues
   → Reject   records a reason            → job stops, brief can be amended and re-run
```

The mechanism stays a file, so `scripts/factory.sh <t> approve` still works. One
mechanism, two front ends — and the file is the audit trail.

This is where a gate finally earns its place: a pause that survives closing the laptop,
approvable from a phone, with the material to judge rendered beside the button. In a
terminal it was a prompt you dismissed to get on with it.

**Reject should be first-class.** In practice the likely failure is "you explored the
wrong branch" — that wants an amended brief and a re-run of `explore`, not a failed job.

---

## The capture stage

The missing capability, not just missing presentation.

Ask each platform build to also write `.maestro/capture.yaml` — a flow that walks the main
screens taking a screenshot at each. The agent knows its own app's navigation, Maestro
already drives both platforms, and we already require `--device`. The `capture` stage then
runs that flow and collects the artefacts into `output/<t>/screenshots/<platform>/`.

Reusing Maestro rather than scripting `simctl` and `adb` separately means one mechanism,
and it stays correct when the app's navigation changes, because the agent maintains the
flow alongside the app.

---

## Code access: make the output a git repo

`git init` per target output; commit after each stage that changes files.

This answers "access the codebase" with a mechanism everyone already has, and three other
things fall out of it for free:

- **diffs between runs** — re-run a target after the site changes and see exactly what
  moved, which is otherwise a matter of reading two apps side by side;
- **provenance** — the commit records which conversation and prompt produced it;
- **no file browser to build** — the console links to the repo and shows changed files.

The brief asked for git from the beginning. This is where it pays.

---

## Security

The console can start agents that run with permissions bypassed. It is a **privileged
control plane**: bind to the LAN, require a shared token, and do not expose it beyond the
machine's own network. It also serves scraped third-party content, which is fine locally
and would not be fine published.

---

## Build order

1. **`capture` stage** — the one missing capability; makes the console worth looking at.
2. **git per target output** — cheap, and pays back immediately in diffs.
3. **`state.json` + supervisor** — the gate becomes a state; the CLI still works.
4. **console** — HTTP server and a plain HTML front end.
5. **Target-model additions** — localhost forwarding, `source:`, explicit bundle ids.

Steps 1 and 2 are useful with no console at all, which is the order's main argument.

Rough size: 600–900 lines total, most of it in step 4, and none of it clever.

## Open questions

- **Rejection semantics.** Does Reject re-run `explore` with an amended brief
  automatically, or stop and wait for a human to edit `targets/<t>/brief.md`? I lean to
  the latter: less magic, and editing the brief is the actual fix.
- **How much of the brief belongs in the UI?** A textarea that writes `brief.md` is
  friendlier than editing a file, but the file is what is versioned. Perhaps the UI edits
  the file and shows the diff.
- **Where the console runs.** On the host alongside Tart is simplest. Running it in the
  guest would put it behind the same VM boundary as everything else, but it needs to start
  and stop the VM, so it has to be outside.
