/**
 * deterministicFixers.ts — shared deterministic (zero-LLM) tsc repair fixers.
 *
 * Ported from codePlanner.ts's tsc gate so the CANVAS/blueprint path
 * (FileGenerator.compileCheckAndFix) can apply the same mechanical repairs the
 * chat/CLI write path has: TS2307 sibling-path resolution + phantom npm
 * stripping, TS2459 missing-export patching, TS5097 extension-stripping,
 * TS2345 partial-object call-sites, TS2355/TS7030 missing returns, TS2322
 * void returns, TS2304/2503/2552 content-driven import insertion, TS2451
 * local-collision dedup.
 *
 * FORMAT TOLERANCE: codePlanner's error strings carry a `(line,col): error
 * TSxxxx:` prefix (`src/a.ts(1,62): error TS2307: Cannot find module
 * '../controllers'.`) while fileGenerator's are suffixed and prefix-less
 * (`TS2307: Cannot find module '../controllers' (line 1)`). Every regex here
 * matches BOTH (a bare `\bTSxxxx:` code anchor and a tolerant line/col
 * extractor), so the same fixer code serves both pipelines and never needs to
 * know where it was called from.
 *
 * All fixers are pure, idempotent, and return null when they can't safely
 * touch anything — callers fall through to their LLM repair prompts.
 *
 * No side effects at module load (mirrors guiShared.ts — safe to import from
 * routes and layers alike).
 */
import * as fs from 'fs';
import path from 'path';
// Project root (backend/src/ai → up 3 = repo root). Used to locate installed
// packages for the phantom-import strip (same resolution as fileGenerator's).
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
/** Node built-in module names (bare + node: prefixed) that never need installing. */
const NODE_BUILTIN_MODULES = new Set([
    'assert', 'async_hooks', 'buffer', 'child_process', 'cluster', 'console', 'constants',
    'crypto', 'dgram', 'diagnostics_channel', 'dns', 'domain', 'events', 'fs', 'http',
    'http2', 'https', 'inspector', 'module', 'net', 'os', 'path', 'perf_hooks', 'process',
    'punycode', 'querystring', 'readline', 'repl', 'stream', 'string_decoder', 'sys',
    'timers', 'tls', 'trace_events', 'tty', 'url', 'util', 'v8', 'vm', 'wasi',
    'worker_threads', 'zlib',
]);
/**
 * Normalize a file path for contract matching: strip ./ prefix, trailing /,
 * and a common source extension — so `from: 'src/game'` matches path
 * `src/game.ts` (and vice versa).
 */
export function normalizeContractPath(p) {
    return (p || '')
        .replace(/^\.\//, '')
        .replace(/\/+$/, '')
        .replace(/\.(ts|tsx|js|jsx|go|rs|py|java|rb|php|c|cpp|cs)$/i, '');
}
/** Escape regex metacharacters in a member name before embedding in \b...\b. */
function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
/**
 * Tolerant line extraction from a tsc error line. Handles BOTH formats:
 *   codePlanner:  src/a.ts(1,62): error TS2307: ...   → line 1, col 62
 *   fileGenerator: TS2307: ... (line 1)                → line 1, col undefined
 */
export function tscErrorPos(e) {
    const suffixed = e.match(/\(line (\d+)\)/);
    if (suffixed)
        return { line: Number(suffixed[1]) };
    const prefixed = e.match(/\((\d+),(\d+)\)/);
    if (prefixed)
        return { line: Number(prefixed[1]), col: Number(prefixed[2]) };
    return null;
}
/**
 * Extract imports from a generated file: { from, members, hasDefault }. Named
 * members are the symbols to verify; hasDefault marks a default import whose
 * local alias is arbitrary.
 */
export function extractImports(code) {
    const out = [];
    // import { A, B } from './x'
    for (const m of code.matchAll(/\bimport\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g)) {
        const members = m[1].split(',').map(s => s.trim().split(/\s+as\s+/)[0]?.trim()).filter(Boolean);
        if (members.length)
            out.push({ from: m[2], members, hasDefault: false });
    }
    // import type { A, B } from './x'  (type-only named imports are still imports)
    for (const m of code.matchAll(/\bimport\s+type\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g)) {
        const members = m[1].split(',').map(s => s.trim().split(/\s+as\s+/)[0]?.trim()).filter(Boolean);
        if (members.length)
            out.push({ from: m[2], members, hasDefault: false });
    }
    // import type X from './x'  and  import type X, { A } from './x'  (default type-only)
    for (const m of code.matchAll(/\bimport\s+type\s+([A-Za-z_$][\w$]*)(?:\s*,\s*\{([^}]*)\})?\s*from\s*['"]([^'"]+)['"]/g)) {
        const named = m[2]
            ? m[2].split(',').map(s => s.trim().split(/\s+as\s+/)[0]?.trim()).filter(Boolean)
            : [];
        out.push({ from: m[3], members: named, hasDefault: true });
    }
    // import X from './x'  and  import X, { A, B } from './x'  (default import)
    for (const m of code.matchAll(/\bimport\s+(?!type\b)([A-Za-z_$][\w$]*)(?:\s*,\s*\{([^}]*)\})?\s*from\s*['"]([^'"]+)['"]/g)) {
        const named = m[2]
            ? m[2].split(',').map(s => s.trim().split(/\s+as\s+/)[0]?.trim()).filter(Boolean)
            : [];
        out.push({ from: m[3], members: named, hasDefault: true });
    }
    return out;
}
/** Compute a relative import specifier from one file to another (extension-stripped). */
export function relativeImportSpecifier(fromPath, toPath) {
    const fromDir = path.posix.dirname(fromPath || 'x.ts');
    const rel = path.posix
        .relative(fromDir, toPath || 'x.ts')
        .replace(/\.(ts|tsx|js|jsx)$/i, '');
    return rel.startsWith('.') ? rel : `./${rel}`;
}
/**
 * Insert import lines after the file's last import (or at the top when the
 * file has none) so a patch never disturbs the file body.
 */
