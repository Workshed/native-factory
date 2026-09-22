/**
 * Walk the Lloyds FTB mortgage calculator, one Continue at a time.
 *
 *   NODE_PATH=$(npm root -g) node reference/walk.ts
 *
 * The journey advances by pressing Continue, so it cannot be crawled by following
 * links. Instead this replays a fixed script of actions from the start on every run and
 * captures each screen it lands on. Replaying rather than holding a session open keeps
 * the capture deterministic and restartable: append one more step, run again, and the
 * earlier screens come out identical.
 */

import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Page } from 'playwright';

// Playwright is a global install; ESM `import` ignores NODE_PATH, createRequire honours it.
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const START = 'https://mortgages.secure.lloydsbank.co.uk/homes/?action=mortgage_calculator&type=ftb';
// fileURLToPath, not .pathname: the working directory has spaces in it and a raw
// pathname keeps them percent-encoded, which mkdir then takes literally.
const OUT = fileURLToPath(new URL('./journey/', import.meta.url));

type Action =
  | { do: 'radio'; label: string }
  | { do: 'fill'; label: string; value: string }
  | { do: 'select'; label: string; value: string }
  | { do: 'check'; label: string }
  | { do: 'click'; label: string }
  /** Click once and expect to stay put -- used to make validation messages appear. */
  | { do: 'probe'; label: string };

/** The journey so far, as a list of named steps. Appended to as each screen is
 *  discovered; every run replays the whole thing from the landing page. */
const SCRIPT: { name: string; actions: Action[] }[] = JSON.parse(
  await readFile(fileURLToPath(new URL('./journey-actions.json', import.meta.url)), 'utf8').catch(
    () => '[]',
  ),
);

const VISIBLE = `(e) => e.checkVisibility({ contentVisibilityAuto: true })`;

/**
 * The landing URL renders "Please wait a few seconds while your content loads" and
 * swaps in the real form afterwards, so the consent banner and the first question are
 * both late arrivals. Poll rather than assume they are there on domcontentloaded.
 */
async function dismissConsent(page: Page): Promise<void> {
  for (let i = 0; i < 20; i++) {
    for (const label of [/reject all/i, /reject/i, /decline/i, /only necessary/i]) {
      const button = page.getByRole('button', { name: label }).first();
      try {
        if (await button.isVisible({ timeout: 500 })) {
          await button.click({ timeout: 3_000 });
          await page.waitForTimeout(1_000);
          return;
        }
      } catch {
        /* next label */
      }
    }
    await page.waitForTimeout(1_000);
  }
}

/** Wait for the interstitial to hand over to real content. */
async function settle(page: Page): Promise<void> {
  for (let i = 0; i < 30; i++) {
    const loading = await page
      .getByText(/while your content loads/i)
      .first()
      .isVisible()
      .catch(() => false);
    const hasControls = await page
      .locator('input, select, button')
      .first()
      .isVisible()
      .catch(() => false);
    if (!loading && hasControls) break;
    await page.waitForTimeout(1_000);
  }
  await page.waitForTimeout(1_000);
}

