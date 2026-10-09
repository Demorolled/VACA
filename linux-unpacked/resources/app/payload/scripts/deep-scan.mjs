#!/usr/bin/env node
/**
 * Deep static scan of the VACA codebase for problem classes that tsc/tests
 * don't catch. Categories:
 *   fence      — markdown ``` fences inside source files
 *   artifact   — prompt scaffolding echoed into source ("REAL FILE CONTENT", ...)
 *   stub       — placeholder/TODO bodies
 *   dup-base   — two source files with the same basename (import collision risk)
 *   py-syntax  — Python files that fail py_compile
 *   go-fmt     — Go files that fail gofmt
 *   secret     — hardcoded secret-looking literals in client code
 *   console    — console.log counts (quality signal only)
 * Usage: node scripts/deep-scan.mjs
 */
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const SKIP = new Set(['node_modules', '.git', 'dist', 'unsloth_compiled_cache', 'huggingface_tokenizers_cache', 'backend/exports', 'out', 'models', 'dataset', 'probes', 'public_html', '.cache', 'checkpoint-288', 'adapter', 'adapter_round7']);

const findings = { fence: [], artifact: [], stub: [], dupBase: [], secret: [], console: [] };
const allFiles = [];

function walk(dir) {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue;
    const p = path.join(dir, name);
    let st; try { st = statSync(p); } catch { continue; }
    if (st.isDirectory()) walk(p);
    else if (/\.(ts|tsx|js|mjs|py|go|css|html)$/.test(name)) allFiles.push(p);
  }
}
walk(ROOT);

const FENCE_RE = /^\s*```/m;
const ARTIFACT_RE = /REAL FILE CONTENT|injected by the platform|generated for the ".*" node|entry point for the node/i;
const STUB_RE = /(not implemented|TODO:?\s*implement|coming soon|placeholder for|FIXME:?\s*implement|unimplemented)/i;
const SECRET_RE = /(DATABASE_URL\s*[:=]|SECRET_KEY\s*[:=]|API_KEY\s*[:=]|yourApiKeyHere|yourSecretKeyHere|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})/;

const srcExt = /\.(ts|tsx|js|mjs|py|go)$/;
for (const f of allFiles) {
  let code; try { code = readFileSync(f, 'utf-8'); } catch { continue; }
  const rel = path.relative(ROOT, f);

  if (srcExt.test(f)) {
    if (FENCE_RE.test(code)) findings.fence.push(rel);
    if (ARTIFACT_RE.test(code)) findings.artifact.push(rel);
    if (STUB_RE.test(code)) findings.stub.push(rel);
    if (SECRET_RE.test(code)) findings.secret.push(rel);
  }
  if (/\.(ts|tsx|js|mjs)$/.test(f)) {
    const n = (code.match(/console\.(log|debug)/g) || []).length;
    if (n > 5) findings.console.push(`${rel} (${n})`);
  }
  const base = path.basename(f);
  if (srcExt.test(f)) {
    const dup = allFiles.filter((g) => path.basename(g) === base && g !== f);
    if (dup.length && !findings.dupBase.some((d) => d.includes(base))) {
      findings.dupBase.push(`${base} → ${dup.length + 1} files`);
    }
  }
}

console.log('── Fences (markdown ``` in source) ──');
findings.fence.length ? findings.fence.forEach((f) => console.log('  ', f)) : console.log('   none');
console.log('── Prompt artifacts ──');
findings.artifact.length ? findings.artifact.forEach((f) => console.log('  ', f)) : console.log('   none');
console.log('── Stub/placeholder markers ──');
findings.stub.length ? findings.stub.forEach((f) => console.log('  ', f)) : console.log('   none');
console.log('── Secret-shaped literals ──');
findings.secret.length ? findings.secret.forEach((f) => console.log('  ', f)) : console.log('   none');
console.log('── Duplicate basenames (import collision risk) ──');
findings.dupBase.length ? findings.dupBase.forEach((f) => console.log('  ', f)) : console.log('   none');
console.log('── Heavy console.log files (signal) ──');
findings.console.slice(0, 30).forEach((f) => console.log('  ', f));

// Python syntax check
console.log('── Python syntax (py_compile) ──');
const pyFiles = allFiles.filter((f) => f.endsWith('.py'));
let pyBad = 0;
for (const f of pyFiles) {
  try { execSync(`python3 -m py_compile "${f}"`, { stdio: 'pipe' }); }
  catch { pyBad++; console.log('  ✗', path.relative(ROOT, f)); }
}
pyBad === 0 && console.log(`   all ${pyFiles.length} OK`);

// Go fmt check
console.log('── Go fmt ──');
const goFiles = allFiles.filter((f) => f.endsWith('.go'));
let goBad = 0;
for (const f of goFiles) {
  try { execSync(`gofmt -e "${f}" >/dev/null`, { stdio: 'pipe' }); }
  catch { goBad++; console.log('  ✗', path.relative(ROOT, f)); }
}
goBad === 0 && console.log(`   all ${goFiles.length} OK`);

console.log(`\nScanned ${allFiles.length} files.`);
