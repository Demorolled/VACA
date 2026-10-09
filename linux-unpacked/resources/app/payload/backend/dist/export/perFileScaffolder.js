/**
 * PerFileScaffolder — scaffolds a project directory using per-node files
 * from the FileGenerator instead of 3 monolithic layers.
 *
 * Each architecture node becomes its own standalone source file with
 * proper imports/exports, organized into a clean directory structure.
 *
 * TREE MODE: a project with several app trees is exported as several SEPARATE
 * APPS — one `apps/<app>/` directory per tree (own src/, entry point and
 * project config) plus one shared `bridge/` directory for the cross-app
 * integration modules. A single-tree project keeps the flat `src/` layout, so
 * pre-Tree-Mode exports are unchanged. The layout itself lives in
 * `utils/treeScope.ts` (planExportLayout / exportDirFor) and is shared with the
 * generator's compile gate, so what compiled during generation is exactly what
 * lands on disk here.
 */
import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';
import { labelToFileName } from '../layers/fileGenerator.js';
import { planExportLayout, exportDirFor, resolveTreeScopes, planBridges, } from '../utils/treeScope.js';
const EXPORTS_DIR = path.resolve(process.cwd(), 'exports');
/** Escape a string for use inside a RegExp. */
function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
/** Escape a value for a C/C++ double-quoted string literal. */
function escapeForCString(s) {
    return (s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n');
}
/** Escape a value for a PHP double-quoted string literal. */
function escapeForPhpString(s) {
    return (s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\$/g, '\\$').replace(/\n/g, '\\n');
}
/** Escape a value for a single-quoted string (Ruby). */
function escapeForSingleQuoted(s) {
    return (s || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n');
}
/**
 * The Python module name for a node label. Python identifiers cannot contain
 * '-', so the exported DIRECTORY, the written FILE and the entry point's
 * import must all agree on this one name.
 *
 * They previously did not: the directory was underscored (safeName), but the
 * file kept the raw name (`arg-parser.py`) and the generated `__init__.py`
 * re-exported from it — `from .arg-parser import *` is a hard SyntaxError, so
 * the whole package was unimportable (measured on the generated Python
 * temperature-converter app: `python3 main.py` died at import time).
 *
 * A leading digit is prefixed with '_' for the same reason (`2d-renderer` is
 * not an importable name either).
 */
export function pythonModuleName(label) {
    const name = labelToFileName(label).replace(/-/g, '_');
    return /^[0-9]/.test(name) ? `_${name}` : name;
}
/** Strip Python comments and string literals (incl. docstrings) before scanning. */
function stripPythonCommentsAndStrings(code) {
    return (code || '')
        .replace(/"""[\s\S]*?"""/g, '""')
        .replace(/'''[\s\S]*?'''/g, "''")
        .replace(/(^|[^\\])#[^\n]*/g, '$1')
        .replace(/"(?:[^"\\\n]|\\.)*"/g, '""')
        .replace(/'(?:[^'\\\n]|\\.)*'/g, "''");
}
// ── Entry-point wiring for compiled languages ────────────────────────────────
// A generated node module is arbitrary LLM-authored code: its API (names,
// arities, return types) is unknown to the scaffolder. So an entry point may
// only CALL a function whose signature was read out of that very file — and
// only a no-argument one, which is the sole call the scaffolder can make
// without inventing arguments. Where nothing callable can be proven it merely
// REFERENCES the module (its type, or a function item) so the module is still
// compiled and linked into the build. Nothing is ever guessed: when a file
// yields neither, the entry point keeps its banner-only behaviour.
/** Names that make a no-argument function a plausible program entry. */
const MODULE_ENTRY_FN_NAMES = new Set([
    'main', 'run', 'start', 'startup', 'boot', 'launch', 'execute', 'exec',
    'process', 'init', 'initialize', 'setup', 'demo', 'app', 'cli', 'selftest',
]);
/** C/C++ names that already belong to the C library — never re-declare them. */
const C_RESERVED_NAMES = new Set([
    'main', 'printf', 'fprintf', 'sprintf', 'snprintf', 'puts', 'putchar',
    'getchar', 'scanf', 'malloc', 'calloc', 'realloc', 'free', 'exit', 'abort',
    'strlen', 'strcmp', 'strcpy', 'strncpy', 'strcat', 'memset', 'memcpy',
    'fopen', 'fclose', 'fgets', 'fputs', 'atoi', 'atof', 'rand', 'srand',
]);
/** Prefer a conventionally named entry (`run`, `start`, `main`…) over any other. */
function pickEntryCallable(candidates) {
    if (candidates.length === 0)
        return null;
    return candidates.find((c) => MODULE_ENTRY_FN_NAMES.has(c.name.toLowerCase())) || candidates[0];
}
/**
 * Drop comments and string/char literals so declaration regexes cannot match
 * text inside them (`// void helper() {` or a log string mentioning a call).
 */
function stripCommentsAndStrings(code) {
    return (code || '')
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/\/\/[^\n]*/g, '')
        .replace(/"(?:[^"\\\n]|\\.)*"/g, '""')
        .replace(/'(?:[^'\\\n]|\\.)*'/g, "''");
}
/** Zero-parameter exported Go funcs — `func Name() {}` / `func Name() T {}`. */
export function goNoArgFuncs(code) {
    const out = [];
    const re = /^func\s+([A-Z][A-Za-z0-9_]*)\s*\(\s*\)\s*([^{]*?)\{/gm;
    let m;
    while ((m = re.exec(stripCommentsAndStrings(code))) !== null) {
        // A non-empty result list means the call returns a value (`_ = pkg.F()`).
        out.push({ name: m[1], returnType: m[2].trim() });
    }
    return out;
}
/** Zero-parameter `pub fn` items in a Rust module. */
export function rustNoArgFuncs(code) {
    const out = [];
    const re = /^pub\s+fn\s+([a-z_][A-Za-z0-9_]*)\s*\(\s*\)\s*(->[^{]*?)?\{/gm;
    let m;
    while ((m = re.exec(stripCommentsAndStrings(code))) !== null) {
        out.push({ name: m[1], returnType: (m[2] || '').trim() });
    }
    return out;
}
/** Any `pub fn` name — referencing a function ITEM compiles for any signature. */
export function rustPublicFns(code) {
    const out = [];
    const re = /^pub\s+fn\s+([a-z_][A-Za-z0-9_]*)/gm;
    let m;
    while ((m = re.exec(stripCommentsAndStrings(code))) !== null)
        out.push(m[1]);
    return out;
}
/**
 * Top-level, non-static, no-argument function definitions in C/C++.
 *
 * Deliberately conservative: the return type is limited to plain scalars,
 * `struct X` and pointers/references, so a `std::vector<int> f()` or a
 * multi-line signature is simply skipped rather than mis-declared.
 */
export function cNoArgFuncs(code, lang) {
    const typePart = '(?:const\\s+|unsigned\\s+|signed\\s+|long\\s+|short\\s+|struct\\s+)*[A-Za-z_]\\w*' +
        (lang === 'cpp' ? '(?:::[A-Za-z_]\\w*)*(?:\\s*[*&]+)?' : '(?:\\s*\\*+)?');
    const re = new RegExp(`^(${typePart})\\s+([A-Za-z_]\\w*)\\s*\\(\\s*(?:void)?\\s*\\)\\s*\\{`, 'gm');
    const out = [];
    let m;
    while ((m = re.exec(stripCommentsAndStrings(code))) !== null) {
        if (C_RESERVED_NAMES.has(m[2]) || m[2].startsWith('_'))
            continue;
        out.push({ name: m[2], returnType: m[1].trim() });
    }
    return out;
}
/** The class a Java file declares (javac: the public class matches the file name). */
export function javaModuleType(code) {
    const m = /^(?:public\s+|final\s+|abstract\s+|sealed\s+|non-sealed\s+)*class\s+([A-Za-z_]\w*)/m.exec(stripCommentsAndStrings(code));
    return m ? m[1] : null;
}
/** No-argument `static` Java methods — the only members an entry can call blindly. */
export function javaStaticNoArgFuncs(code) {
    const out = [];
    const re = /^\s*(?:public\s+|protected\s+|private\s+)?static\s+(?:final\s+)?(?:synchronized\s+)?([A-Za-z_][\w<>\[\],.? ]*?)\s+([A-Za-z_]\w*)\s*\(\s*\)\s*(?:throws\s+[\w., ]+)?\{/gm;
    let m;
    while ((m = re.exec(stripCommentsAndStrings(code))) !== null) {
        out.push({ name: m[2], returnType: m[1].trim(), member: true });
    }
    return out;
}
/** The class/struct/record a C# file declares. */
export function csharpModuleType(code) {
    const m = /^\s*(?:public\s+|internal\s+|static\s+|sealed\s+|abstract\s+|partial\s+)*class\s+([A-Za-z_]\w*)/m.exec(stripCommentsAndStrings(code));
    return m ? m[1] : null;
}
/** No-argument `static` C# methods — the only members an entry can call blindly. */
export function csharpStaticNoArgFuncs(code) {
    const out = [];
    const re = /^\s*(?:public\s+|internal\s+|private\s+|protected\s+)?static\s+([A-Za-z_][\w<>\[\],?. ]*?)\s+([A-Za-z_]\w*)\s*\(\s*\)\s*\{/gm;
    let m;
    while ((m = re.exec(stripCommentsAndStrings(code))) !== null) {
        out.push({ name: m[2], returnType: m[1].trim(), member: true });
    }
    return out;
}
/** The type a Swift file declares (`class`/`struct`/`enum`/`actor`). */
export function swiftModuleType(code) {
    const m = /^\s*(?:public\s+|internal\s+|private\s+|fileprivate\s+|final\s+|open\s+)*(?:class|struct|enum|actor)\s+([A-Za-z_]\w*)/m.exec(stripCommentsAndStrings(code));
    return m ? m[1] : null;
}
/** No-argument Swift functions: column-0 (module-wide) and indented `static` ones. */
export function swiftNoArgFuncs(code) {
    const text = stripCommentsAndStrings(code);
    const out = [];
    const top = /^func\s+([A-Za-z_]\w*)\s*\(\s*\)\s*(?:->\s*[^{]*?)?\{/gm;
    let m;
    while ((m = top.exec(text)) !== null)
        out.push({ name: m[1], returnType: '' });
    const statics = /^\s+(?:public\s+|internal\s+|private\s+)?(?:static|class)\s+func\s+([A-Za-z_]\w*)\s*\(\s*\)\s*(?:->\s*[^{]*?)?\{/gm;
    while ((m = statics.exec(text)) !== null)
        out.push({ name: m[1], returnType: '', member: true });
    return out;
}
/** The type a Kotlin file declares (`class`/`object`). */
export function kotlinModuleType(code) {
    const m = /^\s*(?:(?:public|internal|private|open|data|sealed|abstract|value|annotation|enum)\s+)*(?:class|object)\s+([A-Za-z_]\w*)/m.exec(stripCommentsAndStrings(code));
    return m ? m[1] : null;
}
/** Column-0 Kotlin functions — same module as the entry, so callable directly. */
export function kotlinTopLevelFuncs(code) {
    const out = [];
    const re = /^fun\s+([A-Za-z_]\w*)\s*\(\s*\)\s*\{/gm;
    let m;
    while ((m = re.exec(stripCommentsAndStrings(code))) !== null) {
        out.push({ name: m[1], returnType: '' });
    }
    return out;
}
/** Column-0, zero-parameter `def`s in a Python module — the entry a caller can
 *  invoke without inventing arguments. */
export function pythonNoArgFuncs(code) {
    const out = [];
    const re = /^def\s+([A-Za-z_]\w*)\s*\(\s*\)\s*(?:->[^:\n]*)?:/gm;
    let m;
    while ((m = re.exec(stripPythonCommentsAndStrings(code))) !== null) {
        out.push({ name: m[1], returnType: '' });
    }
    return out;
}
/** Ruby: drop `#` comments and string literals before scanning declarations. */
function stripRubyCommentsAndStrings(code) {
    return (code || '')
        .replace(/"(?:[^"\\\n]|\\.)*"/g, '""')
        .replace(/'(?:[^'\\\n]|\\.)*'/g, "''")
        .replace(/#[^\n]*/g, '');
}
/**
 * Column-0, zero-parameter `def`s in a Ruby file.
 *
 * Ruby allows the parens to be omitted (`def run`), so both shapes are accepted;
 * a parameter list — even `()`-less — disqualifies the entry, because the scaffold
 * cannot invent arguments for it. Methods nested in a `module`/`class` are not
 * matched: they are not callable from the entry point without a receiver.
 */
export function rubyNoArgFuncs(code) {
    const out = [];
    const re = /^def\s+([A-Za-z_]\w*[!?=]?)\s*(?:\(\s*\))?\s*$/gm;
    let m;
    while ((m = re.exec(stripRubyCommentsAndStrings(code))) !== null) {
        out.push({ name: m[1], returnType: '' });
    }
    return out;
}
/**
 * Plan the wiring lines an entry point emits for one node module.
 *
 * `moduleName` is the reference the language needs (a Rust `mod` identifier, a
 * Java/C#/Swift/Kotlin type name, or '' for C/C++ where the symbol is global).
 * `index` only makes generated local names unique.
 */
export function planModuleWiring(language, code, moduleName, index) {
    const declarations = [];
    const references = [];
    const calls = [];
    const lang = (language || '').toLowerCase();
    switch (lang) {
        case 'c':
        case 'cpp': {
            const fn = pickEntryCallable(cNoArgFuncs(code, lang));
            if (fn) {
                // Re-declared with the signature copied from the node file, so the
                // prototype can never disagree with the linked definition.
                declarations.push(`extern ${fn.returnType} ${fn.name}(void);`);
                calls.push(`(void)${fn.name}();`);
            }
            break;
        }
        case 'rust': {
            const fn = pickEntryCallable(rustNoArgFuncs(code));
            if (fn)
                calls.push(`let _ = ${moduleName}::${fn.name}();`);
            else {
                const pub = rustPublicFns(code)[0];
                if (pub)
                    references.push(`let _ = ${moduleName}::${pub};`);
            }
            break;
        }
        case 'java': {
            const cls = moduleName || javaModuleType(code);
            if (cls) {
                references.push(`Class<?> _module${index} = ${cls}.class;`);
                const fn = pickEntryCallable(javaStaticNoArgFuncs(code));
                if (fn)
                    calls.push(`${cls}.${fn.name}();`);
            }
            break;
        }
        case 'csharp': {
            const cls = moduleName || csharpModuleType(code);
            if (cls) {
                references.push(`var _module${index} = typeof(${cls});`);
                const fn = pickEntryCallable(csharpStaticNoArgFuncs(code));
                if (fn)
                    calls.push(`${cls}.${fn.name}();`);
            }
            break;
        }
        case 'swift': {
            const cls = moduleName || swiftModuleType(code);
            if (cls)
                references.push(`_ = ${cls}.self`);
            const fn = pickEntryCallable(swiftNoArgFuncs(code));
            if (fn)
                calls.push(fn.member && cls ? `${cls}.${fn.name}()` : `${fn.name}()`);
            break;
        }
        case 'kotlin': {
            const cls = moduleName || kotlinModuleType(code);
            if (cls)
                references.push(`val _module${index} = ${cls}::class`);
            const fn = pickEntryCallable(kotlinTopLevelFuncs(code));
            if (fn)
                calls.push(`${fn.name}()`);
            break;
        }
        case 'python': {
            // The call is QUALIFIED with the module (`arg_parser.main()`), never a
            // bare name: every CLI node calls its entry `main`, so unqualified calls
            // would resolve to whichever star-import came last and run one node's
            // work several times.
            const fn = pickEntryCallable(pythonNoArgFuncs(code));
            if (fn)
                calls.push(`${moduleName}.${fn.name}()`);
            break;
        }
        case 'ruby': {
            // Ruby has no per-file namespace: a top-level `def` lands on Object, so the
            // call is bare. A file whose only entry takes arguments (`def main(input,
            // output)`) contributes nothing — the same limit Python has.
            const fn = pickEntryCallable(rubyNoArgFuncs(code));
            if (fn)
                calls.push(`${fn.name}()`);
            break;
        }
        default:
            break;
    }
    return { declarations, references, calls };
}
/**
 * Languages whose scaffold entry file a node can TAKE OVER: the entry file is
 * not required to carry a fixed name by the toolchain, and the build globs its
 * sources, so simply not writing it is a complete fix.
 *
 *   c / cpp  — every translation unit links into one binary, so a node `main`
 *              and the scaffold's main.c collide (`ld: multiple definition of
 *              'main'`).
 *   csharp   — the SDK csproj globs every .cs file, so a node's `class Program {
 *              static Main }` collides with the scaffold's Program.cs
 *              (`CS0101: already contains a definition for 'Program'` and
 *              `CS0111: Type 'Program' already defines a member called
 *              'Main'`) — measured live on the generated expense-tracker app.
 *   kotlin   — kotlinc compiles the file set as one module, so a node's
 *              `fun main()` and Main.kt's `fun main()` are a conflicting
 *              overload.
 *
 * Swift is deliberately excluded: only a file named `main.swift` may hold
 * top-level statements, so a node file cannot become the entry point.
 */
const PROMOTABLE_ENTRY_LANGS = new Set(['c', 'cpp', 'csharp', 'kotlin']);
/** True when a node file declares the PROGRAM's entry point for its language. */
export function declaresProgramEntry(code, language) {
    const lang = (language || '').toLowerCase();
    const text = stripCommentsAndStrings(code);
    switch (lang) {
        case 'c':
        case 'cpp':
            return /^[ \t]*(?:int|void)\s+main\s*\(/m.test(text);
        case 'csharp':
            // The same shape the C# gate accepts as an entry point.
            return /\bstatic\s+(?:async\s+)?(?:void|int|Task(?:<int>)?)\s+Main\s*\(/.test(text);
        case 'kotlin':
            return /^fun\s+main\s*\(/m.test(text);
        default:
            return false;
    }
}
export class PerFileScaffolder {
    /**
     * Scaffold a project using per-node files from the FileGenerator.
     * Each file is written to an organized directory structure.
     */
    async scaffold(config) {
        const sanitized = this.sanitizeName(config.projectName);
        const defaultDir = path.join(EXPORTS_DIR, `${sanitized}-perfile-${Date.now()}`);
        // Expand "~" / "~/..." to the user's home dir (matches validate-path).
        const rawDir = config.outputDir;
        const customDir = rawDir
            ? rawDir === '~'
                ? os.homedir()
                : rawDir.startsWith('~/')
                    ? path.join(os.homedir(), rawDir.slice(2))
                    : rawDir
            : undefined;
        let outputDir = customDir
            ? path.resolve(customDir, sanitized)
            : defaultDir;
        // A custom output path may be unwritable (e.g. EACCES on a root-owned dir
        // like /home/desktop, or ENOENT on a missing parent). Don't fail the whole
        // build with a bare 500 — fall back to the default exports/ dir and tell
        // the user so they know where their files actually landed.
        let warning;
        try {
            await fs.mkdir(outputDir, { recursive: true });
        }
        catch (err) {
            const reason = err?.code || err?.message || 'permission denied';
            console.warn(`[PerFileScaffolder] Custom output dir "${outputDir}" unwritable (${reason}) — falling back to ${defaultDir}`);
            outputDir = defaultDir;
            warning = `Custom output path "${config.outputDir}" could not be created (${reason}). Files were written to the default exports directory instead.`;
            await fs.mkdir(outputDir, { recursive: true });
        }
        const created = [];
        const perNodeFiles = [];
        // ── Tree Mode: several app trees ⇒ several APPS ──
        // A second app tree is a second program, not another module: each tree is
        // exported into its own `apps/<app>/` directory (own src/, entry point and
        // project config), and every cross-app handoff lives in one shared
        // `bridge/` directory. We also stamp the app directory onto each file here,
        // so a build that predates the layout (no `appDir` from the generator) still
        // lands in the right app instead of collapsing into one flat src/.
        const trees = Array.isArray(config.trees) ? config.trees : [];
        const layout = planExportLayout(trees);
        const scoped = resolveTreeScopes({
            nodes: (config.nodes || []),
            edges: (config.edges || []),
            trees,
            name: config.projectName,
        });
        const files = config.files.map((f) => this.withLayout(f, layout));
        const bridgeFiles = files.filter((f) => f.isBridge);
        /** Where each file actually landed on disk (used to document a promoted entry). */
        const relPathByFile = new Map();
        // ── Write per-node source files ──
        for (const file of files) {
            const nodeLabel = file.nodeLabel || 'unknown';
            const isPython = (file.language || '').toLowerCase() === 'python';
            // Directory name MUST match the import paths the generator emitted
            // (../<labelToFileName(dep)>/<file>.ts) — sanitizeName kept the label's
            // extension ('timer-input.ts' → 'timer-input-ts'), which broke every
            // cross-file import in exported projects (TS2307). labelToFileName
            // strips the extension first, matching buildImportStatement/runTscCheck.
            // Python can't import hyphenated directory names — use underscores.
            const safeName = isPython ? pythonModuleName(nodeLabel) : labelToFileName(nodeLabel);
            // `src/<safeName>/` for one app; `apps/<app>/src/<safeName>/` for many;
            // `bridge/` for an integration module. Shared with the generator's tsc
            // gate (see utils/treeScope → exportDirFor).
            const relDir = exportDirFor(file, safeName);
            const nodeDir = path.join(outputDir, ...relDir.split('/'));
            await fs.mkdir(nodeDir, { recursive: true });
            // A Python FILE name is a module name too: `arg-parser.py` can neither be
            // imported nor re-exported (`from .arg-parser import *` is a SyntaxError).
            // Write it under the same underscored name the directory/entry point use,
            // so `import arg_parser` finds the module.
            const writtenName = isPython ? `${safeName}.py` : file.fileName;
            const filePath = path.join(nodeDir, writtenName);
            await fs.writeFile(filePath, file.code, 'utf-8');
            // For Python, create an __init__.py that re-exports from the main file
            if (isPython) {
                const initContent = `from .${safeName} import *  # Auto-generated: re-export all from this node
`;
                const initPath = path.join(nodeDir, '__init__.py');
                await fs.writeFile(initPath, initContent, 'utf-8');
                created.push(`${relDir}/__init__.py`);
            }
            const relPath = `${relDir}/${writtenName}`;
            relPathByFile.set(file, relPath);
            created.push(relPath);
            perNodeFiles.push({
                nodeId: file.nodeId,
                nodeLabel: file.nodeLabel,
                filePath: relPath,
                fileName: writtenName,
                validated: file.validated,
            });
        }
        // ── Write dependency graph metadata ──
        const appDirByTreeId = (treeId) => {
            const dirName = layout.appDirByTree[treeId];
            return dirName ? `apps/${dirName}` : undefined;
        };
        const graphData = {
            projectName: config.projectName,
            targetOS: config.targetOS,
            // Tree Mode: the app trees and where each one was laid out. Absent for a
            // single-app project, whose export is unchanged.
            ...(layout.separateApps && trees.length > 0
                ? {
                    apps: trees.map((t) => ({
                        id: t.id,
                        name: t.name,
                        goal: t.goal,
                        dir: appDirByTreeId(t.id),
                    })),
                }
                : {}),
            nodes: files.map(f => ({
                nodeId: f.nodeId,
                nodeLabel: f.nodeLabel,
                fileName: f.fileName,
                language: f.language,
                dependencies: f.dependencies,
                exports: f.exports,
                validated: f.validated,
                ...(f.treeId ? { treeId: f.treeId } : {}),
                ...(f.appDir ? { appDir: f.appDir } : {}),
                ...(f.isBridge ? { isBridge: true, treeIds: f.treeIds || [] } : {}),
            })),
            edges: config.edges.map(e => {
                const d = e.data || {};
                // Tree Mode: an edge whose endpoints sit in different app trees is a
                // data handoff between two separate programs, not a file import. Keep
                // it and the payload the user described — the bridges realize it.
                const isCrossTree = d.kind === 'cross-tree'
                    || (typeof d.sourceTreeId === 'string' && typeof d.targetTreeId === 'string' && d.sourceTreeId !== d.targetTreeId);
                return {
                    source: e.source,
                    target: e.target,
                    // Keep user-described semantic wiring (from the Connect & Describe
                    // dialog) in the scaffold so the connection intent survives export.
                    ...(d.semantic
                        ? {
                            label: d.label,
                            relation: d.relation,
                            codeHint: d.codeHint,
                            sourceHint: d.sourceHint,
                            targetHint: d.targetHint,
                            semantic: true,
                        }
                        : {}),
                    ...(isCrossTree
                        ? {
                            kind: 'cross-tree',
                            sourceTreeId: d.sourceTreeId,
                            targetTreeId: d.targetTreeId,
                            payloadType: d.payloadType,
                            payloadLabel: d.payloadLabel,
                            ...(d.payloadDetail ? { payloadDetail: d.payloadDetail } : {}),
                            ...(d.description ? { description: d.description } : {}),
                        }
                        : {}),
                };
            }),
            // Tree Mode: the integration modules that carry the handoffs above.
            ...(bridgeFiles.length > 0
                ? {
                    bridges: bridgeFiles.map((f) => ({
                        fileName: f.fileName,
                        path: `bridge/${f.fileName}`,
                        treeIds: f.treeIds || [],
                        exports: f.exports,
                        validated: f.validated,
                    })),
                }
                : {}),
        };
        await fs.writeFile(path.join(outputDir, 'dependency-graph.json'), JSON.stringify(graphData, null, 2), 'utf-8');
        created.push('dependency-graph.json');
        // ── Detect primary language across all generated files ──
        const primaryLang = this.detectPrimaryLanguage(files);
        const entryFileName = this.getEntryFileName(primaryLang);
        // Set in the flat branch below when one node file owns the program entry.
        let entryOwner = null;
        if (layout.separateApps) {
            // ── Tree Mode: one self-contained program PER APP ──
            // Each app gets its own entry point and project config inside its own
            // directory, so `cd apps/<app> && npm start` runs THAT app. The entry
            // point imports only that app's modules (the entry builders emit
            // `./src/<module>/<file>`, which resolves identically from the app dir).
            const appDirs = [...new Set(files.filter((f) => !f.isBridge && f.appDir).map((f) => f.appDir))];
            for (const appDir of appDirs) {
                const appFiles = files.filter((f) => !f.isBridge && f.appDir === appDir);
                const tree = trees.find((t) => appDirByTreeId(t.id) === appDir);
                const appLang = this.detectPrimaryLanguage(appFiles);
                const appEntryFileName = this.getEntryFileName(appLang);
                const appConfig = {
                    ...config,
                    files: appFiles,
                    // A UI node in one app must not suppress the bootstrap of a CLI app
                    // beside it — the UI check is per app, not per project.
                    nodes: (config.nodes || []).filter((n) => scoped.treeIdByNode.get(n.id) === tree?.id),
                    entryBridges: this.bridgesForApp(appDir, tree?.id, bridgeFiles),
                };
                const appEntryCode = this.buildEntryPoint(appConfig, appLang);
                const appPath = path.join(outputDir, ...appDir.split('/'));
                await fs.writeFile(path.join(appPath, appEntryFileName), appEntryCode, 'utf-8');
                created.push(`${appDir}/${appEntryFileName}`);
                for (const [fileName, content] of Object.entries(this.buildProjectConfig(appConfig, appLang))) {
                    await fs.writeFile(path.join(appPath, fileName), content, 'utf-8');
                    created.push(`${appDir}/${fileName}`);
                    // Make startup scripts executable
                    if (fileName === 'start.sh') {
                        await fs.chmod(path.join(appPath, fileName), 0o755);
                    }
                }
            }
        }
        else {
            // ── A node that IS the program (C/C++) ──
            // A node file that declares `main` and the scaffold's own main.c both
            // define it, and the link fails (`ld: multiple definition of 'main'` —
            // measured on the generated C word-counter app). When exactly one node
            // owns the entry point, it IS the app: emit no second entry, and let the
            // Makefile compile every source it finds (no hard-coded main.c).
            entryOwner = this.promotedEntryOwner(files, primaryLang);
            if (entryOwner) {
                const ownerRel = relPathByFile.get(entryOwner) || entryOwner.fileName;
                created.push(`${ownerRel}   # program entry point (defines main) — no separate ${entryFileName}`);
                console.log(`[PerFileScaffolder] "${entryOwner.nodeLabel}" defines main() — promoted to the program entry point (no ${entryFileName} emitted)`);
            }
            else {
                // ── Write entry point matching the primary language ──
                const entryCode = this.buildEntryPoint(config, primaryLang);
                await fs.writeFile(path.join(outputDir, entryFileName), entryCode, 'utf-8');
                created.push(entryFileName);
            }
            // ── Write project config files matching the primary language ──
            const projectConfigFiles = this.buildProjectConfig(config, primaryLang, !!entryOwner);
            for (const [fileName, content] of Object.entries(projectConfigFiles)) {
                await fs.writeFile(path.join(outputDir, fileName), content, 'utf-8');
                created.push(fileName);
                // Make startup scripts executable
                if (fileName === 'start.sh') {
                    await fs.chmod(path.join(outputDir, fileName), 0o755);
                }
            }
        }
        // ── Write README ──
        const readme = this.buildReadme(config, primaryLang, entryFileName, {
            entryOwner,
            entryOwnerRel: entryOwner ? relPathByFile.get(entryOwner) || entryOwner.fileName : undefined,
        });
        await fs.writeFile(path.join(outputDir, 'README.md'), readme, 'utf-8');
        created.push('README.md');
        // ── Write .gitignore ──
        const gitignore = this.buildGitignore(primaryLang);
        await fs.writeFile(path.join(outputDir, '.gitignore'), gitignore, 'utf-8');
        created.push('.gitignore');
        return {
            success: true,
            outputPath: outputDir,
            files: created,
            message: `Per-file project scaffolded at ${outputDir} — ${created.length} files created (${config.files.length} per-node source files).`,
            ...(warning ? { warning } : {}),
            perNodeFiles,
        };
    }
    /**
     * Stamp the app directory onto a generated file when the generator did not
     * (a cached build from before the Tree Mode layout, or a caller handing the
     * scaffolder raw files). The app comes from the file's own `appDir`, or from
     * its `treeId` via the layout. Bridges and single-app builds are untouched.
     */
    withLayout(file, layout) {
        if (file.isBridge || file.appDir || !layout.separateApps)
            return file;
        const dirName = (file.treeId && layout.appDirByTree[file.treeId]) || Object.values(layout.appDirByTree)[0];
        return dirName ? { ...file, appDir: `apps/${dirName}` } : file;
    }
    /**
     * The bridge modules an app's entry point should expose: every bridge that
     * connects this app tree to another one. The specifier is the real relative
     * path from the app directory to the shared bridge directory
     * (`../../bridge/<file>`), so the wiring resolves as written.
     */
    bridgesForApp(appDir, treeId, bridges) {
        if (!treeId)
            return [];
        return bridges
            .filter((b) => (b.treeIds || []).includes(treeId))
            .map((b) => ({
            importPath: path.posix.relative(appDir, `bridge/${b.fileName}`),
            alias: this.toIdentifier(b.nodeLabel || b.fileName),
        }));
    }
    /** `bridge-auth-session` → `bridgeAuthSession` (a legal TS binding name). */
    toIdentifier(name) {
        const camel = (name || '')
            .split(/[^a-zA-Z0-9]+/)
            .filter(Boolean)
            .map((part, i) => (i === 0 ? part : part.charAt(0).toUpperCase() + part.slice(1)))
            .join('');
        if (!camel)
            return 'bridge';
        return /^[0-9]/.test(camel) ? `_${camel}` : camel;
    }
    /**
     * The node file that owns the program's entry point, or null when none does.
     *
     * A node that declares the entry point already gives the toolchain a program,
     * so the scaffold's own entry can only CONFLICT with it — it never adds
     * anything. That is why the scaffold steps aside for ANY number of owners
     * (the first one, in file order, is reported in the README): with two or more
     * owners the build is a genuine generation defect the compile gate must
     * report, and emitting a third competing entry (or a Kotlin `Main.kt` that
     * calls the ambiguous `main()`) would hide the real cause behind our own
     * error. Languages whose toolchain requires a FIXED entry file name are not
     * promotable at all — see PROMOTABLE_ENTRY_LANGS.
     */
    promotedEntryOwner(files, primaryLang) {
        if (!PROMOTABLE_ENTRY_LANGS.has(primaryLang))
            return null;
        const owners = files.filter((f) => !f.isBridge
            && (f.language || '').toLowerCase() === primaryLang
            && declaresProgramEntry(f.code, primaryLang));
        return owners.length > 0 ? owners[0] : null;
    }
    /**
     * Detect the primary language across all generated files.
     * Falls back to 'typescript' if no files or mixed.
     */
    detectPrimaryLanguage(files) {
        if (files.length === 0)
            return 'typescript';
        const counts = new Map();
        for (const f of files) {
            const lang = (f.language || 'typescript').toLowerCase();
            counts.set(lang, (counts.get(lang) || 0) + 1);
        }
        let maxCount = 0;
        let primary = 'typescript';
        for (const [lang, count] of counts) {
            if (count > maxCount) {
                maxCount = count;
                primary = lang;
            }
        }
        return primary;
    }
    /**
     * Get the entry point file name for a given language.
     */
    getEntryFileName(language) {
        switch (language) {
            case 'go': return 'main.go';
            case 'rust': return 'main.rs';
            case 'python': return 'main.py';
            case 'java': return 'Main.java'; // javac requires class name == file name
            case 'c': return 'main.c';
            case 'cpp': return 'main.cpp';
            case 'csharp': return 'Program.cs';
            case 'php': return 'index.php';
            case 'ruby': return 'main.rb';
            case 'swift': return 'main.swift';
            case 'kotlin': return 'Main.kt';
            default: return 'index.ts';
        }
    }
    /**
     * Build an entry point that imports and wires all nodes together,
     * matching the primary project language.
     */
    buildEntryPoint(config, primaryLang) {
        switch (primaryLang) {
            case 'go': return this.buildGoEntryPoint(config);
            case 'rust': return this.buildRustEntryPoint(config);
            case 'python': return this.buildPythonEntryPoint(config);
            case 'java': return this.buildJavaEntryPoint(config);
            case 'c': return this.buildCEntryPoint(config);
            case 'cpp': return this.buildCppEntryPoint(config);
            case 'csharp': return this.buildCsharpEntryPoint(config);
            case 'php': return this.buildPhpEntryPoint(config);
            case 'ruby': return this.buildRubyEntryPoint(config);
            case 'swift': return this.buildSwiftEntryPoint(config);
            case 'kotlin': return this.buildKotlinEntryPoint(config);
            default: return this.buildTsEntryPoint(config);
        }
    }
    /**
     * Build a TypeScript entry point (index.ts) with standard imports.
     */
    buildTsEntryPoint(config) {
        const lines = [];
        lines.push('/**');
        lines.push(` * ${config.projectName} — Auto-generated entry point`);
        lines.push(' * Generated by Veronica (VACA)');
        lines.push(' * Each node is a standalone file in src/');
        lines.push(' */');
        lines.push('');
        // Import each TS/JS file. A file with NO detected exports is imported for
        // its side effects — fabricating a name from the label (e.g. `scheme_picker`)
        // breaks `tsc --noEmit` with TS2305/TS2614 because that symbol does not exist.
        // Duplicate export names across files are aliased (main, main_1, ...) so the
        // same symbol is never imported twice in one module (TS2300).
        // Import each TS/JS file. A file with NO detected exports is imported for
        // its side effects — fabricating a name from the label (e.g. `scheme_picker`)
        // breaks `tsc --noEmit` with TS2305/TS2614 because that symbol does not exist.
        // Duplicate export names across files are aliased (main, main_1, ...) so the
        // same symbol is never imported twice in one module (TS2300).
        //
        // TYPE-ONLY exports (interfaces / type aliases) are never imported as
        // values: ESM crashes at runtime with "The requested module ... does not
        // provide an export named 'X'". The first VALUE export is used instead; a
        // file whose exports are all type-only is imported for side effects.
        const isTypeOnlyExport = (name, codeText) => {
            const esc = escapeRegExp(name);
            const typeDecl = new RegExp(`\\bexport\\s+(?:interface|type)\\s+${esc}(?:[^\\w$]|$)`);
            const valueDecl = new RegExp(`\\bexport\\s+(?:function|const|let|var|enum|class|async\\s+function)\\s+${esc}(?:[^\\w$]|$)`);
            return typeDecl.test(codeText) && !valueDecl.test(codeText);
        };
        const importedNames = new Set();
        // Entry-point function names a project can be bootstrapped with. The
        // generation prompt mandates main/start/runApp for CLI/logic entries and
        // render/init/mount/createApp for UI entries — an exported app that only
        // imports and re-exports is dead code (F2 in the build triage).
        const ENTRY_FN_NAMES = new Set([
            'start', 'main', 'runApp', 'bootstrap', 'run',
            'render', 'init', 'mount', 'createApp', 'setup',
        ]);
        let entryAlias = null;
        for (const file of config.files) {
            const lang = (file.language || '').toLowerCase();
            if (lang !== 'typescript' && lang !== 'javascript')
                continue;
            const safeName = labelToFileName(file.nodeLabel);
            const codeText = file.code || '';
            const firstExport = (file.exports || []).find(e => typeof e === 'string' && e.trim() !== '' && !isTypeOnlyExport(e, codeText));
            if (!firstExport) {
                lines.push(`import './src/${safeName}/${file.fileName}';`);
                continue;
            }
            let local = firstExport;
            if (importedNames.has(firstExport)) {
                let i = 1;
                while (importedNames.has(`${firstExport}_${i}`))
                    i++;
                local = `${firstExport}_${i}`;
            }
            importedNames.add(local);
            lines.push(`import { ${firstExport} as ${local} } from './src/${safeName}/${file.fileName}';`);
            if (entryAlias === null && ENTRY_FN_NAMES.has(firstExport)) {
                entryAlias = local;
            }
        }
        // Add comments for non-TS files
        for (const file of config.files) {
            const lang = (file.language || '').toLowerCase();
            if (lang === 'typescript' || lang === 'javascript')
                continue;
            const safeName = labelToFileName(file.nodeLabel);
            lines.push(`// Note: ${file.fileName} is a ${lang} file — integrates separately`);
        }
        // ── Cross-app bridges (Tree Mode) ──
        // The app built next to this one is a SEPARATE program: its modules are not
        // importable from here, so the bridge modules are the only shared contract
        // between the two. Re-exported so both sides are visibly wired to it.
        const entryBridges = config.entryBridges || [];
        if (entryBridges.length > 0) {
            lines.push('');
            lines.push('// ── Cross-app bridges (Tree Mode) ──');
            lines.push('// Shared with the app(s) beside this one — see bridge/ in the project root.');
            for (const bridge of entryBridges) {
                lines.push(`export * as ${bridge.alias} from '${bridge.importPath}';`);
            }
        }
        lines.push('');
        lines.push('// ── App Bootstrap ──');
        lines.push(`console.log('🚀 ${config.projectName} starting...');`);
        lines.push(`console.log('Target: ${config.targetOS}');`);
        if (config.appGoal) {
            lines.push(`console.log('Goal: ${config.appGoal}');`);
        }
        lines.push('');
        const tsFiles = config.files.filter(f => {
            const lang = (f.language || '').toLowerCase();
            return lang === 'typescript' || lang === 'javascript';
        });
        // Deduplicate export names: the re-export block must only emit names
        // that were ACTUALLY imported as local names (not the original export names
        // from the file, which may be default exports or aliased).
        // importedNames is the set of local names after aliasing, built in the
        // import loop above.
        if (tsFiles.length > 0) {
            lines.push(`// ${tsFiles.length} TypeScript modules loaded and ready`);
            if (importedNames.size > 0) {
                lines.push('export {');
                for (const name of [...importedNames].sort()) {
                    lines.push(`  ${name},`);
                }
                lines.push('};');
            }
        }
        // ── Auto-bootstrap ──
        // Invoke the app's entry function so `npm start` actually RUNS the app
        // instead of only importing and printing a banner (F2 in the build
        // triage: the entry was a banner, not a bootstrap). UI entry functions
        // (render/mount/createApp/init) are skipped for UI projects — the preview
        // wrapper (index.html) drives those — but CLI/logic entries are always
        // bootstrapped. Guarded with typeof so a missing entry can never crash
        // module load.
        const hasUiNode = (config.nodes || []).some((n) => n.type === 'ui');
        const hasHtmlFile = config.files.some((f) => /\.html$/i.test(f.fileName));
        const UI_ENTRY_FN_NAMES = new Set(['render', 'init', 'mount', 'createApp', 'setup']);
        if (entryAlias && !(UI_ENTRY_FN_NAMES.has(entryAlias) && (hasUiNode || hasHtmlFile))) {
            lines.push('');
            lines.push('// ── App Bootstrap ──');
            lines.push(`if (typeof ${entryAlias} === 'function') { ${entryAlias}(); }`);
        }
        return lines.join('\n');
    }
    /**
     * Build a Go entry point (main.go) with package-level imports.
     */
    buildGoEntryPoint(config) {
        const lines = [];
        lines.push('// ' + config.projectName + ' — Auto-generated entry point');
        lines.push('// Generated by Veronica (VACA)');
        lines.push('');
        lines.push('package main');
        lines.push('');
        // Import each Go file EXCEPT the program package: `package main` files are
        // executables and cannot be imported ("is a program, not an importable
        // package"). The root main.go below is the program; everything else is a
        // library package the program can import.
        //
        // Every import MUST be used or `go build` fails with "imported and not
        // used". Each package is aliased (pkg0, pkg1, ...) and its first VALUE
        // export (func/var/const — never a type) is referenced via `var _ =`, so
        // the build compiles the whole module and catches real compile errors in
        // every node file instead of failing on the entry point itself.
        const moduleName = this.sanitizeName(config.projectName);
        const used = [];
        const calls = [];
        let pkgIndex = 0;
        for (const file of config.files) {
            const lang = (file.language || '').toLowerCase();
            if (lang !== 'go')
                continue;
            if (/^package\s+main\b/m.test(file.code || ''))
                continue;
            const safeName = labelToFileName(file.nodeLabel);
            const pkgPath = `src/${safeName}`;
            const alias = `pkg${pkgIndex++}`;
            // A no-argument exported func is safe to CALL — and calling it is what
            // makes the entry point RUN the module, not merely compile it.
            const callable = pickEntryCallable(goNoArgFuncs(file.code || ''));
            if (callable) {
                lines.push(`import ${alias} "${moduleName}/${pkgPath}"`);
                // Go rejects a value-returning call used as a bare statement.
                calls.push(callable.returnType ? `  _ = ${alias}.${callable.name}()` : `  ${alias}.${callable.name}()`);
                continue;
            }
            const valueExport = this.firstGoValueExport(file.code || '', file.exports || []);
            if (valueExport) {
                lines.push(`import ${alias} "${moduleName}/${pkgPath}"`);
                used.push(`_ = ${alias}.${valueExport}`);
            }
            else {
                lines.push(`import _ "${moduleName}/${pkgPath}"`);
            }
        }
        lines.push('');
        lines.push('func main() {');
        lines.push(`  println("🚀 ${config.projectName} starting...")`);
        if (config.appGoal) {
            lines.push(`  println("Goal: ${config.appGoal}")`);
        }
        if (used.length > 0 || calls.length > 0) {
            lines.push('');
            lines.push('  // Run the imported packages, then reference the rest so the whole module is wired in:');
            for (const c of calls)
                lines.push(c);
            for (const u of used) {
                lines.push(`  ${u}`);
            }
        }
        lines.push('}');
        return lines.join('\n');
    }
    /**
     * First VALUE export of a Go file — func/var/const, never a type. The
     * scaffolder's export extractor mixes `func` and `type` declarations, and
     * `var _ = pkg.SomeType` is a compile error ("SomeType is not an
     * expression"), so type-only names must be filtered out.
     */
    firstGoValueExport(code, exports) {
        const valueRegex = /^(?:func|var|const)\s+([A-Z][a-zA-Z0-9_]*)/gm;
        const valueNames = new Set();
        let match;
        while ((match = valueRegex.exec(code)) !== null) {
            valueNames.add(match[1]);
        }
        for (const name of exports || []) {
            if (typeof name === 'string' && valueNames.has(name))
                return name;
        }
        return null;
    }
    /**
     * Build a Rust entry point (main.rs) with #[path] mod declarations.
     *
     * Rust's module system resolves `mod foo;` relative to the current file.
     * Since node files are in src/<label>/<file>, we use #[path] attributes
     * to point Rust to the correct file locations.
     */
    buildRustEntryPoint(config) {
        const lines = [];
        lines.push('// ' + config.projectName + ' — Auto-generated entry point');
        lines.push('// Generated by Veronica (VACA)');
        lines.push('');
        // Declare modules for each Rust file using #[path] for correct resolution
        const wiring = [];
        let modIndex = 0;
        for (const file of config.files) {
            const lang = (file.language || '').toLowerCase();
            if (lang !== 'rust')
                continue;
            const safeName = labelToFileName(file.nodeLabel);
            const modName = safeName.replace(/-/g, '_');
            lines.push(`#[path = "src/${safeName}/${file.fileName}"]`);
            lines.push(`mod ${modName};`);
            const plan = planModuleWiring('rust', file.code || '', modName, modIndex++);
            wiring.push(...plan.calls, ...plan.references);
        }
        lines.push('');
        lines.push('fn main() {');
        lines.push(`  println!("🚀 ${config.projectName} starting...");`);
        if (config.appGoal) {
            lines.push(`  println!("Goal: {}", "${config.appGoal}");`);
        }
        if (wiring.length > 0) {
            lines.push('');
            lines.push('  // Call the modules that expose an entry fn, reference the rest so the whole crate is built:');
            for (const w of wiring)
                lines.push(`  ${w}`);
        }
        lines.push('}');
        return lines.join('\n');
    }
    /**
     * Build a Python entry point (main.py) with import statements.
     *
     * Python's per-file architecture puts each node in src/<module_name>/<file>.py
     * with an __init__.py that re-exports everything. The entry point imports from
     * these packages using underscored module names (since Python can't import
     * hyphenated directories).
     */
    buildPythonEntryPoint(config) {
        const lines = [];
        lines.push('"""');
        lines.push(config.projectName + ' — Auto-generated entry point');
        lines.push('Generated by Veronica (VACA)');
        lines.push('"""');
        lines.push('import sys');
        lines.push('import os');
        lines.push('');
        lines.push('# Add src/ to the Python path so imports work');
        lines.push('sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))');
        lines.push('');
        // Import each Python file as a MODULE — never `from … import *`: every CLI
        // node names its entry `main`, so a star import lets the last one shadow the
        // rest and the entry point then runs one node's work several times while
        // never reaching the others. Qualified calls (`arg_parser.main()`) run
        // exactly the node each line names.
        const wiring = [];
        let index = 0;
        for (const file of config.files) {
            const lang = (file.language || '').toLowerCase();
            if (lang !== 'python')
                continue;
            // Python module names use underscores (not hyphens) — the same name as
            // the directory and the written file (see pythonModuleName).
            const modName = pythonModuleName(file.nodeLabel);
            // Each node directory has an __init__.py that re-exports the module, so
            // importing the package is enough.
            lines.push(`import ${modName}  # src/${modName}/${file.fileName}`);
            const plan = planModuleWiring('python', file.code || '', modName, index++);
            wiring.push(...plan.calls);
        }
        lines.push('');
        lines.push('');
        lines.push('def main():');
        lines.push(`  print("🚀 ${config.projectName} starting...")`);
        if (config.appGoal) {
            lines.push(`  print("Goal: " + ${JSON.stringify(config.appGoal)})`);
        }
        if (wiring.length > 0) {
            lines.push('');
            lines.push('  # Run the project modules (the no-argument entry each one exposes):');
            for (const w of wiring)
                lines.push(`  ${w}`);
        }
        else {
            lines.push('');
            lines.push('  # No node exposed a function the entry point can call without arguments.');
        }
        lines.push('');
        lines.push('');
        lines.push('if __name__ == "__main__":');
        lines.push('  main()');
        return lines.join('\n');
    }
    /**
     * Build a Java entry point (Main.java). javac requires the public class name
     * to match the file name, so the entry is a standalone `Main` with a launcher;
     * sibling node classes live in the same (default) package and can be
     * instantiated from here.
     */
    buildJavaEntryPoint(config) {
        const lines = [];
        lines.push('/** ' + config.projectName + ' — Auto-generated entry point. Generated by Veronica (VACA). */');
        lines.push('public class Main {');
        lines.push('  public static void main(String[] args) {');
        lines.push('    System.out.println("\uD83D\uDE80 ' + config.projectName + ' starting...");');
        if (config.appGoal)
            lines.push('    System.out.println("Goal: " + ' + JSON.stringify(config.appGoal) + ');');
        lines.push('');
        lines.push('    // Node classes live in this same package (src/<node>/<File>.java).');
        lines.push('    // Each is referenced so javac compiles and links it, and a class that');
        lines.push('    // declares a no-argument static method has that method called.');
        let index = 0;
        let wired = 0;
        for (const file of config.files) {
            if ((file.language || '').toLowerCase() !== 'java')
                continue;
            const plan = planModuleWiring('java', file.code || '', '', index++);
            if (plan.references.length === 0 && plan.calls.length === 0)
                continue;
            lines.push(`    // ${file.fileName}`);
            for (const r of plan.references)
                lines.push(`    ${r}`);
            for (const c of plan.calls)
                lines.push(`    ${c}`);
            wired++;
        }
        if (wired === 0)
            lines.push('    // (no node classes found to wire up)');
        lines.push('  }');
        lines.push('}');
        return lines.join('\n');
    }
    /** Shared C/C++ entry banner + sibling-header includes. */
    buildCCppEntryPoint(config, lang) {
        const lines = [];
        lines.push('/* ' + config.projectName + ' — Auto-generated entry point. Generated by Veronica (VACA). */');
        lines.push(lang === 'c' ? '#include <stdio.h>' : '#include <iostream>');
        // Only headers can be included without redefining `main`; node source files
        // are compiled as their own translation units.
        for (const file of config.files) {
            const fl = (file.language || '').toLowerCase();
            const isHdr = /\.h(h|pp)?$/i.test(file.fileName);
            if (fl !== lang || !isHdr)
                continue;
            lines.push(`#include "${labelToFileName(file.nodeLabel)}/${file.fileName}"`);
        }
        // Prototypes copied from the node files' own definitions, plus the calls
        // that exercise them. Without these the entry point only printed a banner.
        const declarations = [];
        const calls = [];
        let index = 0;
        for (const file of config.files) {
            const fl = (file.language || '').toLowerCase();
            if (fl !== lang || /\.h(h|pp)?$/i.test(file.fileName))
                continue;
            const plan = planModuleWiring(lang, file.code || '', '', index++);
            declarations.push(...plan.declarations);
            calls.push(...plan.calls);
        }
        if (declarations.length > 0) {
            lines.push('');
            lines.push('/* Node-module entry points (signatures copied from src/<node>/): */');
            for (const d of declarations)
                lines.push(d);
        }
        lines.push('');
        lines.push('int main(int argc, char **argv) {');
        lines.push('  (void)argc; (void)argv;');
        if (lang === 'c') {
            lines.push('  printf("\uD83D\uDE80 ' + config.projectName + ' starting...\\n");');
            if (config.appGoal)
                lines.push('  printf("Goal: ' + escapeForCString(config.appGoal) + '\\n");');
        }
        else {
            lines.push('  std::cout << "\uD83D\uDE80 ' + config.projectName + ' starting..." << std::endl;');
            if (config.appGoal)
                lines.push('  std::cout << "Goal: ' + escapeForCString(config.appGoal) + '" << std::endl;');
        }
        if (calls.length > 0) {
            lines.push('');
            lines.push('  /* Run the project modules: */');
            for (const c of calls)
                lines.push(`  ${c}`);
        }
        else {
            lines.push('  // Node modules under src/<node>/ are separate translation units — none exposes a no-argument entry function.');
        }
        lines.push('  return 0;');
        lines.push('}');
        return lines.join('\n');
    }
    buildCEntryPoint(config) {
        return this.buildCCppEntryPoint(config, 'c');
    }
    buildCppEntryPoint(config) {
        return this.buildCCppEntryPoint(config, 'cpp');
    }
    /** Build a C# entry point (Program.cs) — a runnable top-level Main. */
    buildCsharpEntryPoint(config) {
        const lines = [];
        lines.push('// ' + config.projectName + ' — Auto-generated entry point. Generated by Veronica (VACA).');
        lines.push('using System;');
        lines.push('');
        lines.push('class Program');
        lines.push('{');
        lines.push('    static void Main(string[] args)');
        lines.push('    {');
        lines.push('        Console.WriteLine("\uD83D\uDE80 ' + config.projectName + ' starting...");');
        if (config.appGoal)
            lines.push('        Console.WriteLine("Goal: " + ' + JSON.stringify(config.appGoal) + ');');
        lines.push('');
        lines.push('        // Node classes live under src/<node>/. Each is referenced so the');
        lines.push('        // compiler builds it, and a no-argument static method is called.');
        let index = 0;
        let wired = 0;
        for (const file of config.files) {
            if ((file.language || '').toLowerCase() !== 'csharp')
                continue;
            const plan = planModuleWiring('csharp', file.code || '', '', index++);
            if (plan.references.length === 0 && plan.calls.length === 0)
                continue;
            lines.push(`        // ${file.fileName}`);
            for (const r of plan.references)
                lines.push(`        ${r}`);
            for (const c of plan.calls)
                lines.push(`        ${c}`);
            wired++;
        }
        if (wired === 0)
            lines.push('        // (no node classes found to wire up)');
        lines.push('    }');
        lines.push('}');
        return lines.join('\n');
    }
    /** Build a PHP entry point (index.php) that requires each node file. */
    buildPhpEntryPoint(config) {
        const lines = [];
        lines.push('<?php');
        lines.push('// ' + config.projectName + ' — Auto-generated entry point. Generated by Veronica (VACA).');
        for (const file of config.files) {
            if ((file.language || '').toLowerCase() !== 'php')
                continue;
            lines.push(`require_once __DIR__ . '/src/${labelToFileName(file.nodeLabel)}/${file.fileName}';`);
        }
        lines.push('');
        lines.push('echo "\uD83D\uDE80 ' + config.projectName + ' starting...\\n";');
        if (config.appGoal)
            lines.push('echo "Goal: ' + escapeForPhpString(config.appGoal) + '\\n";');
        lines.push('// Call into the required node modules here.');
        return lines.join('\n');
    }
    /**
     * Build a Ruby entry point (main.rb) that requires each node file and RUNS the
     * nodes' zero-argument entries.
     *
     * Requiring alone only defines methods — and a node that guards its own `main`
     * with `if __FILE__ == $0` never fires when it is required, so the old entry
     * point printed a banner and did nothing (measured on the generated
     * word-statistics app). Each callable name is emitted once: Ruby has no
     * per-file namespace, so two nodes defining the same bare `def` would run the
     * later definition twice.
     */
    buildRubyEntryPoint(config) {
        const lines = [];
        lines.push('# ' + config.projectName + ' — Auto-generated entry point. Generated by Veronica (VACA).');
        const calls = [];
        for (const file of config.files) {
            if ((file.language || '').toLowerCase() !== 'ruby')
                continue;
            lines.push(`require_relative 'src/${labelToFileName(file.nodeLabel)}/${file.fileName}'`);
            calls.push(...planModuleWiring('ruby', file.code || '', '', 0).calls);
        }
        lines.push('');
        lines.push('puts "\uD83D\uDE80 ' + config.projectName + ' starting..."');
        if (config.appGoal)
            lines.push("puts 'Goal: " + escapeForSingleQuoted(config.appGoal) + "'");
        lines.push('');
        const unique = [...new Set(calls)];
        if (unique.length > 0) {
            lines.push('# Run the project modules (the no-argument entry each one exposes):');
            for (const c of unique)
                lines.push(c);
        }
        else {
            lines.push('# No node exposed a function the entry point can call without arguments.');
        }
        return lines.join('\n');
    }
    /**
     * Build a Swift entry point (main.swift).
     *
     * Swift only permits top-level statements in `main.swift` — any other file
     * with them is a compile error — so the entry file must be named exactly
     * `main.swift`. Node files under src/<node>/ compile into the same module,
     * so they are callable from here with no import statement.
     */
    buildSwiftEntryPoint(config) {
        const lines = [];
        lines.push('// ' + config.projectName + ' — Auto-generated entry point. Generated by Veronica (VACA).');
        lines.push('import Foundation');
        lines.push('');
        lines.push('print("\uD83D\uDE80 ' + config.projectName + ' starting...")');
        if (config.appGoal)
            lines.push('print("Goal: ' + escapeForCString(config.appGoal) + '")');
        lines.push('');
        lines.push('// Node files under src/<node>/ compile into this same module. Each type is');
        lines.push('// referenced so swiftc builds it, and a no-argument function is called.');
        let index = 0;
        for (const file of config.files) {
            if ((file.language || '').toLowerCase() !== 'swift')
                continue;
            const plan = planModuleWiring('swift', file.code || '', '', index++);
            if (plan.references.length === 0 && plan.calls.length === 0)
                continue;
            lines.push(`// ${file.fileName}`);
            lines.push(...plan.references, ...plan.calls);
        }
        return lines.join('\n');
    }
    /**
     * Build a Kotlin entry point (Main.kt).
     *
     * kotlinc compiles every file of the module together, so node files under
     * src/<node>/ are visible here without imports; `fun main()` is the JVM
     * entry point.
     */
    buildKotlinEntryPoint(config) {
        const lines = [];
        lines.push('// ' + config.projectName + ' — Auto-generated entry point. Generated by Veronica (VACA).');
        lines.push('');
        lines.push('fun main() {');
        lines.push('    println("\uD83D\uDE80 ' + config.projectName + ' starting...")');
        if (config.appGoal)
            lines.push('    println("Goal: ' + escapeForCString(config.appGoal) + '")');
        lines.push('');
        lines.push('    // Node files under src/<node>/ compile into this same module. Each type is');
        lines.push('    // referenced so kotlinc builds it, and a top-level fun is called.');
        let index = 0;
        for (const file of config.files) {
            if ((file.language || '').toLowerCase() !== 'kotlin')
                continue;
            const plan = planModuleWiring('kotlin', file.code || '', '', index++);
            if (plan.references.length === 0 && plan.calls.length === 0)
                continue;
            lines.push(`    // ${file.fileName}`);
            for (const line of [...plan.references, ...plan.calls])
                lines.push(`    ${line}`);
        }
        lines.push('}');
        return lines.join('\n');
    }
    /**
     * Build project configuration files matching the primary language.
     * Returns a map of filename → file content.
     */
    buildProjectConfig(config, primaryLang, 
    /** True when a node file owns the program entry — no hard-coded main.c/cpp. */
    entryless = false) {
        switch (primaryLang) {
            case 'go': return this.buildGoProjectConfig(config);
            case 'rust': return this.buildRustProjectConfig(config);
            case 'python': return this.buildPythonProjectConfig(config);
            case 'java': return this.buildJavaProjectConfig(config);
            case 'c': return this.buildCProjectConfig(config, entryless);
            case 'cpp': return this.buildCppProjectConfig(config, entryless);
            case 'csharp': return this.buildCsharpProjectConfig(config);
            case 'php': return this.buildPhpProjectConfig(config);
            case 'ruby': return this.buildRubyProjectConfig(config);
            case 'swift': return this.buildSwiftProjectConfig(config);
            case 'kotlin': return this.buildKotlinProjectConfig(config, entryless);
            default: return this.buildTsProjectConfig(config);
        }
    }
    /**
     * Build TypeScript project config (package.json + tsconfig.json).
     */
    buildTsProjectConfig(config) {
        const pkg = {
            name: this.sanitizeName(config.projectName),
            version: '1.0.0',
            description: config.appGoal || `${config.projectName} — generated app`,
            type: 'module',
            scripts: {
                // `node index.ts` cannot run TypeScript — tsx is the correct runner
                // (and is already a devDependency of every generated project).
                start: 'tsx index.ts',
                build: 'tsc',
                dev: 'tsx watch index.ts',
                test: 'echo "No tests configured"',
            },
            dependencies: {},
            devDependencies: {
                typescript: '^5.4.0',
                tsx: '^4.7.0',
                '@types/node': '^20.0.0',
            },
        };
        // Three structural fixes so every exported project compiles out of the box:
        //   1. rootDir must contain EVERY included file — index.ts lives at the root
        //      while node files live under src/, so './src' broke everything with
        //      TS6059. rootDir '.' covers both.
        //   2. Node files import siblings with explicit .ts extensions
        //      (../dep/dep.ts) — requires allowImportingTsExtensions, else every
        //      cross-file import fails with TS5097.
        //   3. noEmit: `build` is a pure typecheck and `start` runs tsx directly,
        //      so noEmit avoids the rewriteRelativeImportExtensions requirement.
        const tsconfig = {
            compilerOptions: {
                target: 'ES2022',
                module: 'ESNext',
                moduleResolution: 'bundler',
                strict: true,
                esModuleInterop: true,
                skipLibCheck: true,
                allowImportingTsExtensions: true,
                noEmit: true,
            },
            include: ['src/**/*.ts', 'index.ts'],
        };
        return {
            'package.json': JSON.stringify(pkg, null, 2),
            'tsconfig.json': JSON.stringify(tsconfig, null, 2),
        };
    }
    /**
     * Build Go project config (go.mod + start.sh).
     */
    buildGoProjectConfig(config) {
        const moduleName = this.sanitizeName(config.projectName);
        const goMod = `module ${moduleName}\n\ngo 1.22\n`;
        // Generate a startup script that builds and runs the Go app
        const binName = moduleName;
        const d = '$'; // literal dollar sign for bash variable references
        const startSh = `#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# ${config.projectName} — Startup Script
# Generated by Veronica (VACA)
#
# Builds the Go binary (if needed) and runs it.
# Passes any CLI arguments through to the binary.
# ──────────────────────────────────────────────

BINARY="${binName}"
BUILD_DIR="./dist"
BINARY_PATH="${d}{BUILD_DIR}/${d}{BINARY}"

# Colors for output (using tput for portability)
GREEN=$(tput setaf 2 2>/dev/null || echo '')
CYAN=$(tput setaf 6 2>/dev/null || echo '')
YELLOW=$(tput setaf 3 2>/dev/null || echo '')
NC=$(tput sgr0 2>/dev/null || echo '')

echo ""
echo "${d}{CYAN}════════════════════════════════════════════${d}{NC}"
echo "${d}{CYAN}  🚀 ${config.projectName}${d}{NC}"
echo "${d}{CYAN}════════════════════════════════════════════${d}{NC}"
echo ""

# Build the binary if it doesn't exist or if source changed
if [ ! -f "${d}{BINARY_PATH}" ] || [ "$(find . -name '*.go' -newer "${d}{BINARY_PATH}" 2>/dev/null | head -1)" != "" ]; then
  echo "${d}{YELLOW}🔨 Building...${d}{NC}"
  mkdir -p "${d}{BUILD_DIR}"
  go build -o "${d}{BINARY_PATH}" .
  echo "${d}{GREEN}✅ Build complete: ${d}{BINARY_PATH}${d}{NC}"
  echo ""
fi

# Run the binary with any passed arguments
echo "${d}{CYAN}▶️  Starting ${d}{BINARY}...${d}{NC}"
echo "${d}{CYAN}─────────────────────────────────────────────${d}{NC}"
echo ""
exec "${d}{BINARY_PATH}" "${d}@"
`;
        return { 'go.mod': goMod, 'start.sh': startSh };
    }
    /**
     * Build Rust project config (Cargo.toml) with [[bin]] section.
     * The [[bin]] section tells Cargo the binary name and entry point path.
     * Without it, Cargo defaults to looking for src/main.rs, but our
     * entry point is at the root as main.rs.
     */
    buildRustProjectConfig(config) {
        const binName = this.sanitizeName(config.projectName);
        const cargo = `[package]
name = "${binName}"
version = "0.1.0"
edition = "2021"
description = "${config.appGoal || config.projectName + ' — generated app'}"

[[bin]]
name = "${binName}"
path = "main.rs"

[dependencies]
`;
        return { 'Cargo.toml': cargo };
    }
    /**
     * Build Python project config (pyproject.toml).
     */
    buildPythonProjectConfig(config) {
        const pyproject = `[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "${this.sanitizeName(config.projectName)}"
version = "0.1.0"
description = "${config.appGoal || config.projectName + ' — generated app'}"
requires-python = ">=3.10"

[tool.pytest.ini_options]
minversion = "7.0"
`;
        return { 'pyproject.toml': pyproject };
    }
    /** Java project config: a dependency-free Makefile (javac / java). */
    buildJavaProjectConfig(config) {
        const t = '\t';
        const makefile = [
            `# ${config.projectName} — Makefile`,
            'JAVAC ?= javac',
            'JAVA  ?= java',
            'SRCS  := Main.java $(wildcard src/*/*.java)',
            'OUT   := out',
            '',
            '.PHONY: all build run clean',
            'all: build',
            '',
            'build:',
            `${t}@mkdir -p $(OUT)`,
            `${t}$(JAVAC) -d $(OUT) $(SRCS)`,
            '',
            'run: build',
            `${t}$(JAVA) -cp $(OUT) Main`,
            '',
            'clean:',
            `${t}rm -rf $(OUT)`,
            '',
        ].join('\n');
        return { Makefile: makefile };
    }
    /**
     * C project config: a Makefile (gcc / c11).
     *
     * `entryless` means a node file IS the entry point (it defines `main`), so the
     * Makefile must not require a main.c that was never written — it compiles
     * every source file under the project instead.
     */
    buildCProjectConfig(config, entryless = false) {
        const t = '\t';
        const srcs = entryless ? '$(wildcard *.c) $(wildcard src/*/*.c)' : 'main.c $(wildcard src/*/*.c)';
        const makefile = [
            `# ${config.projectName} — Makefile`,
            'CC ?= gcc',
            'CFLAGS ?= -std=c11 -O2 -Wall',
            `SRCS := ${srcs}`,
            'OUT := app',
            '',
            '.PHONY: all build run clean',
            'all: build',
            '',
            'build:',
            `${t}$(CC) $(CFLAGS) -o $(OUT) $(SRCS)`,
            '',
            'run: build',
            `${t}./$(OUT)`,
            '',
            'clean:',
            `${t}rm -f $(OUT)`,
            '',
        ].join('\n');
        return { Makefile: makefile };
    }
    /** C++ project config: a Makefile (g++ / c++17). `entryless` as in the C one. */
    buildCppProjectConfig(config, entryless = false) {
        const t = '\t';
        const srcs = entryless ? '$(wildcard *.cpp) $(wildcard src/*/*.cpp)' : 'main.cpp $(wildcard src/*/*.cpp)';
        const makefile = [
            `# ${config.projectName} — Makefile`,
            'CXX ?= g++',
            'CXXFLAGS ?= -std=c++17 -O2 -Wall',
            `SRCS := ${srcs}`,
            'OUT := app',
            '',
            '.PHONY: all build run clean',
            'all: build',
            '',
            'build:',
            `${t}$(CXX) $(CXXFLAGS) -o $(OUT) $(SRCS)`,
            '',
            'run: build',
            `${t}./$(OUT)`,
            '',
            'clean:',
            `${t}rm -f $(OUT)`,
            '',
        ].join('\n');
        return { Makefile: makefile };
    }
    /** C# project config: a minimal SDK-style .csproj. */
    buildCsharpProjectConfig(config) {
        const csproj = '<Project Sdk="Microsoft.NET.Sdk">\n' +
            '  <PropertyGroup>\n' +
            '    <OutputType>Exe</OutputType>\n' +
            '    <TargetFramework>net8.0</TargetFramework>\n' +
            '    <ImplicitUsings>disable</ImplicitUsings>\n' +
            '    <Nullable>disable</Nullable>\n' +
            `    <AssemblyName>${this.sanitizeName(config.projectName)}</AssemblyName>\n` +
            '  </PropertyGroup>\n' +
            '</Project>\n';
        return { 'app.csproj': csproj };
    }
    /** PHP project config: a minimal composer.json (no third-party deps). */
    buildPhpProjectConfig(config) {
        const composer = JSON.stringify({
            name: `vaca/${this.sanitizeName(config.projectName)}`,
            description: config.appGoal || `${config.projectName} — generated app`,
            type: 'project',
            require: {},
        }, null, 2);
        return { 'composer.json': composer };
    }
    /** Ruby project config: a minimal Gemfile (standard library only). */
    buildRubyProjectConfig(config) {
        void config;
        const gemfile = "source 'https://rubygems.org'\n\n# No external gems required — standard library only.\n";
        return { Gemfile: gemfile };
    }
    /** Swift project config: a Makefile (swiftc) — no Package.swift/SwiftPM needed. */
    buildSwiftProjectConfig(config) {
        const t = '\t';
        const makefile = [
            `# ${config.projectName} — Makefile`,
            'SWIFTC ?= swiftc',
            'SRCS := main.swift $(wildcard src/*/*.swift)',
            'OUT := app',
            '',
            '.PHONY: all build run clean',
            'all: build',
            '',
            'build:',
            `${t}$(SWIFTC) $(SRCS) -o $(OUT)`,
            '',
            'run: build',
            `${t}./$(OUT)`,
            '',
            'clean:',
            `${t}rm -f $(OUT)`,
            '',
        ].join('\n');
        return { Makefile: makefile };
    }
    /**
     * Kotlin project config: a Makefile (kotlinc -include-runtime) producing a
     * runnable jar. `entryless` (a node owns `fun main()`) drops the hard-coded
     * Main.kt from the sources, exactly like the C/C++ Makefiles.
     */
    buildKotlinProjectConfig(config, entryless = false) {
        const t = '\t';
        const srcs = entryless ? '$(wildcard *.kt) $(wildcard src/*/*.kt)' : 'Main.kt $(wildcard src/*/*.kt)';
        const makefile = [
            `# ${config.projectName} — Makefile`,
            'KOTLINC ?= kotlinc',
            'JAVA ?= java',
            `SRCS := ${srcs}`,
            'OUT := app.jar',
            '',
            '.PHONY: all build run clean',
            'all: build',
            '',
            'build:',
            `${t}$(KOTLINC) $(SRCS) -include-runtime -d $(OUT)`,
            '',
            'run: build',
            `${t}$(JAVA) -jar $(OUT)`,
            '',
            'clean:',
            `${t}rm -f $(OUT)`,
            '',
        ].join('\n');
        return { Makefile: makefile };
    }
    /**
     * Build a language-appropriate .gitignore.
     */
    buildGitignore(language) {
        switch (language) {
            case 'go':
                return '# Binaries\n*.exe\n*.exe~\n*.dll\n*.so\n*.dylib\n*.test\n*.out\n/go/\n\n# IDE\n.idea/\n.vscode/\n*.swp\n*.swo\n\n# Env\n.env\n';
            case 'rust':
                return '# Generated files\n/target/\n**/*.rs.bk\n\n# IDE\n.idea/\n.vscode/\n*.swp\n*.swo\n\n# Env\n.env\n';
            case 'python':
                return '# Bytecode\n__pycache__/\n*.py[cod]\n*$py.class\n\n# Virtualenv\n.venv/\nvenv/\nENV/\n\n# IDE\n.idea/\n.vscode/\n*.swp\n*.swo\n\n# Env\n.env\n';
            case 'java':
                return '# Compiled classes\nout/\n*.class\n\n# IDE\n.idea/\n.vscode/\n*.swp\n*.swo\n\n# Env\n.env\n';
            case 'c':
            case 'cpp':
                return '# Build output\napp\n*.o\n*.obj\n*.exe\n*.out\n\n# CMake\nbuild/\nCMakeFiles/\nCMakeCache.txt\n\n# IDE\n.idea/\n.vscode/\n*.swp\n*.swo\n\n# Env\n.env\n';
            case 'csharp':
                return '# Build output\nbin/\nobj/\n\n# IDE\n.idea/\n.vscode/\n*.swp\n*.swo\n\n# Env\n.env\n';
            case 'php':
                return '# Composer\nvendor/\n\n# IDE\n.idea/\n.vscode/\n*.swp\n*.swo\n\n# Env\n.env\n';
            case 'ruby':
                return '# Bundler\n/.bundle/\nvendor/bundle\n\n# IDE\n.idea/\n.vscode/\n*.swp\n*.swo\n\n# Env\n.env\n';
            case 'swift':
                return '# Build output\napp\n*.o\n.build/\n\n# IDE\n.idea/\n.vscode/\n*.swp\n*.swo\n\n# Env\n.env\n';
            case 'kotlin':
                return '# Build output\napp.jar\n*.jar\nout/\n*.class\n\n# IDE\n.idea/\n.vscode/\n*.swp\n*.swo\n\n# Env\n.env\n';
            default:
                return 'node_modules/\ndist/\n.env\n';
        }
    }
    /**
     * Build a README describing the per-file project structure.
     */
    buildReadme(config, primaryLang, entryFileName, 
    /** Set when a node file is the program entry (see promotedEntryOwner). */
    opts = {}) {
        const trees = Array.isArray(config.trees) ? config.trees : [];
        const layout = planExportLayout(trees);
        const scoped = resolveTreeScopes({
            nodes: (config.nodes || []),
            edges: (config.edges || []),
            trees,
            name: config.projectName,
        });
        const files = config.files.map((f) => this.withLayout(f, layout));
        const bridgeFiles = files.filter((f) => f.isBridge);
        const moduleFiles = files.filter((f) => !f.isBridge);
        const plannedBridges = planBridges(scoped);
        const appDirFor = (treeId) => {
            const dirName = treeId ? layout.appDirByTree[treeId] : undefined;
            return dirName ? `apps/${dirName}` : undefined;
        };
        // One entry per app that actually has modules on disk: its layout directory
        // and those modules. A tree with no generated file has no directory, so
        // documenting it would describe a project that is not there.
        const appEntries = trees
            .map((t) => ({ tree: t, dir: appDirFor(t.id), files: moduleFiles.filter((f) => f.appDir === appDirFor(t.id)) }))
            .filter((e) => Boolean(e.dir) && e.files.length > 0);
        const lines = [];
        lines.push(`# ${config.projectName}`);
        lines.push('');
        lines.push('Generated by **Veronica (VACA)**');
        lines.push('');
        lines.push('---');
        lines.push('');
        lines.push('## Overview');
        lines.push('');
        lines.push(`**Target OS:** ${config.targetOS}`);
        if (config.linuxDistro)
            lines.push(`**Linux Distro:** ${config.linuxDistro}`);
        if (config.appGoal)
            lines.push(`**Goal:** ${config.appGoal}`);
        if (config.appPurpose)
            lines.push(`**Purpose:** ${config.appPurpose}`);
        lines.push(`**Language:** ${primaryLang.charAt(0).toUpperCase() + primaryLang.slice(1)}`);
        lines.push('');
        lines.push('This project was generated using the **per-file architecture**:');
        lines.push('Each node on the architecture canvas corresponds to one source file.');
        if (layout.separateApps) {
            lines.push('');
            lines.push(`**Tree Mode:** this project holds **${trees.length} separate apps**, each built into its own directory, ` +
                `${plannedBridges.length} cross-app connection(s) realized by shared bridge module(s) in \`bridge/\`.`);
        }
        lines.push('');
        lines.push('## Project Structure');
        lines.push('');
        lines.push('```');
        lines.push('.');
        if (layout.separateApps) {
            // ── Several apps side by side, plus the shared bridge dir ──
            lines.push('├── apps/');
            appEntries.forEach((entry, i) => {
                const isLastApp = i === appEntries.length - 1;
                const branch = isLastApp ? '│   └──' : '│   ├──';
                const sub = isLastApp ? '│       ' : '│   │   ';
                const appLang = this.detectPrimaryLanguage(entry.files);
                lines.push(`${branch} ${path.posix.basename(entry.dir)}/   # ${entry.tree.name}` +
                    (entry.tree.goal ? ` — ${entry.tree.goal}` : ''));
                for (const cfgFile of Object.keys(this.buildProjectConfig(config, appLang))) {
                    lines.push(`${sub}├── ${cfgFile}`);
                }
                lines.push(`${sub}├── ${this.getEntryFileName(appLang)}   # Entry point — this app's own modules`);
                lines.push(`${sub}└── src/`);
                for (const file of entry.files) {
                    lines.push(`${sub}    ├── ${labelToFileName(file.nodeLabel)}/`);
                    lines.push(`${sub}    │   └── ${file.fileName}  ${file.validated ? '✅' : '⚠️'}`);
                }
            });
            if (bridgeFiles.length > 0) {
                lines.push('├── bridge/');
                bridgeFiles.forEach((b, i) => {
                    const last = i === bridgeFiles.length - 1;
                    lines.push(`│   ${last ? '└' : '├'}── ${b.fileName}   # 🔗 cross-app integration module`);
                });
            }
            lines.push('├── dependency-graph.json   # Node + app metadata');
            lines.push('├── README.md');
            lines.push('└── .gitignore');
            lines.push('```');
            lines.push('');
            lines.push(`**${moduleFiles.length} modules across ${appEntries.length} app(s)**` +
                (bridgeFiles.length > 0 ? ` + ${bridgeFiles.length} bridge module(s).` : '.'));
            lines.push('');
            lines.push('## Quick Start');
            lines.push('');
            lines.push('Each app is its own program — run it from its own directory:');
            lines.push('');
            lines.push('```bash');
            for (const entry of appEntries) {
                lines.push(`cd ${entry.dir} && ${this.runCommandFor(this.detectPrimaryLanguage(entry.files))}`);
            }
            lines.push('```');
            if (plannedBridges.length > 0) {
                lines.push('');
                lines.push('## 🔗 Cross-App Connections (Tree Mode)');
                lines.push('');
                lines.push('The apps above are **separate programs** — they cannot import each other. ' +
                    'The only contract between them is the bridge modules in `bridge/` (also re-exported from each app\'s entry point).');
                lines.push('');
                for (const bridge of plannedBridges) {
                    lines.push(`- **${bridge.name}** — \`${bridge.payloadLabel}\`: **${bridge.sourceTreeName}** → **${bridge.targetTreeName}**`);
                    for (const link of bridge.links) {
                        if (link.description || link.relation)
                            lines.push(`  - ${link.description || link.relation}`);
                    }
                }
            }
        }
        else {
            // Structure entries differ by language
            const configFiles = this.buildProjectConfig(config, primaryLang);
            for (const cfgFile of Object.keys(configFiles)) {
                lines.push(`├── ${cfgFile.padEnd(22)} # Project configuration`);
            }
            lines.push(opts.entryOwner
                ? `├── (no ${entryFileName} — the program entry is a node file, below)`
                : `├── ${entryFileName.padEnd(22)} # Entry point — imports all nodes`);
            lines.push('├── dependency-graph.json   # Node dependency metadata');
            lines.push('├── src/');
            for (const file of config.files) {
                const safeName = labelToFileName(file.nodeLabel);
                const status = file.validated ? '✅' : '⚠️';
                lines.push(`│   └── ${safeName}/`);
                lines.push(`│       └── ${file.fileName}  ${status}`);
            }
            lines.push('├── README.md');
            lines.push('└── .gitignore');
            lines.push('```');
            lines.push('');
            lines.push(`**${config.files.length} source files** across ${config.files.length} nodes.`);
            if (opts.entryOwner) {
                lines.push('');
                lines.push(`> **Program entry point:** \`${opts.entryOwnerRel}\` — the ` +
                    `“${opts.entryOwner.nodeLabel}” node defines \`main()\`, so it IS the app ` +
                    `(no second entry file is generated).`);
            }
            lines.push('');
            lines.push('## Quick Start');
            lines.push('');
            lines.push('```bash');
            if (primaryLang === 'go') {
                lines.push('# Run the app (builds and runs via startup script)');
                lines.push('chmod +x start.sh && ./start.sh');
                lines.push('');
                lines.push('# Or using raw Go commands:');
                lines.push('go run .');
                lines.push('go build -o dist/ .');
            }
            else if (primaryLang === 'rust') {
                lines.push('# Run the app');
                lines.push('cargo run');
                lines.push('');
                lines.push('# Build for production');
                lines.push('cargo build --release');
            }
            else if (primaryLang === 'python') {
                lines.push('# Run the app');
                lines.push('python main.py');
                lines.push('');
                lines.push('# Install dependencies (if any)');
                lines.push('pip install -r requirements.txt');
            }
            else if (primaryLang === 'java') {
                lines.push('# Compile and run (uses the Makefile)');
                lines.push('make run');
                lines.push('');
                lines.push('# Or directly:');
                lines.push('javac -d out Main.java src/*/*.java && java -cp out Main');
            }
            else if (primaryLang === 'c' || primaryLang === 'cpp') {
                lines.push('# Build and run (uses the Makefile)');
                lines.push('make run');
            }
            else if (primaryLang === 'csharp') {
                lines.push('# Run the app');
                lines.push('dotnet run');
            }
            else if (primaryLang === 'php') {
                lines.push('# Run the app');
                lines.push('php index.php');
            }
            else if (primaryLang === 'ruby') {
                lines.push('# Run the app');
                lines.push('ruby main.rb');
            }
            else {
                lines.push('# Install dependencies');
                lines.push('npm install');
                lines.push('');
                lines.push('# Run in development mode');
                lines.push('npm run dev');
                lines.push('');
                lines.push('# Build for production');
                lines.push('npm run build');
            }
            lines.push('```');
        }
        lines.push('');
        lines.push('## Node Dependency Graph');
        lines.push('');
        for (const file of moduleFiles) {
            const deps = file.dependencies.length > 0
                ? ` → depends on: ${file.dependencies.join(', ')}`
                : ' → no dependencies';
            const where = layout.separateApps && file.appDir ? ` *(in ${file.appDir})*` : '';
            lines.push(`- **${file.fileName}**${deps}${where}`);
        }
        lines.push('');
        lines.push('---');
        lines.push(`*Generated on ${new Date().toISOString().split('T')[0]}*`);
        return lines.join('\n');
    }
    /** How to run one app of a given language from inside its own directory. */
    runCommandFor(language) {
        switch (language) {
            case 'go': return 'chmod +x start.sh && ./start.sh';
            case 'rust': return 'cargo run';
            case 'python': return 'python main.py';
            case 'java': return 'make run';
            case 'c':
            case 'cpp': return 'make run';
            case 'csharp': return 'dotnet run';
            case 'php': return 'php index.php';
            case 'ruby': return 'ruby main.rb';
            case 'swift': return 'make run';
            case 'kotlin': return 'make run';
            default: return 'npm install && npm run dev';
        }
    }
    sanitizeName(name) {
        return name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-|-$/g, '')
            || 'untitled';
    }
}
