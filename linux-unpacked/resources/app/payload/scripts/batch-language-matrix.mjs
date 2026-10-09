#!/usr/bin/env node
/**
 * batch-language-matrix.mjs — drive VACA's interactive build path across a
 * matrix of simple apps in many languages, and record an HONEST verdict for
 * each one.
 *
 * For every request it calls POST /api/reason/interactive (plan → generate →
 * write → gates, in a single call), then records:
 *   · the language(s) actually produced (from the written file extensions)
 *   · whether the requested language was honoured
 *   · the compile/tsc verdict, the whole-project language gates, stub failures
 *   · the human-readable summary the backend produced
 *
 * Results are appended to a JSONL checkpoint after every request, so a run is
 * resumable and a long batch can be inspected while it is still going.
 *
 * Usage:
 *   node scripts/batch-language-matrix.mjs [--limit N] [--only lang1,lang2]
 *                                          [--base-url http://127.0.0.1:3001]
 *                                          [--out DIR] [--timeout-ms MS]
 *                                          [--set small|hard] [--scale S]
 *                                          [--rerun FILE]
 *
 * `--rerun FILE` re-queues ONLY the rows of a previous JSONL whose failure was
 * infrastructure-side (network drop / HTTP 5xx), not a VACA verdict — used to
 * recover a batch that was poisoned by the local LLM service restarting mid-run.
 */
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));

// ── args ────────────────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
const arg = (name, dflt) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : dflt;
};
const BASE_URL = arg('base-url', 'http://127.0.0.1:3001').replace(/\/+$/, '');
const OUT_DIR = arg('out', path.join(HERE, 'batch-results'));
const LIMIT = Number(arg('limit', '0')) || 0;
const ONLY = (arg('only', '') || '').split(',').map(s => s.trim()).filter(Boolean);
const TIMEOUT_MS = Number(arg('timeout-ms', '900000')) || 900000;
const SCALE = arg('scale', 'small');
const SET = arg('set', 'small');
const RERUN = arg('rerun', '');

// A row whose failure came from the transport (backend/LLM unreachable) is not
// a verdict about VACA, so it must not count as one — and it is exactly what
// `--rerun` recovers.
const isInfraFailure = (r) =>
  r.verdict === 'FAIL' &&
  /network:|HTTP 5\d\d|Connection error|fetch failed|client timeout/i.test(r.reason || '');