/** Everything a step asks: headings, prose, fields with their labels, buttons, errors. */
async function capture(page: Page, slug: string) {
  await page.setViewportSize({ width: 393, height: 852 });
  await page.waitForTimeout(500);

  const data = await page.evaluate((vis) => {
    const visible = new Function('return ' + vis)() as (e: Element) => boolean;
    const txt = (e: Element | null) => (e?.textContent ?? '').replace(/\s+/g, ' ').trim();

    const labelFor = (el: HTMLInputElement) => {
      const byFor = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (byFor) return txt(byFor);
      const wrap = el.closest('label');
      if (wrap) return txt(wrap);
      const aria = el.getAttribute('aria-label');
      if (aria) return aria;
      const desc = el.getAttribute('aria-labelledby');
      if (desc) return desc.split(/\s+/).map((i) => txt(document.getElementById(i))).join(' ');
      return '';
    };

    // Nearest heading above the field, so grouped radios keep their question. The
    // fieldset's own <legend> is rendered empty here and the question is a sibling
    // role=heading div, so both have to be in the scan and empties skipped.
    const questionFor = (el: Element) => {
      const all = [...document.querySelectorAll('h1,h2,h3,h4,legend,[role="heading"]')];
      let best = '';
      for (const h of all) {
        if (h.contains(el)) continue;
        if (txt(h) && h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) best = txt(h);
      }
      return best;
    };

    // Each field is wired to `<name>-hint` / `<name>-error` divs via aria-describedby;
    // they are where help text and validation messages land.
    const describedBy = (el: Element) =>
      (el.getAttribute('aria-describedby') ?? '')
        .split(/\s+/)
        .filter(Boolean)
        .map((id) => ({ id, text: txt(document.getElementById(id)) }))
        .filter((d) => d.text);

    const fields = [...document.querySelectorAll('input,select,textarea')]
      .filter(visible)
      .map((e) => {
        const el = e as HTMLInputElement;
        return {
          tag: el.tagName.toLowerCase(),
          type: el.type ?? '',
          name: el.name ?? '',
          id: el.id ?? '',
          value: el.value ?? '',
          checked: el.checked ?? false,
          required: el.required ?? false,
          maxlength: el.getAttribute('maxlength') ?? '',
          inputmode: el.getAttribute('inputmode') ?? '',
          pattern: el.getAttribute('pattern') ?? '',
          placeholder: el.placeholder ?? '',
          label: labelFor(el),
          question: questionFor(el),
          described: describedBy(el),
          options:
            el.tagName.toLowerCase() === 'select'
              ? [...(e as unknown as HTMLSelectElement).options].map((o) => o.text.trim())
              : undefined,
        };
      });

    // Hint and error are distinct divs per question, `<name>-hint` / `<name>-error`.
    // Reading them by id beats a class*="error" sweep, which matched whole option
    // groups and reported their labels as validation messages.
    const byIdSuffix = (suffix: string) =>
      [...document.querySelectorAll(`[id$="${suffix}"]`)]
        .map((e) => ({ id: e.id, text: txt(e) }))
        .filter((d) => d.text);

    const hints = byIdSuffix('-hint');
    const errors = byIdSuffix('-error');

    return {
      url: location.href,
      title: document.title,
      headings: [...document.querySelectorAll('h1,h2,h3,h4')].filter(visible).map(txt).filter(Boolean),
      text: (document.body?.innerText ?? '').slice(0, 20_000),
      fields,
      buttons: [...document.querySelectorAll('button,[role="button"],input[type="submit"],a[class*="btn" i]')]
        .filter(visible)
        .map((e) => txt(e) || (e as HTMLInputElement).value || e.getAttribute('aria-label') || '')
        .filter(Boolean),
      hints,
      errors,
    };
  }, VISIBLE);

  const aria = await page.locator('main').first().ariaSnapshot().catch(() => '');
  // Two shots per screen: the phone viewport exactly as a user first sees it, and the
  // whole page, because from the income step on the content is several screens tall
  // and the interesting part is usually below the fold.
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(250);
  await page.screenshot({ path: join(OUT, `${slug}.viewport.png`) });
  await page.screenshot({ path: join(OUT, `${slug}.png`), fullPage: true });
  await writeFile(join(OUT, `${slug}.json`), JSON.stringify({ ...data, aria }, null, 2));

  console.log(`\n${'='.repeat(70)}\n## ${slug}  ${data.url}\n${'='.repeat(70)}`);
  console.log(data.text);
  console.log('\n--- FIELDS ---');
  for (const f of data.fields) {
    console.log(
      `  [${f.type || f.tag}] name=${f.name} id=${f.id} label=${JSON.stringify(f.label)} q=${JSON.stringify(f.question)}` +
        `${f.checked ? ' CHECKED' : ''}${f.value ? ` value=${JSON.stringify(f.value)}` : ''}` +
        `${f.maxlength ? ` maxlength=${f.maxlength}` : ''}${f.inputmode ? ` inputmode=${f.inputmode}` : ''}` +
        `${f.options ? ` options=${JSON.stringify(f.options)}` : ''}` +
        `${f.described.length ? ` described=${JSON.stringify(f.described.map((d) => d.text))}` : ''}`,
    );
  }
  console.log('--- BUTTONS ---\n  ' + data.buttons.join(' | '));
  if (data.hints.length)
    console.log('--- HINTS ---\n  ' + data.hints.map((h) => `${h.id}: ${h.text}`).join('\n  '));
  if (data.errors.length)
    console.log('--- ERRORS ---\n  ' + data.errors.map((e) => `${e.id}: ${e.text}`).join('\n  '));
  console.log('--- ARIA ---\n' + aria);
  return data;
}

