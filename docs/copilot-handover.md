# Handover: prove the GitHub Copilot path

For whoever picks this up on a second machine. Written 2026-09-27, when everything below
was true and none of it had been tried with Copilot.

Delete this file once the task is done and the findings have moved into
`docs/workflow.md` and the ADRs. It is a task brief, not reference material.

---

## The task

Run an existing target end to end with `NF_PROVIDER=copilot`, and report what differs.

The claim under test is in `docs/architecture.md` and `docs/workflow.md`:

> Switching coding agent changes nothing about the website inspection, the project
> structure or the native build process.

That claim has **never been exercised**. Every build to date used `claude-code`. It is
the least-supported statement in the repository and should be treated as a hypothesis.

## What is already proven — do not re-verify

| | |
|---|---|
| VM, provisioning, guest doctor | `scripts/setup-guest.sh`, then `doctor.py --guest` |
| ACP seam with Claude Code, on a subscription | no API key anywhere |
| Android emulator bridge | four ADB clients, `scripts/adb-bridge.sh verify` |
| Full pipeline, three targets | form, content site, and a local dev server |
| Supervisor, gate, console, capture, git-per-target | all exercised |

If one of these fails on the new machine it is a setup problem, not a Copilot problem.
`python3 scripts/doctor.py` first, always.

## What is not proven

1. That `copilot --acp --stdio` starts and speaks ACP under OpenHands at all.
2. That a Copilot login survives into the ACP subprocess the way Claude Code's does.
3. That Copilot follows `prompts/build-native-apps.md` closely enough to produce a
   buildable project, Maestro flows and `NOTES.md`.
4. Everything after that — whether its apps are any good.

Expect to find at least one thing wrong. Two of the three targets found latent faults
the previous one could not have shown.

## Copilot specifics

Recovered from a provider adapter this project used to have, and verified against
GitHub's documentation on 2026-09-20. Re-check it; it will have moved.

**Install** — `scripts/setup-guest.sh` already does this:

```bash
npm install -g @github/copilot        # needs Node 22+
# or: brew install --cask copilot-cli
```

**ACP server**: `copilot --acp --stdio`. `--stdio` is the default transport, passed
explicitly so the intent survives a change of default.

**Authentication**: a **fine-grained personal access token** with the *Copilot Requests*
permission, on a **user-owned** (not organisation) token. Read from these, in order of
precedence:

```
COPILOT_GITHUB_TOKEN    preferred
GH_TOKEN                the GitHub CLI's token, if it carries Copilot Requests
GITHUB_TOKEN            lowest
```

Interactive `/login` should also work and is how Claude Code was authenticated here —
try it first, since it avoids putting a token in the VM at all.

**BYOK is deliberately not wired.** Copilot supports bring-your-own-key through
`COPILOT_PROVIDER_*` and `COPILOT_PROVIDERS_CONFIG`. Do not use it. It reintroduces the
metered per-token billing that subscription auth was chosen to avoid, which was an
explicit requirement. If Copilot will not authenticate any other way, report that rather
than working around it.

## How the provider routing works

OpenHands' ACP registry has six built-in keys — `claude-code`, `codex`, `gemini-cli`,
`kimi-code`, `opencode`, `pi` — plus `custom`. **There is no `copilot`.**

`provider_settings()` in `scripts/factory.sh` resolves this:

```
claude-code  {"agent_kind":"acp","acp_server":"claude-code"}
copilot      {"agent_kind":"acp","acp_server":"custom",
              "acp_command":["copilot","--acp","--stdio"]}
```

The custom shape is **verified accepted** by the agent server — it created a conversation
from it. What is unverified is everything after acceptance.

## Do this in order

```bash
python3 scripts/doctor.py                    # host
# … set up the VM per README.md …
python3 scripts/doctor.py --guest            # via tart exec; expect 0 failed

tart exec -it nf /bin/zsh -l                 # copilot  → /login
scripts/agent-canvas.sh up

# the site local-devsite points at; the shell to recreate it is in its brief
python3 -m http.server 3000 --bind 127.0.0.1

NF_PROVIDER=copilot scripts/supervise.sh local-devsite
```

`local-devsite` is the right first target: two pages, local, minutes not hours, and it
exercises the loopback bridge as a side effect. Do not start with something large.

Then compare against what `claude-code` produced for the same target — the build is in
`output/local-devsite/` as its own git repository, so `git log` and `git show` give you a
diff rather than a reading exercise.

## Differences are expected, and are not failures

From the brief, and it matters here:

> Do not attempt to make Claude Code and Copilot behave identically. They may use their
> own tools and reasoning differently. The contract is simply: the selected agent can
> inspect and modify the workspace and execute the commands necessary to build and test
> the native applications.

So a different project layout, a different navigation approach, different Maestro flows —
all fine. What would be a real failure: it cannot build, it ignores the brief's scope, it
reproduces the source site's branding when told not to, or it needs provider-specific
instructions in the shared prompt. That last one is the thing to watch, because it is the
failure that quietly undoes the seam.

If Copilot needs something Claude Code did not, it belongs in
`prompts/platform-*.md` only if it is true for every provider. Otherwise it belongs in a
provider-specific note in documentation — never in the shared prompt.

## Traps that will bite, and what each looks like

Every one of these cost real time here.

| Symptom | Cause |
|---|---|
| A script behaves as though your edit never happened; `SyntaxError: Unexpected character '\0'` past the end of a file | The shared mount serves the guest **stale content** for modified files. Use `scripts/run-in-guest.sh`. |
| Gradle hangs on `Cannot reach ADB server` | AGP ignores `ADB_SERVER_SOCKET`. The bridge forwards `localhost:5037` **inside** the guest instead. `scripts/adb-bridge.sh up`. |
| Maestro: `Package … is not installed` while reporting `Running on Pixel_9…` | It picked the Android device for an iOS flow. Always pass `--device`. |
| `capture` reports `0 screenshot(s)` | The flow failed. Maestro writes **no** screenshots when a flow fails, not even ones already taken. Capture flows must navigate and screenshot and nothing else. |
| `IOSDriverTimeoutException` | Maestro's iOS driver is slow under load. `factory.sh` sets `MAESTRO_DRIVER_STARTUP_TIMEOUT=180000`. |
| The VM and emulator are killed mid-run | Memory. A 16 GB guest plus an emulator needs headroom; `doctor.py` warns when more is compressed than available. |
| One page captured, title contains "Error" | The site is blocking headless Chromium. `engine: webkit` in `target.yaml`. |
| A config default silently not applied | `cfg` prints nothing and **succeeds** for an absent key; use `cfg_or`. |

## Where to put what you find

- A provider difference that changes the design → an ADR in `docs/adr/`.
- Anything about running targets → `docs/workflow.md`.
- Copilot setup facts → replace the *Copilot specifics* section above, then delete this
  file once the path is proven.

Record what you tried that **did not** work too. Half the value in this repository's
history is the things that looked right and were not.