// ── the matrix ──────────────────────────────────────────────────────────────
// Every request names its language explicitly and describes a CLI/console tool:
// the language keyword is what the plan stage keys off, and a CLI framing keeps
// a browser/UI heuristic from silently re-routing the build to TypeScript.
// ── the HARD matrix ──────────────────────────────────────────────────────────
// Harder than REQUESTS on purpose: every prompt asks for MULTIPLE files and for
// state that must round-trip (JSON on disk), a data structure (linked list /
// priority queue), or a real parser — the things single-file snippets never
// exercise. Ordered one-per-language first so `--limit 13` still sweeps every
// language instead of only the first few. Still stdlib-only so a failure is
// VACA's, not a missing dependency.
const HARD_REQUESTS = [
  { lang: 'python',     name: 'task-manager',      request: 'a multi-file Python CLI task manager with add, list, done and remove subcommands that persists tasks to a JSON file and supports priorities' },
  { lang: 'go',         name: 'note-manager',      request: 'a multi-file Go CLI note manager with add, list and search subcommands that stores notes in a JSON file' },
  { lang: 'rust',       name: 'top-words',         request: 'a multi-module Rust CLI tool that reads a text file and prints the top 10 most frequent words with their counts' },
  { lang: 'java',       name: 'task-manager',      request: 'a multi-class Java CLI task manager with add, list and complete subcommands backed by a text file' },
  { lang: 'csharp',     name: 'contact-book',      request: 'a multi-class C# CLI contact manager with add, search and list subcommands persisted to a JSON file' },
  { lang: 'swift',      name: 'expr-calc',         request: 'a Swift CLI calculator that parses and evaluates arithmetic expressions with + - * / and parentheses' },
  { lang: 'kotlin',     name: 'task-manager',      request: 'a multi-file Kotlin CLI task manager with add, list and delete subcommands persisted to a JSON file' },
  { lang: 'php',        name: 'task-manager',      request: 'a multi-file PHP CLI task manager with add, list and done subcommands that reads and writes a JSON file' },
  { lang: 'ruby',       name: 'task-manager',      request: 'a multi-file Ruby CLI task manager with add, list and complete subcommands persisted to a JSON file' },
  { lang: 'cpp',        name: 'task-manager',      request: 'a multi-file C++ CLI task manager using a priority queue with add, list and complete commands persisted to a file' },
  { lang: 'c',          name: 'task-manager',      request: 'a multi-file C CLI task manager using a linked list with add, list and remove commands persisted to a text file' },
  { lang: 'typescript', name: 'task-manager',      request: 'a multi-module TypeScript CLI task manager with add, list and done subcommands that persists tasks to a JSON file' },
  { lang: 'javascript', name: 'task-manager',      request: 'a multi-module JavaScript CLI task manager with add, list and done subcommands that persists tasks to a JSON file' },
  // ── second pass: algorithmic / parser stress ──
  { lang: 'python',     name: 'dup-finder',        request: 'a Python CLI that recursively scans a directory and reports duplicate files by content hash' },
  { lang: 'go',         name: 'largest-files',     request: 'a Go command-line tool that walks a directory tree and prints the ten largest files with their sizes' },
  { lang: 'rust',       name: 'rpn-calc',          request: 'a Rust CLI that implements a stack-based reverse Polish notation calculator reading an expression from argv' },
  { lang: 'java',       name: 'csv-stats',         request: 'a Java CLI that reads a CSV file and prints per-column statistics (count, min, max, mean) for numeric columns' },
  { lang: 'csharp',     name: 'expr-parser',       request: 'a C# CLI that implements a bracket-balanced arithmetic expression evaluator with a recursive descent parser' },
  { lang: 'swift',      name: 'word-frequency',    request: 'a Swift CLI that implements a word frequency counter reading from a file' },
  { lang: 'kotlin',     name: 'char-histogram',    request: 'a Kotlin CLI that computes a character frequency histogram of a text file' },
  { lang: 'php',        name: 'dir-listing',       request: 'a PHP CLI that recursively lists directory contents with file sizes' },
  { lang: 'ruby',       name: 'csv-stats',         request: 'a Ruby CLI that parses a CSV file and prints per-column statistics' },
  { lang: 'cpp',        name: 'expr-parser',       request: 'a multi-file C++ CLI that evaluates arithmetic expressions with a recursive descent parser' },
  { lang: 'c',          name: 'char-histogram',    request: 'a C CLI that computes a character frequency histogram of a text file' },
  { lang: 'typescript', name: 'ext-scan',          request: 'a multi-module TypeScript CLI that recursively scans a directory and reports counts by file extension' },
  { lang: 'javascript', name: 'dir-hasher',        request: 'a JavaScript CLI that computes the SHA-256 hash of every file in a directory' },
];

