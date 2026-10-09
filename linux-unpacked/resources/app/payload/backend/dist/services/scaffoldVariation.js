/**
 * scaffoldVariation — the SCAFFOLD self-improvement operators.
 *
 * Direction (2026-10-03): **VACA builds the scaffold; the LLM fills in the
 * code.** So the thing that should self-improve is the SCAFFOLD — the
 * blueprint's architecture checklist and its wiring graph (the module
 * contracts VACA hands the model). This module is the pure, deterministic core
 * of that loop: it MUTATES a blueprint into candidate variants and SCORES them,
 * with no LLM and no disk. The idle `MicroExperimenterService` drives it —
 * generate variants → build each → score on the shared gates → keep the winner.
 *
 * Why pure: the operators are the part that must be provably correct (a bad
 * mutation produces an incoherent app, and the scorer then blames the model).
 * Keeping them side-effect-free means the whole search can be unit-tested
 * without a browser, a compiler, or a model.
 *
 * The variants are only ever *proposed*: `isValidVariant()` enforces the same
 * referential-integrity rule the bible uses (every wiring endpoint must be a
 * checklist module, no duplicate/empty labels), so a mutation can never produce
 * a dangling edge the real builder would silently drop.
 */
import { scanFileExports, extractImports } from '../ai/deterministicFixers.js';
import { isStubBody, MARKDOWN_FENCE_RE } from '../knowledge/qualityGate.js';
import { languageFromPath } from '../utils/languageFromPath.js';
/**
 * Node built-ins the adherence gate treats as legitimate bare imports.
 * MIRROR of `BUILTIN_PKGS` in scripts/acceptance_check.mjs — the gate is
 * strict: a bare import that is NOT a builtin is a phantom package the app
 * does not ship, regardless of whether this repo happens to have it installed.
 * (deterministicFixers.isSafeNonRelativeImport is deliberately more lenient
 * for repair; the adherence metric must match the canonical checker.)
 */
const ADHERENCE_BUILTIN_PKGS = new Set([
    'fs', 'path', 'os', 'http', 'https', 'url', 'util', 'crypto', 'events',
    'stream', 'zlib', 'child_process', 'assert', 'buffer', 'querystring',
    'readline', 'net', 'dns', 'tty', 'vm', 'worker_threads', 'perf_hooks',
    'timers', 'string_decoder', 'constants', 'process',
]);
// ─── Scoring ───────────────────────────────────────────────────────────────
/**
 * Combine the gates into ONE number, higher = better.
 *
 * Adherence leads (it is the direct measure of "did the model follow VACA's
 * scaffold"), then the hard build verdicts, then penalties for drift (the
 * scaffold over- or under-promised) and contract violations. The weights are
 * deliberately simple integers so the ranking is inspectable and stable — this
 * is a search heuristic, not a graded exam.
 */
export function scoreVariant(m) {
    if (!m)
        return 0;
    let s = 0;
    s += 4 * clamp01(m.adherence);
    s += 3 * (m.tscClean ? 1 : 0);
    s += 2 * (m.smokePassed ? 1 : 0);
    s -= 0.5 * m.driftMissing;
    s -= 0.5 * m.driftUnexpected;
    s -= 0.2 * Math.min(m.contractViolations, 10);
    return Math.round(s * 1000) / 1000;
}
/**
 * Is `challenger` a real improvement over `incumbent`? Requires a margin, not
 * just a higher number, because a single build's output is stochastic (the
 * GATE_NUMBERS noise band is ±1pp) — an "improvement" inside the noise must not
 * be adopted.
 */
export function isImprovement(challenger, incumbent, margin = 0.25) {
    if (!challenger.ok)
        return false;
    return challenger.score >= incumbent.score + margin;
}
function clamp01(n) {
    if (!Number.isFinite(n))
        return 0;
    return n < 0 ? 0 : n > 1 ? 1 : n;
}
// ─── Validation ────────────────────────────────────────────────────────────
/**
 * A variant is only usable if it satisfies the SAME integrity rule the bible
 * enforces: non-empty, unique checklist labels and no dangling wiring edge.
 * (A dangling edge is dropped by the real builder with a warning, which would
 * silently make the variant look simpler than it is — so reject it here.)
 */