export function insertImportLines(content, lines) {
    if (!lines.length)
        return content;
    const all = content.split('\n');
    let lastImport = -1;
    for (let i = 0; i < all.length; i++) {
        if (/^\s*import(?:\s+type)?\s+/.test(all[i]) && /;\s*$/.test(all[i]))
            lastImport = i;
    }
    const insertAt = lastImport + 1;
    return [...all.slice(0, insertAt), ...lines, ...all.slice(insertAt)].join('\n');
}
/**
 * Scan a file's ACTUAL exported names from its written content. Best-effort
 * regex — never a gate, only feeds deterministic fixes.
 */
export function scanFileExports(src) {
    const names = new Set();
    const BANNED = new Set(['default', 'async', 'declare', 'abstract', 'function', 'const', 'let', 'var', 'interface', 'class', 'type', 'enum', 'readonly', 'import', 'export', 'from']);
    for (const m of src.matchAll(/export\s+(?:type\s+|interface\s+|class\s+|function\s+|const\s+|enum\s+|abstract\s+class\s+)?([A-Za-z_$][\w$]*)/g)) {
        const name = m[1];
        if (!BANNED.has(name))
            names.add(name);
    }
    for (const m of src.matchAll(/export\s*\{([^}]*)\}/g)) {
        for (const nm of m[1].matchAll(/[A-Za-z_$][\w$]*/g))
            names.add(nm[0]);
    }
    return names;
}
/** The package name a bare specifier refers to ('@scope/pkg' or 'pkg'). */
function packageNameFromSpecifier(spec) {
    const parts = spec.split('/');
    return spec.startsWith('@') && parts.length >= 2 ? `${parts[0]}/${parts[1]}` : parts[0];
}
/** True when a bare specifier resolves to an installed package. */
function isInstalledPackage(spec) {
    const pkg = packageNameFromSpecifier(spec);
    if (!pkg)
        return false;
    return [
        path.join(PROJECT_ROOT, 'node_modules', pkg),
        path.join(PROJECT_ROOT, 'backend', 'node_modules', pkg),
    ].some(p => fs.existsSync(p));
}
/** True when a NON-RELATIVE import specifier is safe: Node builtin or installed package. */
export function isSafeNonRelativeImport(spec) {
    if (spec.startsWith('node:'))
        return true;
    if (NODE_BUILTIN_MODULES.has(packageNameFromSpecifier(spec)))
        return true;
    return isInstalledPackage(spec);
}
/**
 * Deterministically remove import/export statements whose non-relative
 * specifier is neither a Node builtin nor an installed package (phantom npm
 * dependencies the writer invented). Zero LLM calls; never touches the body.
 */
export function stripPhantomPackageImports(content) {
    let changed = false;
    const dropIfPhantom = (whole, spec) => {
        if (spec.startsWith('.') || spec.startsWith('/') || isSafeNonRelativeImport(spec))
            return whole;
        changed = true;
        return '';
    };
    const out = content
        .replace(/^\s*import\s+(?!\.)(?:type\s+)?[^;]*?\s+from\s*['"]([^'"]+)['"]\s*;?\s*$/gm, dropIfPhantom)
        .replace(/^\s*import\s+['"]([^'"]+)['"]\s*;?\s*$/gm, dropIfPhantom)
        .replace(/^\s*export\s+(?:\*|\{[^}]*\}|[A-Za-z_$][\w$]*)\s+from\s*['"]([^'"]+)['"]\s*;?\s*$/gm, dropIfPhantom)
        .replace(/^\s*(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*require\s*\(\s*['"]([^'"]+)['"]\s*\)\s*;?\s*$/gm, dropIfPhantom)
        .replace(/^\s*(?:const|let|var)\s*\{[^}]*\}\s*=\s*require\s*\(\s*['"]([^'"]+)['"]\s*\)\s*;?\s*$/gm, dropIfPhantom)
        .replace(/^\s*require\s*\(\s*['"]([^'"]+)['"]\s*\)\s*;?\s*$/gm, dropIfPhantom);
    return changed ? out : null;
}
/**
 * CONTENT-DRIVEN missing-import fix (zero LLM): when the model references a
 * symbol (TS2304/2503/2552) that IS exported by exactly ONE sibling, insert
 * the import deterministically. Returns patched content or null.
 */
