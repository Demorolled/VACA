// TEMPORARY batch runner — delete after use.
// Generates single-file GUI apps through the REAL pipeline (planProject +
// generatePlanFiles), then runs the same runtime smoke engine used by the sweep.
// Usage (from backend/): npx tsx ../scripts/_genbatch.tmp.mts <armLabel>
import fs from 'fs';
import path from 'path';
import { planProject, generatePlanFiles } from '../backend/src/routes/codePlanner.js';
import { runRuntimeSmokeTest } from '../backend/src/sandbox/runtimeSmokeTest.js';

const arm = process.argv[2] || 'A';

const TASKS = [
  'Build a tic-tac-toe game in a single HTML file, human vs a simple AI.',
  'Build a checkers game in a single HTML file where a human plays against a simple AI.',
  'Build an image gallery app in a single HTML file with a lightbox and tag filters.',
  'Build a temperature converter in a single HTML file supporting Celsius, Fahrenheit and Kelvin.',
  'Build a sudoku solver and player in a single HTML file.',
  'Build a memory match card game in a single HTML file with a move counter and a timer.',
  'Build a quiz app in a single HTML file with score tracking and a results screen.',
  'Build an expense tracker in a single HTML file with categories, a running total and localStorage persistence.',
];

const outRoot = path.resolve('../runs/genbatch', arm);
fs.mkdirSync(outRoot, { recursive: true });
const results: any[] = [];
const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 48);

for (let i = 0; i < TASKS.length; i++) {
  const task = TASKS[i];
  const t0 = Date.now();
  let gen: any = null;
  let err: string | null = null;
  try {
    const p = await planProject(task);
    gen = await generatePlanFiles(task, p?.plan ?? null, undefined, 300_000);
  } catch (e) {
    err = e instanceof Error ? e.message : String(e);
  }

  const slugDir = path.join(outRoot, slugify(task));
  fs.mkdirSync(slugDir, { recursive: true });
  const files: Array<{ fileName: string; code: string }> = [];
  for (const f of gen?.files ?? []) {
    const base = String(f.path).split('/').pop() || 'file';
    fs.writeFileSync(path.join(slugDir, base), f.content, 'utf-8');
    files.push({ fileName: base, code: f.content });
  }

  let smoke: any = null;
  try {
    smoke = await runRuntimeSmokeTest(files);
  } catch (e) {
    smoke = { available: false, reason: String(e) };
  }

  const status = smoke?.available ? (smoke.success ? 'PASS' : 'FAIL') : 'UNAVAIL';
  const secs = Math.round((Date.now() - t0) / 1000);
  console.log(`[${arm}] ${i + 1}/${TASKS.length} ${status} mode=${gen?.mode ?? '-'} ${secs}s :: ${task.slice(0, 52)}`);
  if (smoke?.available && !smoke.success) {
    for (const c of smoke.checks.filter((c: any) => c.status === 'fail')) console.log(`        ❌ ${c.name} — ${String(c.detail).slice(0, 130)}`);
  }
  results.push({ task, files: files.map((f) => f.fileName), mode: gen?.mode, exportDir: gen?.exportDir, err, secs, smoke });
  fs.writeFileSync(path.join(outRoot, 'results.json'), JSON.stringify(results, null, 2));
}

const ok = results.filter((r) => r.smoke?.available);
console.log(`\n[${arm}] DONE — apps ${ok.length}, PASS ${ok.filter((r) => r.smoke.success).length}, FAIL ${ok.filter((r) => r.smoke.available && !r.smoke.success).length}`);
process.exit(0);