export function isValidVariant(bp) {
    const checklist = (bp.architecture_checklist || []).map((m) => m.trim()).filter(Boolean);
    if (checklist.length < 2)
        return false;
    if (new Set(checklist).size !== checklist.length)
        return false;
    const known = new Set(checklist);
    for (const w of bp.wiring_graph || []) {
        if (!w || !known.has((w.source_module || '').trim()))
            return false;
        if (!known.has((w.destination_module || '').trim()))
            return false;
    }
    return true;
}
// ─── Mutation operators ────────────────────────────────────────────────────
// Every operator is pure: it returns a NEW blueprint (deep-cloned) or null when
// the change does not apply to this blueprint.
function clone(bp) {
    return {
        ...bp,
        keywords: [...(bp.keywords || [])],
        target_stack: { ...bp.target_stack },
        architecture_checklist: [...(bp.architecture_checklist || [])],
        wiring_graph: (bp.wiring_graph || []).map((w) => ({ ...w })),
    };
}
function shortHash(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) {
        h ^= s.charCodeAt(i);
        h = Math.imul(h, 16777619);
    }
    return (h >>> 0).toString(36).slice(0, 6);
}
/** The modules that read FROM `module` (its importers), per the wiring graph. */
function importersOf(wiring, module) {
    return wiring.filter((w) => w.source_module === module);
}
/** The modules `module` reads from (its dependencies). */
function dependenciesOf(wiring, module) {
    return wiring.filter((w) => w.destination_module === module);
}
/**
 * SPLIT a module into two: keep the original as the state/owner, add a derived
 * module after it, and reroute the original's outbound contracts through the
 * new module. Models the "one module is doing two jobs" smell — the scaffold
 * promises fewer, fatter modules than the app needs.
 *
 * Only applies when the module HAS outbound wiring (otherwise the new module
 * would be an unconnected leaf, which is what `add_leaf_module` is for).
 */
export function splitModule(bp, module, newName, data = 'derived_data') {
    const checklist = bp.architecture_checklist || [];
    if (!checklist.includes(module))
        return null;
    const cleanNew = newName.trim();
    if (!cleanNew || checklist.includes(cleanNew))
        return null;
    const outbound = importersOf(bp.wiring_graph || [], module);
    if (outbound.length === 0)
        return null;
    const next = clone(bp);
    const idx = next.architecture_checklist.indexOf(module);
    next.architecture_checklist.splice(idx + 1, 0, cleanNew);
    // Original → new module, then new module → each former importer.
    next.wiring_graph = next.wiring_graph.map((w) => w.source_module === module ? { ...w, source_module: cleanNew } : w);
    next.wiring_graph.push({ source_module: module, destination_module: cleanNew, data_passed: data });
    return {
        id: `split_module:${shortHash(`${bp.app_type}|${module}|${cleanNew}`)}`,
        op: 'split_module',
        rationale: `split "${module}" into "${module}" + "${cleanNew}" (${outbound.length} outbound contract(s) rerouted)`,
        blueprint: next,
    };
}
/**
 * MERGE two modules into one: fold `absorbed` into `kept` and rewire every edge
 * that touched the absorbed module onto the kept one (dropping self-edges that
 * the merge creates). Models the opposite smell — the scaffold over-fragments.
 */
export function mergeModules(bp, kept, absorbed, mergedName) {
    const checklist = bp.architecture_checklist || [];
    if (!checklist.includes(kept) || !checklist.includes(absorbed) || kept === absorbed)
        return null;
    const name = (mergedName || kept).trim();
    if (!name)
        return null;
    const next = clone(bp);
    next.architecture_checklist = next.architecture_checklist
        .filter((m) => m !== absorbed)
        .map((m) => (m === kept ? name : m));
    const remap = (m) => (m === absorbed || m === kept ? name : m);
    const seen = new Set();
    next.wiring_graph = next.wiring_graph
        .map((w) => ({ ...w, source_module: remap(w.source_module), destination_module: remap(w.destination_module) }))
        .filter((w) => {
        if (w.source_module === w.destination_module)
            return false; // merge-created self-edge
        const key = `${w.source_module}→${w.destination_module}`;
        if (seen.has(key))
            return false; // dedupe now-identical edges
        seen.add(key);
        return true;
    });
    return {
        id: `merge_modules:${shortHash(`${bp.app_type}|${kept}|${absorbed}`)}`,
        op: 'merge_modules',
        rationale: `merged "${absorbed}" into "${kept}"${name !== kept ? ` as "${name}"` : ''}`,
        blueprint: next,
    };
}
/**
 * ADD a missing wiring contract between two modules that both exist. Models the
 * scaffold's most common defect: modules that should exchange data but have no
 * edge, so the model is never told they connect.
 */