const REQUESTS = [
  { lang: 'python',     name: 'temp-converter',    request: 'a Python CLI tool that converts temperatures between Celsius and Fahrenheit' },
  { lang: 'python',     name: 'word-counter',      request: 'a Python command-line tool that counts the words and lines in a text file' },
  { lang: 'python',     name: 'lowercase-renamer', request: 'a Python script that renames every file in a folder to lowercase' },
  { lang: 'go',         name: 'file-hasher',       request: 'a Go CLI tool that computes the SHA-256 hash of a file' },
  { lang: 'go',         name: 'dir-sizes',         request: 'a Go command-line utility that prints the size of every file in a directory' },
  { lang: 'go',         name: 'json-to-yaml',      request: 'a Go CLI tool that converts a JSON file to YAML' },
  { lang: 'rust',       name: 'char-counter',      request: 'a Rust CLI tool that counts the characters in a string' },
  { lang: 'rust',       name: 'reverse-lines',     request: 'a Rust command-line tool that reverses the lines of a text file' },
  { lang: 'java',       name: 'multiplication',    request: 'a Java CLI tool that prints a multiplication table for a number' },
  { lang: 'java',       name: 'prime-check',       request: 'a Java command-line tool that checks whether a number is prime' },
  { lang: 'csharp',     name: 'dec-to-binary',     request: 'a C# CLI tool that converts a decimal number to binary' },
  { lang: 'csharp',     name: 'reverse-string',    request: 'a C# command-line tool that reverses a string' },
  { lang: 'csharp',     name: 'average-list',      request: 'a C# CLI tool that computes the average of a list of numbers' },
  { lang: 'swift',      name: 'c-to-f',            request: 'a Swift CLI tool that converts Celsius to Fahrenheit' },
  { lang: 'swift',      name: 'vowel-count',       request: 'a Swift command-line tool that counts the vowels in a string' },
  { lang: 'kotlin',     name: 'factorial',         request: 'a Kotlin CLI tool that computes the factorial of a number' },
  { lang: 'kotlin',     name: 'sort-words',        request: 'a Kotlin command-line tool that sorts a list of words alphabetically' },
  { lang: 'php',        name: 'line-count',        request: 'a PHP CLI script that counts the lines in a text file' },
  { lang: 'php',        name: 'currency-format',   request: 'a PHP command-line script that formats a number as currency' },
  { lang: 'php',        name: 'reverse-string',    request: 'a PHP CLI script that reverses a string' },
  { lang: 'ruby',       name: 'fibonacci',         request: 'a Ruby CLI tool that prints the first N Fibonacci numbers' },
  { lang: 'ruby',       name: 'word-count',        request: 'a Ruby command-line tool that counts the words in a string' },
  { lang: 'ruby',       name: 'title-case',        request: 'a Ruby CLI script that converts a string to title case' },
  { lang: 'cpp',        name: 'gcd',               request: 'a C++ CLI tool that computes the greatest common divisor of two numbers' },
  { lang: 'cpp',        name: 'reverse-string',    request: 'a C++ command-line tool that reverses a string' },
  { lang: 'cpp',        name: 'primes-to-n',       request: 'a C++ CLI tool that prints all prime numbers up to N' },
  { lang: 'c',          name: 'char-count',        request: 'a C CLI tool that counts the characters in a string' },
  { lang: 'c',          name: 'to-hex',            request: 'a C command-line tool that converts a number to hexadecimal' },
  { lang: 'typescript', name: 'email-validate',    request: 'a TypeScript CLI tool that validates an email address' },
  { lang: 'javascript', name: 'dedupe-lines',      request: 'a JavaScript command-line tool that removes duplicate lines from a text file' },
];

// ── extension → language (for reporting what was ACTUALLY produced) ─────────
const EXT_LANG = {
  '.ts': 'typescript', '.tsx': 'typescript', '.js': 'javascript', '.mjs': 'javascript',
  '.py': 'python', '.go': 'go', '.rs': 'rust', '.java': 'java', '.cs': 'csharp',
  '.swift': 'swift', '.kt': 'kotlin', '.php': 'php', '.rb': 'ruby', '.cpp': 'cpp',
  '.cc': 'cpp', '.cxx': 'cpp', '.hpp': 'cpp', '.h': 'c', '.c': 'c',
  '.html': 'html', '.css': 'css', '.json': 'json', '.md': 'md',
  '.sh': 'sh', '.yml': 'yaml', '.yaml': 'yaml', '.toml': 'toml',
  '.jsonc': 'json', '.csproj': 'csharp', '.gradle': 'kotlin', '.txt': 'txt',
};
const langOf = (p) => EXT_LANG[path.extname(p).toLowerCase()] || null;

// ── request ─────────────────────────────────────────────────────────────────
// POST via node:http, NOT global fetch: Node's fetch (undici) imposes a fixed
// 300_000 ms default bodyTimeout that CANNOT be raised without the undici
// package, and a hard multi-file build legitimately runs longer than that —
// measured live, the 301 s "fetch failed" rows were requests the backend was
// still happily processing. node:http lets --timeout-ms be a real total budget.
function postJson(url, payload, timeoutMs) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const data = Buffer.from(JSON.stringify(payload));
    let done = false;
    const finish = (fn, arg) => { if (!done) { done = true; clearTimeout(timer); fn(arg); } };
    const req = http.request({
      hostname: u.hostname,
      port: u.port || 80,
      path: u.pathname + u.search,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': data.length },
    }, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => finish(resolve, { status: res.statusCode, text: Buffer.concat(chunks).toString('utf8') }));
      res.on('error', (e) => finish(reject, e));
    });
    const timer = setTimeout(() => req.destroy(new Error(`client timeout after ${timeoutMs}ms`)), timeoutMs);
    req.on('error', (e) => finish(reject, e));
    req.write(data);
    req.end();
  });
}

