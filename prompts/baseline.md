# Record how the app behaves today

**Change no production code in this conversation.** The output is a safety net.

A repository is mounted at the working directory, with `SURVEY.md` at its root. Read that
first. Build and run the app, walk its main journeys, and record them as Maestro flows in
`.maestro/baseline/`, with a screenshot of each screen.

Everything that follows this stage is a change to an app with thin tests. These flows are
most of what will catch a regression, so they are worth more care than their size
suggests.

## Assert behaviour, not appearance

The work ahead includes UI rework. A flow that asserts how a screen *looks* will break by
design on the first restyling task, and a safety net that cries wolf gets switched off.

Assert on:

- **reachability** — this screen can be got to from that one;
- **content that identifies a screen** — a heading, a product name, a label on a control;
- **state transitions** — after this action, that changes.

Do not assert on:

- **copy supplied by the operating system.** `ContentUnavailableView`'s "Check the
  spelling or try a new search", a system alert's buttons, date formats. Those are owned
  by the OS and change with a version or a locale, breaking your flow with no edit to the
  repository. This has already happened in one of these apps.
- **long strings.** A whole paragraph of marketing copy asserts on wording nobody
  intended to freeze. Pick the few distinctive words that identify the screen.
- **layout, colour, spacing, or anything that a restyle would legitimately change.**

Prefer accessibility identifiers where they exist. Where they do not, say so in your
report — adding them is a reasonable later task, and it makes every future flow steadier.

## Coverage to aim for

Every screen reachable without credentials or network, and every primary action on each.
Breadth beats depth: one flow per journey that proves it still works is worth more here
than an exhaustive exploration of one screen.

Where a journey needs data or a login you do not have, record what you could and name the
gap in your report. An honest gap is useful; a flow that silently skips the interesting
half is not.

## Screenshots

Take one per screen, named in navigation order (`01-home`, `02-catalogue`…). These are
**review material, not assertions** — they are what a human compares against after a UI
task, so they need to be legible rather than exhaustive.

Keep the screenshot steps in the same flows. A separate screenshot-only flow drifts out
of step with the ones that assert.

## Before you finish

Run every flow you wrote and make sure each passes, individually, with `--device`. A
baseline flow that was never run is worse than none: it will fail on the first task and
be assumed to be a regression.

## Finish

Write `BASELINE.md` at the repository root: what each flow covers, what is deliberately
not covered and why, and anything that made a journey hard to pin down — missing
accessibility identifiers, non-deterministic content, timing.
