import { describe, it, expect, beforeAll, afterAll } from 'vitest';
let mod;
beforeAll(async () => {
    mod = await import('./runtimeSmokeTest.js');
});
afterAll(() => {
    delete process.env.VACA_SKIP_RUNTIME_SMOKE;
});
const mkFile = (fileName, code = '<!DOCTYPE html><html><body><h1>hi</h1></body></html>') => ({ fileName, code });
describe('findEntryHtml', () => {
    it('prefers index.html', () => {
        expect(mod.findEntryHtml([mkFile('other.html'), mkFile('index.html'), mkFile('app.ts')])).toBe('index.html');
    });
    it('falls back to the first html file when no index.html', () => {
        expect(mod.findEntryHtml([mkFile('a.ts'), mkFile('app.html'), mkFile('main.html')])).toBe('app.html');
    });
    it('returns null when there are no html files', () => {
        expect(mod.findEntryHtml([mkFile('app.ts'), mkFile('main.ts')])).toBeNull();
    });
    it('returns null for an empty set', () => {
        expect(mod.findEntryHtml([])).toBeNull();
    });
});
describe('isRuntimeSmokeEnabled', () => {
    it('is enabled by default', () => {
        delete process.env.VACA_SKIP_RUNTIME_SMOKE;
        expect(mod.isRuntimeSmokeEnabled()).toBe(true);
    });
    it('is disabled when the env guard is set to 1', () => {
        process.env.VACA_SKIP_RUNTIME_SMOKE = '1';
        expect(mod.isRuntimeSmokeEnabled()).toBe(false);
    });
    it('is disabled when the env guard is set to true', () => {
        process.env.VACA_SKIP_RUNTIME_SMOKE = 'true';
        expect(mod.isRuntimeSmokeEnabled()).toBe(false);
    });
    it('is enabled for arbitrary other values', () => {
        process.env.VACA_SKIP_RUNTIME_SMOKE = '0';
        expect(mod.isRuntimeSmokeEnabled()).toBe(true);
    });
});
describe('runRuntimeSmokeTest', () => {
    it('returns available:false without touching playwright when disabled', async () => {
        process.env.VACA_SKIP_RUNTIME_SMOKE = '1';
        const res = await mod.runRuntimeSmokeTest([mkFile('index.html')]);
        expect(res.available).toBe(false);
        expect(res.reason).toContain('VACA_SKIP_RUNTIME_SMOKE');
    });
    it('returns available:false with a clear reason when no html entry exists', async () => {
        delete process.env.VACA_SKIP_RUNTIME_SMOKE;
        const res = await mod.runRuntimeSmokeTest([mkFile('app.ts', 'export const x = 1;')]);
        expect(res.available).toBe(false);
        expect(res.entryFile).toBeNull();
        expect(res.reason).toContain('no HTML entry');
        expect(res.checks[0].status).toBe('skip');
    });
    it('produces a well-formed result shape when the browser is available', async () => {
        delete process.env.VACA_SKIP_RUNTIME_SMOKE;
        const res = await mod.runRuntimeSmokeTest([
            mkFile('index.html', `<!DOCTYPE html><html><head></head><body><div id="app-container"><button>Go</button></div></body></html>`),
        ]);
        // available will be true on dev machines with chromium; we don't assert
        // success (apps are arbitrary) — just the shape invariants in both cases.
        if (res.available) {
            expect(typeof res.success).toBe('boolean');
            expect(Array.isArray(res.checks)).toBe(true);
            expect(res.checks.length).toBeGreaterThan(0);
            expect(Array.isArray(res.consoleErrors)).toBe(true);
            expect(res.entryFile).toBe('index.html');
            expect(typeof res.durationMs).toBe('number');
        }
        else {
            expect(typeof res.reason).toBe('string');
        }
    });
});
describe('interaction probe', () => {
    // Regression: the probe must detect a response ANYWHERE in the document, not
    // just inside #app-container. Before the fix an app like this (which mounts
    // into <body>) could never register a response, so "apps don't respond" was
    // an artifact of the probe rather than a property of the app.
    it('detects a DOM response outside #app-container', async () => {
        delete process.env.VACA_SKIP_RUNTIME_SMOKE;
        const res = await mod.runRuntimeSmokeTest([
            mkFile('index.html', `<!DOCTYPE html><html><body>
           <h1 id="count">0</h1>
           <button id="b">go</button>
           <script>
             document.getElementById('b').addEventListener('click', function () {
               var el = document.getElementById('count');
               el.textContent = String(Number(el.textContent) + 1);
             });
           </script>
         </body></html>`),
        ]);
        // If no browser is installed the probe can't run; other tests cover the
        // unavailable shape.
        if (!res.available)
            return;
        expect(res.entryFile).toBe('index.html');
        expect(res.interactions.clicked).toBeGreaterThan(0);
        expect(res.interactions.domChangedAfterClick).toBeGreaterThan(0);
        expect(res.checks.find((c) => c.name === 'dom-responds')?.status).toBe('pass');
    });
    // Regression: a div-based control (addEventListener, no button/a/[role]/[onclick])
    // is invisible to the selector-only probe. Real apps wire board cells this way.
    it('clicks a div-based control that registered a click listener', async () => {
        delete process.env.VACA_SKIP_RUNTIME_SMOKE;
        const res = await mod.runRuntimeSmokeTest([
            mkFile('index.html', `<!DOCTYPE html><html><body>
        <div id="box" style="width:120px;height:120px;background:#333">click me</div>
        <h1 id="out">0</h1>
        <script>
          document.getElementById('box').addEventListener('click', function () {
            var o = document.getElementById('out');
            o.textContent = String(Number(o.textContent) + 1);
          });
        </script>
      </body></html>`),
        ]);
        if (!res.available)
            return;
        expect(res.interactions.clickableFound).toBeGreaterThan(0);
        expect(res.interactions.clicked).toBeGreaterThan(0);
        expect(res.interactions.domChangedAfterClick).toBeGreaterThan(0);
    });
    // A control can be present and wired but hidden (closed modal, zero-size). The
    // probe un-hides it for the click, so a geometry-dependent handler still runs.
    it('clicks a listener element hidden inside display:none', async () => {
        delete process.env.VACA_SKIP_RUNTIME_SMOKE;
        const res = await mod.runRuntimeSmokeTest([
            mkFile('index.html', `<!DOCTYPE html><html><body>
        <div id="wizard" style="display:none">
          <div id="next" style="width:80px;height:40px">next</div>
        </div>
        <h1 id="step">0</h1>
        <script>
          document.getElementById('next').addEventListener('click', function () {
            // Only counts when the probe un-hid us for the click.
            if (this.getBoundingClientRect().width > 0) {
              var s = document.getElementById('step');
              s.textContent = String(Number(s.textContent) + 1);
            }
          });
        </script>
      </body></html>`),
        ]);
        if (!res.available)
            return;
        expect(res.interactions.clicked).toBeGreaterThan(0);
        expect(res.interactions.domChangedAfterClick).toBeGreaterThan(0);
    });
    it('reports the body as mounted when there is no #app-container', async () => {
        delete process.env.VACA_SKIP_RUNTIME_SMOKE;
        const res = await mod.runRuntimeSmokeTest([
            mkFile('index.html', `<!DOCTYPE html><html><body><main><h1>Hello</h1></main></body></html>`),
        ]);
        if (!res.available)
            return;
        const mounted = res.checks.find((c) => c.name === 'app-mounted');
        expect(mounted?.status).toBe('pass');
        expect(mounted?.detail).toContain('body');
    });
});
describe('formatSmokeResult', () => {
    it('formats an unavailable result', () => {
        const text = mod.formatSmokeResult({ available: false, reason: 'no browser', success: false, durationMs: 0, entryFile: null, checks: [], consoleErrors: [], interactions: { clickableFound: 0, clicked: 0, inputsFound: 0, typed: 0, domChangedAfterClick: 0 } });
        expect(text).toContain('Runtime smoke unavailable');
    });
    it('formats a passing result with checks', () => {
        const text = mod.formatSmokeResult({ available: true, success: true, durationMs: 100, entryFile: 'index.html', checks: [{ name: 'loads-without-errors', status: 'pass', detail: 'ok' }], consoleErrors: [], interactions: { clickableFound: 2, clicked: 2, inputsFound: 1, typed: 1, domChangedAfterClick: 2 } });
        expect(text).toContain('PASS');
        expect(text).toContain('loads-without-errors');
        expect(text).toContain('2 clicked');
    });
});