export function applyContentDrivenImportFix(content, selfPath, allFiles, errs) {
    const missing = new Set();
    for (const e of errs) {
        const m = e.match(/Cannot find (?:name|namespace) '([A-Za-z_$][\w$]*)'/);
        if (m)
            missing.add(m[1]);
    }
    if (!missing.size)
        return null;
    const alreadyImported = new Set();
    for (const imp of extractImports(content)) {
        for (const mm of imp.members)
            alreadyImported.add(mm);
        if (imp.hasDefault)
            alreadyImported.add('default');
    }
    const localDecls = new Set();
    for (const m of content.matchAll(/\b(?:function|class|interface|type|enum|const|let|var)\s+([A-Za-z_$][\w$]*)\b/g)) {
        localDecls.add(m[1]);
    }
    const selfKey = normalizeContractPath(selfPath);
    const ownerBy = new Map(); // missing name -> sibling keys
    for (const f of allFiles) {
        if (!f?.path || !f.content)
            continue;
        const key = normalizeContractPath(f.path);
        if (key === selfKey)
            continue;
        const exports = scanFileExports(f.content);
        for (const name of missing) {
            if (!exports.has(name))
                continue;
            if (!ownerBy.has(name))
                ownerBy.set(name, []);
            ownerBy.get(name).push(key);
        }
    }
    const pathByKey = new Map(allFiles.filter(f => f?.path).map(f => [normalizeContractPath(f.path), f.path]));
    const newLines = [];
    for (const name of missing) {
        if (alreadyImported.has(name) || localDecls.has(name))
            continue;
        const owners = ownerBy.get(name);
        if (!owners || owners.length !== 1)
            continue; // ambiguous or missing everywhere
        const ownerPath = pathByKey.get(owners[0]);
        if (!ownerPath)
            continue;
        const spec = relativeImportSpecifier(selfPath, ownerPath);
        newLines.push(`import { ${name} } from '${spec}';`);
    }
    if (!newLines.length)
        return null;
    const out = insertImportLines(content, newLines);
    return out !== content ? out : null;
}
/**
 * Deterministic TS2307 sibling-path resolver (zero LLM): tsc reports "Cannot
 * find module '../controllers'" when the import's RELATIVE PATH is wrong for
 * the actual sibling layout. For each failing relative specifier, resolve its
 * basename against the ACTUAL files; when exactly ONE file matches, rewrite
 * the import path. Ambiguous/unresolved → null (LLM repair).
 */
