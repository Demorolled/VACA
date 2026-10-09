#!/usr/bin/env node
/**
 * vaca-lang-matrix-report — turn a `dry-run-languages.ts` run into a plain-text
 * PASS/FAIL report, verified independently of VACA's own gate.
 *
 * VACA's language gate is run *inside* the pipeline that produced the code, so a
 * bug in the gate can vouch for a broken build (the historical "tsCompileClean:
 * true while 8/9 files failed" false positive). This script re-checks every
 * generated case itself, with the real toolchain, on a COPY of the output:
 *
 *   python   python3 -m py_compile, then a no-input smoke run
 *   go       `go build ./...` against a generated go.mod
 *   rust     rustc (UNVERIFIED when the toolchain is not installed)
 *   c        gcc -fsyntax-only -std=c11
 *   cpp      g++ -fsyntax-only -std=c++17
 *   java     javac -d <tmp>
 *   csharp   csc/dotnet (UNVERIFIED when not installed)
 *   swift    swiftc -typecheck
 *   kotlin   kotlinc <files> -d <tmp>.jar
 *   php      php -l per file
 *   ruby     ruby -c per file
 *   js       node --check per file
 *
 * "Unverified" is never reported as clean — a missing toolchain is called out
 * explicitly rather than silently passing.
 *
 * Usage:
 *   node scripts/vaca-lang-matrix-report.mjs --out out/vaca-lang-matrix/tier1
 *        [--txt PATH]        write the report somewhere other than <out>/BUILD-REPORT.txt
 *        [--keep]            leave the temp verification workspaces in place
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync, cpSync, rmSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function argValue(flag) {
  const i = process.argv.indexOf(flag);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

const OUT = path.resolve(ROOT, argValue('--out') || 'out/vaca-lang-matrix/tier1');
const TXT = path.resolve(ROOT, argValue('--txt') || path.join(OUT, 'BUILD-REPORT.txt'));
const KEEP = process.argv.includes('--keep');
// Languages the tier is SUPPOSED to cover. Any that produced no row are reported
// as NOT RUN rather than quietly missing, so a partial sweep can never be read
// as a complete one.
const EXPECT = (argValue('--expect') || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);

// Toolchains that install OUTSIDE PATH are still real toolchains — the backend's
// own gate searches these (see backend/src/sandbox/nonTsCompileGate.ts
// EXTRA_BIN_DIRS), so this report must search them too or it would declare a
// present toolchain "unverified".
const EXTRA_BIN_DIRS = [
  path.join(os.homedir(), '.cargo', 'bin'),
  path.join(os.homedir(), '.dotnet'),
  path.join(os.homedir(), '.local', 'share', 'swiftly', 'bin'),
  path.join(os.homedir(), '.local', 'bin'),
  '/usr/local/bin',
  '/snap/bin',
];

/** Absolute path to the first executable found across PATH + EXTRA_BIN_DIRS. */
function which(bins) {
  const dirs = [...(process.env.PATH || '').split(path.delimiter), ...EXTRA_BIN_DIRS].filter(Boolean);
  for (const bin of bins) {
    for (const dir of dirs) {
      const candidate = path.join(dir, bin);
      try {
        if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
      } catch { /* unreadable dir — keep looking */ }
    }
  }
  return null;
}

const TOOLS = {
  python: which(['python3']),
  go: which(['go']),
  rust: which(['rustc']),
  c: which(['gcc']),
  cpp: which(['g++']),
  java: which(['javac']),
  csharp: which(['csc', 'mcs']),
  dotnet: which(['dotnet']),
  swift: which(['swiftc']),
  kotlin: which(['kotlinc']),
  php: which(['php']),
  ruby: which(['ruby']),
  js: which(['node']),
};

const summaryPath = path.join(OUT, '_summary.json');
if (!existsSync(summaryPath)) {
  console.error(`No _summary.json in ${OUT} — run the dry-run harness first:\n` +
    `  (cd backend && node ../node_modules/.bin/tsx src/scripts/dry-run-languages.ts --out ${path.relative(path.join(ROOT, 'backend'), OUT)})`);
  process.exit(1);
}