export function addWiring(bp, source, destination, data) {
    const checklist = bp.architecture_checklist || [];
    if (!checklist.includes(source) || !checklist.includes(destination) || source === destination)
        return null;
    if ((bp.wiring_graph || []).some((w) => w.source_module === source && w.destination_module === destination))
        return null;
    const next = clone(bp);
    next.wiring_graph.push({ source_module: source, destination_module: destination, data_passed: data || 'data' });
    return {
        id: `add_wiring:${shortHash(`${bp.app_type}|${source}|${destination}|${data}`)}`,
        op: 'add_wiring',
        rationale: `added contract ${source} → ${destination} (${data || 'data'})`,
        blueprint: next,
    };
}
/**
 * REFINE the `data_passed` label of an existing contract. A vague label ("data",
 * "results") gives the model no type to define; a domain label does. Models the
 * scaffold naming a contract too generically.
 */
export function refineContract(bp, source, destination, newData) {
    const clean = newData.trim();
    if (!clean)
        return null;
    const wiring = bp.wiring_graph || [];
    const hit = wiring.find((w) => w.source_module === source && w.destination_module === destination);
    if (!hit || (hit.data_passed || '').trim() === clean)
        return null;
    const next = clone(bp);
    const target = next.wiring_graph.find((w) => w.source_module === source && w.destination_module === destination);
    target.data_passed = clean;
    return {
        id: `refine_contract:${shortHash(`${bp.app_type}|${source}|${destination}|${clean}`)}`,
        op: 'refine_contract',
        rationale: `refined contract ${source} → ${destination}: "${hit.data_passed}" → "${clean}"`,
        blueprint: next,
    };
}
/**
 * ADD a new leaf module wired from an existing source. Models a scaffold that
 * omits a responsibility the app obviously needs (a renderer, a validator, a
 * persistence adapter). The source must exist so the new module is connected.
 */
export function addLeafModule(bp, newName, source, data = 'data') {
    const checklist = bp.architecture_checklist || [];
    const clean = newName.trim();
    if (!clean || checklist.includes(clean) || !checklist.includes(source))
        return null;
    const next = clone(bp);
    next.architecture_checklist.push(clean);
    next.wiring_graph.push({ source_module: source, destination_module: clean, data_passed: data || 'data' });
    return {
        id: `add_leaf_module:${shortHash(`${bp.app_type}|${clean}|${source}`)}`,
        op: 'add_leaf_module',
        rationale: `added leaf module "${clean}" wired from "${source}"`,
        blueprint: next,
    };
}
/**
 * Deterministically propose a bounded set of scaffold variants for a blueprint.
 *
 * Ordering is by expected value (cheap, high-signal changes first): fix vague
 * contracts → add missing wiring → split the fattest module → merge the
 * thinnest → add a missing leaf. Duplicates and invalid variants are dropped.
 */
