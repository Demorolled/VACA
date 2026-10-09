#!/usr/bin/env node
/**
 * acceptance_check.mjs — does a generated file PARSE and EXPORT what the task declared?
 * =============================================================================
 * The 7-task gold-similarity eval has saturated: base 0.3814, every SFT variant
 * 0.6659-0.6861, and code_like pinned at 7/7 for all of them. It cannot tell a
 * file that compiles from one that merely looks similar, and it is only 7 tasks
 * (two of which are duplicates). This is the replacement gate.
 *
 * For each candidate file it:
 *   1. builds an in-memory TypeScript program of just that file, so the
 *      diagnostics are about THIS file (real syntax + local type errors), not
 *      about the 200 other files it would need to compile a whole app,
 *   2. collects the exported symbols from the AST (ESM + CommonJS),
 *   3. compares them with the `expected exports` the task declared.
 *
 * Module-resolution errors (TS2307 / TS2792) are ignored on purpose — a single
 * file asked to `import '../services/noteService'` cannot resolve it here.
 *
 * Usage:
 *   node acceptance_check.mjs --in batch.json --out results.json [--ts-dir DIR]
 * batch.json = [{ id, file, lang, expects: ["router", ...], text }]
 */
import { createRequire } from "module";
import { fileURLToPath } from "url";
import path from "path";
import fs from "fs";
import os from "os";

const HERE = path.dirname(fileURLToPath(import.meta.url));

const args = process.argv.slice(2);
const opt = (name, dflt) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : dflt;
};
const inFile = opt("--in");
const outFile = opt("--out");
const mode = opt("--mode", "code");
const tsDir = opt("--ts-dir", path.join(HERE, "..", "node_modules", "typescript"));
const exportsDir = opt("--exports-dir", path.join(HERE, "..", "backend", "exports"));
if (!inFile || !outFile) {
  console.error("usage: node acceptance_check.mjs --in batch.json --out results.json " +
                "[--ts-dir DIR] [--mode code|app] [--exports-dir DIR]");
  process.exit(2);
}
if (!["code", "app", "adherence"].includes(mode)) {
  console.error(`FATAL: --mode must be code, app or adherence, got ${mode}`);
  process.exit(2);
}

// ── app mode ─────────────────────────────────────────────────────────────────
// The code gate typechecks ONE file in isolation, so it is structurally blind to
// whether a file's imports and exports line up with the files around it. For each
// task the export dir it came from is
// on disk (verified: 197/197 present, 188 with every planned file, and the gold
// dirs compile with 0 errors), so app mode stages the generated file over a copy
// of that real app and typechecks the WHOLE thing. Diagnostics from the gold
// siblings are ignored — only the subject file is judged.
const APP_EXTS = { ts: "ts", tsx: "tsx", js: "js", jsx: "jsx", mjs: "mjs", cjs: "cjs" };
const APP_COPY_EXTS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]);

