/**
 * blueprint/mockup.ts — pre-build GUI mockup for the fast preview.
 *
 * The "GUI before code" idea: when a user describes an app, we can show them
 * what the interface should look like BEFORE burning minutes generating (and
 * possibly fixing) all the real code files. This module builds that preview
 * fully DETERMINISTICALLY from the matched blueprint — no LLM call, no
 * stochastic output, sub-second to build:
 *
 *   - a self-contained HTML page styled like the app's GUI would look
 *     (sidebar of modules, palette from the blueprint stack, data-flow cards)
 *   - which is then rendered to a real PNG via headless Chromium (Playwright,
 *     already used by the runtime smoke test) so the frontend can show an
 *     actual image — "how it should look" — before any code exists.
 *
 * Design rules:
 *   - buildGuiMockupHtml is a PURE function of (blueprint, goal, opts) — the
 *     same input always yields the same HTML (unit-testable, deterministic).
 *   - renderGuiMockupToPng degrades gracefully like the runtime smoke test:
 *     if Playwright/browser is unavailable it returns { available:false }
 *     instead of throwing, and the route falls back to returning the raw HTML
 *     (which the frontend can still display in an iframe).
 */
/** User-selectable color themes for the mockup (dark, accent-tinted). */
export const MOCKUP_THEMES = [
    { id: 'ocean', label: 'Ocean', accent: '#4a9eff', accent2: '#7dd3fc', surface: '#14142a', border: 'rgba(74,158,255,0.25)' },
    { id: 'violet', label: 'Violet', accent: '#a78bfa', accent2: '#c4b5fd', surface: '#17152b', border: 'rgba(167,139,250,0.3)' },
    { id: 'emerald', label: 'Emerald', accent: '#34d399', accent2: '#6ee7b7', surface: '#0f1f1a', border: 'rgba(52,211,153,0.3)' },
    { id: 'rose', label: 'Rose', accent: '#f472b6', accent2: '#f9a8d4', surface: '#231322', border: 'rgba(244,114,182,0.3)' },
    { id: 'amber', label: 'Amber', accent: '#fbbf24', accent2: '#fde68a', surface: '#221a10', border: 'rgba(251,191,36,0.3)' },
    { id: 'slate', label: 'Slate', accent: '#94a3b8', accent2: '#cbd5e1', surface: '#14161f', border: 'rgba(148,163,184,0.25)' },
    { id: 'cyan', label: 'Cyan', accent: '#22d3ee', accent2: '#67e8f9', surface: '#0c1f24', border: 'rgba(34,211,238,0.3)' },
];
/** User-selectable layout shells for the mockup. */
export const MOCKUP_LAYOUTS = [
    { id: 'sidebar', label: 'Sidebar', hint: 'App shell with a left module sidebar' },
    { id: 'dashboard', label: 'Dashboard', hint: 'Top bar + stat cards + module grid' },
    { id: 'topnav', label: 'Top Nav', hint: 'Horizontal module navigation, full-width content' },
];
/** Resolve a theme id to its palette entry (falls back to a deterministic pick). */
function resolveTheme(appType, theme) {
    const found = theme ? MOCKUP_THEMES.find(t => t.id === theme) : undefined;
    if (found)
        return found;
    const idx = Math.floor(hashStr(appType) * MOCKUP_THEMES.length);
    return MOCKUP_THEMES[idx];
}
/**
 * Pure comparison of promised modules vs. generated files. Files are matched
 * on their nodeLabel (the module name the planner assigned); the auto preview
 * wrapper (`preview_gui_wrapper`) is excluded — it's an assembler, not a
 * promised module. Matching is trim + case-insensitive so label drift between
 * the checklist and the node label doesn't false-positive.
 */