async function build(req) {
  const started = Date.now();
  let httpStatus = 0;
  let body = null;
  let netError = null;
  try {
    const res = await postJson(
      `${BASE_URL}/api/reason/interactive`,
      { request: req.request, scale: SCALE, autoWrite: true },
      TIMEOUT_MS,
    );
    httpStatus = res.status;
    body = res.text ? JSON.parse(res.text) : null;
  } catch (err) {
    netError = String(err?.message || err);
  }

  const ms = Date.now() - started;

  if (netError) {
    return { ...req, verdict: 'FAIL', reason: `network: ${netError}`, httpStatus, ms };
  }
  if (httpStatus !== 200) {
    return { ...req, verdict: 'FAIL', reason: `HTTP ${httpStatus}: ${body?.error || 'unknown'}`, httpStatus, ms, timeout: !!body?.timeout };
  }
  if (body?.step !== 'done') {
    // 'plan' or 'questions' — never reached code generation.
    return {
      ...req, verdict: 'FAIL', httpStatus, ms,
      reason: `stopped at step "${body?.step}": ${body?.error || (body?.needsAnswers ? 'wanted clarifying answers' : 'no plan')}`,
      step: body?.step, summary: body?.reasoning || body?.error || '',
    };
  }

  const files = (body.files || []).map(f => f.path);
  const producedLangs = [...new Set(files.map(langOf).filter(Boolean))];
  const codeLangs = producedLangs.filter(l => !['html', 'css', 'json', 'md', 'yaml', 'toml', 'sh', 'txt'].includes(l));
  const gates = body.languageGates || [];
  // Honour the requested language if EITHER the written extensions say so OR the
  // backend's own language gate resolved it. A valid script need not carry an
  // extension: measured live, a Ruby CLI was planned as `bin/count_words` (a
  // shebang script), so the extension map saw no language at all and the row was
  // wrongly reported as "language not honored (got none, wanted ruby)" while the
  // backend's ruby gate had resolved it correctly from the planned language.
  const gateLangs = [...new Set(
    gates.map(g => g.language).filter(l => l && l !== 'duplicate-definitions'),
  )];
  const languageHonored = codeLangs.includes(req.lang) || gateLangs.includes(req.lang);
  const stubs = body.stubFailures || [];
  const compileStatus = body.compileStatus || 'unknown';
  const tscErrors = body.tscErrors ?? 0;
  const summary = body.summary || '';

  // The summary IS the backend's own shared verdict (buildWriteSummary over
  // deriveBuildVerdict), so classify from it rather than re-deriving.
  const marker = (summary.match(/^([❌✅⚠️])/) || [])[1] || '?';
  let failureKind = null;
  if (/compile error\(s\) remain/.test(summary)) failureKind = 'tsc';
  else if (/compile gate FAILED/.test(summary)) failureKind = 'language';
  else if (/stub\/placeholder/.test(summary)) failureKind = 'stub';
  else if (/smoke check FAILED/.test(summary)) failureKind = 'smoke';
  else if (/compile NOT verified/.test(summary)) failureKind = 'noGate';
  else if (marker === '⚠️' && !/Wrote \d+ file/.test(summary)) failureKind = 'other';

  // A missing local toolchain is an ENVIRONMENT limit, not a VACA defect: the
  // gate is right to refuse to call it clean, but reporting it as a code
  // failure would be dishonest. (nonTsCompileGate: "unverified is never clean".)
  const envBlocked = failureKind === 'language' &&
    /is not installed|gate unavailable|unverified is not clean/i.test(summary);

  const problems = [];
  if (!body.writtenCount) problems.push('no files written');
  if (!languageHonored) problems.push(`language not honored (got ${codeLangs.join('+') || gateLangs.join('+') || 'none'}, wanted ${req.lang})`);
  if (failureKind && !envBlocked && failureKind !== 'noGate') {
    problems.push(`${failureKind}: ${summary.replace(/^[❌⚠️]\s*/, '').slice(0, 180)}`);
  }

  const unverified = !problems.length && (envBlocked || failureKind === 'noGate' || marker !== '✅');
  const verdict = problems.length ? 'FAIL' : unverified ? 'UNVERIFIED' : 'PASS';
  const reason = problems.length
    ? problems.join(' | ')
    : envBlocked
      ? `toolchain not installed locally — ${summary.slice(0, 140)}`
      : failureKind === 'noGate'
        ? `no gate applied — ${summary.slice(0, 140)}`
        : '';

  return {
    ...req,
    verdict,
    reason,
    marker,
    failureKind,
    envBlocked,
    httpStatus, ms,
    step: body.step,
    exportDir: body.exportDir,
    mode: body.mode,
    repairRounds: body.repairRounds ?? 0,
    totalFiles: body.totalFiles ?? files.length,
    writtenCount: body.writtenCount ?? 0,
    files,
    codeLangs,
    gateLangs,
    languageHonored,
    compileStatus,
    tscErrors,
    languageGates: gates.map(g => ({ language: g.language, clean: g.clean, errors: (g.errors || []).slice(0, 3) })),
    stubFailures: stubs.slice(0, 5),
    summary: summary.slice(0, 400),
  };
}