export function applyDeterministicSiblingPathFix(content, selfPath, allFiles, errs) {
    const failing = new Set();
    for (const e of errs) {
        const m = e.match(/\bTS2307: Cannot find module '([^']+)'/);
        if (!m)
            continue;
        const spec = m[1];
        if (spec.startsWith('.'))
            failing.add(spec);
    }
    if (!failing.size)
        return null;
    const selfKey = normalizeContractPath(selfPath);
    const pathByKey = new Map(allFiles.filter(f => f?.path).map(f => [normalizeContractPath(f.path), f.path]));
    const baseOf = (p) => (p.split(/[\\/]/).pop() || '').replace(/\.(ts|tsx|js|jsx)$/i, '');
    const dirLast = (p) => {
        const segs = p.split(/[\\/]/);
        segs.pop();
        return segs[segs.length - 1] || '';
    };
    // Compare basenames tolerantly of the label-vs-filename separator: node
    // LABELS keep underscores ("core_engine") while the scaffold FILE for that
    // label is hyphenated by labelToFileName ("core-engine"), and the model
    // writes imports in BOTH forms. Normalize [_ -] to a canonical separator so
    // "../input_handler/input_handler.ts" resolves to the real
    // "input-handler/input-handler.ts".
    const canon = (s) => s.toLowerCase().replace(/[_\s-]+/g, '-');
    const rewrites = [];
    for (const spec of failing) {
        const base = baseOf(spec);
        if (!base)
            continue;
        const matches = [];
        for (const f of allFiles) {
            if (!f?.path)
                continue;
            const key = normalizeContractPath(f.path);
            if (key === selfKey)
                continue;
            const fileBase = baseOf(f.path);
            if (canon(fileBase) === canon(base)) {
                matches.push(f.path);
            }
            else if (canon(fileBase) === 'index' && canon(dirLast(f.path)) === canon(base)) {
                matches.push(f.path); // directory-style: 'components' → components/index.ts
            }
        }
        if (matches.length !== 1)
            continue; // ambiguous or unresolved → LLM
        const target = baseOf(matches[0]).toLowerCase() === 'index'
            ? matches[0].replace(/[\\/]index\.(ts|tsx|js|jsx)$/i, '')
            : matches[0];
        let correct = relativeImportSpecifier(selfPath, target);
        if (correct === './')
            correct = './index';
        if (correct === spec)
            continue;
        rewrites.push({ from: spec, to: correct });
    }
    if (!rewrites.length)
        return null;
    let out = content;
    for (const { from, to } of rewrites) {
        const escaped = from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const anyQuote = `['"]`;
        const replaced = out
            .replace(new RegExp(`from\\s*${anyQuote}${escaped}${anyQuote}`, 'g'), `from '${to}'`)
            .replace(new RegExp(`\\bimport\\s*${anyQuote}${escaped}${anyQuote}`, 'g'), `import '${to}'`)
            .replace(new RegExp(`require\\s*\\(\\s*${anyQuote}${escaped}${anyQuote}\\s*\\)`, 'g'), `require('${to}')`);
        out = replaced;
    }
    return out !== content ? out : null;
}
/** Placeholder value for a primitive member type (TS2345 partial-object patcher). */
function primitivePlaceholder(type) {
    const t = type.trim();
    if (t === 'string')
        return "''";
    if (t === 'number')
        return '0';
    if (t === 'boolean')
        return 'false';
    if (t.endsWith('[]'))
        return '[]';
    return null;
}
/** Extract REQUIRED (non-optional) members of a named interface/class/type. */
function extractRequiredInterfaceMembers(src, typeName) {
    let m = new RegExp(`(?:interface|class)\\s+${escapeRegExp(typeName)}\\b[^{]*\\{([\\s\\S]*?)\\n\\}`).exec(src);
    if (!m) {
        m = new RegExp(`type\\s+${escapeRegExp(typeName)}\\s*=\\s*\\{([\\s\\S]*?)\\n\\}`).exec(src);
    }
    if (!m)
        return null;
    const out = new Map();
    for (const line of m[1].split('\n')) {
        const mm = line.match(/^\s*([A-Za-z_$][\w$]*)(\??)\s*:\s*([^;]+);/);
        if (mm && !mm[2])
            out.set(mm[1], mm[3].trim());
    }
    return out.size ? out : null;
}
/**
 * Deterministic TS2345 partial-object call-site patcher (zero LLM): a call
 * passes a PARTIAL object literal (`addNote({ content: 'x' })`) where a full
 * interface is required. For each error whose argument is a single-line object
 * literal, insert the missing primitive-typed members with placeholders.
 * Multi-line/ambiguous/complex-typed member cases fall through to the LLM.
 */
