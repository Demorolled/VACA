/**
 * preview-e2e.mjs — browser QA of the preview feature end-to-end.
 *
 * Walks: chat "show me a preview" → mockup window auto-opens → toast with
 * ⚙ link → settings dropdown + highlighted Auto GUI Preview row → ⚡ Build
 * This Now → pre-filled dialog auto-starts the build → project loads.
 *
 * Runs against the Vite dev server (:5173, proxies /api to :3001).
 * Uses its own isolated Chromium profile, so no user data is touched.
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:5173';
const GOAL = process.env.E2E_GOAL || 'show me a preview of a pomodoro timer app';
const GOAL_RE = process.env.E2E_GOAL_RE || /pomodoro/i;
const SHOTS = '/tmp/preview-e2e';

const results = [];
function check(name, ok, detail = '') {
  results.push({ name, ok, detail });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

// Collect console errors + failed requests + HTTP >= 400 responses so
// "anything that breaks" surfaces with its URL.
const consoleErrors = [];
const failedRequests = [];
const badResponses = [];
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text());
});
page.on('pageerror', (err) => consoleErrors.push(`PAGEERROR: ${err.message}`));
page.on('requestfailed', (req) => failedRequests.push(`${req.method()} ${req.url()} → ${req.failure()?.errorText}`));
page.on('response', (res) => {
  if (res.status() >= 400) badResponses.push(`${res.status()} ${res.request().method()} ${res.url()}`);
});

try {
  // ── 1. Load the app ──
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForSelector('.terminal-input', { timeout: 30000 });
  check('app loads, chat input visible', true);

  // ── 2. Ask for a preview of an app (nothing built yet) ──
  const aiBefore = await page.$$eval('.terminal-message.ai', (els) => els.length).catch(() => 0);
  await page.fill('.terminal-input', GOAL);
  await page.press('.terminal-input', 'Enter');
  check('message sent', true);

  // The chat's proactive plan-code call shares the single LLM slot with the
  // build — let it settle (first AI reply) so the build doesn't queue behind it.
  await page
    .waitForFunction((n) => document.querySelectorAll('.terminal-message.ai').length > n, aiBefore, {
      timeout: 120000,
    })
    .catch(() => {});

  // ── 3. Mockup window auto-opens (no button click) ──
  await page.waitForSelector('.fpw-window', { timeout: 20000 });
  const title = await page.textContent('.fpw-title-text').catch(() => '');
  check('floating preview window opens', true, `title="${title}"`);
  check('window says Planned Interface (mockup, not live)', /Planned Interface/.test(title), title);

  // ── 4. Mockup image actually renders ──
  await page.waitForSelector('.mpp-img', { timeout: 30000 });
  const imgOk = await page.$eval('.mpp-img', (img) => img.complete && img.naturalWidth > 0);
  check('mockup PNG renders (naturalWidth > 0)', imgOk);
  const badge = await page.textContent('.mpp-badge').catch(() => '');
  const modules = await page.$$eval('.mpp-module', (els) => els.length).catch(() => 0);
  check('mockup shows blueprint badge + modules', !!badge.trim() && modules > 0, `badge="${badge}" modules=${modules}`);
  await page.screenshot({ path: `${SHOTS}-1-mockup.png` });

  // ── 5. Toast appears with the ⚙ settings link ──
  await page.waitForSelector('.preview-toast', { timeout: 10000 });
  const toastText = await page.textContent('.preview-toast');
  check('toast explains the window', /GUI preview/.test(toastText), toastText.slice(0, 80));
  const settingsBtn = await page.$('.preview-toast-settings');
  check('toast has ⚙ Auto Preview setting link', !!settingsBtn);

  // ── 6. Toast link opens Settings with Auto GUI Preview highlighted ──
  await settingsBtn.click();
  await page.waitForSelector('.settings-dropdown', { timeout: 10000 });
  const highlighted = await page.$('.settings-toggle-row.highlight');
  check('settings dropdown opens', true);
  check('Auto GUI Preview row is highlighted', !!highlighted);
  await page.screenshot({ path: `${SHOTS}-2-settings-highlight.png` });

  // Close the settings dropdown (click outside) — the mockup window stays.
  await page.mouse.click(10, 500);

  // ── 7. ⚡ Build This Now → pre-filled dialog auto-starts ──
  await page.waitForSelector('.mpp-build-btn', { timeout: 10000 });
  await page.click('.mpp-build-btn');
  await page.waitForSelector('.bp-dialog', { timeout: 15000 });
  const goalVal = await page.inputValue('.bp-goal-input').catch(() => '');
  check('Build dialog opens', true);
  check('goal pre-filled from the preview', GOAL_RE.test(goalVal), goalVal);
  // The floating window should close once the build takes over.
  const fpwGone = await page.waitForSelector('.fpw-window', { state: 'detached', timeout: 8000 }).then(() => true).catch(() => false);
  check('floating window closes when build starts', fpwGone);

  // The dialog auto-started the build — wait for the done phase. The build
  // races the chat's own plan-code/architect LLM calls (same model slot), so
  // it can take several minutes; distinguish "still building" from "failed".
  const buildOutcome = await page
    .waitForFunction(() => {
      const dlg = document.querySelector('.bp-dialog');
      const txt = dlg?.textContent || '';
      if (/Loaded into canvas|Project loaded|generated code attached/i.test(txt)) return 'done';
      if (/Build failed|Could not|error/i.test(txt) && /Generate the Code|Preview GUI/.test(txt)) return 'error';
      return false;
    }, { timeout: 480000 })
    .catch(() => 'timeout');
  check('build completes and loads project into canvas', buildOutcome === 'done', String(buildOutcome));
  await page.screenshot({ path: `${SHOTS}-3-build-done.png` });

  // ── 8. Canvas should now have nodes with generated code ──
  const codeNodes = await page.$$eval('.react-flow__node', (els) => els.length).catch(() => 0);
  check('canvas has nodes after build', codeNodes > 0, `${codeNodes} node(s)`);
} catch (err) {
  console.error('💥 E2E script error:', err.message);
  await page.screenshot({ path: `${SHOTS}-error.png` }).catch(() => {});
  check('e2e completed without script error', false, err.message);
} finally {
  check('no console/page errors', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));
  check('no failed API requests', failedRequests.length === 0, failedRequests.slice(0, 3).join(' | '));
  check('no HTTP >= 400 responses', badResponses.length === 0, badResponses.slice(0, 5).join(' | '));
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n════════ ${results.length - failed.length}/${results.length} checks passed ════════`);
process.exit(failed.length > 0 ? 1 : 0);