function checkApp(item, st, shims) {
  const ext = APP_EXTS[extOf(item.file)] || APP_EXTS[item.lang];
  // The slug is the id's prefix, so a batch saved before slugs were recorded can
  // still be re-scored.
  const slug = item.slug || String(item.id || "").split("__", 1)[0];
  const base = { id: item.id, file: item.file, ext: ext || item.lang, mode: "app",
                 expects: item.expects || [], slug };
  if (!ext || !slug) {
    return { ...base, applicable: false, parsed: false, passed: false, n_errors: 0,
             errors: ["skipped: not a code file"] };
  }
  const goldDir = path.join(exportsDir, slug);
  if (!fs.existsSync(goldDir)) {
    return { ...base, applicable: false, parsed: false, passed: false, n_errors: 0,
             errors: [`no export dir ${goldDir}`] };
  }
  const stage = fs.mkdtempSync(path.join(os.tmpdir(), "vaca-app-"));
  try {
    fs.cpSync(goldDir, stage, { recursive: true });
    fs.rmSync(path.join(stage, "_training.json"), { force: true });
    const subject = path.join(stage, item.file);
    fs.mkdirSync(path.dirname(subject), { recursive: true });
    fs.writeFileSync(subject, item.text || "");
    // The same globals the isolated gate provides, so app mode does not punish a
    // file for `process`/`React` just because @types are not installed here.
    fs.writeFileSync(path.join(stage, "_shims.d.ts"), shims);

    const rootNames = [];
    const walk = (d) => {
      for (const e of fs.readdirSync(d, { withFileTypes: true })) {
        const p = path.join(d, e.name);
        if (e.isDirectory()) walk(p);
        else if (e.name.endsWith(".d.ts") || APP_COPY_EXTS.has(path.extname(e.name))) rootNames.push(p);
      }
    };
    walk(stage);

    const opts = compilerOptions();
    const program = ts.createProgram(rootNames, opts);
    const diags = ts.getPreEmitDiagnostics(program)
      .filter((d) => d.file && path.resolve(d.file.fileName) === path.resolve(subject))
      .filter((d) => !IGNORE_CODES.has(d.code));
    const record = { ...base, app_files: rootNames.length, n_errors: diags.length };
    record.errors = diags.slice(0, 5).map((d) => {
      const pos = d.start != null ? d.file.getLineAndCharacterOfPosition(d.start) : null;
      const where = pos ? `L${pos.line + 1}: ` : "";
      return `TS${d.code} ${where}${ts.flattenDiagnosticMessageText(d.messageText, " ")}`.slice(0, 300);
    });
    const sf = program.getSourceFile(subject);
    const { names, wildcard } = sf ? collectExports(sf) : { names: new Set(), wildcard: false };
    record.exports_found = [...names].sort();
    record.exports_missing = (item.expects || []).filter(
      (n) => !names.has(n) && !(wildcard && n !== "default"));
    record.parsed = true;
    // passed is COMPILATION ONLY here. The declared-exports check is code mode's
    // job; folding it in would double-count ~12 gold files whose on-disk exports
    // simply differ from the sidecar's `exports[]` list.
    record.ok_exports = record.exports_missing.length === 0;
    record.passed = record.n_errors === 0;
    return record;
  } catch (e) {
    return { ...base, parsed: false, ok_exports: false, passed: false, n_errors: 1,
             errors: [`FATAL ${e.name}: ${e.message}`.slice(0, 300)] };
  } finally {
    fs.rmSync(stage, { recursive: true, force: true });
  }
}