// ── main ────────────────────────────────────────────────────────────────────
fs.mkdirSync(OUT_DIR, { recursive: true });
const runId = new Date().toISOString().replace(/[:.]/g, '-');
const outFile = path.join(OUT_DIR, `matrix-${runId}.jsonl`);

let queue = SET === 'hard' ? HARD_REQUESTS : REQUESTS;
if (RERUN) {
  const prior = fs.readFileSync(RERUN, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
  queue = prior.filter(isInfraFailure).map(r => ({ lang: r.lang, name: r.name, request: r.request }));
  if (!queue.length) {
    console.error(`--rerun: no infra-failed rows found in ${RERUN} — nothing to recover.`);
    process.exit(2);
  }
}
if (ONLY.length) queue = queue.filter(r => ONLY.includes(r.lang));
if (LIMIT) queue = queue.slice(0, LIMIT);

console.log(`── VACA language matrix ──`);
console.log(`   endpoint : ${BASE_URL}/api/reason/interactive`);
console.log(`   set      : ${RERUN ? `rerun(${path.basename(RERUN)})` : SET}`);
console.log(`   scale    : ${SCALE}`);
console.log(`   requests : ${queue.length}`);
console.log(`   results  : ${outFile}\n`);

const t0 = Date.now();
const results = [];
for (const [i, req] of queue.entries()) {
  const label = `[${i + 1}/${queue.length}] ${req.lang.padEnd(11)} ${req.name}`;
  process.stdout.write(`${label} … `);
  let r;
  try {
    r = await build(req);
  } catch (err) {
    r = { ...req, verdict: 'FAIL', reason: `harness error: ${String(err?.message || err)}`, ms: 0 };
  }
  results.push(r);
  fs.appendFileSync(outFile, JSON.stringify(r) + '\n');
  console.log(`${r.verdict}  (${Math.round(r.ms / 1000)}s)  ${r.reason ? r.reason.slice(0, 150) : ''}`);
}

const tally = (rs) => ({
  pass: rs.filter(r => r.verdict === 'PASS').length,
  unverified: rs.filter(r => r.verdict === 'UNVERIFIED').length,
  fail: rs.filter(r => r.verdict === 'FAIL').length,
});
const t = tally(results);
console.log(`\n── done in ${Math.round((Date.now() - t0) / 1000)}s ──`);
console.log(`   PASS ${t.pass} · UNVERIFIED ${t.unverified} · FAIL ${t.fail}  (of ${results.length})`);
console.log(`results: ${outFile}`);

const byLang = new Map();
for (const r of results) {
  const e = byLang.get(r.lang) || [];
  e.push(r);
  byLang.set(r.lang, e);
}
console.log('\n── by language (pass/unverif/fail) ──');
for (const [lang, rs] of byLang) {
  const c = tally(rs);
  console.log(`   ${lang.padEnd(11)} ${c.pass}/${c.unverified}/${c.fail}`);
}
console.log('\n── failures ──');
for (const r of results.filter(r => r.verdict === 'FAIL')) {
  console.log(`   ${r.lang.padEnd(11)} ${r.name.padEnd(16)} ${(r.reason || '').slice(0, 170)}`);
}