/** Match a control by its visible label; radios here are styled spans, not text nodes. */
async function act(page: Page, a: Action) {
  if (a.do === 'probe') {
    await page.getByRole('button', { name: a.label, exact: false }).first().click({ timeout: 10_000 });
    await page.waitForTimeout(3_000);
    return;
  }
  if (a.do === 'click') {
    // Transitions are client-side and take a second or two, so the click has to be
    // confirmed rather than assumed. Two things make that fiddly:
    //
    //  - after a failed Continue, the site swallows the next Continue entirely; the
    //    one after that advances. So retry rather than click once.
    //  - validation text appearing and disappearing changes innerText without the
    //    step changing, so the signature is headings + field names, which only move
    //    when the flow actually moves.
    const signature = () =>
      page.evaluate(() =>
        [
          ...[...document.querySelectorAll('h1,h2,h3,[role="heading"]')].map((e) =>
            (e.textContent ?? '').trim(),
          ),
          ...[...document.querySelectorAll('input,select,textarea')].map(
            (e) => (e as HTMLInputElement).name,
          ),
        ].join('|'),
      );

    const before = await signature();
    const button = page.getByRole('button', { name: a.label, exact: false }).first();
    for (let attempt = 0; attempt < 3; attempt++) {
      await button.click({ timeout: 10_000 });
      await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => {});
      await settle(page);
      for (let i = 0; i < 10; i++) {
        if ((await signature()) !== before) return;
        await page.waitForTimeout(1_000);
      }
    }
    return;
  }
  if (a.do === 'radio' || a.do === 'check') {
    const role = a.do === 'radio' ? 'radio' : 'checkbox';
    // Click the styled <label>, never check() the input. The inputs are zero-size and
    // opacity:0 behind a label, and force-checking them sets `checked` in the DOM
    // without firing the handler React listens on -- on the journey-type screen that
    // produced a visibly selected option that Continue then ignored, silently.
    // Substring match: option labels carry typographic apostrophes ("I’m ready…").
    const input = page.getByRole(role, { name: a.label, exact: false }).first();
    if (await input.count()) {
      const wrapper = input.locator('xpath=ancestor::label[1]');
      if (await wrapper.count()) await wrapper.first().click({ timeout: 10_000 });
      else await input.check({ force: true, timeout: 10_000 });
    } else {
      await page.getByText(a.label, { exact: false }).first().click({ timeout: 10_000 });
    }
    await page.waitForTimeout(400);
    return;
  }
  if (a.do === 'select') {
    await page.getByLabel(a.label).first().selectOption({ label: a.value }, { timeout: 10_000 });
    await page.waitForTimeout(300);
    return;
  }
  // `label` may be either the visible label or the field's name attribute -- the
  // income questions are full sentences, so addressing them by name is far less
  // brittle than reproducing the prose.
  const byLabel = page.getByLabel(a.label).first();
  const field = (await byLabel.count()) ? byLabel : page.locator(`[name="${a.label}"]`).first();
  await field.fill(a.value, { timeout: 10_000 });
  await page.waitForTimeout(300);
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 393, height: 852 },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
  userAgent:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
});
const page: Page = await context.newPage();

await mkdir(OUT, { recursive: true });
await page.goto(START, { waitUntil: 'domcontentloaded', timeout: 60_000 });
await dismissConsent(page);
await settle(page);

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

let n = 0;
await capture(page, `${String(++n).padStart(2, '0')}-landing`);

for (const step of SCRIPT) {
  console.log(`\n>>> replaying: ${step.name}`);
  for (const a of step.actions) {
    console.log(`    ${a.do} ${JSON.stringify(a)}`);
    await act(page, a);
  }
  await capture(page, `${String(++n).padStart(2, '0')}-${slug(step.name)}`);
}

await browser.close();
