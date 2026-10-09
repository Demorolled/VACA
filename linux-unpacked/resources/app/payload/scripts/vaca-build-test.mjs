#!/usr/bin/env node
/**
 * VACA full-pipeline build test driver.
 *
 * Runs the exact flow the frontend uses, but directly against the live API:
 *   1. POST /api/projects            — create an empty project
 *   2. POST /api/architect/plan      — LLM designs nodes/edges
 *   3. PUT  /api/projects/:id        — save the plan
 *   4. POST /api/generate/:id/files  — per-file generation + tsc gate + runtime smoke
 *   5. POST /api/export/:id/per-file-scaffold — write the project to disk
 *
 * Usage: node scripts/vaca-build-test.mjs '<goal>' '<purpose>' [--out DIR] [--scale small]
 * Writes a JSON report to ./out/vaca-builds/<slug>/report.json and prints progress.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const API = process.env.VACA_API || 'http://localhost:3001/api';
const goal = process.argv[2];
const purpose = process.argv[3] || '';
const scale = (process.argv.find((a) => a.startsWith('--scale=')) || '--scale=small').split('=')[1];
const outArgIdx = process.argv.indexOf('--out');
const outDir = outArgIdx !== -1 ? process.argv[outArgIdx + 1] : null;

if (!goal) {
  console.error('usage: node scripts/vaca-build-test.mjs "<goal>" "<purpose>" [--out DIR] [--scale small]');
  process.exit(1);
}

const slug = goal.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const reportDir = path.join(root, 'out', 'vaca-builds', slug);
mkdirSync(reportDir, { recursive: true });

const report = { goal, purpose, scale, startedAt: new Date().toISOString(), steps: [], errors: [] };
const step = (name, detail) => {
  const s = { name, detail, at: new Date().toISOString() };
  report.steps.push(s);
  console.log(`[${new Date().toISOString()}] ▶ ${name} — ${typeof detail === 'string' ? detail : JSON.stringify(detail).slice(0, 200)}`);
  return s;
};
const fail = (where, msg) => { report.errors.push({ where, msg }); console.error(`[FAIL] ${where}: ${msg}`); };

async function api(method, url, body, timeoutMs = 120000) {
  const res = await fetch(`${API}${url}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON */ }
  return { status: res.status, data };
}

try {
  // 1. Create project
  step('create-project', { name: goal });
  const created = await api('POST', '/projects', { name: goal, targetOS: 'linux' }, 15000);
  if (created.status !== 201 || !created.data?.id) { fail('create-project', JSON.stringify(created.data)); process.exit(2); }
  const projectId = created.data.id;
  step('project-id', projectId);

  // 2. Plan architecture
  step('architect-plan', 'LLM designing nodes/edges (can take 1-2 min)');
  const plan = await api('POST', '/architect/plan', { goal, purpose, targetOS: 'linux', scale }, 180000);
  if (!plan.data?.success || !Array.isArray(plan.data?.nodes) || plan.data.nodes.length === 0) {
    fail('architect-plan', JSON.stringify(plan.data).slice(0, 500));
    process.exit(3);
  }
  step('plan-result', { nodes: plan.data.nodes.length, edges: plan.data.edges.length, types: plan.data.architecture?.nodeTypes });
  writeFileSync(path.join(reportDir, 'plan.json'), JSON.stringify(plan.data, null, 2));

  // 3. Save plan to project
  step('save-plan', `PUT /api/projects/${projectId}`);
  const saved = await api('PUT', `/projects/${projectId}`, { nodes: plan.data.nodes, edges: plan.data.edges }, 15000);
  if (saved.status !== 200) fail('save-plan', `status ${saved.status}`);

  // 4. Generate files (full validation: tsc gate + runtime smoke, no skips)
  step('generate-files', 'per-file generation + tsc gate + runtime smoke (can take several minutes)');
  const gen = await api('POST', `/generate/${projectId}/files`, {}, 900000);
  if (!gen.data?.success) { fail('generate-files', JSON.stringify(gen.data).slice(0, 500)); process.exit(4); }
  const g = gen.data;
  report.generation = {
    totalFiles: g.summary?.totalFiles, totalChars: g.summary?.totalChars,
    totalErrors: g.summary?.totalErrors, validated: g.summary?.validated, failed: g.summary?.failed,
    isAllValidated: g.summary?.isAllValidated, tsCompileClean: g.summary?.tsCompileClean,
    contractViolations: g.summary?.contractViolations,
    runtimeSmoke: g.runtimeSmoke ? { available: g.runtimeSmoke.available, success: g.runtimeSmoke.success, checks: g.runtimeSmoke.checks, consoleErrors: g.runtimeSmoke.consoleErrors } : null,
    timingMs: g.timingMs,
    perFile: (g.files || []).map((f) => ({ fileName: f.fileName, nodeLabel: f.nodeLabel, validated: f.validated, errors: f.errors, codeLength: f.code.length })),
  };
  step('generate-summary', report.generation);
  writeFileSync(path.join(reportDir, 'generation.json'), JSON.stringify(g, null, 2));
  writeFileSync(path.join(reportDir, 'files.json'), JSON.stringify((g.files || []).map((f) => ({ fileName: f.fileName, code: f.code })), null, 2));

  // 5. Export
  step('export', 'per-file scaffold to disk');
  const exportOpts = { projectName: goal, targetOS: 'linux' };
  if (outDir) exportOpts.outputDir = outDir;
  const ex = await api('POST', `/export/${projectId}/per-file-scaffold`, exportOpts, 120000);
  if (!ex.data?.success) { fail('export', JSON.stringify(ex.data).slice(0, 500)); process.exit(5); }
  report.export = { outputPath: ex.data.outputPath, files: ex.data.files, message: ex.data.message };
  step('export-path', ex.data.outputPath);

  report.completedAt = new Date().toISOString();
  report.ok = report.errors.length === 0;
} catch (e) {
  fail('driver', e instanceof Error ? e.message : String(e));
  report.completedAt = new Date().toISOString();
  report.ok = false;
}

writeFileSync(path.join(reportDir, 'report.json'), JSON.stringify(report, null, 2));
console.log(`\n[${new Date().toISOString()}] DONE → ${path.join(reportDir, 'report.json')} (ok=${report.ok}, errors=${report.errors.length})`);
