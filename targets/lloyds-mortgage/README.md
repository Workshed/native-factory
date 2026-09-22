# Lloyds FTB mortgage calculator — target fixture

Written by the coding agent, not by hand, while exploring the site (2026-09-22).

| File | What it is |
|---|---|
| `brief.md` | the target-specific half of the build prompt |
| `walk.ts` | replayable Playwright driver for the whole journey |
| `journey-actions.json` | the 12-step declarative script `walk.ts` replays |

## Why the driver is kept and the capture is not

`walk.ts` replays from the landing page on every run and re-captures all 13 states, so
**the recipe regenerates the input**. Keeping the recipe rather than the output means:

- it stays fresh — `journey.md` says plainly that rates are time-sensitive and will not
  reproduce, so a committed capture would be stale within days;
- the repository holds our code rather than a third party's page content and branding;
- when the site changes, you re-run and **diff**, instead of re-reading 17 KB of prose
  and hoping you notice.

The generated `reference/` — `journey.md`, per-state JSON, screenshots — stays gitignored.

## Reproducing

```bash
scripts/run-in-guest.sh targets/lloyds-mortgage/walk.ts
```

About five minutes. Writes `reference/journey/` and `reference/journey.md` into the
mounted workspace.

## Worth stealing for the runner

The action DSL is the interesting part, and it was not designed up front:

```json
{ "name": "journey-type", "actions": [
  { "do": "radio", "label": "Just me" },
  { "do": "click", "label": "Continue" } ] }
```

`radio` · `fill` · `click` · `probe` — where `probe` presses submit with a question
unanswered, expecting to stay put, in order to capture the validation text. Four verbs
covered an entire multi-step financial form.

If a runner ever needs a generic interaction layer, this is its shape: a per-target
actions file and one shared replayer, rather than a bespoke script per site. `walk.ts`
is currently Lloyds-specific only in its start URL and a couple of selectors.
