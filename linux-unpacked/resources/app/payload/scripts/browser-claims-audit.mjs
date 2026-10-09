#!/usr/bin/env node
/* Live browser run of the VACA claims-audit tester.
 * Usage: node scripts/browser-claims-audit.mjs [quick|full]   (default: quick)
 * Opens http://127.0.0.1:3001/projects/claims-audit.html, clicks the chosen
 * test button, waits for the run to finish (score settles), then prints every
 * card's status + the overall score and any improvements text.
 */
import { chromium } from 'playwright';

const mode = process.argv[2] === 'full' ? 'full' : 'quick';
const BTN_ID = mode === 'full' ? '#runFull' : '#runQuick';
const URL = 'http://127.0.0.1:3001/projects/claims-audit.html';
const TIMEOUT_MS = (mode === 'full' ? 16 : 12) * 60 * 1000; // min budget

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const consoleErrors = [];
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text().slice(0, 300));
});
page.on('pageerror', (err) => consoleErrors.push('PAGEERROR: ' + String(err).slice(0, 300)));

console.log('opening', URL);
await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(1500);

const title = await page.title();
console.log('TITLE:', title);

const btn = page.locator(BTN_ID);
const btnText = (await btn.textContent().catch(() => '')).trim();
console.log(`${mode.toUpperCase()} BUTTON:`, btnText);
await btn.click();
console.log(`clicked ${mode} test — waiting for completion…`);

// Poll: the run is complete when #scorePct stops saying "Testing…" (finalize()
// replaces it with "X/Y (Z%)") and the run button is re-enabled. runCard marks
// cards with class 'run' — never wait on 'pending'.
const deadline = Date.now() + TIMEOUT_MS;
let done = false;
const start = Date.now();
while (Date.now() < deadline && !done) {
  await page.waitForTimeout(20000);
  const pct = (await page.locator('#scorePct').textContent().catch(() => '')).trim();
  const btnDisabled = await page.locator(BTN_ID).isDisabled().catch(() => true);
  const elapsed = Math.round((Date.now() - start) / 1000);
  console.log(`  …${elapsed}s: pct="${pct}" btnDisabled=${btnDisabled}`);
  if (pct && !pct.includes('Testing') && !btnDisabled) {
    await page.waitForTimeout(5000);
    done = true;
    break;
  }
  if (elapsed % 60 < 20 && elapsed > 20) {
    const runCards = await page.locator('.card.run').count().catch(() => -1);
    console.log(`    (cards currently marked run: ${runCards})`);
  }
}

console.log('\n===== FINAL STATE =====');
const score = (await page.locator('#scoreNum').textContent().catch(() => '')).trim();
const max = (await page.locator('#scoreMax').textContent().catch(() => '')).trim();
console.log(`SCORE: ${score} / ${max}`);

const cards = page.locator('.card');
const n = await cards.count().catch(() => 0);
console.log(`CARDS: ${n}`);
for (let i = 0; i < n; i++) {
  const card = cards.nth(i);
  const cls = (await card.getAttribute('class').catch(() => '')).trim();
  const text = (await card.textContent().catch(() => '')).replace(/\s+/g, ' ').trim();
  console.log(`- [${cls || '?'}] ${text.slice(0, 200)}`);
}

// Improvements box is #improveBox; each item is a .improve div with a
// priority chip (.p.p1/p2/p3), a title (<b>) and a body (<p>).
const impBox = page.locator('#improveBox .improve');
const impN = await impBox.count().catch(() => 0);
console.log(`\nIMPROVEMENTS (${impN}):`);
for (let i = 0; i < impN; i++) {
  const it = impBox.nth(i);
  const prio = (await it.locator('.p').textContent().catch(() => '?')).trim();
  const title = (await it.locator('b').textContent().catch(() => '?')).trim();
  const body = (await it.locator('p').textContent().catch(() => '')).replace(/\s+/g, ' ').trim();
  console.log(`- [${prio}] ${title}: ${body.slice(0, 320)}`);
}

console.log('\nCONSOLE ERRORS:', consoleErrors.length ? consoleErrors.slice(0, 8) : 'none');

await browser.close();
console.log('DONE');
