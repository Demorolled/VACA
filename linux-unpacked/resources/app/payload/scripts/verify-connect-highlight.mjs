/**
 * Real-browser verification (Playwright + system Chrome) of the build-mode
 * "connect two nodes" flow:
 *
 *   1. Load a 2-node build project from the app's own Load dialog.
 *   2. Multi-select both nodes on the 3D canvas (plain click + Shift-click) and
 *      assert the "Connect these two…" bar appears.
 *   3. Open Connect & Describe (mode="build"), confirm both nodes are
 *      preselected and the copy is the build-mode copy.
 *   4. Type a description, Interpret (backend call stubbed via route), Apply.
 *   5. Assert: the toast names both nodes, the dialog auto-closes, and the
 *      canvas actually DRAWS the new semantic edge — and draws it EMPHASISED
 *      while highlighted (measured by counting mint-green pixels in canvas
 *      screenshots before / during / after the highlight window).
 *
 * Run from the project root (needs the Vite dev server on the given URL):
 *   node scripts/verify-connect-highlight.mjs [url]
 */
import { chromium } from 'playwright';

const URL = process.argv[2] || 'http://localhost:5199/';
const CHROME = process.env.CHROME_PATH || '/usr/bin/google-chrome';

const NODE_A = { id: 'n_alpha', label: 'Alpha Loader', type: 'logic' };   // blue
const NODE_B = { id: 'n_beta', label: 'Beta Engine', type: 'output' };    // red
// (Neither node type is green, so any mint-green pixel in a canvas screenshot
//  must come from the semantic edge.)

const SEED_PROJECT = {
  id: 'proj_verify_connect',
  name: 'Verify Connect',
  targetOS: 'linux',
  version: 1,
  savedAt: new Date().toISOString(),
  trees: [{ id: 'tree_1', name: 'App 1', goal: 'verify connect', targetOS: 'linux', rootNodeId: 'master-node' }],
  nodes: [
    { id: 'master-node', type: 'master', position: { x: 0, y: 0 }, data: { label: 'App Blueprint', appGoal: 'verify', selectedOS: 'linux', status: 'pending', treeId: 'tree_1' } },
    { id: NODE_A.id, type: NODE_A.type, position: { x: -150, y: 0 }, data: { label: NODE_A.label, description: 'loads things', type: NODE_A.type, language: 'typescript', treeId: 'tree_1' } },
    { id: NODE_B.id, type: NODE_B.type, position: { x: 150, y: 0 }, data: { label: NODE_B.label, description: 'engine', type: NODE_B.type, language: 'typescript', treeId: 'tree_1' } },
  ],
  edges: [],
};

const report = { steps: [], checks: {}, errors: [], mint: {} };
const step = (m) => { report.steps.push(m); console.log('•', m); };
const check = (name, ok, detail) => { report.checks[name] = { ok: !!ok, detail }; console.log(ok ? '  ✓' : '  ✗', name, detail ?? ''); return !!ok; };

/** Count mint-green pixels in a PNG buffer (decoded in-page, no image deps). */
async function mintCount(page, buf) {
  const b64 = buf.toString('base64');
  return page.evaluate(async (b64) => {
    const img = new Image();
    img.src = 'data:image/png;base64,' + b64;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0);
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    let mint = 0;
    for (let i = 0; i < d.length; i += 4) {
      const r = d[i], g = d[i + 1], b = d[i + 2];
      // "greenish": green dominates red and (mildly) blue, not near-black.
      if (g > 60 && g - r >= 20 && g - b >= 5) mint++;
    }
    return { mint, w: c.width, h: c.height };
  }, b64);
}

const browser = await chromium.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--disable-features=IsolateOrigins'],
});
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

page.on('pageerror', (e) => report.errors.push('pageerror: ' + String(e)));

// Seed the saved-project store + a user name before any app script runs.
await page.addInitScript((proj) => {
  localStorage.setItem('vaia-projects', JSON.stringify([proj]));
  localStorage.setItem('vaia-user-name', 'browser-verifier');
  localStorage.setItem('vaia-tutorial-seen', 'true'); // don't let the walkthrough block clicks
}, SEED_PROJECT);

// Stub the interpret backend so we exercise the real dialog without the LLM.
await page.route('**/api/merge/connect', async (route) => {
  let body = {};
  try { body = JSON.parse(route.request().postData() || '{}'); } catch {}
  const edge = {
    id: 'sem-edge-1',
    source: body.sourceNodeId,
    target: body.targetNodeId,
    label: 'Alpha feeds Beta',
    data: {
      label: 'Alpha feeds Beta', relation: 'provides widget data',
      codeHint: 'import from Alpha', sourceHint: 'export parse()', targetHint: 'consume parse()',
      description: body.description || '', semantic: true,
    },
  };
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, edge }) });
});

// ── 1. Load project through the app's own Load dialog ──
await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(2500);
await page.locator('.project-control-btn[title="Load project"]').click();
await page.locator('.project-modal .load-btn').first().click();
await page.waitForTimeout(500);
// The Load dialog stays open after loading — close it so it stops intercepting
// canvas clicks.
if (await page.locator('.project-modal-close').count()) await page.locator('.project-modal-close').click();
await page.waitForTimeout(2500);
const canvas = page.locator('canvas').first();
await canvas.waitFor({ state: 'visible', timeout: 10000 });
step('loaded seeded 2-node project via the Load dialog');