/** Run a command, never throwing. Returns exit code + trimmed output. */
function run(cmd, args, opts = {}) {
  const res = spawnSync(cmd, args, {
    encoding: 'utf-8',
    timeout: opts.timeoutMs ?? 120_000,
    input: opts.input ?? '',
    cwd: opts.cwd,
    maxBuffer: 8 * 1024 * 1024,
  });
  if (res.error) {
    const e = res.error;
    if (e.code === 'ENOENT') return { code: null, missing: true, out: '', err: `${cmd} not found` };
    return { code: null, missing: false, out: res.stdout || '', err: String(e.message || e) };
  }
  return { code: res.status, missing: false, out: (res.stdout || '').trim(), err: (res.stderr || '').trim() };
}

/** Short human label for a resolved tool path — the last path segment. */
const toolName = (p) => (p ? path.basename(p) : '(missing)');

/** All files under dir, relative paths, skipping VACA's own metadata files. */
function listFiles(dir) {
  const out = [];
  const walk = (d) => {
    for (const name of readdirSync(d)) {
      const abs = path.join(d, name);
      if (statSync(abs).isDirectory()) walk(abs);
      else out.push(path.relative(dir, abs));
    }
  };
  walk(dir);
  return out.sort();
}

const firstLines = (s, n = 3) => s.split('\n').filter(Boolean).slice(0, n).join(' | ').slice(0, 300);

// ─── Independent verification, one function per language ────────────────────

