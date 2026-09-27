# Discovery

`scripts/inspect-site.ts` crawls a site and writes `reference/`. No LLM is involved: it
produces artefacts, and interpreting them is the agent's job afterwards. A disagreement
about what a site does is then settled by reading a file rather than re-running a model.

```bash
scripts/factory.sh <target> inspect
# or directly:
scripts/run-in-guest.sh scripts/inspect-site.ts <url> --out <dir> [--engine webkit]
```

## What it captures

Per screen, at 393×852 and 412×915: URL, title, headings, text, links, buttons, inputs,
a full-page screenshot per viewport, and an ARIA snapshot. Plus a readable `site.md`.

## Engine: when Chromium will not do

Chromium is the default. Some sites block headless Chromium outright — one target served
it an `Error 1007` page while returning the real page to plain `curl` with a default
user-agent, so it is headless detection rather than user-agent filtering. Measured:

| Configuration | Result |
|---|---|
| chromium headless, with or without device emulation | **blocked** |
| chromium headless + `--disable-blink-features=AutomationControlled` | **blocked** |
| chromium headed | ok |
| webkit, headless | **ok** |

`engine: webkit` in `target.yaml`. WebKit needs no display, is already in the image, and
is the closer engine to what an iOS user sees — a reasonable default for anything that
resists Chromium.

**Symptom to recognise:** one screen captured, a title containing "Error", and a
body that mentions retrying later.

## Sites on this machine's loopback

A dev server at `http://localhost:3000` is unreachable from the guest, where `localhost`
is the guest. `scripts/site-bridge.sh` forwards **both ways**, and the pipeline brings it
up automatically for any target whose URL is loopback:

```text
host   socat <gateway>:3000 -> 127.0.0.1:3000     expose to the vmnet only
guest  socat 127.0.0.1:3000 -> <gateway>:3000     make localhost mean the host
```

The guest-side half is the one that matters, and it is the same insight as the adb bridge
(ADR-0002): rather than asking every client to honour a rewritten address, make the
client's assumption true. Two consequences, both of which earn it:

- **The URL never changes.** `http://localhost:3000` works verbatim in the guest, so
  nothing rewrites anything and the reference material records the URL you gave.
- **The `Host` header stays `localhost:3000`.** Dev servers that check it — Vite and
  webpack-dev-server reject unknown hosts by default — see exactly what they expect. The
  obvious alternative, binding your dev server to `0.0.0.0` and pointing the guest at the
  host's IP, publishes your work to the network *and* requires an `allowedHosts` entry.

Extra ports (an API on 3001, say) go in `forward_ports:`.

```bash
scripts/site-bridge.sh up 3000 3001
scripts/site-bridge.sh verify 3000
scripts/site-bridge.sh down
```

## Scoping the crawl

- `include_path: /careers/where-we-are` — confines the frontier to a section. Without it,
  "one level deep" from a careers listing reached job search, the cookie notice and a
  Workday job template.
- Header, footer and nav links are excluded from both the capture and the frontier.
- `max_routes` caps the crawl.

## Content anchoring

Captures are taken from the first of `[role="main"]`, `main`, `article`, `body` that the
page has.

Excluding chrome *elements* is not enough on a large site: mega-menus and promo rails sit
in plain `div`s. Capturing from `body` buried a careers page's real headings under
"Sustainability", "Our brands" and "2025 annual report" — the same six site-wide items on
every page, with the office name nowhere in the list. Anchoring on the main landmark gave
exactly the page's own content.

## Client-rendered pages

After `domcontentloaded` the crawler waits for `networkidle` (tolerating the timeout —
analytics beacons and polling mean it can legitimately never fire) and then settles
briefly. Without this, a client-rendered calculator captured as a header,
"Loading component…" and a footer.

## Cookie banners

Dismissed before capture, trying "reject" variants before "accept" — declining is the
conservative default when clicking on someone's behalf. The dialog usually stays in the
DOM afterwards, so captures are filtered with `Element.checkVisibility()`.

Note that a stricter pixel test is wrong here: custom-styled radios are routinely
zero-size `opacity: 0` inputs behind a styled label, and measuring boxes reported a form
as having no inputs at all.

## Redaction

URLs are redacted before they are written: parameters whose names look like credentials
or identity (`token`, `auth`, `mcmid`, `_ga`, `utm_`…) **and any long opaque value** —
vendor prefixes are endless, so shape catches the ones nobody has heard of.
A URL supplied for one target carried an Adobe Marketing Cloud blob containing a
persistent visitor id.
