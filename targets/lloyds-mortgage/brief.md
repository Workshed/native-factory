# Target: mortgage affordability calculator

Source: `https://mortgages.secure.lloydsbank.co.uk/homes/?action=mortgage_calculator&type=ftb`

Reference material is in `reference/` — read `reference/journey.md` first. It documents the
whole flow as a numbered sequence with screenshots, field names, hints, validation
messages and the business rule. `reference/journey/NN-*.png` are the screenshots and the
matching `.json` files hold the full text and ARIA snapshot of each state.

## Scope for this slice

Build **screens 1 to 3 plus the affordability result**:

1. *Get some quick figures* — purpose, first home, stage of journey, then number of applicants
2. *What would you like to find out* — borrow / rates / both
3. *Your income* — employment status, then basic income, additional income, other income
4. **Result** — "You could borrow up to £X over a term of 25 years"

**Out of scope:** the outgoings screen, the deal list, stamp duty and fee breakdowns,
energy performance, and every call to action that leaves the calculator (*Agreement in
Principle*, *Save progress*, *Neighbourhood Guide*). Ignore all header and footer
navigation.

## The rule that matters

The affordability figure is **5.5 × total annual income**, over a 25-year term. With
£45,000 basic and nothing else, the site returns £247,500. Reproduce that.

## Branding

**Do not reproduce the bank's identity.** No Lloyds name, no black horse, not the green
livery. Call it "Mortgage Calculator" and use the platform's own default styling —
system colours, standard controls. This is a pipeline test, not a bank app, and an app
that looks official is the one outcome to avoid.

Product behaviour, content and business rules are what we are reproducing. Visual
identity is not.

## Deliberate deviations expected

- **The silent failure must not be copied.** On the real site, pressing *Search and
  recalculate* with empty fields does nothing at all — no message, no change. Native
  equivalents should show a validation error. Document this in your notes as an
  intentional deviation.
- Web radio lists become the platform's idiomatic selection control.
- Progressive disclosure (screens that append content below rather than replacing it)
  should become whatever reads naturally on the platform — that may be one scrolling
  form, or a step-by-step flow. Say which you chose and why.

## Money and validation

Currency fields are integer pounds, entered without separators, `inputmode="decimal"` on
the web. Basic income is required; additional and other income are optional and default
to zero. The site caps basic income at 7 characters.