function verify(language, workDir, files) {
  const pick = (re) => files.filter((f) => re.test(f));
  const note = (status, detail) => ({ status, detail });

  switch (language) {
    case 'python': {
      const py = pick(/\.py$/i);
      if (!py.length) return note('FAIL', 'no .py files generated');
      if (!TOOLS.python) return note('UNVERIFIED', 'python3 not installed');
      const bad = [];
      for (const f of py) {
        const r = run(TOOLS.python, ['-m', 'py_compile', f], { cwd: workDir });
        if (r.code !== 0) bad.push(`${f}: ${firstLines(r.err || r.out)}`);
      }
      if (bad.length) return note('FAIL', `py_compile: ${bad.join(' ;; ')}`);
      const entry = files.find((f) => /(__main__|main|cli)\.py$/i.test(f)) || py[0];
      const smoke = run(TOOLS.python, [entry], { cwd: workDir, timeoutMs: 10_000 });
      return note('PASS', `py_compile OK (${py.length} file${py.length > 1 ? 's' : ''}); smoke run "${entry}" exit=${smoke.code}`);
    }
    case 'go': {
      const go = pick(/\.go$/i);
      if (!go.length) return note('FAIL', 'no .go files generated');
      if (!TOOLS.go) return note('UNVERIFIED', 'go not installed');
      writeFileSync(path.join(workDir, 'go.mod'), `module vaca-verify\n\ngo 1.21\n`, 'utf-8');
      const b = run(TOOLS.go, ['build', './...'], { cwd: workDir, timeoutMs: 180_000 });
      if (b.code !== 0) return note('FAIL', `go build: ${firstLines(b.err || b.out)}`);
      return note('PASS', `go build ./... OK (${go.length} file${go.length > 1 ? 's' : ''})`);
    }
    case 'rust': {
      const rs = pick(/\.rs$/i);
      if (!rs.length) return note('FAIL', 'no .rs files generated');
      if (!TOOLS.rust) return note('UNVERIFIED', 'rustc not installed');
      const entry = files.find((f) => /main\.rs$/i.test(f)) || rs[0];
      const r = run(TOOLS.rust, ['--edition', '2021', '--emit=metadata', '--crate-type', 'lib', entry], { cwd: workDir, timeoutMs: 180_000 });
      if (r.code !== 0) return note('FAIL', `rustc: ${firstLines(r.err || r.out)}`);
      return note('PASS', `rustc metadata build OK (${rs.length} file${rs.length > 1 ? 's' : ''})`);
    }
    case 'c': {
      const cs = pick(/\.c$/i);
      if (!cs.length) return note('FAIL', 'no .c files generated');
      if (!TOOLS.c) return note('UNVERIFIED', 'gcc not installed');
      const bad = [];
      for (const f of cs) {
        const r = run(TOOLS.c, ['-fsyntax-only', '-std=c11', '-I', '.', f], { cwd: workDir, timeoutMs: 120_000 });
        if (r.code !== 0) bad.push(`${f}: ${firstLines(r.err || r.out)}`);
      }
      return bad.length ? note('FAIL', `gcc -fsyntax-only: ${bad.join(' ;; ')}`)
        : note('PASS', `gcc -fsyntax-only OK (${cs.length} file${cs.length > 1 ? 's' : ''})`);
    }
    case 'cpp': {
      const cpp = pick(/\.(cpp|cc|cxx)$/i);
      if (!cpp.length) return note('FAIL', 'no .cpp files generated');
      if (!TOOLS.cpp) return note('UNVERIFIED', 'g++ not installed');
      const bad = [];
      for (const f of cpp) {
        const r = run(TOOLS.cpp, ['-fsyntax-only', '-std=c++17', '-I', '.', f], { cwd: workDir, timeoutMs: 120_000 });
        if (r.code !== 0) bad.push(`${f}: ${firstLines(r.err || r.out)}`);
      }
      return bad.length ? note('FAIL', `g++ -fsyntax-only: ${bad.join(' ;; ')}`)
        : note('PASS', `g++ -fsyntax-only OK (${cpp.length} file${cpp.length > 1 ? 's' : ''})`);
    }
    case 'java': {
      const jv = pick(/\.java$/i);
      if (!jv.length) return note('FAIL', 'no .java files generated');
      if (!TOOLS.java) return note('UNVERIFIED', 'javac not installed');
      const classes = path.join(workDir, '.classes');
      mkdirSync(classes, { recursive: true });
      const r = run(TOOLS.java, ['-d', classes, ...jv], { cwd: workDir, timeoutMs: 180_000 });
      if (r.code !== 0) return note('FAIL', `javac: ${firstLines(r.err || r.out)}`);
      return note('PASS', `javac OK (${jv.length} file${jv.length > 1 ? 's' : ''})`);
    }
    case 'csharp': {
      const cs = pick(/\.cs$/i);
      if (!cs.length) return note('FAIL', 'no .cs files generated');
      // `csc`/`mcs` can compile a bare file list; `dotnet` cannot without a
      // project file, so an SDK-only box stays honestly UNVERIFIED here.
      if (!TOOLS.csharp) {
        return note('UNVERIFIED', TOOLS.dotnet
          ? `only the dotnet SDK is present (${toolName(TOOLS.dotnet)}) — it needs a project file, so a bare-file check is impossible`
          : 'csc/mcs/dotnet not installed');
      }
      const r = run(TOOLS.csharp, ['-target:library', '-out:' + path.join(workDir, 'out.dll'), ...cs], { cwd: workDir, timeoutMs: 240_000 });
      if (r.code !== 0) return note('FAIL', `${toolName(TOOLS.csharp)}: ${firstLines(r.err || r.out)}`);
      return note('PASS', `${toolName(TOOLS.csharp)} OK (${cs.length} file${cs.length > 1 ? 's' : ''})`);
    }
    case 'swift': {
      const sw = pick(/\.swift$/i);
      if (!sw.length) return note('FAIL', 'no .swift files generated');
      if (!TOOLS.swift) return note('UNVERIFIED', 'swiftc not installed');
      const r = run(TOOLS.swift, ['-typecheck', ...sw], { cwd: workDir, timeoutMs: 240_000 });
      if (r.code !== 0) return note('FAIL', `swiftc -typecheck: ${firstLines(r.err || r.out)}`);
      return note('PASS', `swiftc -typecheck OK (${sw.length} file${sw.length > 1 ? 's' : ''})`);
    }
    case 'kotlin': {
      const kt = pick(/\.kt$/i);
      if (!kt.length) return note('FAIL', 'no .kt files generated');
      if (!TOOLS.kotlin) return note('UNVERIFIED', 'kotlinc not installed');
      const jar = path.join(workDir, 'out.jar');
      const r = run(TOOLS.kotlin, [...kt, '-d', jar], { cwd: workDir, timeoutMs: 420_000 });
      if (r.code !== 0) return note('FAIL', `kotlinc: ${firstLines(r.err || r.out)}`);
      return note('PASS', `kotlinc OK (${kt.length} file${kt.length > 1 ? 's' : ''})`);
    }
    case 'php': {
      const php = pick(/\.php$/i);
      if (!php.length) return note('FAIL', 'no .php files generated');
      if (!TOOLS.php) return note('UNVERIFIED', 'php not installed');
      const bad = [];
      for (const f of php) {
        const r = run(TOOLS.php, ['-l', f], { cwd: workDir });
        if (r.code !== 0) bad.push(`${f}: ${firstLines(r.err || r.out)}`);
      }
      return bad.length ? note('FAIL', `php -l: ${bad.join(' ;; ')}`)
        : note('PASS', `php -l OK (${php.length} file${php.length > 1 ? 's' : ''})`);
    }
    case 'ruby': {
      const rb = pick(/\.rb$/i);
      if (!rb.length) return note('FAIL', 'no .rb files generated');
      if (!TOOLS.ruby) return note('UNVERIFIED', 'ruby not installed');
      const bad = [];
      for (const f of rb) {
        const r = run(TOOLS.ruby, ['-c', f], { cwd: workDir });
        if (r.code !== 0) bad.push(`${f}: ${firstLines(r.err || r.out)}`);
      }
      return bad.length ? note('FAIL', `ruby -c: ${bad.join(' ;; ')}`)
        : note('PASS', `ruby -c OK (${rb.length} file${rb.length > 1 ? 's' : ''})`);
    }
    case 'javascript': {
      const js = pick(/\.(js|mjs|cjs)$/i);
      if (!js.length) return note('FAIL', 'no .js files generated');
      if (!TOOLS.js) return note('UNVERIFIED', 'node not installed');
      const bad = [];
      for (const f of js) {
        const r = run(TOOLS.js, ['--check', f], { cwd: workDir });
        if (r.code !== 0) bad.push(`${f}: ${firstLines(r.err || r.out)}`);
      }
      return bad.length ? note('FAIL', `node --check: ${bad.join(' ;; ')}`)
        : note('PASS', `node --check OK (${js.length} file${js.length > 1 ? 's' : ''})`);
    }
    default:
      return note('UNVERIFIED', `no independent check for "${language}"`);
  }
}

