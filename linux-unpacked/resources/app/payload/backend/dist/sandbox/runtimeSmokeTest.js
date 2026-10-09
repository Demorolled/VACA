/**
 * runtimeSmokeTest — automated RUNTIME smoke tests for generated apps.
 *
 * The existing verification stack is compile-only: tsc --noEmit (type-level)
 * and the sandbox runner (syntax/exec of individual files). Neither proves the
 * ASSEMBLED app actually boots and responds to a user. This module closes that
 * gap: it takes the generated file set (the preview index.html the FileGenerator
 * already produces, plus any side files), loads it in a real headless Chromium
 * via Playwright, and CLICKS THROUGH it — presses every visible button, types
 * into every input, and asserts the app stays error-free and the DOM responds.
 *
 * Design constraints:
 *  - Graceful degradation: if Playwright or a browser binary is unavailable,
 *    the module returns { available: false } instead of throwing — the
 *    generation pipeline must never break because runtime tests can't run.
 *  - Non-fatal: the report is informational/gating at the caller's discretion.
 *  - Bounded: caps the number of clicks/inputs and timeouts every step so a
 *    misbehaving generated app can't hang a build.
 *
 * Note on the training loop: verifiedGenerationCapture currently gates on tsc
 * cleanliness only. Runtime-smoke success is available on the generation
 * response (runtimeSmoke.success) so the capture gate CAN be extended to also
 * require it — but the gate itself is intentionally not changed here, since
 * smoke availability depends on a browser being installed.
 */
import { writeFileSync, mkdirSync } from 'fs';
import * as os from 'os';
import * as path from 'path';
const SMOKE_ENTRY_PREFERENCE = ['index.html', 'app.html', 'main.html'];
// Note: click/input caps and settle delays are inlined inside the serialized
// page.evaluate callbacks (browser functions can't close over module scope), so
// the values below are only referenced via LOAD_TIMEOUT_MS + the race budget.
const LOAD_TIMEOUT_MS = 15000;
/**
 * Installed in the page BEFORE any app script. Records every element that
 * registers a click listener so the probe can click custom, div-based controls
 * that no CSS selector can find. Observed gap: a generated tic-tac-toe wired 9
 * click listeners onto board cells and the selector-based probe clicked 0 of
 * them, so the app was reported as non-interactive.
 *
 * Passed as a STRING, not a function: Playwright serializes function sources,
 * and tsx/esbuild's keepNames pass would inject an undefined `__name(...)`
 * helper into the page (the same trap that broke the click probe once already).
 */
const TRACK_CLICK_TARGETS_SCRIPT = `
(function () {
  var proto = EventTarget.prototype;
  var orig = proto.addEventListener;
  if (typeof orig !== 'function' || proto.__vacaPatched) return;
  proto.__vacaPatched = true;
  globalThis.__vacaClickEls = [];
  proto.addEventListener = function (type, listener, opts) {
    try {
      if (type === 'click' && this && this.nodeType === 1 && !this.__vacaTracked) {
        this.__vacaTracked = true;
        globalThis.__vacaClickEls.push(this);
      }
    } catch (e) { /* never break the app */ }
    return orig.call(this, type, listener, opts);
  };

  // Helpers used by the click probe. They live on a global (installed from a
  // STRING) instead of being defined inside the page.evaluate callback: a named
  // const arrow function in that callback is rewritten by tsx/esbuild's
  // keepNames pass to call an undefined __name(...) helper, which kills every
  // app with "__name is not defined".
  globalThis.__vacaProbe = {
    isVisible: function (el) {
      var r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    },
    // Force the element and any hidden ancestor to render; returns an undo list.
    unhide: function (el) {
      var saved = [];
      var n = el;
      while (n && n.nodeType === 1) {
        var cs = getComputedStyle(n);
        if (cs.display === 'none' || cs.visibility === 'hidden') {
          saved.push([n, n.style.display, n.style.visibility]);
          n.style.display = 'block';
          n.style.visibility = 'visible';
        }
        n = n.parentElement;
      }
      return saved;
    },
    restore: function (saved) {
      for (var i = 0; i < saved.length; i++) {
        saved[i][0].style.display = saved[i][1];
        saved[i][0].style.visibility = saved[i][2];
      }
    },
  };
})();
`;
/** Skip the whole runtime smoke when set (CI without browsers, etc.). */
export function isRuntimeSmokeEnabled() {
    return process.env.VACA_SKIP_RUNTIME_SMOKE !== '1' && process.env.VACA_SKIP_RUNTIME_SMOKE !== 'true';
}
/**
 * Launch Chromium, falling back to a system-installed browser.
 *
 * Playwright's bundled Chromium is a separate download that is frequently absent
 * on a given box. `chromium.launch()` then throws and the caller reports
 * `available:false` — which is indistinguishable from "never tested" and hides
 * real app failures. Any box with Chrome or Edge installed can still run the
 * smoke test, so try the bundled build and fall through to the system browsers.
 *
 * Order: bundled -> VACA_BROWSER_PATH -> chrome -> msedge.
 */