export function compareModulesToFiles(promisedModules, files) {
    const norm = (s) => s.trim().toLowerCase();
    const expected = (promisedModules || []).map(m => m.trim()).filter(Boolean);
    const generated = (files || [])
        .filter(f => f.nodeId !== 'preview_gui_wrapper')
        .map(f => (f.nodeLabel || '').trim())
        .filter(Boolean);
    const genNorm = new Set(generated.map(norm));
    const expNorm = new Set(expected.map(norm));
    const matched = expected.filter(m => genNorm.has(norm(m)));
    const missing = expected.filter(m => !genNorm.has(norm(m)));
    const unexpected = generated.filter(g => !expNorm.has(norm(g)));
    return {
        expected,
        generated,
        matched,
        missing,
        unexpected,
        clean: missing.length === 0 && unexpected.length === 0,
    };
}
/** Escape text for safe injection into the mockup HTML. */
function esc(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
/** Stable hash → 0..1 for deterministic palette/derivation choices. */
function hashStr(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) {
        h ^= s.charCodeAt(i);
        h = Math.imul(h, 16777619);
    }
    return (h >>> 0) / 4294967295;
}
/** Simple deterministic LCG for stable pseudo-random layout jitter. */
function mulberry32(seed) {
    let a = seed >>> 0;
    return () => {
        a |= 0;
        a = (a + 0x6d2b79f5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}
/** Map a VACA node type to an emoji + label for the module cards. */
function moduleGlyph(type) {
    switch (type) {
        case 'ui': return { icon: '🖥️', color: '#4a9eff', label: 'Interface' };
        case 'database': return { icon: '🗄️', color: '#fbbf24', label: 'Data' };
        case 'api': return { icon: '🔌', color: '#a78bfa', label: 'API' };
        case 'input': return { icon: '⌨️', color: '#4ade80', label: 'Input' };
        case 'output': return { icon: '📤', color: '#f87171', label: 'Output' };
        default: return { icon: '🧩', color: '#60a5fa', label: 'Logic' };
    }
}
/** Guess a module's node type from its name (mirrors bible.moduleNodeType). */
export function moduleNodeType(moduleName) {
    const n = moduleName.toLowerCase();
    if (/(ui|screen|view|page|frontend|layout|component|widget|interface|renderer)/.test(n))
        return 'ui';
    if (/(database|db|storage|store|sql|repository|model|schema|persistence|cache|indexer)/.test(n))
        return 'database';
    if (/(api|server|endpoint|service|gateway|auth|session|sync|backend|websocket|webhook|notification|email|payment|streaming)/.test(n))
        return 'api';
    if (/(input|controller|command|parser|handler|queue|worker|processor|listener)/.test(n))
        return 'input';
    if (/(output|export|report|display|publish|notify|broadcast)/.test(n))
        return 'output';
    return 'logic';
}
/**
 * Build a self-contained HTML page that looks like the app's GUI would:
 * a layout shell (sidebar / dashboard / topnav) themed by the chosen (or
 * deterministically picked) palette, a hero with the goal, a grid of
 * per-module cards (with the data each module owns), and a data-flow strip
 * derived from the wiring graph. Purely deterministic for a fixed input.
 */
export function buildGuiMockupHtml(blueprint, goal, opts = {}) {
    const palette = resolveTheme(blueprint.app_type, opts.theme);
    const layout = (opts.layout && MOCKUP_LAYOUTS.some(l => l.id === opts.layout)) ? opts.layout : 'sidebar';
    const appName = (goal.trim().slice(0, 40)) || blueprint.description || blueprint.app_type;
    const purpose = opts.purpose || blueprint.description || '';
    // Module cards — one per architecture_checklist entry, typed + glyph'd.
    // All layout variants use the SAME capped list so they always agree (a
    // 40-module blueprint would otherwise show an endless sidebar).
    const modules = (blueprint.architecture_checklist || []).slice(0, 14);
    const navModules = modules;
    const cards = modules.map((mod, i) => {
        const type = moduleNodeType(mod);
        const g = moduleGlyph(type);
        const rnd = mulberry32(hashStr(blueprint.app_type + '|' + mod) * 4294967296);
        // Stable "owned data" placeholder lines so the card looks like a GUI card
        // (a list of the kinds of things this module would show/own).
        const sampleLines = [
            `${mod} status · ready`,
            `items: ${Math.floor(rnd() * 90) + 4}`,
        ];
        return `
      <div class="card" style="border-left:3px solid ${g.color}">
        <div class="card-head">
          <span class="card-icon" style="background:${g.color}22;color:${g.color}">${g.icon}</span>
          <span class="card-title">${esc(mod)}</span>
          <span class="card-type" style="color:${g.color}">${g.label}</span>
        </div>
        <ul class="card-lines">
          ${sampleLines.map(l => `<li>${esc(l)}</li>`).join('')}
        </ul>
      </div>`;
    }).join('\n');
    // Data-flow strip from the wiring graph.
    const wiring = (blueprint.wiring_graph || []).slice(0, 12);
    const flow = wiring.length
        ? wiring.map((w) => `
        <span class="flow-node">${esc(w.source_module)}</span>
        <span class="flow-arrow">→</span>
        <span class="flow-node">${esc(w.destination_module)}</span>
      `).join('\n')
        : '<span class="flow-node">single module</span>';
    // Stack line — where the app lives.
    const stack = blueprint.target_stack || { frontend: 'web', backend: '—', database: '—' };
    // ── Shared body pieces ──
    const heroBlock = `
        <div class="hero">
          <h1>${esc(appName)}</h1>
          <p>${esc(purpose)}</p>
          <div class="hero-stack">
            <span class="stack-chip">⚙️ ${esc(stack.frontend || 'web')}</span>
            <span class="stack-chip">⚡ ${esc(stack.backend || '—')}</span>
            <span class="stack-chip">💾 ${esc(stack.database || '—')}</span>
            ${opts.targetOS ? `<span class="stack-chip">🖥 ${esc(opts.targetOS)}</span>` : ''}
            ${opts.language ? `<span class="stack-chip">📦 ${esc(opts.language)}</span>` : ''}
          </div>
        </div>`;
    const modulesBlock = `
        <div>
          <div class="section-label">Modules</div>
          <div class="grid">${cards}</div>
        </div>`;
    const flowBlock = wiring.length ? `
        <div>
          <div class="section-label">Data Flow</div>
          <div class="flow">${flow}</div>
        </div>` : '';
    // ── Layout shells ──
    let layoutBody;
    if (layout === 'topnav') {
        layoutBody = `
    <div class="layout layout-topnav">
      <div class="topnav">
        <span class="topnav-brand">${esc(appName)}</span>
        ${navModules.map((mod, i) => {
            const g = moduleGlyph(moduleNodeType(mod));
            return `<span class="topnav-item${i === 0 ? ' active' : ''}">${g.icon} ${esc(mod)}</span>`;
        }).join('\n')}
      </div>
      <div class="main">
        ${heroBlock}
        ${modulesBlock}
        ${flowBlock}
      </div>
    </div>`;
    }
    else if (layout === 'dashboard') {
        const statCards = [
            { v: String(navModules.length), l: 'Modules' },
            { v: String(wiring.length), l: 'Data Flows' },
            { v: stack.frontend || '—', l: 'Frontend' },
            { v: stack.backend || '—', l: 'Backend' },
            { v: stack.database || '—', l: 'Database' },
        ];
        layoutBody = `
    <div class="layout layout-topnav">
      <div class="topnav">
        <span class="topnav-brand">${esc(appName)}</span>
        <span class="topnav-item active">📊 Dashboard</span>
        <span class="topnav-item">${esc(navModules[0] || 'Modules')}</span>
        <span class="topnav-item">Settings</span>
      </div>
      <div class="main">
        ${heroBlock}
        <div>
          <div class="section-label">Overview</div>
          <div class="stat-row">
            ${statCards.map(s => `
            <div class="stat-card"><div class="stat-value">${esc(s.v)}</div><div class="stat-label">${esc(s.l)}</div></div>`).join('\n')}
          </div>
        </div>
        ${modulesBlock}
        ${flowBlock}
      </div>
    </div>`;
    }
    else {
        // sidebar (default)
        layoutBody = `
    <div class="layout">
      <div class="sidebar">
        <div class="sidebar-title">Modules</div>
        ${navModules.map((mod, i) => {
            const g = moduleGlyph(moduleNodeType(mod));
            return `<div class="nav-item${i === 0 ? ' active' : ''}"><span>${g.icon}</span><span>${esc(mod)}</span></div>`;
        }).join('\n')}
      </div>
      <div class="main">
        ${heroBlock}
        ${modulesBlock}
        ${flowBlock}
      </div>
    </div>`;
    }
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(appName)} — GUI Mockup</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: auto; }
  body {
    font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
    background: #0b0b18; color: #e2e8f0;
    display: flex; align-items: flex-start; justify-content: center;
    padding: 24px;
  }
  .browser {
    width: 100%; max-width: 1180px; align-self: flex-start;
    background: ${palette.surface};
    border: 1px solid ${palette.border};
    border-radius: 14px;
    display: flex; flex-direction: column;
    overflow: visible;
    box-shadow: 0 24px 80px rgba(0,0,0,0.5);
  }
  .chrome {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 16px;
    background: rgba(255,255,255,0.03);
    border-bottom: 1px solid ${palette.border};
  }
  .dot { width: 11px; height: 11px; border-radius: 50%; display: inline-block; }
  .address {
    flex: 1; margin-left: 8px; padding: 5px 12px;
    background: rgba(0,0,0,0.35); border-radius: 8px;
    font-size: 11.5px; color: #94a3b8; letter-spacing: 0.02em;
  }
  .badge {
    font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; color: ${palette.accent2};
    border: 1px solid ${palette.border}; border-radius: 99px;
    padding: 3px 10px; background: ${palette.accent}14;
  }
  .layout { display: flex; }
  .sidebar {
    width: 232px; flex-shrink: 0;
    border-right: 1px solid ${palette.border};
    padding: 18px 12px;
    display: flex; flex-direction: column; gap: 4px;
    background: rgba(0,0,0,0.18);
  }
  .sidebar-title {
    font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; color: #64748b; padding: 0 8px 8px;
  }
  .nav-item {
    padding: 8px 10px; border-radius: 8px;
    font-size: 12px; color: #cbd5e1;
    display: flex; align-items: center; gap: 8px;
  }
  .nav-item.active { background: ${palette.accent}1e; color: ${palette.accent2}; }
  .nav-item span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .main { flex: 1; padding: 22px 26px; display: flex; flex-direction: column; gap: 20px; overflow: visible; }
  .layout-topnav { flex-direction: column; }
  .topnav {
    display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
    padding: 12px 20px; border-bottom: 1px solid ${palette.border};
    background: rgba(0,0,0,0.18);
  }
  .topnav-brand { font-size: 13px; font-weight: 800; color: #f1f5f9; margin-right: 12px; }
  .topnav-item {
    padding: 5px 12px; border-radius: 99px;
    font-size: 11px; color: #cbd5e1;
    background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
  }
  .topnav-item.active { background: ${palette.accent}1e; color: ${palette.accent2}; border-color: ${palette.border}; }
  .stat-row {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px;
  }
  .stat-card {
    background: rgba(255,255,255,0.03); border: 1px solid ${palette.border};
    border-radius: 10px; padding: 14px 16px;
  }
  .stat-value { font-size: 22px; font-weight: 800; color: ${palette.accent2}; }
  .stat-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b; margin-top: 2px; }
  .hero h1 { font-size: 22px; font-weight: 800; color: #f1f5f9; margin-bottom: 6px; }
  .hero p { font-size: 12.5px; color: #94a3b8; line-height: 1.5; max-width: 620px; }
  .hero-stack {
    display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap;
  }
  .stack-chip {
    font-size: 10.5px; color: ${palette.accent2};
    border: 1px solid ${palette.border}; border-radius: 99px;
    padding: 3px 10px; background: ${palette.accent}10;
  }
  .section-label {
    font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; color: #64748b; margin-bottom: 10px;
  }
  .grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 12px;
  }
  .card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px; padding: 12px 14px;
  }
  .card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .card-icon { width: 26px; height: 26px; border-radius: 7px; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; }
  .card-title { font-size: 12.5px; font-weight: 700; color: #e2e8f0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .card-type { font-size: 9.5px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }
  .card-lines { list-style: none; display: flex; flex-direction: column; gap: 3px; }
  .card-lines li { font-size: 11px; color: #94a3b8; }
  .flow {
    display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
    padding: 12px 14px; background: rgba(0,0,0,0.2);
    border: 1px solid ${palette.border}; border-radius: 10px;
  }
  .flow-node {
    font-size: 11px; font-weight: 600; color: ${palette.accent2};
    background: ${palette.accent}14; border: 1px solid ${palette.border};
    border-radius: 6px; padding: 4px 10px;
  }
  .flow-arrow { color: #64748b; font-size: 13px; }
  .foot {
    padding: 10px 18px; border-top: 1px solid ${palette.border};
    font-size: 10px; color: #64748b;
    display: flex; justify-content: space-between; align-items: center;
  }
</style>
</head>
<body>
  <div class="browser">
    <div class="chrome">
      <span class="dot" style="background:#ff5f57"></span>
      <span class="dot" style="background:#febc2e"></span>
      <span class="dot" style="background:#28c840"></span>
      <span class="address">🖥 GUI preview — ${esc(blueprint.app_type)}</span>
      <span class="badge">Mockup</span>
    </div>
    ${layoutBody}
    <div class="foot">
      <span>VACA pre-build GUI mockup · deterministic · no code generated yet</span>
      <span>${esc(blueprint.app_type)}</span>
    </div>
  </div>
</body>
</html>`;
}
/**
 * Render mockup HTML to a base64 PNG via headless Chromium (Playwright).
 * Graceful: returns { available:false, reason } when the browser toolchain is
 * missing — never throws — so the route can fall back to the raw HTML.
 */
export async function renderGuiMockupToPng(html) {
    const start = Date.now();
    const fail = (reason) => ({
        available: false,
        reason,
        html,
        durationMs: Date.now() - start,
    });
    let chromium;
    try {
        ({ chromium } = await import('playwright'));
    }
    catch (err) {
        return fail(`Playwright unavailable: ${err instanceof Error ? err.message : String(err)}`);
    }
    let browser = null;
    try {
        browser = await chromium.launch({
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
        });
    }
    catch (err) {
        return fail(`Could not launch Chromium: ${err instanceof Error ? err.message : String(err)}`);
    }
    try {
        const page = await browser.newPage({ viewport: { width: 1240, height: 860 } });
        await page.setContent(html, { waitUntil: 'domcontentloaded' });
        // Let web fonts / layout settle a beat so the PNG isn't mid-reflow.
        await page.waitForTimeout(350);
        // Shrink the viewport to the real content height so a short mockup is not
        // padded with dead space below, then fullPage so tall blueprints (many
        // modules) are never clipped at the bottom.
        // `document` runs inside the browser context (Playwright evaluate) — the
        // backend's tsconfig has no DOM lib, so access it via globalThis.
        const contentHeight = await page.evaluate(() => Math.max(globalThis.document.body.scrollHeight, 300));
        await page.setViewportSize({ width: 1240, height: contentHeight });
        await page.waitForTimeout(120);
        const png = await page.screenshot({ type: 'png', fullPage: true });
        return {
            available: true,
            imageBase64: png.toString('base64'),
            html,
            durationMs: Date.now() - start,
        };
    }
    catch (err) {
        return fail(`Screenshot failed: ${err instanceof Error ? err.message : String(err)}`);
    }
    finally {
        try {
            await browser.close();
        }
        catch { /* ignore */ }
    }
}