// ─── Gather + verify ────────────────────────────────────────────────────────

const rows = JSON.parse(readFileSync(summaryPath, 'utf-8'));
const TIER_LABEL = rows[0]?.tier || argValue('--tier') || '(unknown)';
const workRoot = path.join(os.tmpdir(), `vaca-verify-${process.pid}`);
mkdirSync(workRoot, { recursive: true });

const byLanguage = new Map(rows.map((r) => [String(r.language).toLowerCase(), r]));
const languages = EXPECT.length ? EXPECT : rows.map((r) => r.language);

const results = [];
for (const language of languages) {
  const row = byLanguage.get(String(language).toLowerCase());
  if (!row) {
    results.push({
      language,
      tier: TIER_LABEL,
      purpose: '(no run recorded)',
      ok: false,
      error: null,
      dir: '(not run)',
      files: [],
      paths: [],
      gateClean: null,
      gateErrors: [],
      stubFailures: [],
      ms: 0,
      vacaGate: 'n/a',
      independent: { status: 'N/A', detail: 'NOT ATTEMPTED in this pass' },
      verdict: 'NOT RUN',
    });
    continue;
  }
  const srcDir = row.dir;
  const rec = { ...row, independent: null, verdict: 'FAIL', files: [] };

  if (!row.ok || row.error) {
    rec.independent = { status: 'N/A', detail: row.error ? `pipeline error: ${row.error}` : 'pipeline reported failure' };
    rec.verdict = 'FAIL';
    results.push(rec);
    continue;
  }

  if (!srcDir || !existsSync(srcDir)) {
    rec.independent = { status: 'N/A', detail: `generated dir missing: ${srcDir}` };
    results.push(rec);
    continue;
  }

  const workDir = path.join(workRoot, `${row.tier || 'small'}-${row.language}`);
  cpSync(srcDir, workDir, { recursive: true });
  rec.files = listFiles(workDir).filter((f) => !f.startsWith('_') && !f.endsWith('_meta.json'));

  try {
    rec.independent = verify(row.language, workDir, rec.files);
  } catch (e) {
    rec.independent = { status: 'UNVERIFIED', detail: `check crashed: ${e?.message || e}` };
  }

  const vacaGate = row.gateClean === true ? 'PASS' : row.gateClean === false ? 'FAIL' : 'n/a';
  rec.vacaGate = vacaGate;
  rec.verdict = rec.independent.status === 'PASS' ? 'PASS'
    : rec.independent.status === 'FAIL' ? 'FAIL'
      : 'UNVERIFIED';
  results.push(rec);
}

if (!KEEP) rmSync(workRoot, { recursive: true, force: true });

// ─── Text report ────────────────────────────────────────────────────────────

const counts = { PASS: 0, FAIL: 0, UNVERIFIED: 0, 'NOT RUN': 0 };
for (const r of results) counts[r.verdict] = (counts[r.verdict] || 0) + 1;