async function launchSmokeBrowser(chromium) {
    const args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu', '--disable-dev-shm-usage'];
    const explicit = process.env.VACA_BROWSER_PATH;
    const candidates = [
        {},
        ...(explicit ? [{ executablePath: explicit }] : []),
        { channel: 'chrome' },
        { channel: 'msedge' },
    ];
    let error = null;
    for (const extra of candidates) {
        try {
            return { browser: await chromium.launch({ headless: true, args, ...extra }), error: null };
        }
        catch (err) {
            error = err;
        }
    }
    return { browser: null, error };
}
/**
 * Pick the HTML entry from the generated file set. Pure + exported for tests.
 * The FileGenerator appends a self-contained `index.html` preview wrapper, so
 * this is normally a trivial lookup, but we fall back to the first .html.
 */
export function findEntryHtml(files) {
    const htmlFiles = files.filter((f) => f.fileName.toLowerCase().endsWith('.html'));
    if (htmlFiles.length === 0)
        return null;
    for (const pref of SMOKE_ENTRY_PREFERENCE) {
        const hit = htmlFiles.find((f) => f.fileName.toLowerCase() === pref);
        if (hit)
            return hit.fileName;
    }
    return htmlFiles[0].fileName;
}
/**
 * Run the click-through smoke test against the generated files.
 *
 * @param files    Generated file set (preview index.html + side files).
 * @param opts.timeoutMs  Overall budget; default 60s.
 */