// ── adherence mode ───────────────────────────────────────────────────────────
// "Harness adherence" = does the generated file RESPECT the contract VACA's
// scaffold hands it? The code/app gates answer "does it compile / export what
// was declared"; this gate answers the different question the training loop
// cares about: did the model take its lead from the harness, or did it invent
// its own structure? Seven binary checks per file, grounded in VACA's real
// build contract (named exports, self-contained code, imports only from the
// declared app plan, no phantom npm packages, no prose/fences, no JSX in .ts,
// no stub bodies). Each is independent, so the failure MIX is as useful as the
// score.
const BUILTIN_PKGS = new Set([
  "fs", "path", "os", "http", "https", "url", "util", "crypto", "events",
  "stream", "zlib", "child_process", "assert", "buffer", "querystring",
  "readline", "net", "dns", "tty", "vm", "worker_threads", "perf_hooks",
  "timers", "string_decoder", "constants", "process",
]);
const RELATIVE_IMPORT_RE = /^\s*import\s[\s\S]*?from\s*['"](\.[^'"]*)['"]/gm;
const SIDE_EFFECT_IMPORT_RE = /^\s*import\s*['"](\.[^'"]*)['"]/gm;
const REQUIRE_RE = /require\(\s*['"](\.[^'"]*)['"]\s*\)/g;
const PROSE_FENCE_RE = /```/;
const PROSE_LINE_RE = /^\s*(Here(?:'s| is)|Sure[,!]|Certainly|Note:|Explanation|The above|This (?:code|file|component))/i;
const STUB_RE = /\/\/\s*(?:TODO|FIXME)\s*:?\s*(?:Implement|implement)|throw new Error\(['"]Not implemented|REAL FILE CONTENT/i;

/** Bare (non-relative) import specifiers — `react`, `lodash`, `@scope/x`. */
function bareImports(sf, ts, text) {
  const out = new Set();
  for (const st of sf.statements) {
    if (ts.isImportDeclaration(st) && ts.isStringLiteral(st.moduleSpecifier)) {
      const spec = st.moduleSpecifier.text;
      if (!spec.startsWith(".") && !spec.startsWith("/")) out.add(spec);
    }
  }
  for (const m of text.matchAll(/require\(\s*['"]([^'".][^'"]*)['"]\s*\)/g)) out.add(m[1]);
  return out;
}

/** Relative import specifiers, as written. */
function relativeImports(text) {
  const out = [];
  for (const re of [RELATIVE_IMPORT_RE, SIDE_EFFECT_IMPORT_RE, REQUIRE_RE]) {
    re.lastIndex = 0;
    for (const m of text.matchAll(re)) out.push(m[1]);
  }
  return out;
}

/**
 * Does a relative specifier resolve to a declared sibling file? Extension- and
 * directory-tolerant: `./game`, `../game.ts`, `./game/` all match sibling
 * `game.ts` (the sibling list is basenames from the app plan).
 */
function resolvesToSibling(spec, siblings) {
  const base = spec.replace(/^\.+\//, "").replace(/\/$/, "").replace(/\.[A-Za-z0-9]+$/, "");
  const last = base.split("/").pop() || base;
  return siblings.some((s) => {
    const sb = s.replace(/\.[A-Za-z0-9]+$/, "");
    return sb === base || sb === last || sb.endsWith(`/${last}`);
  });
}

function checkAdherence(item, ts, shims) {
  const ext = KIND_EXT[extOf(item.file)] || KIND_EXT[item.lang] || "ts";
  const text = item.text || "";
  const expects = item.expects || [];
  const siblings = item.siblings || [];
  const checks = {};
  let sf = null;
  try {
    sf = ts.createSourceFile(`/subject.${ext}`, text, ts.ScriptTarget.ES2020, true,
                             ext === "tsx" ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  } catch { /* unparsable — every check below fails on its own merits */ }

  // 1. Export contract — every declared export is present.
  const { names, wildcard } = sf ? collectExports(sf) : { names: new Set(), wildcard: false };
  const missing = expects.filter((n) => !names.has(n) && !(wildcard && n !== "default"));
  checks.exports_declared = missing.length === 0;

  // 2. No phantom npm packages — a bare import that is not a node builtin is
  //    a package the generated app does not ship (the phantom-package class).
  const bare = sf ? bareImports(sf, ts, text) : new Set();
  const phantom = [...bare].filter((b) => !BUILTIN_PKGS.has(b) && !b.startsWith("node:"));
  checks.no_phantom_imports = phantom.length === 0;

  // 3. Imports stay inside the declared app plan (or are type-only/builtin).
  const rel = relativeImports(text);
  checks.sibling_imports_ok = rel.every((r) => resolvesToSibling(r, siblings));

  // 4. Named exports only — `export default` is the delegation-facade smell
  //    VACA's contract explicitly forbids.
  checks.no_default_export = !/\bexport\s+default\b/.test(text);

  // 5. No prose/markdown leakage (fences or conversational preamble).
  checks.no_prose_leak = !PROSE_FENCE_RE.test(text) &&
    !text.split("\n").slice(0, 6).some((l) => PROSE_LINE_RE.test(l));

  // 6. No JSX in a plain .ts file (a JSX-in-ts leak will not run).
  checks.no_jsx_in_ts = ext !== "ts" || !/<[A-Za-z][^>]*>[\s\S]*<\//.test(text);

  // 7. Not a stub / placeholder body.
  checks.not_stub = !STUB_RE.test(text);

  const total = Object.keys(checks).length;
  const passed = Object.values(checks).filter(Boolean).length;
  return {
    id: item.id, file: item.file, ext, mode: "adherence",
    expects, siblings,
    checks, checks_passed: passed, checks_total: total,
    score: Math.round((passed / total) * 10000) / 10000,
    harness_adherent: passed === total,
    exports_missing: missing,
    phantom_imports: phantom,
    bad_relative_imports: rel.filter((r) => !resolvesToSibling(r, siblings)),
    exports_found: [...names].sort(),
  };
}

const require = createRequire(import.meta.url);
let ts = null;
if (mode === "code" || mode === "app" || mode === "adherence") {
  try {
    ts = require(`${tsDir}/lib/typescript.js`);
  } catch (e) {
    console.error(`FATAL: cannot load typescript from ${tsDir}: ${e.message}`);
    process.exit(2);
  }
}

// Diagnostics that only mean "this one file cannot see its neighbours".
const IGNORE_CODES = new Set([2307, 2792, 7016, 2306, 1479]);

// Ambient declarations so that a single file checked in isolation does not fail on
// globals its runtime provides (node, react, express). Without these, `process`,
// `JSX.Element` and `module.exports` produce TS2304/TS2503 noise that has nothing
// to do with the model's output. Genuinely undefined identifiers still error.
//
// DO NOT add `declare module "*";` back. It reads as "imports are any", but an
// ambient wildcard has no exports, so TypeScript types every NAMED import from it
// as a namespace — and a namespace cannot be used as a type:
//
//     import { Cheese } from './entities/cheese';
//     foo: Cheese            // TS2709: Cannot use namespace 'Cheese' as a type
//
// That fired on correct code and cost the gate ~20 points (measured on the 197-
// task corpus: distill 0.5584 -> 0.7563, nogrpo 0.3503 -> 0.5787 purely by
// deleting this one line). Letting the import stay
// unresolved instead yields TS2307, which is already ignored below, and the
// binding becomes `any` — which is what the wildcard was supposed to do.
const SHIMS = `declare const process: any;
declare const require: any;
declare const module: any;
declare const exports: any;
declare const global: any;
declare const Buffer: any;
declare const __dirname: string;
declare const __filename: string;
declare const React: any;
declare const describe: any;
declare const it: any;
declare const test: any;
declare const expect: any;
declare const beforeEach: any;
declare const afterEach: any;
declare namespace JSX { interface Element {} interface IntrinsicElements { [key: string]: any; } }
declare namespace NodeJS { interface ProcessEnv { [key: string]: string | undefined; } }
declare namespace Express { interface Request {} interface Response {} interface Router {} }
`;
const extOf = (f) => {
  const m = /\.([A-Za-z0-9]+)$/.exec(f || "");
  return m ? m[1].toLowerCase() : "";
};
const KIND_EXT = { ts: "ts", tsx: "tsx", js: "js", jsx: "jsx", mjs: "mjs", cjs: "cjs" };

// Built lazily: `ts` is only loaded for code/app modes, so evaluating this at
// module scope would throw on a null dereference before any check runs.
const compilerOptions = () => ({
  noEmit: true,
  target: ts.ScriptTarget.ES2020,
  module: ts.ModuleKind.ESNext,
  moduleResolution: ts.ModuleResolutionKind.NodeJs,
  skipLibCheck: true,
  allowJs: true,
  jsx: ts.JsxEmit.ReactJSX,
  strict: false,
  noImplicitAny: false,
  esModuleInterop: true,
  allowSyntheticDefaultImports: true,
  types: [],
});

const hasExportModifier = (node) =>
  !!(ts.getCombinedModifierFlags(node) & ts.ModifierFlags.Export);

function collectExports(sf) {
  const names = new Set();
  let wildcard = false;
  for (const st of sf.statements) {
    if (ts.isExportDeclaration(st)) {
      if (!st.exportClause) { wildcard = true; continue; }
      if (ts.isNamedExports(st.exportClause)) {
        for (const el of st.exportClause.elements) names.add(el.name.text);
      } else { wildcard = true; }
      continue;
    }
    if (ts.isExportAssignment(st)) { names.add("default"); continue; }
    if (ts.isVariableStatement(st) && hasExportModifier(st)) {
      for (const d of st.declarationList.declarations) {
        if (ts.isIdentifier(d.name)) names.add(d.name.text);
        else for (const el of d.name.elements) {          // destructuring
          if (ts.isIdentifier(el.name)) names.add(el.name.text);
          else if (ts.isBindingElement(el.name) && ts.isIdentifier(el.name.name)) names.add(el.name.name.text);
        }
      }
      continue;
    }
    if (ts.isFunctionDeclaration(st) || ts.isClassDeclaration(st) ||
        ts.isInterfaceDeclaration(st) || ts.isTypeAliasDeclaration(st) ||
        ts.isEnumDeclaration(st) || ts.isModuleDeclaration(st)) {
      const flags = ts.getCombinedModifierFlags(st);
      if (flags & ts.ModifierFlags.Default) names.add("default");
      if (flags & (ts.ModifierFlags.Export | ts.ModifierFlags.Default) &&
          st.name && ts.isIdentifier(st.name)) names.add(st.name.text);
      continue;
    }
    // CommonJS: module.exports = {...} / exports.foo = ...
    if (ts.isExpressionStatement(st) && ts.isBinaryExpression(st.expression) &&
        st.expression.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
      const lhs = st.expression.left, rhs = st.expression.right;
      if (lhs.getText(sf) === "module.exports" && ts.isObjectLiteralExpression(rhs)) {
        // `module.exports = { addTask, ... }`
        for (const p of rhs.properties) {
          const n = p.name && (ts.isIdentifier(p.name) || ts.isStringLiteral(p.name)) ? p.name.text : null;
          if (n) names.add(n);
        }
      } else if (ts.isPropertyAccessExpression(lhs)) {
        // `exports.foo = ...` OR `module.exports.foo = ...`
        const obj = lhs.expression.getText(sf);
        if (obj === "exports" || obj === "module.exports") names.add(lhs.name.text);
      }
    }
  }
  return { names, wildcard };
}

const batch = JSON.parse(fs.readFileSync(inFile, "utf8"));
const results = {};

for (const item of batch) {
  if (mode === "app") { results[item.id] = checkApp(item, ts, SHIMS); continue; }
  if (mode === "adherence") { results[item.id] = checkAdherence(item, ts, SHIMS); continue; }
  const ext = KIND_EXT[extOf(item.file)] || KIND_EXT[item.lang] || "ts";
  const subject = `/subject.${ext}`;
  const text = item.text || "";
  const virtual = {
    [subject]: text,
    "/shims.d.ts": SHIMS,
  };
  const record = { id: item.id, file: item.file, ext, expects: item.expects || [] };

  try {
    const opts = compilerOptions();
    const host = ts.createCompilerHost(opts);
    const origGetSourceFile = host.getSourceFile.bind(host);
    host.getSourceFile = (fileName, languageVersion, onError, shouldCreate) => {
      if (Object.prototype.hasOwnProperty.call(virtual, fileName)) {
        return ts.createSourceFile(fileName, virtual[fileName], languageVersion, true);
      }
      return origGetSourceFile(fileName, languageVersion, onError, shouldCreate);
    };
    const origFileExists = host.fileExists.bind(host);
    host.fileExists = (f) => Object.prototype.hasOwnProperty.call(virtual, f) || origFileExists(f);
    const origReadFile = host.readFile.bind(host);
    host.readFile = (f) => (Object.prototype.hasOwnProperty.call(virtual, f) ? virtual[f] : origReadFile(f));

    const program = ts.createProgram(Object.keys(virtual), opts, host);
    const sf = program.getSourceFile(subject);
    const diags = ts.getPreEmitDiagnostics(program, sf)
      .filter((d) => !d.file || d.file.fileName === subject)
      .filter((d) => !IGNORE_CODES.has(d.code));

    record.n_errors = diags.length;
    record.errors = diags.slice(0, 5).map((d) => {
      const pos = d.file && d.start != null ? d.file.getLineAndCharacterOfPosition(d.start) : null;
      const where = pos ? `L${pos.line + 1}: ` : "";
      return `TS${d.code} ${where}${ts.flattenDiagnosticMessageText(d.messageText, " ")}`.slice(0, 300);
    });

    const { names, wildcard } = collectExports(sf);
    record.exports_found = [...names].sort();
    record.wildcard = wildcard;
    record.exports_missing = (item.expects || []).filter(
      (n) => !names.has(n) && !(wildcard && n !== "default"));

    record.parsed = true;
    record.ok_exports = record.exports_missing.length === 0;
    record.passed = record.n_errors === 0 && record.ok_exports;
  } catch (e) {
    record.parsed = false;
    record.ok_exports = false;
    record.passed = false;
    record.n_errors = 1;
    record.errors = [`FATAL ${e.name}: ${e.message}`.slice(0, 300)];
    record.exports_found = [];
    record.exports_missing = item.expects || [];
  }
  results[item.id] = record;
}

fs.writeFileSync(outFile, JSON.stringify({
  mode,
  typescript: ts ? ts.version : null,
  n: batch.length,
  results,
}, null, 2) + "\n");
console.log(mode === "app"
  ? `[acc] staged + typechecked ${batch.length} files IN their real export dirs `
    + `with typescript ${ts.version} -> ${outFile}`
  : mode === "adherence"
    ? `[acc] scored harness adherence for ${batch.length} files `
      + `with typescript ${ts.version} -> ${outFile}`
    : `[acc] checked ${batch.length} files with typescript ${ts.version} -> ${outFile}`);
