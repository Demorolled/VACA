import { readFileSync } from 'node:fs';

const s = readFileSync('projects/claims-audit.html', 'utf8');
const m = s.match(/<script>([\s\S]*)<\/script>/);
if (!m) { console.log('NO SCRIPT FOUND'); process.exit(1); }
try { new Function(m[1]); console.log('JS parses OK'); }
catch (e) { console.log('JS ERROR:', e.message); process.exit(1); }

const stale = s.includes("'Blueprint integrity'");
console.log(stale ? 'STALE SUGGESTION STILL PRESENT' : 'stale suggestion removed OK');

// sanity: the probe-side integrity check lines still exist
for (const probe of ['dangleMod', 'dangleEdge']) {
  if (!s.includes(probe)) { console.log('MISSING probe check:', probe); process.exit(1); }
}
console.log('probe integrity checks present (dangleMod + dangleEdge)');