export function generateVariants(bp, opts = {}) {
    const max = opts.max ?? 6;
    const names = (opts.proposedNames || []).filter((n) => n && n.trim());
    const wiring = bp.wiring_graph || [];
    const checklist = bp.architecture_checklist || [];
    const out = [];
    const push = (v) => {
        if (!v)
            return;
        if (!isValidVariant(v.blueprint))
            return;
        if (out.some((o) => o.id === v.id))
            return;
        out.push(v);
    };
    // 1. Refine the vaguest contract labels (generic labels carry no type info).
    const GENERIC = new Set(['data', 'results', 'requests', 'state', 'info', 'output', 'input', 'payload']);
    for (const w of wiring) {
        if (out.length >= max)
            break;
        const label = (w.data_passed || '').trim().toLowerCase();
        if (GENERIC.has(label)) {
            push(refineContract(bp, w.source_module, w.destination_module, `${w.source_module.replace(/\s+/g, '_').toLowerCase()}_payload`));
        }
    }
    // 2. Add a contract between a module and a module it has no edge to yet.
    //    Prefer the entry (a module nothing imports from) → a leaf (imports nothing).
    if (out.length < max) {
        const hasIncoming = new Set(wiring.map((w) => w.destination_module));
        const hasOutgoing = new Set(wiring.map((w) => w.source_module));
        const entries = checklist.filter((m) => !hasIncoming.has(m));
        const leaves = checklist.filter((m) => !hasOutgoing.has(m));
        for (const e of entries) {
            for (const l of leaves) {
                if (out.length >= max)
                    break;
                if (e !== l)
                    push(addWiring(bp, e, l, `${l.replace(/\s+/g, '_').toLowerCase()}_input`));
            }
        }
    }
    // 3. Split the module with the most outbound contracts (the fattest one).
    //    `>= 1` (not `> 1`): a module with a single importer is still splittable,
    //    and on a small blueprint the fattest module often has only one.
    if (out.length < max && names.length) {
        const fattest = [...checklist].sort((a, b) => importersOf(wiring, b).length - importersOf(wiring, a).length)[0];
        if (fattest && importersOf(wiring, fattest).length >= 1) {
            push(splitModule(bp, fattest, names[0]));
        }
    }
    // 4. Merge the two modules with no edge between them (the thinnest pair).
    if (out.length < max) {
        for (let i = 0; i < checklist.length && out.length < max; i++) {
            for (let j = i + 1; j < checklist.length && out.length < max; j++) {
                const a = checklist[i];
                const b = checklist[j];
                const connected = wiring.some((w) => (w.source_module === a && w.destination_module === b) || (w.source_module === b && w.destination_module === a));
                if (!connected)
                    push(mergeModules(bp, a, b));
            }
        }
    }
    // 5. Add a missing leaf module (only when the caller proposed a name).
    if (out.length < max && names.length > 1) {
        const source = dependenciesOf(wiring, checklist[checklist.length - 1])[0]?.source_module || checklist[0];
        push(addLeafModule(bp, names[1], source));
    }
    return out.slice(0, max);
}
// ─── In-process adherence scoring ─────────────────────────────────────────
// The canonical adherence gate is scripts/acceptance_check.mjs (7 binary checks
// per file). The self-improvement loop runs in the backend, so it computes the
// SAME checks here without shelling out. Kept in lockstep by the scaffold
// variation test, which mirrors the .mjs cases.
const JSX_TAG_RE = /<\/?[A-Za-z][A-Za-z0-9]*\s[^>]*>|<\/[A-Za-z][A-Za-z0-9]*\s*>/;
/** Prose/markdown leakage in the first lines (a model narrating instead of coding). */
const PROSE_LINE_RE = /^\s*(Here(?:'s| is)|Sure[,!]|Certainly|Note:|Explanation|The above|This (?:code|file|component))/i;
/**
 * Does a NON-TypeScript source file declare at least one function/class/type?
 * The analog of `exports_declared` for languages whose "exports" are ordinary
 * top-level declarations (the harness checks themselves are TS-shaped, so the
 * scaffold loop scored every Go/Rust/C#/… file ~0 before this).
 */
function declaresCode(code, language) {
    switch (language) {
        case 'go':
            return /(?:^|\n)\s*(?:func|type|var|const)\s+[A-Za-z_]/.test(code);
        case 'python':
            return /(?:^|\n)\s*(?:async\s+def|def|class)\s+[A-Za-z_]/.test(code);
        case 'rust':
            return /(?:^|\n)\s*(?:pub\s+)?(?:fn|struct|enum|trait|impl|const|static|type|mod)\b/.test(code);
        case 'java':
            return /\b(?:class|interface|enum|record)\s+[A-Za-z_]/.test(code) ||
                /\b(?:public|private|protected|static)\s+[\w<>,.\[\]\s]+\s+\w+\s*\(/.test(code);
        case 'csharp':
            return /\b(?:class|struct|record|interface|enum)\s+[A-Za-z_]/.test(code) ||
                /\b(?:public|private|protected|internal|static)\s+[\w<>,.\[\]\s]+\s+\w+\s*\(/.test(code);
        case 'c':
        case 'cpp':
            return /[A-Za-z_]\w*(?:\s*\*)?\s+[A-Za-z_]\w*\s*\([^;{}]*\)\s*\{/.test(code) ||
                /\b(?:class|struct|namespace|template|typedef|enum)\b/.test(code);
        case 'php':
            return /\bfunction\s+[A-Za-z_]/.test(code) || /\b(?:class|interface|trait)\s+[A-Za-z_]/.test(code);
        case 'ruby':
            return /(?:^|\n)\s*(?:def|class|module)\s+[A-Za-z_]/.test(code);
        case 'kotlin':
            return /\b(?:fun|class|object|interface|data\s+class|enum\s+class)\s+[A-Za-z_]/.test(code);
        case 'swift':
            return /\b(?:func|class|struct|enum|protocol|extension)\s+[A-Za-z_]/.test(code);
        default:
            return code.trim().length > 0;
    }
}
// ── Cross-file import / contract resolution (compiled languages) ───────────
// The TS branch already scores `sibling_imports_ok` — do a file's relative
// imports point at files that exist. The compiled languages have the SAME
// failure class (a file references a module the build never produced), so they
// get the analogous `imports_resolve` check. It is deliberately conservative:
// anything it cannot classify passes, and only an unambiguously dangling
// project-local reference FAILS.
/** Framework / standard-library roots that need no project file to exist. */
const CS_STDLIB_ROOTS = new Set([
    'System', 'Microsoft', 'Windows', 'Newtonsoft', 'NUnit', 'Xunit', 'Azure',
    'Grpc', 'Google', 'Serilog', 'McMaster',
]);
/**
 * True when every project-local import/reference in `code` resolves against the
 * file set. External/stdlib imports are never punished (we cannot know the
 * framework), so only a dangling PROJECT-LOCAL reference fails.
 */
export function importsResolve(code, language, files) {
    const paths = new Set(files.map((f) => (f.path || '').replace(/\\/g, '/')));
    const basenames = new Set(files.map((f) => ((f.path || '').split('/').pop() || '').toLowerCase()));
    const dirs = new Set();
    for (const p of paths) {
        const parts = p.split('/');
        for (let i = 1; i < parts.length; i++)
            dirs.add(parts.slice(0, i).join('/'));
        if (parts.length > 1)
            dirs.add(parts[parts.length - 2]); // bare dir name
    }
    switch (language) {
        case 'go': {
            const re = /import\s*(?:\(\s*([\s\S]*?)\s*\)|(?:\w+\s+)?"([^"]+)")/g;
            let m;
            while ((m = re.exec(code)) !== null) {
                const group = m[1] ?? `"${m[2]}"`;
                for (const im of group.matchAll(/"([^"]+)"/g)) {
                    const p = im[1];
                    const srcIdx = p.lastIndexOf('/src/');
                    if (srcIdx === -1)
                        continue; // stdlib / third-party — not project-local
                    const dir = p.slice(srcIdx + 5).replace(/\/$/, '');
                    if (dir && !dirs.has(dir) && !dirs.has(dir.split('/')[0]))
                        return false;
                }
            }
            return true;
        }
        case 'rust': {
            const lines = code.split('\n');
            for (const line of lines) {
                const pathAttr = line.match(/^\s*#\[path\s*=\s*"([^"]+)"\]/);
                if (pathAttr) {
                    const target = pathAttr[1].replace(/\\/g, '/').replace(/^\.\//, '');
                    if (!paths.has(target))
                        return false;
                    continue;
                }
                const modDecl = line.match(/^\s*(?:pub\s+)?mod\s+([A-Za-z_]\w*)\s*;/);
                if (modDecl) {
                    // A bare `mod N;` (no #[path]) needs N.rs anywhere in the set.
                    const name = modDecl[1].toLowerCase();
                    const found = basenames.has(`${name}.rs`)
                        || [...paths].some((p) => p.toLowerCase().endsWith(`/${name}/mod.rs`));
                    if (!found)
                        return false;
                }
            }
            return true;
        }
        case 'java': {
            // Node classes share the default package (no import needed), so a
            // non-JDK import must name a class this build actually produced.
            for (const im of code.matchAll(/^\s*import\s+(?:static\s+)?([\w.]+)\s*;/gm)) {
                const fq = im[1];
                if (fq.startsWith('java.') || fq.startsWith('javax.') || fq.startsWith('jakarta.'))
                    continue;
                const simple = fq.split('.').pop() || '';
                if (!basenames.has(`${simple.toLowerCase()}.java`))
                    return false;
            }
            return true;
        }
        case 'csharp': {
            const declared = new Set();
            for (const f of files) {
                if (typeof f.content !== 'string')
                    continue;
                for (const ns of f.content.matchAll(/^\s*namespace\s+([\w.]+)/gm))
                    declared.add(ns[1]);
            }
            const isDeclared = (ns) => {
                if (declared.has(ns))
                    return true;
                for (const d of declared)
                    if (d.startsWith(`${ns}.`))
                        return true;
                return false;
            };
            for (const us of code.matchAll(/^\s*using\s+(?:static\s+)?([\w.]+)\s*;/gm)) {
                const ns = us[1];
                if (CS_STDLIB_ROOTS.has(ns.split('.')[0]))
                    continue;
                if (isDeclared(ns))
                    continue;
                return false; // a project-local namespace no file declares
            }
            return true;
        }
        default:
            return true;
    }
}
/** Languages whose cross-file imports are checked by `imports_resolve`. */
const IMPORT_CHECKED_LANGS = new Set(['go', 'rust', 'java', 'csharp']);
/**
 * The harness-adherence checks, evaluated on an in-memory file set.
 *
 * TypeScript/JavaScript keeps the original seven binary checks (exports declared,
 * no phantom imports, sibling imports resolve, no default export, no prose leak,
 * no JSX-in-.ts, not a stub) — byte-for-byte the same metric as before.
 *
 * NON-TS files get a language-appropriate subset: the TS-only checks (relative
 * imports, default exports, JSX) do not exist in Go/Rust/C#/…, so running them
 * would fail every file and make the scaffold self-improvement loop blind to
 * non-TS scaffolds. What remains is what genuinely transfers: the file declares
 * code, its cross-file references resolve (Go/Rust/C#/Java — the analog of
 * `sibling_imports_ok`), it is not a stub, and no markdown/prose leaked in.
 */
export function scoreFilesAdherence(files) {
    const failures = {};
    let passed = 0;
    let fully = 0;
    let checks = 0;
    const siblings = new Set(files.map((f) => (f.path.split('/').pop() || '').replace(/\.(ts|tsx|js|jsx|mjs|cjs)$/i, '')));
    for (const f of files || []) {
        const code = f.content || '';
        const language = languageFromPath(f.path);
        const isTsJs = language === 'typescript' || language === 'javascript';
        let results;
        if (isTsJs) {
            const ext = (f.path.split('.').pop() || '').toLowerCase();
            const imports = extractImports(code);
            const rel = imports.filter((i) => i.from.startsWith('.'));
            results = [
                ['exports_declared', scanFileExports(code).size > 0],
                ['no_phantom_imports', imports.every((i) => i.from.startsWith('.') || ADHERENCE_BUILTIN_PKGS.has(i.from) || i.from.startsWith('node:'))],
                ['sibling_imports_ok', rel.every((i) => siblings.has((i.from.split('/').pop() || '').replace(/\.(ts|tsx|js|jsx)$/i, '')))],
                ['no_default_export', !/\bexport\s+default\b/.test(code)],
                ['no_prose_leak', !MARKDOWN_FENCE_RE.test(code) && !code.split('\n').slice(0, 6).some((l) => PROSE_LINE_RE.test(l))],
                ['no_jsx_in_ts', ext !== 'ts' || !JSX_TAG_RE.test(code)],
                ['not_stub', !isStubBody(code)],
            ];
        }
        else {
            results = [['declares_code', declaresCode(code, language)]];
            if (IMPORT_CHECKED_LANGS.has(language)) {
                results.push(['imports_resolve', importsResolve(code, language, files)]);
            }
            results.push(['no_prose_leak', !MARKDOWN_FENCE_RE.test(code) && !code.split('\n').slice(0, 6).some((l) => PROSE_LINE_RE.test(l))], ['not_stub', !isStubBody(code)]);
        }
        let filePassed = 0;
        for (const [name, ok] of results) {
            checks++;
            if (ok)
                filePassed++;
            else
                failures[name] = (failures[name] || 0) + 1;
        }
        passed += filePassed;
        if (filePassed === results.length)
            fully++;
    }
    return {
        score: checks > 0 ? Math.round((passed / checks) * 10000) / 10000 : 0,
        fullyAdherent: fully,
        fileCount: (files || []).length,
        failures,
    };
}
// ─── Reporting ─────────────────────────────────────────────────────────────
/** A compact one-line summary of a variant's score, for logs / the ideas DB. */
export function describeScoredVariant(v) {
    if (!v.metrics)
        return `${v.id} — build failed`;
    const m = v.metrics;
    return (`${v.id} score=${v.score} adherence=${m.adherence.toFixed(3)} ` +
        `(${m.fullyAdherent}/${m.fileCount} fully adherent) tsc=${m.tscClean ? 'clean' : 'errors'} ` +
        `smoke=${m.smokePassed ? 'ok' : 'FAIL'} drift=-${m.driftMissing}/+${m.driftUnexpected} ` +
        `violations=${m.contractViolations}`);
}