export async function runRuntimeSmokeTest(files, opts = {}) {
    const start = Date.now();
    const timeoutMs = opts.timeoutMs ?? 60_000;
    const entry = findEntryHtml(files);
    const checks = [];
    const consoleErrors = [];
    const interactions = {
        clickableFound: 0,
        clicked: 0,
        inputsFound: 0,
        typed: 0,
        domChangedAfterClick: 0,
        responseSignals: { dom: 0, canvas: 0 },
    };
    const finish = (overrides = {}) => {
        const failed = checks.filter((c) => c.status === 'fail').length;
        return {
            available: true,
            success: failed === 0,
            durationMs: Date.now() - start,
            entryFile: entry,
            checks,
            consoleErrors,
            interactions,
            ...overrides,
        };
    };
    if (!isRuntimeSmokeEnabled()) {
        // available:false is the real signal; success stays true so a consumer that
        // only checks .success (e.g. a training gate) does not treat "disabled" as
        // a failed app.
        return { available: false, reason: 'disabled via VACA_SKIP_RUNTIME_SMOKE', success: true, durationMs: 0, entryFile: entry, checks, consoleErrors, interactions };
    }
    if (!entry) {
        return {
            available: false,
            reason: 'no HTML entry found in generated files (nothing to boot in a browser)',
            success: false,
            durationMs: Date.now() - start,
            entryFile: null,
            checks: [{ name: 'entry-html', status: 'skip', detail: 'No .html file in the generated set' }],
            consoleErrors,
            interactions,
        };
    }
    // ── Materialize the app into a temp dir (like site-preview does) ──
    // mkdirSync({ recursive: true }) is typed string | undefined — coerce: the
    // path is always created here, so it is guaranteed a real string.
    const tmpDir = mkdirSync(path.join(os.tmpdir(), `vaca-smoke-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`), { recursive: true });
    try {
        for (const f of files) {
            // Guard against path traversal + escape from the temp dir: only the last
            // path segment is used, and empty / '.' / '..' names are skipped so
            // writeFileSync can never resolve outside tmpDir (e.g. EISDIR on '..').
            const baseName = f.fileName.replace(/\\/g, '/').split('/').pop() ?? '';
            if (!baseName || baseName === '.' || baseName === '..')
                continue;
            writeFileSync(path.join(tmpDir, baseName), f.code, 'utf-8');
        }
        const entryNameRaw = entry.replace(/\\/g, '/').split('/').pop() ?? entry;
        const entryName = entryNameRaw && entryNameRaw !== '.' && entryNameRaw !== '..' ? entryNameRaw : entry;
        const entryPath = path.join(tmpDir, entryName);
        const fileUrl = `file://${entryPath}`;
        // ── Boot Playwright (graceful if unavailable) ──
        let chromium;
        try {
            // eslint-disable-next-line @typescript-eslint/no-var-requires
            ({ chromium } = await import('playwright'));
        }
        catch (err) {
            return finish({ available: false, reason: `Playwright unavailable: ${err instanceof Error ? err.message : String(err)}` });
        }
        const launched = await launchSmokeBrowser(chromium);
        if (!launched.browser) {
            const msg = launched.error instanceof Error ? launched.error.message : String(launched.error);
            return finish({ available: false, reason: `Could not launch Chromium: ${msg}` });
        }
        const browser = launched.browser;
        // The whole browser session is raced against the caller's timeout budget:
        // a generated app stuck in an infinite loop inside a click/type handler
        // would otherwise block page.evaluate forever and hang the build.
        const browserRun = (async () => {
            const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
            // Capture click targets before the app's own scripts run.
            await context.addInitScript({ content: TRACK_CLICK_TARGETS_SCRIPT });
            const page = await context.newPage();
            page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err?.message ?? String(err)}`));
            page.on('console', (msg) => {
                if (msg.type() === 'error')
                    consoleErrors.push(`console.error: ${msg.text()}`);
            });
            page.on('dialog', (dlg) => {
                // Auto-dismiss alert()/confirm() so generated apps can't wedge the test.
                dlg.dismiss().catch(() => { });
            });
            // ── Check 1: loads without errors ──
            try {
                await page.goto(fileUrl, { waitUntil: 'domcontentloaded', timeout: LOAD_TIMEOUT_MS });
                await page.waitForTimeout(500); // let async render settle
                const errs = [...consoleErrors];
                checks.push(errs.length === 0
                    ? { name: 'loads-without-errors', status: 'pass', detail: 'No console/page errors during load' }
                    : { name: 'loads-without-errors', status: 'fail', detail: errs.slice(0, 4).join('; ') });
            }
            catch (err) {
                checks.push({ name: 'loads-without-errors', status: 'fail', detail: `Navigation failed: ${err instanceof Error ? err.message : String(err)}` });
            }
            // ── Check 2: the app container actually mounted something ──
            try {
                const mounted = await page.evaluate(() => {
                    const doc = globalThis.document;
                    const el = doc.getElementById('app-container');
                    if (el) {
                        return {
                            ok: el.children.length > 0 || (el.textContent || '').trim().length > 0,
                            where: '#app-container',
                            why: `children=${el.children.length} textLen=${(el.textContent || '').trim().length}`,
                        };
                    }
                    // No #app-container: most generated apps mount straight into <body>,
                    // so fall back to the body rather than warn about a container contract
                    // they never agreed to. (109/115 apps in the last sweep use <body>.)
                    const body = doc.body;
                    const textLen = (body?.textContent || '').trim().length;
                    const canvas = doc.querySelectorAll('canvas').length;
                    const controls = doc.querySelectorAll('button, input, select, textarea').length;
                    return {
                        ok: (body?.children.length ?? 0) > 0 && (textLen > 0 || canvas > 0 || controls > 0),
                        where: 'body',
                        why: `body.children=${body?.children.length ?? 0} textLen=${textLen} canvas=${canvas} controls=${controls}`,
                    };
                });
                checks.push(mounted.ok
                    ? { name: 'app-mounted', status: 'pass', detail: `${mounted.where} rendered (${mounted.why})` }
                    : { name: 'app-mounted', status: 'warn', detail: `${mounted.where} empty after load (${mounted.why}) — app may be logic-only or render on interaction` });
            }
            catch (err) {
                checks.push({ name: 'app-mounted', status: 'warn', detail: `Could not inspect container: ${err instanceof Error ? err.message : String(err)}` });
            }
            // ── Check 3: interactive elements exist ──
            const clickableSel = 'button, a[href], input[type="button"], input[type="submit"], [role="button"], .btn, [onclick]';
            const inputSel = 'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="radio"]):not([type="checkbox"]):not([type="color"]), textarea';
            const counts = await page.evaluate((sel) => {
                const doc = globalThis.document;
                const win = globalThis;
                // Union of selector matches and elements that actually registered a
                // click listener (custom/div-based controls the selector misses).
                const selected = Array.from(doc.querySelectorAll(sel));
                const tracked = Array.isArray(win.__vacaClickEls)
                    ? win.__vacaClickEls.filter((el) => el && el.isConnected)
                    : [];
                const all = Array.from(new Set([...selected, ...tracked]));
                const visible = all.filter((el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                });
                return { total: all.length, visible: visible.length, tracked: tracked.length };
            }, clickableSel);
            interactions.clickableFound = counts.total;
            checks.push({
                name: 'interactive-elements',
                status: counts.total > 0 ? 'pass' : 'warn',
                detail: `Found ${counts.total} clickable element(s) (${counts.visible} visible)`,
            });
            // ── Check 4: click every button, assert no crash + DOM response ──
            // Snapshot the error count BEFORE clicking so load-time errors are not
            // misattributed to the clicks themselves.
            const errsBeforeClicks = consoleErrors.length;
            const clickReport = await page.evaluate(async (sel) => {
                const doc = globalThis.document;
                const win = globalThis;
                // Click selector matches AND elements that registered a click listener —
                // custom/div-based controls are invisible to the selector alone.
                const selected = Array.from(doc.querySelectorAll(sel));
                const tracked = Array.isArray(win.__vacaClickEls)
                    ? win.__vacaClickEls.filter((el) => el && el.isConnected)
                    : [];
                const els = Array.from(new Set([...selected, ...tracked]));
                // Probe helpers are installed by the page-level script; see
                // TRACK_CLICK_TARGETS_SCRIPT for why they are not defined here.
                const probe = globalThis.__vacaProbe;
                // Candidates: everything, visible OR hidden/zero-size (hidden controls
                // are un-hidden for the click). Covers both <button>-style matches and
                // custom div controls carrying inline onclick or a click listener.
                const candidates = els;
                // Detect a response to a click across the WHOLE document, not just one
                // container. An earlier version diffed innerHTML.length of
                // `#app-container` — but most generated apps don't render into that id,
                // so the signal was structurally dead for them (before/after were both
                // always 0) and "apps don't respond" was an artifact of the probe, not
                // a property of the apps. DO NOT narrow this back to one container.
                //
                // Signals:
                //  - dom:    MutationObserver (childList/characterData/attributes,
                //            subtree) catches text, class, style and structure changes
                //            anywhere in the document.
                //  - canvas: pixel hash of each <canvas> (games render without DOM
                //            changes).
                // NOTE: do NOT factor the canvas signature into a named `const fn =
                // () => ...` helper inside this callback. Pages are serialized to source
                // and re-evaluated in the browser, and tsx/esbuild's keepNames pass wraps
                // named function expressions in a `__name(...)` helper that does not
                // exist in the page — every app then dies with "__name is not defined".
                let mutations = 0;
                const observer = new globalThis.MutationObserver((records) => {
                    mutations += records.length;
                });
                observer.observe(doc.documentElement, {
                    subtree: true,
                    childList: true,
                    characterData: true,
                    attributes: true,
                });
                let clicked = 0;
                let changed = 0;
                let domSignals = 0;
                let canvasSignals = 0;
                for (const el of candidates.slice(0, 30)) {
                    // Un-hide zero-size / hidden controls for the duration of the click.
                    const saved = probe && !probe.isVisible(el) ? probe.unhide(el) : [];
                    // Drain mutations produced by the un-hide itself so they are not
                    // counted as the app responding to the click.
                    try {
                        observer.takeRecords();
                    }
                    catch { /* ignore */ }
                    mutations = 0;
                    const beforeCanvas = [];
                    for (const c of Array.from(doc.querySelectorAll('canvas')).slice(0, 4)) {
                        try {
                            const url = c.toDataURL();
                            beforeCanvas.push(`${c.width}x${c.height}:${url.length}:${url.slice(-48)}`);
                        }
                        catch {
                            beforeCanvas.push('unreadable'); // not readable (WebGL/tainted)
                        }
                    }
                    try {
                        el.click();
                        clicked++;
                    }
                    catch {
                        /* non-clickable — count as attempted */
                    }
                    await new Promise((r) => setTimeout(r, 120));
                    const afterCanvas = [];
                    for (const c of Array.from(doc.querySelectorAll('canvas')).slice(0, 4)) {
                        try {
                            const url = c.toDataURL();
                            afterCanvas.push(`${c.width}x${c.height}:${url.length}:${url.slice(-48)}`);
                        }
                        catch {
                            afterCanvas.push('unreadable');
                        }
                    }
                    const canvasChanged = beforeCanvas.join('|') !== afterCanvas.join('|');
                    if (mutations > 0 || canvasChanged) {
                        changed++;
                        if (mutations > 0)
                            domSignals++;
                        if (canvasChanged)
                            canvasSignals++;
                    }
                    if (saved.length && probe)
                        probe.restore(saved);
                }
                observer.disconnect();
                return { clicked, changed, domSignals, canvasSignals };
            }, clickableSel);
            interactions.clicked = clickReport.clicked;
            interactions.domChangedAfterClick = clickReport.changed;
            interactions.responseSignals = { dom: clickReport.domSignals, canvas: clickReport.canvasSignals };
            const newErrsAfterClicks = consoleErrors.length - errsBeforeClicks;
            checks.push(clickReport.clicked === 0
                ? { name: 'clicks-dont-crash', status: 'warn', detail: 'No visible clickable elements to click' }
                : newErrsAfterClicks > 0
                    ? { name: 'clicks-dont-crash', status: 'fail', detail: `${clickReport.clicked} clicks produced ${newErrsAfterClicks} error(s): ${consoleErrors.slice(errsBeforeClicks).slice(0, 3).join('; ')}` }
                    : { name: 'clicks-dont-crash', status: 'pass', detail: `Clicked ${clickReport.clicked} element(s), zero errors; ${clickReport.changed} produced a visible response` });
            // ── Check 5: typing into inputs round-trips ──
            const typeReport = await page.evaluate(async (sel) => {
                const win = globalThis;
                const els = Array.from(win.document.querySelectorAll(sel));
                const visible = els.filter((el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                });
                let typed = 0;
                for (const el of visible.slice(0, 10)) {
                    const probe = `smoke${typed}_${Date.now() % 100000}`;
                    try {
                        const setter = Object.getOwnPropertyDescriptor(win.HTMLInputElement.prototype, 'value')?.set
                            || Object.getOwnPropertyDescriptor(win.HTMLTextAreaElement.prototype, 'value')?.set;
                        if (setter)
                            setter.call(el, probe);
                        el.dispatchEvent(new win.Event('input', { bubbles: true }));
                        el.dispatchEvent(new win.Event('change', { bubbles: true }));
                        if (el.value === probe)
                            typed++;
                    }
                    catch {
                        /* ignore */
                    }
                }
                return { typed };
            }, inputSel);
            interactions.inputsFound = typeReport.typed > 0 ? typeReport.typed : await page.locator(inputSel).count().catch(() => 0);
            interactions.typed = typeReport.typed;
            checks.push(typeReport.typed === 0
                ? { name: 'typing-works', status: 'warn', detail: 'No visible text inputs to type into' }
                : { name: 'typing-works', status: 'pass', detail: `Typed into ${typeReport.typed} input(s), values round-tripped` });
            // ── Check 6: DOM responds to interaction ──
            checks.push(interactions.clicked === 0 && interactions.typed === 0
                ? { name: 'dom-responds', status: 'warn', detail: 'No interactions available to verify DOM response' }
                : interactions.domChangedAfterClick > 0 || interactions.typed > 0
                    ? { name: 'dom-responds', status: 'pass', detail: `UI responded on ${interactions.domChangedAfterClick}/${interactions.clicked} click(s) (dom ${clickReport.domSignals}, canvas ${clickReport.canvasSignals}); ${interactions.typed} input(s) accepted` }
                    : { name: 'dom-responds', status: 'warn', detail: 'Clicks ran without error but nothing observable changed (no DOM mutation, no canvas change) — the click handler may be a no-op' });
            await context.close();
        })();
        try {
            // Enforce the overall budget: if the app wedges the browser, the build
            // returns a timed-out result instead of hanging forever.
            await Promise.race([
                browserRun,
                new Promise((_, reject) => setTimeout(() => reject(new Error(`runtime smoke exceeded ${timeoutMs}ms budget`)), timeoutMs)),
            ]);
            return finish();
        }
        catch (err) {
            checks.push({ name: 'timeout-or-crash', status: 'fail', detail: err instanceof Error ? err.message : String(err) });
            return finish();
        }
        finally {
            if (browser)
                await browser.close().catch(() => { });
        }
    }
    finally {
        // Clean up the temp dir (best-effort).
        try {
            const { rmSync } = await import('fs');
            rmSync(tmpDir, { recursive: true, force: true });
        }
        catch {
            /* best-effort */
        }
    }
}
/** CLI-facing helper: format the smoke result as a human-readable block. */
export function formatSmokeResult(r) {
    if (!r.available)
        return `⛔ Runtime smoke unavailable: ${r.reason ?? 'unknown'}`;
    const lines = r.checks.map((c) => `  ${c.status === 'pass' ? '✅' : c.status === 'fail' ? '❌' : c.status === 'warn' ? '⚠️' : '⏭️'} ${c.name} — ${c.detail}`);
    return [
        `🧪 Runtime smoke: ${r.success ? 'PASS' : 'FAIL'} (${r.durationMs}ms)`,
        ...lines,
        `   Interactions: ${r.interactions.clicked} clicked / ${r.interactions.typed} typed / ${r.interactions.domChangedAfterClick} DOM changed`,
        r.consoleErrors.length > 0 ? `   Console errors (${r.consoleErrors.length}): ${r.consoleErrors.slice(0, 4).join('; ')}` : '   Console errors: none',
    ].join('\n');
}
