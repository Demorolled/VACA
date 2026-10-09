/**
 * nonTsRepair — the shared non-TS build gate + repair machinery used by BOTH
 * generation pipelines (the chat/planner path in `routes/codePlanner.ts` and the
 * canvas path in `layers/fileGenerator.ts`).
 *
 * Previously this lived only in `routes/codePlanner.ts`, so the canvas path ran
 * the non-TS compile gate + stub gate but could never REPAIR a failure (and had
 * no deterministic sanitizer or contract-aware stub gate). The gates and the
 * repair loop are pure (fs + spawned toolchains + an INJECTED LLM callback), so
 * they belong in `sandbox/` — importing them from a routes module into a layer
 * would be a cycle.
 *
 * Everything LLM-shaped is injected (`repairCall`), never imported: the sandbox
 * layer must stay unit-testable without a model server.
 */
import * as fs from 'fs';
import * as path from 'path';
import { resolveGateLanguage, sanitizeGoModuleName, runNonTsProjectGates } from './nonTsCompileGate.js';
import { runStubGate } from './buildVerification.js';
import { memberImplementationState } from '../knowledge/qualityGate.js';
import { resolveCrossFileDuplicates } from './duplicateDeclarations.js';
const MAX_NONTS_REPAIR_ROUNDS = 2;
/** Normalize a file path for contract matching (strip ./, trailing /, ext). */
function normalizeContractPath(p) {
    return (p || '')
        .replace(/^\.\//, '')
        .replace(/\/+$/, '')
        .replace(/\.(ts|tsx|js|jsx|go|rs|py|java|rb|php|c|cpp|cs)$/i, '');
}
/** Resolve a relative path safely INSIDE the export dir. */
function safeJoin(exportDir, relPath) {
    const rel = path.normalize(relPath || 'file.txt').replace(/^(\.\.(\/|\\|$))+/, '');
    const full = path.resolve(exportDir, rel);
    return full.startsWith(exportDir + path.sep) ? full : path.join(exportDir, 'file.txt');
}
// ─── Language classification ─────────────────────────────────────────────
/**
 * True when a file is a NON-TS gateable code language (Java, Go, Python, Rust,
 * C/C++, C#, Swift, Kotlin, PHP, Ruby). Their compiles are judged by the
 * whole-project non-TS gate, never by the JS/TS import heuristics.
 */
export function isNonTsGateFile(language, relPath) {
    return resolveGateLanguage(language, relPath) !== null;
}
// ─── Deterministic source fixups ─────────────────────────────────────────
/** Languages whose blocks are delimited by braces (truncation ⇒ unbalanced). */
const BRACE_LANGS = new Set(['java', 'go', 'c', 'cpp', 'csharp', 'rust', 'swift', 'kotlin', 'php', 'javascript', 'typescript']);
/**
 * Count `{` minus `}` for a C-family source, IGNORING braces inside string/char
 * literals and line/block comments. A positive result means the file ended
 * before its blocks closed (truncation). Pure + best-effort.
 */
export function braceBalance(content) {
    let depth = 0;
    let i = 0;
    const n = content.length;
    while (i < n) {
        const c = content[i];
        const two = content.slice(i, i + 2);
        if (two === '//') {
            const nl = content.indexOf('\n', i);
            i = nl === -1 ? n : nl;
            continue;
        }
        if (two === '/*') {
            const end = content.indexOf('*/', i + 2);
            i = end === -1 ? n : end + 2;
            continue;
        }
        if (c === '"' || c === '\'' || c === '`') {
            const quote = c;
            i += 1;
            while (i < n) {
                if (content[i] === '\\') {
                    i += 2;
                    continue;
                }
                if (content[i] === quote) {
                    i += 1;
                    break;
                }
                i += 1;
            }
            continue;
        }
        if (c === '{')
            depth += 1;
        else if (c === '}')
            depth -= 1;
        i += 1;
    }
    return depth;
}
/**
 * Deterministic source fixups for a NON-TS file, zero LLM calls:
 *   - Java: remove bare `import Foo;` lines (a single-identifier import is
 *     ALWAYS a compile error; a same-package class needs no import).
 *   - Brace languages: append missing closing braces when truncated (guarded).
 * Returns the fixed content, or null when nothing needed changing.
 */
/**
 * A Go package name for the directory a node file is staged in. Go requires
 * every file of one directory to share a package, and the default package name
 * is the directory's base name sanitized to a legal identifier.
 */
export function goPackageNameFromPath(relPath) {
    const dir = (relPath || '').replace(/\\/g, '/').split('/').slice(0, -1).pop() || 'app';
    const name = dir.toLowerCase().replace(/[^a-z0-9]+/g, '');
    if (!name || /^[0-9]/.test(name) || GO_KEYWORDS.has(name))
        return 'app';
    return name;
}
const GO_KEYWORDS = new Set([
    'break', 'case', 'chan', 'const', 'continue', 'default', 'defer', 'else',
    'fallthrough', 'for', 'func', 'go', 'goto', 'if', 'import', 'interface',
    'map', 'package', 'range', 'return', 'select', 'struct', 'switch', 'type', 'var',
]);
export function sanitizeNonTsSource(content, language, relPath) {
    let out = content;
    if (language === 'java') {
        out = out.split('\n').filter((l) => !/^\s*import\s+[A-Za-z_$][\w$]*\s*;\s*$/.test(l)).join('\n');
    }
    // Go: a node file staged in its OWN directory must not claim `package main`
    // unless it really is the program (declares `func main()`). The generator's
    // prompt forbids it, but a model that ignores the rule leaves a main package
    // with no main function — `go build ./...` fails with "function main is
    // undeclared in the main package", and the file is unimportable, so its code
    // silently never reaches the binary (measured on the generated Go
    // string-tools app: its CLI node was dead code the whole way through).
    if (language === 'go' && relPath && !/\bfunc\s+main\s*\(/.test(out) && /^\s*package\s+main\b/m.test(out)) {
        out = out.replace(/^(\s*)package\s+main\b/m, `$1package ${goPackageNameFromPath(relPath)}`);
    }
    if (BRACE_LANGS.has(language)) {
        const bal = braceBalance(out);
        if (bal > 0 && bal <= 12) {
            out = out.replace(/\s*$/, '') + '\n' + Array(bal).fill('}').join('\n') + '\n';
        }
    }
    return out === content ? null : out;
}
// ─── Contract-aware implementation gate ──────────────────────────────────
/**
 * A PLANNED export the generated code never really implements:
 *   - `trivial`: body is EMPTY or a single placeholder `return <literal>;`
 *   - `absent`:   no callable declaration (only flagged for non-TS languages;
 *                 TS/JS use the export-drift check in `verifyGeneratedContracts`)
 * Class/type exports have no callable body and are skipped.
 */
export function findUnimplementedPlannedExports(files, contractFiles) {
    const failures = [];
    for (const cf of contractFiles) {
        const exports = cf.exports || [];
        if (!exports.length)
            continue;
        const gen = files.find((f) => normalizeContractPath(f.path) === normalizeContractPath(cf.path));
        if (!gen)
            continue;
        const nonTs = isNonTsGateFile(cf.language, cf.path);
        for (const name of exports) {
            const state = memberImplementationState(gen.content, name, cf.language);
            if (state === 'trivial') {
                failures.push(`${cf.path}: planned export '${name}' has a trivial/unimplemented body (placeholder return or empty)`);
            }
            else if (state === 'absent' && nonTs) {
                failures.push(`${cf.path}: planned export '${name}' is not implemented in the generated code`);
            }
        }
    }
    return failures;
}
// ─── Failure → file routing ──────────────────────────────────────────────
/**
 * Group whole-project non-TS gate errors by the working file they refer to.
 * A `wholeSetGate` (`javac -d classes <all files>`) returns ONE concatenated
 * string for MANY files, so attribution is PER LINE: a line naming a file
 * becomes the "current" file and its `symbol:` context lines accrue to it.
 * The LONGEST matching path wins so `a.java` cannot steal a `src/a.java` error.
 */
export function groupGateErrorsByFile(gates, files) {
    const byFile = new Map();
    const append = (key, line) => {
        const list = byFile.get(key) || [];
        list.push(line);
        byFile.set(key, list);
    };
    for (const g of gates) {
        if (g.clean)
            continue;
        for (const err of g.errors) {
            let current = '';
            for (const line of err.split('\n')) {
                let best = '';
                for (const f of files) {
                    if (line.includes(f.path) && f.path.length > best.length)
                        best = f.path;
                }
                if (best)
                    current = best;
                if (current)
                    append(current, line);
            }
        }
    }
    return byFile;
}
/**
 * The file path a gate/stub failure message refers to. Stub failures are either
 * a bare path (`src/Game.java`) or `path: detail`. Returns '' when no path.
 */
export function pathFromGateFailure(message) {
    const m = message.match(/^([^\s:]+\.((?:tsx?|jsx?|mjs|cjs|go|py|rs|c|cc|cpp|h|hpp|cs|java|swift|kt|php|rb|html?)))(?::\s|$)/i);
    return m ? m[1] : '';
}
/** Group stub/unimplemented failures by the working file they refer to. */
export function groupStubFailuresByFile(stubFailures, files) {
    const byFile = new Map();
    for (const s of stubFailures) {
        const p = pathFromGateFailure(s);
        if (!p)
            continue;
        const match = files.find((f) => normalizeContractPath(f.path) === normalizeContractPath(p));
        if (!match)
            continue;
        const list = byFile.get(match.path) || [];
        list.push(s);
        byFile.set(match.path, list);
    }
    return byFile;
}
/**
 * Run the whole-project non-TS compile gate plus the file-level stub gate and
 * the contract-aware implementation gate. Shared by both pipelines.
 */
export async function runProjectGates(request, files, contractFiles, 
/** The caller gates node files only and a scaffolder writes the entry (canvas path). */
scaffoldSuppliesEntry = false) {
    const langByPath = new Map();
    for (const f of contractFiles)
        langByPath.set(normalizeContractPath(f.path), (f.language || '').toLowerCase());
    const nonTs = files
        .map((f) => ({ relPath: f.path, code: f.content, language: resolveGateLanguage(langByPath.get(normalizeContractPath(f.path)), f.path) || '' }))
        .filter((f) => f.language);
    const languageGates = nonTs.length
        ? await runNonTsProjectGates(nonTs, sanitizeGoModuleName(request), { scaffoldSuppliesEntry })
        : [];
    const stubFailures = [...new Set([
            ...runStubGate(files),
            ...findUnimplementedPlannedExports(files, contractFiles),
        ])];
    return { languageGates, stubFailures };
}
// ─── Repair prompt ───────────────────────────────────────────────────────
/**
 * Repair prompt for a non-TS file that either fails to compile OR has a
 * stub/unimplemented body. Includes the sibling files' REAL code so a typed
 * language can align signatures (names alone are not enough).
 */
export function buildNonTsRepairPrompt(request, file, currentContent, opts, siblings) {
    const lang = (file.language || '').trim();
    const siblingBlock = (siblings || [])
        .map((f) => `───── ${f.path}${f.language ? ` (${f.language})` : ''} ─────\n${(f.content || '').slice(0, 2200)}`)
        .join('\n\n');
    const compilerErrors = opts.compilerErrors || [];
    const stubNotes = opts.stubNotes || [];
    const reasons = [];
    if (compilerErrors.length)
        reasons.push(`━━━ COMPILER ERRORS ━━━\n${compilerErrors.join('\n')}`);
    if (stubNotes.length)
        reasons.push(`━━━ UNIMPLEMENTED / STUBBED (must be fully implemented) ━━━\n${stubNotes.join('\n')}`);
    return `User request: ${request}\n\nThe file ${file.path}${lang ? ` (${lang})` : ''} is incomplete or does not compile.\n\n${reasons.join('\n\n')}\n\n━━━ CURRENT CONTENT ━━━\n${currentContent.substring(0, 6000)}\n\n━━━ SIBLING FILES (their REAL code — match these signatures EXACTLY) ━━━\n${siblingBlock || '  (none)'}\n\n━━━ TASK ━━━\nFix the problems above and return the COMPLETE corrected file for ${file.path}.\n- EVERY method/function you keep MUST have a REAL implementation. NEVER leave a \`// TODO\`/\`FIXME\`, an empty body, or a placeholder \`return false/0/null;\`. A method that only returns a constant without doing its job is NOT finished — implement the actual logic (this game/app must work when run).\n- The sibling code above is AUTHORITATIVE: call only members that exist there, with the EXACT names, parameter types/count, and return types shown. If a call does not match a sibling's real signature, change YOUR call to match it (do not redefine the sibling).\n- Use ${lang || 'this language'}'s NATIVE module semantics. NEVER add JavaScript/TypeScript syntax such as \`import { X } from './y';\`.\n- When the sibling files are in the SAME package / module / directory, reference them DIRECTLY — do NOT add an import statement for them (a same-package import is a compile error in some languages, e.g. Java's default package refuses \`import Foo;\`).\n- Do not change filenames or restructure unrelated code. Keep all existing working behaviour.\nReturn ONLY the file's raw code — no markdown fences, no JSON wrapper, no commentary.`;
}
/**
 * Run the non-TS project gates and, on a compile failure OR a stub/unimplemented
 * body, give the model bounded repair rounds. Deterministic sanitize passes run
 * before the first gate and after every repair round. Mutates `files` in place
 * and rewrites repaired files to `exportDir`.
 */
export async function runNonTsGatesWithRepair(opts) {
    const { request, files, contractFiles, exportDir, timeoutMs, canRepair, consumeRepair, repairCall } = opts;
    const scaffoldSuppliesEntry = opts.scaffoldSuppliesEntry === true;
    const log = opts.log ?? ((msg, level = 'info') => (level === 'warn' ? console.warn(msg) : console.log(msg)));
    const emit = opts.onProgress ?? (() => { });
    const langOf = (p) => {
        const t = contractFiles.find((x) => normalizeContractPath(x.path) === normalizeContractPath(p));
        return (t?.language || '').toLowerCase();
    };
    const sanitizeAll = () => {
        let n = 0;
        for (const f of files) {
            const lang = resolveGateLanguage(langOf(f.path), f.path);
            if (!lang)
                continue;
            const fixed = sanitizeNonTsSource(f.content, lang, f.path);
            if (fixed && fixed !== f.content) {
                f.content = fixed;
                try {
                    fs.writeFileSync(safeJoin(exportDir, f.path), fixed, 'utf-8');
                }
                catch { /* noop */ }
                n += 1;
            }
        }
        if (n)
            log(`[nonTsRepair] sanitize: ${n} file(s) fixed (bare imports / truncation)`, 'warn');
        return n;
    };
    /**
     * Deterministic cross-file duplicate-declaration pass (see
     * sandbox/duplicateDeclarations.ts). A shared domain type declared by two
     * nodes is a redeclaration error in Swift/C#/Kotlin/Java; this removes the
     * redundant copy from the non-owner file instead of spending a repair round
     * on a full-file rewrite that is not convergent for this defect class.
     * Returns the failures for the duplicates it could NOT safely resolve.
     */
    const dedupeAll = () => {
        const res = resolveCrossFileDuplicates(files, contractFiles);
        for (const p of res.changedPaths) {
            const f = files.find((w) => normalizeContractPath(w.path) === normalizeContractPath(p));
            if (!f)
                continue;
            try {
                fs.writeFileSync(safeJoin(exportDir, f.path), f.content, 'utf-8');
            }
            catch { /* noop */ }
        }
        for (const n of res.notes) {
            log(`[nonTsRepair] duplicate '${n.symbol}' ${n.action === 'deleted' ? 'removed from' : 'reported in'} ${n.path} (owner ${n.ownerPath})`, 'warn');
        }
        return res.failures;
    };
    /**
     * Fold the duplicates that could not be resolved into the verdict as one
     * attributed gate, so the repair loop fixes them with the OWNER named — the
     * fact a bare `CS0101` never carried.
     */
    const withDuplicateFailures = (gates, failures) => failures.length > 0 ? [...gates, { language: 'duplicate-definitions', clean: false, errors: failures }] : gates;
    const sanitizedPre = sanitizeAll();
    const duplicateFailuresPre = dedupeAll();
    let { languageGates, stubFailures } = await runProjectGates(request, files, contractFiles, scaffoldSuppliesEntry);
    languageGates = withDuplicateFailures(languageGates, duplicateFailuresPre);
    if (sanitizedPre) {
        log(`[nonTsRepair] gates after sanitize: ${languageGates.map((g) => `${g.language}=${g.clean ? 'PASS' : 'FAIL'}`).join(', ') || '(none)'}`);
    }
    let rounds = 0;
    while ((languageGates.some((g) => !g.clean) || stubFailures.length > 0) &&
        rounds < MAX_NONTS_REPAIR_ROUNDS &&
        canRepair()) {
        const compileByFile = groupGateErrorsByFile(languageGates, files);
        const stubByFile = groupStubFailuresByFile(stubFailures, files);
        const failingPaths = [...new Set([...compileByFile.keys(), ...stubByFile.keys()])];
        if (!failingPaths.length)
            break;
        rounds += 1;
        const failingLangs = languageGates
            .filter((g) => !g.clean && g.language !== 'duplicate-definitions')
            .map((g) => g.language)
            .join('/');
        const duplicateCount = languageGates.find((g) => g.language === 'duplicate-definitions')?.errors.length || 0;
        const what = [
            failingLangs ? `${failingLangs} compile error(s)` : '',
            duplicateCount ? `${duplicateCount} duplicate definition(s)` : '',
            stubFailures.length ? `${stubFailures.length} stub/unimplemented` : '',
        ].filter(Boolean).join(' + ');
        log(`[nonTsRepair] repair (round ${rounds}) — ${what}: ${failingPaths.join(', ')}`, 'warn');
        emit({ phase: 'validating', percent: 93, message: `Fixing ${what}…` });
        let changed = false;
        for (const filePath of failingPaths) {
            if (!canRepair())
                break;
            const cf = files.find((w) => normalizeContractPath(w.path) === normalizeContractPath(filePath));
            if (!cf)
                continue;
            const compiled = compileByFile.get(filePath) || [];
            const stub = stubByFile.get(filePath) || [];
            if (!compiled.length && !stub.length)
                continue;
            const planned = contractFiles.find((t) => normalizeContractPath(t.path) === normalizeContractPath(cf.path))
                || { path: cf.path, summary: '', language: '' };
            const siblingFiles = files
                .filter((w) => normalizeContractPath(w.path) !== normalizeContractPath(cf.path))
                .map((w) => ({
                path: w.path,
                content: w.content,
                language: contractFiles.find((t) => normalizeContractPath(t.path) === normalizeContractPath(w.path))?.language,
            }));
            consumeRepair();
            const prompt = buildNonTsRepairPrompt(request, planned, cf.content, { compilerErrors: compiled, stubNotes: stub }, siblingFiles);
            const content = await repairCall(prompt);
            if (content && content !== cf.content) {
                cf.content = content;
                try {
                    fs.writeFileSync(safeJoin(exportDir, cf.path), content, 'utf-8');
                }
                catch { /* noop */ }
                changed = true;
            }
        }
        sanitizeAll();
        const duplicateFailures = dedupeAll();
        const regate = await runProjectGates(request, files, contractFiles, scaffoldSuppliesEntry);
        languageGates = withDuplicateFailures(regate.languageGates, duplicateFailures);
        stubFailures = regate.stubFailures;
        if (!changed)
            break;
    }
    return { languageGates, stubFailures, rounds, sanitized: sanitizedPre > 0 };
}
