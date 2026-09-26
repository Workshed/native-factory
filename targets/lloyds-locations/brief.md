# Target: office locations, listing and detail

Source: `https://www.lloydsbankinggroup.com/careers/where-we-are.html`

Reference material is in `reference/` — start with `reference/site.md`. Ten screens were
captured: the listing and nine location pages. Each `reference/screens/*.json` holds that
page's headings, text, links and ARIA snapshot; `reference/screenshots/` has both phone
viewports.

There is no `journey.md` for this target and none is needed — the flow is links, not a
form, so the deterministic crawl captured all of it.

## Scope

Two screens, and the navigation between them:

1. **Locations list** — the nine offices: Belfast, Birmingham, Bristol, Chester,
   Edinburgh, Halifax, Leeds, London, Manchester. The listing page's intro copy sets the
   context; keep its sense.
2. **Location detail** — tapping a location opens its page. Reproduce the content
   sections the reference captured for that office: the introduction, and the
   facilities/benefits sections (*Workspaces*, *Health and wellbeing*, *Food and drink*,
   *Clubs and networks*, *Travel support* — these vary by office, so drive them from the
   captured data rather than hard-coding one office's set).
3. **Back** returns to the listing, with scroll position preserved.

**Out of scope:** job search, individual vacancies, "Why join us", videos, the cookie
notice, and every site-wide navigation item — *Sustainability*, *Our brands*, annual
reports and the rest. The crawl already excluded these; do not reintroduce them.

Where a location page carries a notice (Edinburgh's "Watch this space" about office
improvements, for instance), keep it — it is content, not chrome.

## Content, not a live feed

All nine locations' content is in `reference/`. Bundle it as local data — a JSON or
Swift/Kotlin structure — and render from that. **No networking.** This is a pipeline
test; fetching a bank's pages at runtime is neither needed nor wanted.

## Branding

**Do not reproduce the bank's identity.** No Lloyds Banking Group name, no logo, no
brand colours. Call it "Our Locations" and use the platform's own default styling. This
is a pipeline test, not a recruitment app.

Location names, office descriptions and facilities are content and should be kept.
References to the employer by name in body copy should be generalised ("the Group", "our
offices") rather than reproduced.

## Native shape

This is a master/detail list, which both platforms have strong conventions for. Use them
— a navigation stack with a list, not a bespoke layout. The nine locations are a short,
fixed set, so a plain scrolling list is right; no search, no filtering, no sections.

Say in your notes what you chose for the detail screen's section layout and why.