export function applyDeterministicPartialObjectFix(content, selfPath, allFiles, errs) {
    const targets = [];
    for (const e of errs) {
        const m = e.match(/TS2345: Argument of type '\{([^}]*)\}' is not assignable to parameter of type '([A-Za-z_$][\w$]*)'/);
        if (!m)
            continue;
        const pos = tscErrorPos(e);
        if (!pos)
            continue;
        const present = [...m[1].matchAll(/([A-Za-z_$][\w$]*)\s*:/g)].map(x => x[1]);
        targets.push({ line: pos.line, type: m[2], present });
    }
    if (!targets.length)
        return null;
    const selfKey = normalizeContractPath(selfPath);
    const selfDir = path.posix.dirname((selfPath || 'x.ts').replace(/\\/g, '/'));
    const importedKeys = [];
    for (const m of content.matchAll(/(?:from\s+|import\s*|require\s*\(\s*)(['"]?)(\.{1,2}\/[^'")\s]+)/g)) {
        const spec = m[2];
        if (!spec.startsWith('.'))
            continue;
        const resolved = normalizeContractPath(path.posix.join(selfDir, spec));
        if (resolved && resolved !== selfKey && !importedKeys.includes(resolved))
            importedKeys.push(resolved);
    }
    const ordered = [];
    for (const key of importedKeys) {
        const hit = allFiles.find(f => f?.content && normalizeContractPath(f.path) === key);
        if (hit)
            ordered.push(hit);
    }
    for (const f of allFiles) {
        if (!f?.content)
            continue;
        if (normalizeContractPath(f.path) === selfKey)
            continue;
        if (ordered.includes(f))
            continue;
        ordered.push(f);
    }
    const requiredBy = new Map();
    for (const t of targets) {
        if (requiredBy.has(t.type))
            continue;
        for (const f of ordered) {
            if (!f?.content)
                continue;
            const members = extractRequiredInterfaceMembers(f.content, t.type);
            if (members) {
                requiredBy.set(t.type, members);
                break;
            }
        }
    }
    const lines = content.split('\n');
    let changed = false;
    for (const t of targets) {
        const idx = t.line - 1;
        if (idx < 0 || idx >= lines.length)
            continue;
        const line = lines[idx];
        const pairs = [...line.matchAll(/\{[^{}]*\}/g)];
        if (pairs.length !== 1)
            continue;
        const lit = pairs[0][0];
        const required = requiredBy.get(t.type);
        if (!required)
            continue;
        const placeholders = [];
        let safe = true;
        for (const [name, type] of required) {
            if (t.present.includes(name))
                continue;
            if (new RegExp(`\\b${escapeRegExp(name)}\\s*:`).test(lit)) {
                safe = false;
                break;
            }
            const ph = primitivePlaceholder(type);
            if (ph === null) {
                safe = false;
                break;
            }
            if (new RegExp(`\\.${escapeRegExp(name)}\\b|\\['${name}'\\]|\\["${name}"\\]`).test(content)) {
                safe = false;
                break;
            }
            placeholders.push(`${name}: ${ph}`);
        }
        if (!safe || !placeholders.length)
            continue;
        const newLit = lit.slice(0, -1).trimEnd() + ', ' + placeholders.join(', ') + ' }';
        lines[idx] = line.replace(lit, newLit);
        changed = true;
    }
    if (!changed)
        return null;
    const out = lines.join('\n');
    return out !== content ? out : null;
}
/**
 * Deterministic TS5097 extension-strip (zero LLM): rewrite every relative
 * import/export/require specifier that ends in .ts/.tsx/.js/.jsx IF the
 * extension-stripped path resolves to an actual file in the project. Returns
 * patched content or null.
 */
export function normalizeImportExtensions(content, selfPath, allFiles) {
    const selfDir = path.posix.dirname(selfPath || 'x.ts');
    const keyOf = (p) => normalizeContractPath(path.posix.normalize(p));
    const byKey = new Map(allFiles.filter(f => f?.path).map(f => [normalizeContractPath(f.path), f.path]));
    let changed = false;
    const fixSpec = (spec) => {
        if (!spec.startsWith('.'))
            return spec;
        const stripped = spec.replace(/\.(ts|tsx|js|jsx)$/i, '');
        if (stripped === spec)
            return spec;
        if (byKey.has(keyOf(path.posix.join(selfDir, stripped)))) {
            changed = true;
            return stripped;
        }
        return spec;
    };
    const out = content
        .replace(/(\bfrom\s*['"])([^'"]+)(['"])/g, (m, pre, spec, post) => pre + fixSpec(spec) + post)
        .replace(/(\bimport\s*['"])([^'"]+)(['"])/g, (m, pre, spec, post) => pre + fixSpec(spec) + post)
        .replace(/(\brequire\s*\(\s*['"])([^'"]+)(['"]\s*\))/g, (m, pre, spec, post) => pre + fixSpec(spec) + post);
    return changed ? out : null;
}
/**
 * Deterministic TS2459 missing-export fix (zero LLM): a file IMPORTS a name
 * that another file DECLARES locally but never exports. This patches the
 * CAUSING file (adds `export`), which the per-file repair loop never selects
 * on its own (it has no errors). Returns the TARGET file's path + patched
 * content so the caller can update a DIFFERENT file than the one repaired.
 */
export function applyDeterministicMissingExportFix(selfPath, allFiles, errs) {
    const wanted = [];
    for (const e of errs) {
        const m = e.match(/\bTS2459: Module '([^']+)' declares '([A-Za-z_$][\w$]*)' locally, but it is not exported/);
        if (m)
            wanted.push({ spec: m[1].replace(/^"|"$/g, ''), name: m[2] });
    }
    if (!wanted.length)
        return null;
    const selfDir = path.posix.dirname(selfPath || 'x.ts');
    const keyOf = (p) => normalizeContractPath(path.posix.normalize(p));
    const pathByKey = new Map(allFiles.filter(f => f?.path).map(f => [normalizeContractPath(f.path), f.path]));
    for (const { spec, name } of wanted) {
        const targetPath = pathByKey.get(keyOf(path.posix.join(selfDir, spec)));
        if (!targetPath)
            continue;
        const target = allFiles.find(f => f?.path === targetPath);
        const content = target?.content;
        if (!content)
            continue;
        const re = new RegExp(`^(\\s*)(export\\s+)?(?:abstract\\s+class|async\\s+function|interface|class|type|enum|function|const|let|var)\\s+${escapeRegExp(name)}\\b`, 'gm');
        const matches = [...content.matchAll(re)];
        const unexported = matches.filter(mx => !mx[2]);
        if (matches.length !== 1 || unexported.length !== 1)
            continue;
        const patched = content.replace(re, (m, ws) => `${ws}export ${m.trimStart()}`);
        if (patched === content)
            continue;
        return { path: targetPath, content: patched };
    }
    return null;
}
/**
 * Deterministic export-NAME fix (zero LLM): tsc reports
 *
 *   TS2724: '"../game-state/game-state.ts"' has no exported member named
 *           'GameState'. Did you mean 'gameState'?
 *
 * — the importer guessed a different NAME/CASING than the module actually
 * exports. This was a systematic, repeatable defect in real builds: the
 * blueprint contract names the symbol `GameState` while the generated file
 * emits `gameState`, so every consumer of that module failed the same way and
 * each one burned a slow 14B repair round on it.
 *
 * tsc hands us the exact replacement in the message, so rewrite the imported
 * member (preserving any `as` alias) instead of regenerating. Only the named
 * import binding is touched — never the file body. Covers TS2724, TS2614 and
 * TS2305, which all carry the same "Did you mean 'X'?" hint.
 */
export function applyDeterministicExportNameFix(content, errs) {
    const renames = new Map();
    for (const e of errs) {
        const m = e.match(/no exported member(?:\s+named)?\s*'([^']+)'[\s\S]{0,140}?Did you mean\s*'([^']+)'/);
        if (!m)
            continue;
        const wrong = m[1];
        const right = m[2];
        if (wrong && right && wrong !== right)
            renames.set(wrong, right);
    }
    if (renames.size === 0)
        return null;
    const lines = content.split('\n');
    let changed = false;
    for (let i = 0; i < lines.length; i++) {
        const im = lines[i].match(/^(\s*import\s*(?:type\s+)?\{)([^}]*)(\}\s*from\s*['"][^'"]+['"]\s*;?\s*)$/);
        if (!im)
            continue;
        const members = im[2].split(',').map((s) => s.trim()).filter(Boolean);
        let touched = false;
        const next = members.map((mm) => {
            // Keep the local alias: `GameState as State` → `gameState as State`.
            const asMatch = mm.match(/^([A-Za-z_$][\w$]*)(\s+as\s+[A-Za-z_$][\w$]*)?$/);
            if (!asMatch)
                return mm;
            const target = renames.get(asMatch[1]);
            if (!target)
                return mm;
            touched = true;
            return `${target}${asMatch[2] || ''}`;
        });
        if (!touched)
            continue;
        lines[i] = `${im[1]} ${next.join(', ')} ${im[3]}`;
        changed = true;
    }
    if (!changed)
        return null;
    const out = lines.join('\n');
    return out !== content ? out : null;
}
/**
 * Deterministic TS2451 local-collision fix (zero LLM): a file that IMPORTS a
 * name AND also declares it locally ("Cannot redeclare block-scoped variable
 * 'X'"). The local declaration wins: drop the imported member.
 */
export function applyDeterministicLocalCollisionFix(content, errs) {
    const colliding = new Set();
    for (const e of errs) {
        const m = e.match(/Cannot redeclare block-scoped (?:variable|function|class|const) '([A-Za-z_$][\w$]*)'/);
        if (m)
            colliding.add(m[1]);
    }
    if (!colliding.size)
        return null;
    const lines = content.split('\n');
    let changed = false;
    for (let i = 0; i < lines.length; i++) {
        const im = lines[i].match(/^(\s*import\s*(?:type\s+)?\{)([^}]*)(\}\s*from\s*['"][^'"]+['"]\s*;?\s*)$/);
        if (!im)
            continue;
        const members = im[2].split(',').map((s) => s.trim()).filter(Boolean);
        const kept = members.filter((mm) => {
            const binding = mm.split(/\s+as\s+/)[0]?.trim();
            return !colliding.has(binding);
        });
        if (kept.length === members.length)
            continue;
        if (!kept.length) {
            lines[i] = '';
        }
        else {
            lines[i] = `${im[1]} ${kept.join(', ')} ${im[3]}`;
        }
        changed = true;
    }
    if (!changed)
        return null;
    const out = lines.filter(l => l.trim() !== '' || true).join('\n').replace(/\n{3,}/g, '\n\n');
    return out !== content ? out : null;
}
/**
 * Deterministic TS2355/TS7030 fix ("must return a value"): a function declared
 * with a primitive non-void return type whose body falls through gets a
 * type-appropriate `return <default>;` inserted before its closing brace.
 * Only fires for primitives we can synthesize a safe default for. Col-anchored
 * when the caller's errors carry a column (codePlanner format); without one
 * (fileGenerator format) the signature regex on the error line is the anchor.
 */
export function applyDeterministicMissingReturnFix(content, errors) {
    const DEFAULT_BY_TYPE = {
        number: '0',
        string: "''",
        boolean: 'false',
        bigint: '0n',
    };
    const lines = content.split('\n');
    let changed = false;
    const errs = errors
        .map((e, i) => ({ e, i, loc: tscErrorPos(e) }))
        .filter(x => x.loc && /TS(2355|7030)/.test(x.e))
        .sort((a, b) => b.loc.line - a.loc.line);
    for (const { e: err, loc } of errs) {
        const lineNo = loc.line - 1;
        const col = loc.col !== undefined ? loc.col - 1 : -1;
        const sigLine = lines[lineNo];
        if (!sigLine || sigLine.length === 0)
            continue;
        const sig = sigLine.match(/(\)\s*:\s*)((?:Promise<)?(number|string|boolean|bigint)(?:>)?)(\s*(?:=>\s*)?\{)/);
        if (!sig)
            continue;
        // With a column available, verify it lands on the annotation (codePlanner
        // anchors); without one (fileGenerator), accept the line's signature match.
        if (col >= 0) {
            const annStart = sig.index !== undefined ? sig.index + sig[1].length : -1;
            if (annStart < 0 || col < annStart - 2 || col > annStart + sig[2].length + 2)
                continue;
        }
        const defaultVal = DEFAULT_BY_TYPE[sig[3]];
        const openBrace = sigLine.indexOf('{', (sig.index ?? 0) + sig[0].length - 1);
        if (openBrace < 0)
            continue;
        let depth = 0;
        let quote = null;
        let esc = false;
        let lineComment = false;
        let blockComment = false;
        let closeLi = -1;
        let closeIdx = -1;
        for (let li = lineNo; li < lines.length; li++) {
            const line = lines[li];
            const start = li === lineNo ? openBrace : 0;
            for (let ci = start; ci < line.length; ci++) {
                const ch = line[ci];
                const next = line[ci + 1];
                if (lineComment)
                    continue;
                if (blockComment) {
                    if (ch === '*' && next === '/') {
                        blockComment = false;
                        ci++;
                    }
                    continue;
                }
                if (quote) {
                    if (esc)
                        esc = false;
                    else if (ch === '\\')
                        esc = true;
                    else if (ch === quote)
                        quote = null;
                    continue;
                }
                if (ch === '/' && next === '/') {
                    lineComment = true;
                    ci++;
                    continue;
                }
                if (ch === '/' && next === '*') {
                    blockComment = true;
                    ci++;
                    continue;
                }
                if (ch === '"' || ch === "'" || ch === '`') {
                    quote = ch;
                    continue;
                }
                if (ch === '{')
                    depth++;
                else if (ch === '}') {
                    depth--;
                    if (depth === 0) {
                        closeLi = li;
                        closeIdx = ci;
                        li = lines.length;
                        break;
                    }
                }
            }
            lineComment = false;
        }
        if (closeLi < 0)
            continue;
        const closeLine = lines[closeLi];
        if (closeLine.slice(0, closeIdx).trim().length > 0)
            continue;
        const prior = lines[closeLi - 1]?.trim();
        if (prior && /^return(\s|;|$)/.test(prior))
            continue;
        const closeIndent = closeLine.match(/^\s*/)?.[0] ?? '';
        const insertion = `${closeIndent}  return ${defaultVal};`;
        lines.splice(closeLi, 0, insertion);
        changed = true;
    }
    return changed ? lines.join('\n') : null;
}
/**
 * Deterministic TS2341 private-access fix (zero LLM): a caller in one file
 * accesses a member declared `private` in a class in ANOTHER file ("Property
 * 'X' is private and only accessible within class 'Y'"). The generated app has
 * no encapsulation requirement — the smallest safe repair is to make the
 * member public in the DECLARING file (the same cross-file patch shape as the
 * TS2459 missing-export fixer). Returns { path, content } of the declaring
 * file, or null when the class/member can't be located unambiguously.
 *
 * Only promotes members whose declaration is a simple field (no accessor
 * pair); `private` → `public` keeps every existing reference legal without
 * renaming anything.
 */
export function applyDeterministicPrivateAccessFix(selfPath, allFiles, errs) {
    const wanted = [];
    for (const e of errs) {
        const m = e.match(/TS2341: Property '([A-Za-z_$][\w$]*)' is private and only accessible within class '([A-Za-z_$][\w$]*)'/);
        if (m)
            wanted.push({ cls: m[2], member: m[1] });
    }
    if (!wanted.length)
        return null;
    const selfKey = normalizeContractPath(selfPath);
    // Search siblings FIRST (the declaring class is usually in another file),
    // then self — a file accessing its OWN private member is a different bug.
    const ordered = [
        ...allFiles.filter(f => f?.content && normalizeContractPath(f.path) !== selfKey),
        ...allFiles.filter(f => f?.content && normalizeContractPath(f.path) === selfKey),
    ];
    for (const { cls, member } of wanted) {
        for (const f of ordered) {
            const content = f.content;
            // Locate the class body: `class Y` ... first closing brace at column 0.
            const classRe = new RegExp(`\\bclass\\s+${escapeRegExp(cls)}\\b[^{]*\\{`);
            const cm = classRe.exec(content);
            if (!cm)
                continue;
            const bodyStart = cm.index + cm[0].length;
            let depth = 1;
            let bodyEnd = -1;
            for (let i = bodyStart; i < content.length; i++) {
                if (content[i] === '{')
                    depth++;
                else if (content[i] === '}') {
                    depth--;
                    if (depth === 0) {
                        bodyEnd = i;
                        break;
                    }
                }
            }
            if (bodyEnd < 0)
                continue;
            const body = content.slice(bodyStart, bodyEnd);
            // Match a field declaration: `private X` / `private readonly X` / `#X` —
            // with an optional type/initializer after the name. Never match a METHOD
            // call `this.x(` or a parameter `(x: T)`, and never a `private` method
            // whose name merely PREFIXES the member (`private xyz` for member `x`).
            const fieldRe = new RegExp(`(^|[\\s;}])(private)\\s+(readonly\\s+)?(${escapeRegExp(member)})(\\s*(?!\\s*\\().*?);`, 'm');
            const fm = fieldRe.exec(body);
            if (!fm)
                continue;
            // Re-emit everything after the member name (type annotation, initializer)
            // so the field keeps its shape — only the visibility keyword changes.
            const patched = body.replace(fieldRe, (_m, pre, _vis, ro, name, tail) => `${pre}public${ro ? ' ' + ro.trim() : ''} ${name}${tail}`);
            const out = content.slice(0, bodyStart) + patched + content.slice(bodyEnd);
            if (out === content)
                continue;
            return { path: f.path, content: out };
        }
    }
    return null;
}
/**
 * Deterministic TS2322 void-return fix (zero LLM): when a function declared
 * `: void` / `: Promise<void>` has `return <literal>;`, the value is discarded
 * anyway — rewrite it to `return;`. Only strips LITERALS (number/string/
 * boolean/null). Without a column anchor (fileGenerator format), only patches
 * a line that has exactly one literal return statement.
 */
export function applyDeterministicVoidReturnFix(content, errors) {
    if (!errors.some(e => /TS2322:.*not assignable to type '(Promise<)?void'/.test(e)))
        return null;
    const lines = content.split('\n');
    let changed = false;
    for (const err of errors) {
        if (!/TS2322:.*not assignable to type '(Promise<)?void'/.test(err))
            continue;
        const pos = tscErrorPos(err);
        if (!pos)
            continue;
        const lineNo = pos.line - 1;
        const line = lines[lineNo];
        if (!line)
            continue;
        if (pos.col !== undefined) {
            const col = pos.col - 1;
            const kw = line.lastIndexOf('return', col);
            if (kw < 0 || !/^return\s+/.test(line.slice(kw)))
                continue;
            if (kw > 0 && /['"`/A-Za-z0-9_$]/.test(line[kw - 1]))
                continue;
            const rest = line.slice(kw);
            const m = rest.match(/^return\s+((?:-?\d+(?:\.\d+)?|'[^']*'|"[^"]*"|`[^`$]*`|true|false|null))\s*;/);
            if (!m)
                continue;
            lines[lineNo] = line.slice(0, kw) + 'return;' + rest.slice(m[0].length);
            changed = true;
            continue;
        }
        // No column (fileGenerator format): only patch when the line has EXACTLY
        // one literal return statement (unambiguous).
        const matches = [...line.matchAll(/\breturn\s+((?:-?\d+(?:\.\d+)?|'[^']*'|"[^"]*"|`[^`$]*`|true|false|null))\s*;/g)];
        if (matches.length !== 1)
            continue;
        const m = matches[0];
        const kw = m.index;
        if (kw > 0 && /['"`/A-Za-z0-9_$]/.test(line[kw - 1]))
            continue;
        lines[lineNo] = line.slice(0, kw) + 'return;' + line.slice(kw + m[0].length);
        changed = true;
    }
    return changed ? lines.join('\n') : null;
}
/**
 * Deterministic circular-SELF-import strip (zero LLM): a file imports a name
 * from ITS OWN scaffold path (`import { X } from '../core-engine/core-engine.ts'`
 * inside core-engine.ts — the model hallucinated a type like `Request` and
 * "imported" it from itself, producing TS2303 circular-alias + TS2459). A
 * self-import can never resolve — the name does not exist in the file — so
 * the only mechanical repair is to DROP the import; the body's usage then
 * surfaces as a clean TS2304 (`Cannot find name`) which the scope-leak lint /
 * content-driven fixer / LLM repair resolves by declaring the type locally.
 */
export function stripCircularSelfImports(content, selfPath) {
    const selfKey = normalizeContractPath(selfPath);
    const selfDir = path.posix.dirname((selfPath || 'x.ts').replace(/\\/g, '/'));
    let changed = false;
    const out = content
        .split('\n')
        .map(line => {
        const m = line.match(/^\s*import\s+(?:type\s+)?[^;]*?\s+from\s*['"]([^'"]+)['"]\s*;?$/);
        if (!m)
            return line;
        const spec = m[1];
        if (!spec.startsWith('.'))
            return line;
        const resolved = normalizeContractPath(path.posix.normalize(path.posix.join(selfDir, spec)));
        if (resolved === selfKey) {
            changed = true;
            return '';
        }
        return line;
    })
        .join('\n')
        .replace(/\n{3,}/g, '\n\n');
    return changed ? out : null;
}
