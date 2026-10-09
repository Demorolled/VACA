#!/usr/bin/env node
/**
 * probe-gates — re-run the non-TS compile gates against a SAVED export dir.
 *
 * Why: when the language matrix reports FAIL, we cannot tell from the JSONL
 * whether the gate is wrong (staging/routing/include-path bug) or whether the
 * generator really emitted broken code. The export directory is still on disk,
 * so this replays the gate over exactly those files, independently of the app.
 *
 *   node scripts/probe-gates.mjs <exportDir> [<exportDir> ...]
 *   node scripts/probe-gates.mjs --gate <path/to/nonTsCompileGate.js> <exportDir> ...
 *
 * Also useful for regression: run it against an OLD export after changing the
 * gate to prove the change flips the verdict.
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const DEFAULT_GATE = 'backend/dist/sandbox/nonTsCompileGate.js';

const args = process.argv.slice(2);
let gatePath = DEFAULT_GATE;
let moduleName = null;
const dirs = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--gate') { gatePath = args[++i]; continue; }
  // Go is the one gate whose verdict depends on the module path: the gate
  // writes `module <name>` into go.mod, so replaying with the wrong name makes
  // a self-import look unresolvable even when the generated code is fine.
  if (args[i] === '--module') { moduleName = args[++i]; continue; }
  dirs.push(args[i]);
}
if (!dirs.length) {
  console.error('usage: node scripts/probe-gates.mjs [--gate <gate.js>] <exportDir> ...');
  process.exit(2);
}

const gate = await import(pathToFileURL(path.resolve(gatePath)).href);
const abs = (d) => (path.isAbsolute(d) ? d : path.resolve(process.cwd(), d));

/** Every file under `root` as {relPath, code}, skipping bookkeeping files. */
function readProject(root) {
  const out = [];
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      if (e.name === 'node_modules' || e.name === '.git') continue;
      if (e.name === '_training.json') continue;
      const p = path.join(dir, e.name);
      if (e.isDirectory()) { walk(p); continue; }
      out.push({ relPath: path.relative(root, p), code: fs.readFileSync(p, 'utf8') });
    }
  };
  walk(root);
  return out.sort((a, b) => a.relPath.localeCompare(b.relPath));
}

console.log(`gate: ${gatePath}`);

for (const d of dirs) {
  const root = abs(d);
  const files = readProject(root);
  // The planner labels each file; we only have the bytes. Run unlabelled (the
  // harder case: .h resolves to null and must be re-routed) and labelled.
  const labelled = files.map((f) => ({
    ...f,
    language: gate.resolveGateLanguage(undefined, f.relPath) || undefined,
  }));

  for (const [label, set] of [['unlabelled', files], ['extension-labelled', labelled]]) {
    const gates = await gate.runNonTsProjectGates(set, moduleName || path.basename(root), {});
    const clean = gate.allLanguageGatesClean(gates);
    console.log(`\n=== ${root}`);
    console.log(`  [${label}] files=${files.length} clean=${clean}`);
    for (const g of gates) {
      console.log(`    ${g.language}: ${g.clean ? 'clean' : 'FAIL'}`);
      for (const err of g.errors) {
        console.log('      ' + String(err).split('\n').slice(0, 6).join('\n      '));
      }
    }
  }
}
