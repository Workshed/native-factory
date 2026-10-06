# Design: working an existing app down a task list

A second pipeline sharing the existing platform. **Design only — nothing here is built.**

Two repositories, one per platform. A plan in markdown. Large features and UI rework,
some of it platform-specific. Days of work per platform.

---

## The constraint that shapes everything

**Test coverage is poor.**

On the greenfield targets, "it builds and its flows pass" was a reasonable signal: the
agent wrote the app *and* the flows, so the flows described what it had just built. On an
existing app that signal is much weaker — an agent can satisfy it completely while
breaking something it never opened.

Three consequences, and they drive the rest of this document:

1. **Build a safety net before changing anything.** Not as a nice-to-have at the end.
2. **Smaller tasks, gated more often.** Long autonomous chains are exactly wrong when the
   verification is thin; the cost of a bad run is proportional to how much it touched.
3. **Human review is load-bearing**, so the pipeline's job is to make review *cheap* —
   small diffs, before/after screenshots, and a clear statement of what was and was not
   verified.

### The safety net, specifically

A `baseline` stage, run once per repository before any task: drive the existing app and
record **Maestro flows that assert behaviour and content** — navigate here, do this,
expect that — plus screenshots of each screen.

Behaviour, deliberately, not appearance. The plan includes UI rework, so visual baselines
would break *by design* and teach everyone to ignore them. Behavioural flows survive
restyling and still catch the thing that actually matters: navigation broken, state lost,
a screen that no longer loads.

Screenshots are kept, but as **review material rather than assertions**. Before-and-after
on every task is the single cheapest thing that makes UI rework reviewable. They are
lifted out of the clone into `output/<target>/baseline/`, so the branch that eventually
gets pushed carries flows but not a pile of PNGs.

This is characterisation testing through the UI. It is not a substitute for unit tests,
and the design should say so rather than imply the problem is solved.

### Then raise coverage, as the first tasks on the list

Better than working around thin tests is removing the constraint, and "add substantial
coverage with minimal code modification" is unusually well suited to an agent: the
specification is the existing code, which it can read.

It also has a property the rest of this design does not — **it is self-checking**. A
coverage task is supposed to change no behaviour, so if the baseline flows still pass,
the task was almost certainly safe. The safety net validates the building of the safety
net, and that is as close to a free lunch as this gets.

Three rules make it work, and all three are counterintuitive enough to need stating in
the prompt:

- **Pin current behaviour, including bugs.** A test written against existing code records
  what the code *does*, not what it should do. Where something looks wrong, add the test
  that captures the actual behaviour and a comment saying it looks wrong — do not fix it.
  Otherwise nobody can distinguish "my change broke this" from "this was always wrong",
  which is the entire value being bought.
- **Minimal modification means stop, not improvise.** Some code is untestable without
  refactoring — a singleton, a view model that builds its own dependencies, a network
  call in `viewDidLoad`. When that happens, write what coverage is reachable, then
  **report the refactor needed and stop**. A refactor is its own task, with its own
  review, not a side effect of a testing task.
- **Report coverage before and after**, so the task list's progress is a number rather
  than a feeling.

Sequencing therefore becomes: `baseline` → coverage tasks → feature and UI tasks. By the
time the large UI rework starts, the thing verifying it is no longer only a handful of
UI flows.

---

## Target shape

```yaml
kind: codebase

repos:
  ios:     ../their-ios-app          # mounted read-write under repos/
  android: ../their-android-app

tasks: plan.md                        # the markdown you already have

branch_prefix: factory/               # one branch per task, never main
plan: survey gate baseline task verify capture
```

Both repositories live under one `repos/` mount rather than one mount each — Tart fixes
mounts at `tart run` time, so a mount per repository would mean restarting the VM to add
a project. The same reasoning produced the single `sources/` mount.

Unlike `sources/`, this one is **read-write**: the point is to change it.

## The plan is the state

The markdown checklist is both the input and the progress record:

```markdown
## Onboarding
- [ ] (both) Redesign onboarding as three steps
- [ ] (ios) Adopt the new navigation API
- [ ] (android) Move settings to DataStore

## Account
- [ ] (both) Rework the account screen layout
```

`(both)`, `(ios)`, `(android)` make platform-specific work first-class rather than an
afterthought — which matters, because half the point of the task list is that the two
apps are not the same.

**The runner ticks the box, not the agent**, and only after verification passes. An agent
that can mark its own homework will eventually mark it generously, and the plan is too
important to leave to good intentions. It is also diffable, so progress is visible in
`git log` without any other tracking.

## Stages

| Stage | Does | Gate? |
|---|---|---|
| `survey` | agent reads a repository and writes `SURVEY.md`: module layout, navigation, state management, test setup, conventions | **yes** |
| `baseline` | record behavioural Maestro flows and screenshots of the app as it is | |
| `task` | implement one task, on its own branch | |
| `verify` | existing tests + baseline flows + build, both platforms | |
| `capture` | after-screenshots, paired with the baseline | |

`survey` is the equivalent of `journey.md`, and the gate it carries is the same bet: a
survey costs an agent half an hour and a human five minutes, and it is where "it has
misunderstood the architecture" is cheap to catch. On the first real run it found that
the project has no shared scheme checked in and no test action configured — so *any*
coverage task has to solve project-file plumbing before it can add a single test. That is
precisely the kind of thing that turns a one-hour task into a lost afternoon when nobody
looked first. After that the gate moves per task —
approve the task plan, not the whole backlog.

## Branching

One branch per task, `factory/<task-slug>`, never main. Whether those become pull
requests is a preference rather than a design decision — the branch is what matters,
because it makes "throw this one away" a cheap outcome. Given thin tests, that needs to
stay cheap.

## What the build prompt becomes

`prompts/build-native-apps.md` assumes greenfield — it says "scaffold", and mentions the
reference site ten times. Modification is a different document, and most of it is
restraint:

- change the minimum that satisfies the task;
- follow the conventions already in the file you are editing, not your preferred ones;
- do not reformat, re-indent, reorganise imports, or "tidy" adjacent code;
- do not upgrade dependencies or change build configuration unless the task says to;
- if the task cannot be done without a wider change, **stop and say so** rather than
  making it.

That last one is the important one. The failure mode on an existing codebase is not an
agent that cannot do the task; it is an agent that does the task *and nine other things*,
producing a diff nobody can review.

## What this does not fix

- **Thin tests stay thin until the coverage tasks run.** The baseline catches navigation
  and content regressions; it will not catch a wrong calculation behind a screen nobody
  walks. That is the gap the first tasks on the list are for, and until they are done the
  verification is weaker than it will look.
- **Serial throughput.** The two-guest ceiling means one task at a time: roughly 30–60
  minutes per platform per task. A few days of work per platform is a few days of wall
  clock, not an afternoon.
- **Review still has to happen.** The pipeline can make a diff small and legible. It
  cannot decide whether the feature is right.

## Build order

1. ~~**`survey` + the modification prompt**~~ — **built 2026-10-06.** `kind: codebase`,
   a `repos/` mount, repository cloning, `prompts/survey.md` and
   `prompts/modify-existing.md`. Proven against a real iOS project: 388 lines of
   `SURVEY.md`, and the gate halts on it.
2. ~~**`baseline`**~~ — **built 2026-10-06.** Proven against a real iOS app: three
   behavioural flows, seven screenshots, and a `BASELINE.md` naming its own gaps.
3. **`task` + `verify` + branching** — the loop itself.
4. **Plan parsing and box-ticking** — mechanical once the loop works.
5. **Console: task list, before/after pairs** — presentation last, as before.

Steps 1 and 2 are useful with no task loop at all, which is the same argument that
ordered the console work.

## Where this lives: the same repository, behind `kind:`

Not a branch, not a separate repository. The split between what is shared and what is
new is lopsided enough to settle it by counting:

| | lines |
|---|---|
| **Platform** — VM, doctor, adb and site bridges, agent-canvas, run-in-guest, supervisor, console | **1,616** |
| **Pipeline** — website-specific: `inspect-site.ts`, `stage_inspect`, `stage_explore` | **405** |

A separate repository would duplicate the 1,616 — and, worse, duplicate the documentation
of every trap in `vm.md`, `discovery.md` and the ADRs, which is where most of the real
value of this project sits. A branch would be worse again: two products on two branches
diverge and never merge.

Extracting the platform as a shared dependency is the thing to do when there are three
consumers, not two. The split is clean enough that it stays easy later, which is an
argument for deciding it later, with evidence.

### What the switch actually touches

Less than expected, because `plan:` already made stages per-target:

| | |
|---|---|
| default plan | already overridable per target; `kind` only picks a different default |
| workspace root | `output/<target>` for a website, `repos/` for a codebase |
| prompt composition | `build-native-apps.md` vs `modify-existing.md` |
| console's new-target form | different fields per kind |

Four places. New stages are **new functions**, not conditionals inside old ones, because
dispatch is already a `case` on the stage name. That was accidental rather than
foresighted — the plan mechanism was built so one target could skip `explore` — but it is
why this is a switch rather than a fork.

```yaml
kind: codebase          # or: website (the default, so existing targets are unchanged)
```

The console's **New target** form chooses the kind up front and shows the right fields: a
URL for a website, repository paths and a plan file for a codebase.

### The honest risk

If the two pipelines diverge a long way, `factory.sh` becomes a place where two unrelated
things are interleaved. The mitigation is structural rather than hopeful — stages are
separate functions, so divergence adds files rather than nesting — but it is worth
watching, and worth splitting if `factory.sh` starts needing `kind` in more than those
four places.

## Parked: JSON project files and Xcode 27

Xcode 27 reportedly supports a JSON-based project format in place of `project.pbxproj`.
Unverified here — it postdates what this project can check from inside the VM — but if
true it dissolves the survey's sharpest finding, that a hand-written `project.pbxproj`
with no shared scheme makes adding a test target a plumbing exercise before it is a
testing one.

**Checked:** a stable `macos-tahoe-xcode:27` image exists, and the guest's macOS 26.6.2
clears the floor Xcode 27 needs. So the toolchain path is open; it costs a ~69 GB pull,
a re-provision and re-authenticating the agents.

**Recommendation if it is pursued: convert the projects by hand, not as a task.** It
touches both apps' project files at once, which is the largest blast radius available
here; reviewing an agent's conversion to a format the reviewer is also new to is harder
than doing the conversion; and the survey's value is computed against a file that would
be about to be replaced.

Sequencing matters — convert, *then* rebuild the VM on Xcode 27, then survey. A survey
run on 26.5 cannot build a project saved in a 27-only format.

Before committing to it: does the rest of the team and CI have Xcode 27, is it
reversible, and do the `xcodebuild` invocations change? The last one would need
`prompts/platform-ios.md`, `prompts/survey.md` and the `capture` stage revisiting.

## Open questions

- **Does `verify` run the existing test suites?** It should, but "poor coverage" may mean
  they are also slow or flaky. Worth measuring before making them a gate.
- ~~What happens to a task that fails verification?~~ **Decided: stop.** The branch is
  left for inspection and the run halts in a `failed` state carrying which task and which
  check failed. The fix is the same shape as rejection at the gate — a human reads it and
  amends *that task* in the plan, then resumes. Carrying on would produce more branches
  nobody has looked at, and with thin tests a second failure probably means the survey was
  wrong rather than the task.
- **How much coverage is "substantial"?** A number in the task makes it checkable and
  makes it gameable — an agent asked for 60% can reach it by testing getters. Better
  phrased per area ("the account view model's state transitions") than as a percentage,
  with the percentage reported rather than targeted.
- **Do the two platforms share one task branch or get one each?** Separate repositories
  suggest separate branches, but a `(both)` task then lands in two places with no link
  between them beyond the name.
