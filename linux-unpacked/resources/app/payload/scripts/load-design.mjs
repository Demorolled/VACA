#!/usr/bin/env node
/**
 * Load a stored design directly into the running VACA frontend.
 *
 * The canvas is a WebGL (three.js) scene, so nodes have no DOM to click.
 * Instead we inject the design into the live Zustand store by dynamically
 * importing the SAME module the app uses (/src/store/projectStore.ts under
 * Vite dev), then call replaceNodes(). The 3D canvas renders the nodes.
 *
 * Env:
 *   APP_URL       default http://localhost:5173
 *   API_URL       default http://127.0.0.1:3001
 *   DESIGN_ID     the stored design id to load (default design_1781315221040)
 *   BASE_URL      served store module path prefix (default /src)
 */
import { chromium } from 'playwright';

const APP_URL = process.env.APP_URL || 'http://localhost:5173';
const API_URL = process.env.API_URL || 'http://127.0.0.1:3001';
const DESIGN_ID = process.env.DESIGN_ID || 'design_1781315221040';

// ── 1. Fetch the stored design from the backend ──
const res = await fetch(`${API_URL}/api/designs/search?q=`);
const data = await res.json();
const design = (data.designs || []).find((d) => d.id === DESIGN_ID);
if (!design) {
  console.error('Design not found:', DESIGN_ID);
  console.log('Available ids:', (data.designs || []).slice(0, 30).map((d) => `${d.id} (${d.name.slice(0, 30)})`).join('\n'));
  process.exit(1);
}
console.log(`Loaded design: ${design.name} — ${design.nodes.length} nodes, ${design.edges.length} stored edges, targetOS=${design.targetOS}`);

// Remap edges against the design's node ids (the stored edge ids can be stale).
const nodeIds = new Set(design.nodes.map((n) => n.id));
const usableEdges = (design.edges || []).filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));
console.log(`Edges that resolve to node ids: ${usableEdges.length}/${design.edges.length}`);

// ── 2. Launch visible Chrome (on the VNC display) ──
const browser = await chromium.launch({
  channel: 'chrome',
  headless: false,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled', '--start-maximized'],
});
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
const page = await ctx.newPage();
page.on('console', (m) => { if (m.type() === 'error') console.log('[console.error]', m.text().slice(0, 160)); });

console.log('Opening', APP_URL, '…');
await page.goto(APP_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
// Give the app time to mount so the store module is warm.
await page.waitForFunction(() => document.querySelectorAll('.react-flow__view-port, canvas').length > 0, { timeout: 30000 })
  .catch(() => console.log('wait-for-canvas timed out'));

const goal = design.goal || design.name;
const purpose = design.purpose || '';

const payload = {
  nodes: design.nodes.map((dn, i) => ({
    label: dn.label,
    description: dn.description || '',
    type: dn.type,
    language: dn.language ? dn.language.split(' ')[0] : (design.targetOS === 'linux' ? 'python' : 'typescript'),
    appGoal: goal,
    appPurpose: purpose,
    _pos: dn.position || { x: 250, y: 200 + i * 170 },
    _refId: dn.id,
  })),
  usableEdges,
  goal,
  purpose,
  os: design.targetOS || 'linux',
};

const result = await page.evaluate(async ({ nodes, usableEdges, goal, purpose, os }) => {
  const diag = { flowNodesBuilt: 0, moduleHasStore: false, replaceIsFn: false, err: null };
  try {
    const m = await import('/src/store/projectStore.ts');
    diag.moduleHasStore = typeof m.useProjectStore !== 'undefined';
    diag.replaceIsFn = typeof m.useProjectStore.getState().replaceNodes === 'function';

    const s = m.useProjectStore.getState();
    diag.before = s.nodes.length;

    const idMap = {};
    const flowNodes = nodes.map((n, i) => {
      const id = `design_${Date.now()}_${i}`;
      idMap[n._refId] = id;
      return {
        id,
        type: n.type,
        position: n._pos,
        data: {
          label: n.label,
          description: n.description,
          type: n.type,
          status: 'pending',
          language: n.language,
          appGoal: n.appGoal,
          appPurpose: n.appPurpose,
        },
      };
    });
    diag.flowNodesBuilt = flowNodes.length;

    const masterNode = {
      id: `master_design_${Date.now()}`,
      type: 'master',
      position: { x: 250, y: 40 },
      data: { label: 'App Blueprint', type: 'master', status: 'pending', appGoal: goal, appPurpose: purpose, selectedOS: os, scale: 'medium' },
    };

    const flowEdges = usableEdges
      .filter((e) => idMap[e.source] && idMap[e.target])
      .map((e, i) => ({ id: `edge_design_${i}`, source: idMap[e.source], target: idMap[e.target], type: 'default' }));

    s.replaceNodes([masterNode, ...flowNodes], flowEdges, os);
    s.setWizardStep('filling-nodes');
    if (goal) s.setUserGoal(goal);
    if (purpose) s.setUserPurpose(purpose);
    if (goal) s.setProjectName(goal.substring(0, 40));

    await new Promise((r) => setTimeout(r, 50));
    const fresh = m.useProjectStore.getState();
    diag.after = fresh.nodes.length;
    diag.labels = fresh.nodes.filter((n) => n.type !== 'master').map((n) => n.data?.label);
  } catch (e) {
    diag.err = String(e && e.message ? e.message : e);
  }
  return diag;
}, payload);

console.log('\nInjection diagnostics:');
console.log(' ', JSON.stringify(result, null, 1));

// Let the 3D canvas render the new nodes.
await page.waitForTimeout(4000);
console.log('\nBrowser left open at', APP_URL, 'on DISPLAY', process.env.DISPLAY || '(unset)', '— ready for you to edit.');