const pad = (s, n) => String(s).padEnd(n).slice(0, n);
const L = [];
L.push('VACA LANGUAGE BUILD MATRIX — PASS/FAIL REPORT');
L.push('='.repeat(78));
L.push(`generated : ${new Date().toISOString()}`);
L.push(`tier      : ${TIER_LABEL}`);
L.push(`source    : ${OUT}`);
L.push(`model     : see backend/llm-config.json (the live VACA planner model)`);
L.push('');
L.push(`PASS ${counts.PASS}   FAIL ${counts.FAIL}   UNVERIFIED ${counts.UNVERIFIED}   NOT RUN ${counts['NOT RUN']}   (of ${results.length})`);
L.push('');
L.push('VERDICT KEY');
L.push('  PASS       — pipeline produced files AND the real toolchain accepted them');
L.push('  FAIL       — pipeline failed, or the real toolchain rejected the output');
L.push('  UNVERIFIED — no toolchain on this box can vouch (never counted as a pass)');
L.push('  NOT RUN    — this tier has not been built for that language yet');
L.push('');
L.push(`${pad('LANGUAGE', 11)}${pad('VACA GATE', 11)}${pad('FILES', 6)}${pad('VERDICT', 11)}REAL-TOOLCHAIN CHECK`);
L.push('-'.repeat(78));
for (const r of results) {
  L.push(`${pad(r.language, 11)}${pad(r.vacaGate || 'n/a', 11)}${pad(r.files.length, 6)}${pad(r.verdict, 11)}${r.independent?.detail || ''}`);
}
// Gate vs independent verdict — a disagreement is the interesting signal: the
// gate passing while the real toolchain fails is a false-positive, the gate
// failing while the toolchain accepts the code is a false-negative.
const disagreements = results.filter((r) => r.vacaGate && r.independent &&
  r.independent.status !== 'N/A' &&
  ((r.vacaGate === 'PASS' && r.independent.status !== 'PASS') ||
    (r.vacaGate === 'FAIL' && r.independent.status === 'PASS')));
L.push('');
L.push('GATE vs INDEPENDENT CHECK — DISAGREEMENTS');
L.push('-'.repeat(78));
if (!disagreements.length) {
  L.push('  none — VACA\'s own gate agreed with the real toolchain everywhere it ran');
} else {
  for (const r of disagreements) {
    const kind = r.vacaGate === 'PASS' ? 'FALSE POSITIVE (gate passed broken code)' : 'FALSE NEGATIVE (gate failed code the toolchain accepts)';
    L.push(`  ${r.language}: VACA gate=${r.vacaGate} but independent=${r.independent.status} — ${kind}`);
    L.push(`    ${r.independent.detail}`);
  }
}
L.push('');
L.push('PER-CASE DETAIL');
L.push('-'.repeat(78));
for (const r of results) {
  L.push(`# ${r.language}  [${r.verdict}]`);
  L.push(`  purpose    : ${r.purpose}`);
  L.push(`  files      : ${r.files.length ? r.files.join(', ') : '(none)'}`);
  L.push(`  VACA gate  : ${r.vacaGate || 'n/a'}${r.gateErrors?.length ? ' — ' + r.gateErrors.slice(0, 3).join(' ;; ') : ''}`);
  L.push(`  planned    : ${r.paths?.join(', ') || '(none)'}${r.plannedLanguage ? `  (detected: ${r.plannedLanguage})` : ''}`);
  L.push(`  stub flags : ${r.stubFailures?.length ? r.stubFailures.slice(0, 3).join(' ;; ') : 'none'}`);
  L.push(`  build time : ${r.ms} ms   mode=${r.mode ?? 'n/a'}  repairRounds=${r.repairRounds ?? 'n/a'}`);
  L.push(`  output dir : ${r.dir}`);
  L.push(`  independent: ${r.independent?.status} — ${r.independent?.detail || ''}`);
  L.push('');
}
L.push('NOTES / LIMITATIONS');
L.push('  • Verification compiles a COPY of each exported case in /tmp; the generated');
L.push('    trees under the source dir are left untouched.');
L.push('  • A missing toolchain yields UNVERIFIED, not PASS — install with');
L.push('    scripts/install-toolchains.sh to turn those into real verdicts.');
L.push('  • This checks that the code COMPILES. It is not a functional/behavioural test:');
L.push('    only the interpreted languages here get a no-input smoke run.');

const text = L.join('\n') + '\n';
mkdirSync(path.dirname(TXT), { recursive: true });
writeFileSync(TXT, text, 'utf-8');
console.log(text);
console.log(`\nReport written → ${TXT}`);