// The one-shot auto-centering latched on the empty canvas at boot, so the
// loaded nodes may sit off-camera. Reset the view so both are on screen.
await page.locator('[title="Reset camera view"]').click();
await page.waitForTimeout(800);
// Hide the absolutely-positioned UI bars (and the detail panel) so screenshots
// show pure WebGL and nothing intercepts canvas clicks. The connect bar is kept
// — it is what we click to open the dialog.
await page.addStyleTag({
  content: '.canvas-wrapper > div:not(:first-child):not(.canvas-connect-bar):not(.merge-overlay){display:none !important;}',
});
await page.waitForTimeout(300);

// Baseline canvas screenshot — no edge exists yet.
report.mint.before = await mintCount(page, await canvas.screenshot());

// ── 2. Locate the two nodes by the colour centroid of their spheres ──
//    (node A is blue `logic`, node B is red `output`; neither is green).
const centroid = async (buf, kind) => {
  const b64 = buf.toString('base64');
  return page.evaluate(async ({ b64, kind }) => {
    const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
    const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0);
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    let sx = 0, sy = 0, n = 0;
    for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
      const i = (y * c.width + x) * 4; const r = d[i], g = d[i + 1], bl = d[i + 2];
      const isBlue = bl > 90 && bl > r + 40 && bl > g + 25;
      const isRed = r > 85 && r - g > 45 && r - bl > 45;
      if ((kind === 'blue' && isBlue) || (kind === 'red' && isRed)) { sx += x; sy += y; n++; }
    }
    return n ? { x: Math.round(sx / n), y: Math.round(sy / n), n } : null;
  }, { b64, kind });
};
const box = await canvas.boundingBox();
const shot = await canvas.screenshot();
const cA = await centroid(shot, 'blue');
const cB = await centroid(shot, 'red');
check('found-node-A-on-canvas', !!cA && cA.n > 40, JSON.stringify(cA));
check('found-node-B-on-canvas', !!cB && cB.n > 40, JSON.stringify(cB));
if (!cA || !cB) {
  console.log(JSON.stringify(report, null, 2));
  await browser.close();
  process.exit(1);
}

// Plain click A → [A]; Shift-click B → [A, B].
await page.mouse.click(box.x + cA.x, box.y + cA.y);
await page.waitForTimeout(250);
await page.keyboard.down('Shift');
await page.mouse.click(box.x + cB.x, box.y + cB.y);
await page.keyboard.up('Shift');
await page.waitForTimeout(400);
const barVisible = (await page.locator('.canvas-connect-bar').count()) > 0;
check('multi-select-connect-bar-appears', barVisible);
if (!barVisible) {
  console.log(JSON.stringify(report, null, 2));
  await browser.close();
  process.exit(1);
}

// ── 3. Open Connect & Describe (build mode) from the bar ──
await page.locator('.canvas-connect-btn', { hasText: 'Connect these two' }).click();
await page.waitForTimeout(500);
const dialogVisible = (await page.locator('.connect-dialog').count()) > 0;
check('connect-dialog-opens', dialogVisible);
const subtitle = dialogVisible ? await page.locator('.merge-subtitle').innerText() : '';
check('dialog-is-build-mode', /same app/i.test(subtitle), subtitle.slice(0, 60));

const selects = page.locator('.connect-dialog .merge-select');
const srcVal = await selects.nth(0).inputValue();
const tgtVal = await selects.nth(1).inputValue();
check('pair-preselected', (srcVal === NODE_A.id && tgtVal === NODE_B.id) || (srcVal === NODE_B.id && tgtVal === NODE_A.id),
  `${srcVal} -> ${tgtVal}`);

// ── 4. Describe + Interpret + Apply ──
await page.locator('.connect-textarea').fill('Alpha Loader feeds parsed widgets into Beta Engine');
await page.locator('.connect-dialog button.merge-btn-primary', { hasText: 'Interpret' }).click();
await page.waitForTimeout(600);
const applyBtn = page.locator('.connect-dialog button.merge-btn-primary', { hasText: 'Apply connection' });
check('interpret-returns-edge', (await applyBtn.count()) > 0);
await applyBtn.click();
step('applied the interpreted connection');

// ── 5a. Toast names both nodes ──
await page.waitForTimeout(700);
const toastText = (await page.locator('.app-toast').count()) ? await page.locator('.app-toast').innerText() : '';
check('toast-shown', !!toastText, toastText);
check('toast-names-both-nodes', toastText.includes(NODE_A.label) && toastText.includes(NODE_B.label), toastText);

// ── 5b. Canvas draws the edge, highlighted, then settles ──
// Dialog auto-closes at 2s; highlight clears at 5s. Sample inside each window.
await page.waitForTimeout(2500); // ~3.2s after apply → dialog gone, highlight ON
report.checks['dialog-auto-closed'] = { ok: (await page.locator('.connect-dialog').count()) === 0 };
const sHighlighted = await mintCount(page, await canvas.screenshot());
report.mint.highlighted = sHighlighted;

await page.waitForTimeout(3200); // ~6.4s after apply → highlight cleared
const sSettled = await mintCount(page, await canvas.screenshot());
report.mint.settled = sSettled;

const base = report.mint.before.mint;
check('canvas-draws-new-edge', sSettled.mint > base + 200, `before=${base} settled=${sSettled.mint}`);
check('edge-is-emphasised-while-highlighted', sHighlighted.mint > sSettled.mint, `highlighted=${sHighlighted.mint} settled=${sSettled.mint}`);

await page.screenshot({ path: '/tmp/vaca-verify-final.png' });
console.log('\n=== REPORT ===');
console.log(JSON.stringify(report, null, 2));
const allOk = Object.values(report.checks).every((c) => c.ok) && report.errors.length === 0;
console.log(allOk ? '\nALL CHECKS PASSED' : '\nSOME CHECKS FAILED');
await browser.close();
process.exit(allOk ? 0 : 2);
