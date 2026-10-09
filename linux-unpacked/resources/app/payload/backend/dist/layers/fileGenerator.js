/**
 * FileGenerator — generates individual code files per node with proper imports/exports.
 *
 * Instead of generating 3 monolithic layers, each node produces its own standalone file
 * that can be edited individually. Files import from each other based on graph edges.
 *
 * This is the core of the "node-per-file" architecture — each node on the canvas
 * corresponds 1:1 to a source file in the generated project.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { AITranslator, classifyCodeComplexity } from '../ai/translator.js';
// Reuse the chat/CLI path's GUI intent detection + concrete widget templates so
// the canvas node-based build enforces the same GUI-entry quality floor.
// Imported from the neutral shared module (NOT from the routes module) to avoid
// triggering Router()/AITranslator side effects at module load.
import { isGuiRequest, GUI_WIDGET_SECTION, APP_QUALITY_RULES, inlineExternalScriptRefs, stripTypeScriptKeepExports } from '../ai/guiShared.js';
import { VACA_BRAIN_DOCTRINE } from '../ai/prompts.js';
// Deterministic (zero-LLM) tsc repair fixers shared with codePlanner's tsc
// gate — TS2307 sibling-path resolution, TS2459 missing-export patching,
// TS2345 partial-object call-sites, TS2304 content-driven imports, etc. The
// canvas repair loop runs these BEFORE spending a slow regeneration, and only
// files no fixer can touch fall through to the LLM. Imported from the neutral
// shared module (NOT codePlanner, a routes module) to avoid Router/translator
// side effects at load.
import { applyContentDrivenImportFix, applyDeterministicExportNameFix, applyDeterministicLocalCollisionFix, applyDeterministicMissingExportFix, applyDeterministicMissingReturnFix, applyDeterministicPartialObjectFix, applyDeterministicPrivateAccessFix, applyDeterministicSiblingPathFix, applyDeterministicVoidReturnFix, normalizeImportExtensions, stripCircularSelfImports, stripPhantomPackageImports, } from '../ai/deterministicFixers.js';
import { buildSync as esbuildBuildSync } from 'esbuild';
import { buildSemanticSection } from '../utils/semanticConnect.js';
import { resolveTreeScopes, planBridges, buildCrossTreeBoundarySection, buildBridgePrompt, parseBridgeResponse, bridgeFileName, planExportLayout, exportDirFor, BRIDGE_SYSTEM_PROMPT, } from '../utils/treeScope.js';
import { SandboxRunner } from '../sandbox/runner.js';
import { sanitizeGoModuleName } from '../sandbox/nonTsCompileGate.js';
import { runNonTsGatesWithRepair, pathFromGateFailure } from '../sandbox/nonTsRepair.js';
import { runTscGate, deriveBuildVerdict } from '../sandbox/buildVerification.js';
// The shared behavioral smoke gate — the same probes + bounded repair loop the
// chat path (routes/codePlanner.ts) runs. Extracted to sandbox/ so BOTH
// pipelines verify behavior, not just compilation.
import { runStagedBehavioralSmoke } from '../sandbox/behavioralSmoke.js';
import { learningEngine } from '../knowledge/learningEngine.js';
import { isStubBody } from '../knowledge/qualityGate.js';
import { getRegistry } from '../tools/ToolRegistry.js';
import { captureVerifiedGeneration } from '../training/verifiedGenerationCapture.js';
// Project root (backend/src/layers → up 3 = repo root). Used to locate the
// TypeScript compiler for the live compile-check pass.
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const TSC_BIN = path.join(PROJECT_ROOT, 'node_modules', 'typescript', 'bin', 'tsc');
/**
 * GUI-intent detection for the canvas path — mirrors codePlanner's isGuiRequest
 * but for a node-based Project: explicit ui/gui-layout/ui-functions nodes always
 * signal a GUI app; otherwise fall back to the shared request/answer detector
 * fed with the master node's goal + purpose + project name.
 */
function isGuiCanvasProject(project) {
    const masterNode = project.nodes.find((n) => n.type === 'master');
    const goal = masterNode?.data?.appGoal || project.name || '';
    const purpose = masterNode?.data?.appPurpose || '';
    if (project.nodes.some((n) => n.type === 'ui' || n.type === 'gui-layout' || n.type === 'ui-functions'))
        return true;
    return isGuiRequest(`${goal} ${purpose}`);
}
/**
 * Scale guidance injected into every per-file generation prompt so each
 * generated file matches the target program size. Reads the scale the user
 * picked (master node data), defaulting to Medium.
 */
export function buildScaleSection(scale) {
    switch (scale) {
        case 'small':
            return `PROGRAM SCALE: Small — this file is one module in a small (4–8 file) app.\n- Keep the file lean and focused: implement exactly what the node describes.\n- Include basic error handling, but do NOT over-engineer or add speculative abstractions.`;
        case 'large':
            return `PROGRAM SCALE: Large — this file is one module in a large (25+ file) program.\n- Write PRODUCTION-GRADE code: comprehensive error handling, edge cases, and defensive checks.\n- Design for integration: expose clean, typed exports so sibling modules can build on this file.\n- Prefer configuration/constants over hardcoded values where the app is expected to vary.`;
        case 'enterprise':
            return `PROGRAM SCALE: Enterprise — this file is one module in an enterprise (50+ file) platform.\n- Maximum robustness: thorough validation, error handling, and defensive programming.\n- Keep code testable and auditable (clear boundaries, injected config, no hidden globals).\n- Expose stable, typed interfaces for other modules; document non-obvious behavior.`;
        case 'medium':
        default:
            return `PROGRAM SCALE: Medium — this file is one module in a standard (8–14 file) app.\n- Include solid error handling and clear structure.\n- Expose typed exports so other modules can import this file cleanly.`;
    }
}
/**
 * Human-readable export contract for a file's dependency (used in prompts).
 * An EMPTY contract is rendered as an explicit NONE so the model never reads
 * "exports: " and invents imports from a file that exposes nothing.
 */
function describeExports(info) {
    if (!info)
        return '(unknown — not yet generated)';
    const parts = [...(info.names || [])];
    // Render the member whitelist for class/interface exports so the model can
    // see exactly what it may call: `ChessBoard { getPiece, setPiece, clone }`.
    for (const name of info.names) {
        const members = info.members?.[name];
        if (members && members.length > 0) {
            parts.push(`${name} { ${members.join(', ')} }`);
        }
    }
    if (info.defaultName) {
        const members = info.members?.[info.defaultName];
        if (members && members.length > 0) {
            parts.push(`default ${info.defaultName} { ${members.join(', ')} }`);
        }
        else {
            parts.push(`default ${info.defaultName}`);
        }
    }
    return parts.length ? parts.join(', ') : 'NONE — do NOT import from this file';
}
/**
 * Extract the text inside the brace block starting at `start` (which points just
 * past an opening `{`). Returns the depth-1 body (outer braces excluded), or
 * null when the braces never close. Tracks strings/template literals so a `}`
 * inside a string can't terminate the block early.
 */
function extractBraceBody(code, start) {
    let depth = 1;
    let i = start;
    const n = code.length;
    while (i < n) {
        const c = code[i];
        if (c === '{')
            depth++;
        else if (c === '}') {
            depth--;
            if (depth === 0)
                return code.slice(start, i);
        }
        else if (c === '"' || c === '\'' || c === '`') {
            // Skip string literals so braces inside strings are ignored.
            const quote = c;
            i++;
            while (i < n && code[i] !== quote) {
                if (code[i] === '\\')
                    i++;
                i++;
            }
        }
        else if (c === '/' && code[i + 1] === '/') {
            while (i < n && code[i] !== '\n')
                i++;
        }
        else if (c === '/' && code[i + 1] === '*') {
            i += 2;
            while (i < n && !(code[i] === '*' && code[i + 1] === '/'))
                i++;
            i++;
        }
        i++;
    }
    return null;
}
/** True when two export contracts are identical (named + default + members). */
function sameExports(a, b) {
    if (!a || !b)
        return a === b;
    if (a.defaultName !== b.defaultName)
        return false;
    const as = [...a.names].sort();
    const bs = [...b.names].sort();
    if (as.length !== bs.length || !as.every((n, i) => n === bs[i]))
        return false;
    // Member whitelists must match too — a changed member list means dependents
    // that call those members must regenerate.
    for (const name of as) {
        const am = [...(a.members?.[name] || [])].sort();
        const bm = [...(b.members?.[name] || [])].sort();
        if (am.length !== bm.length || !am.every((n, i) => n === bm[i]))
            return false;
    }
    return true;
}
/**
 * Build a dependency graph from project edges.
 * Returns a map of node label → [labels it depends on]
 *
 * Callers pass the edges of ONE app tree (`resolveTreeScopes(project).intraEdges`
 * — see generateFiles): an edge between two app trees is a data handoff, not an
 * import, and feeding it here made app 2's file try to import app 1's source.
 * Exported so that boundary rule is unit-tested.
 */
export function buildDependencyGraph(nodes, edges) {
    const graph = new Map();
    // Build reverse dependency: if A → B edge, then B depends on A
    for (const edge of edges) {
        const sourceNode = nodes.find(n => n.id === edge.source);
        const targetNode = nodes.find(n => n.id === edge.target);
        if (!sourceNode || !targetNode)
            continue;
        const sourceLabel = sourceNode.data.label;
        const targetLabel = targetNode.data.label;
        if (!graph.has(targetLabel))
            graph.set(targetLabel, []);
        const deps = graph.get(targetLabel);
        if (!deps.includes(sourceLabel))
            deps.push(sourceLabel);
    }
    return graph;
}
/**
 * Get the file extension for a given language.
 */
export function getFileExtension(language) {
    switch (language?.toLowerCase()) {
        case 'typescript': return 'ts';
        case 'javascript': return 'js';
        case 'python': return 'py';
        case 'go': return 'go';
        case 'rust': return 'rs';
        case 'cpp':
        case 'c++': return 'cpp';
        case 'c': return 'c';
        case 'csharp':
        case 'c#': return 'cs';
        case 'swift': return 'swift';
        case 'kotlin': return 'kt';
        case 'java': return 'java';
        case 'ruby': return 'rb';
        case 'php': return 'php';
        case 'html': return 'html';
        case 'css': return 'css';
        default: return 'ts';
    }
}
/**
 * Check whether a file extension matches the expected extension for a given language.
 */
export function extensionMatchesLanguage(ext, language) {
    if (!ext || !language)
        return false;
    const langExt = getFileExtension(language);
    return ext.toLowerCase() === langExt.toLowerCase();
}
/**
 * Known file extensions that might appear in node labels.
 */
const KNOWN_EXTENSIONS = [
    '.ts', '.tsx', '.js', '.jsx', '.py', '.go', '.rs', '.rb', '.php',
    '.java', '.kt', '.swift', '.cpp', '.c', '.h', '.cs', '.css',
    '.html', '.scss', '.less', '.sql', '.json', '.xml', '.yaml', '.yml',
    '.md', '.sh', '.bash', '.dockerfile', '.toml', '.cfg', '.ini',
];
/**
 * Strip known file extensions from a label, returning [stripped_label, extension].
 * If no known extension is found, returns [original_label, ''] and keeps the original language-based extension.
 */
export function stripLabelExtension(label) {
    const lower = label.toLowerCase();
    for (const ext of KNOWN_EXTENSIONS) {
        if (lower.endsWith(ext)) {
            return {
                name: label.slice(0, -ext.length),
                extOverride: ext.slice(1), // Remove the leading dot
            };
        }
    }
    return { name: label, extOverride: '' };
}
/**
 * Sanitize a label into a valid file name (without extension).
 * Export so generation routes can reuse without duplicating extension logic.
 */
export function labelToFileName(label) {
    // Strip embedded extension first so we don't get "main.go" → "main-go" → "main-go.go"
    const { name } = stripLabelExtension(label);
    return name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
        .substring(0, 60) || 'untitled';
}
/**
 * The PascalCase type name a node label implies (`budget-store` -> `BudgetStore`).
 *
 * Only a heuristic, and deliberately used as one: the point is to tell the
 * model which CONCEPT a sibling already owns, not to predict its identifiers.
 */
export function nodeTypeStem(label) {
    const base = stripLabelExtension(label || '').name;
    return base
        .split(/[^A-Za-z0-9]+/)
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
        .join('');
}
/**
 * The graph-free TYPE OWNERSHIP block injected into every per-node prompt.
 *
 * A duplicate class across nodes is the #1 generation-quality build failure
 * (measured: `TemperatureLog` declared by both `cli.swift` and `stats.swift`;
 * `BudgetStore`/`BudgetEntry` declared twice in the C# budget app). It happens
 * because each node is generated independently and, on a build with no wiring
 * graph, NOTHING says which node owns the app's shared domain types. The
 * blueprint path's `contractContext` covers this only when the ownership can be
 * derived from a wiring edge (`blueprint/bible.ts`), and a canvas build has no
 * edges at all — so this block states the rule directly: exactly one file owns
 * each domain type, and a sibling's concept is never redeclared.
 *
 * Emitted for every project with at least two code nodes; a single-file app has
 * nothing to collide with, so its prompt stays byte-identical.
 */
export function buildTypeOwnershipSection(nodeLabel, siblings) {
    if (siblings.length === 0)
        return '';
    const stem = nodeTypeStem(nodeLabel);
    const lines = [];
    lines.push('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    lines.push('TYPE OWNERSHIP (MANDATORY)');
    lines.push('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    lines.push('Every domain type in this app has EXACTLY ONE owner file. A class/struct/record/interface/enum declared in two files is a redeclaration error and fails the build.');
    lines.push(`THIS FILE ("${nodeLabel}") owns the types that carry ITS OWN responsibility${stem ? ` — its own domain type is named like \`${stem}\`` : ''}. Declare those here, once, and export them.`);
    lines.push('These sibling nodes own THEIR concepts — their types are NOT yours:');
    for (const s of siblings.slice(0, 20)) {
        const sibStem = nodeTypeStem(s.label);
        const desc = String(s.description || '').replace(/\s+/g, ' ').trim().slice(0, 70);
        lines.push(`  - ${s.label}${sibStem ? ` — owns types named like \`${sibStem}*\`` : ''}${desc ? ` (${desc})` : ''}`);
    }
    lines.push('BEFORE you declare any type: if the concept belongs to a sibling above (a store, a record, a stats/log type), use THAT sibling\'s exported type instead of writing your own — add an import/using only if this language needs one. NEVER declare a type whose definition already exists in a sibling file.');
    lines.push('If no sibling owns the concept, declare it in exactly ONE file — this one — and export it so siblings reuse it.');
    lines.push('Do NOT declare the program entry point (main/Main) — only one file in the app may define it.');
    return `\n\n${lines.join('\n')}`;
}
/**
 * Sanitize a label into a valid export/function name (camelCase).
 */
function labelToExportName(label) {
    const sanitized = label.replace(/[^a-zA-Z0-9]/g, ' ');
    return sanitized
        .split(/\s+/)
        .map((word, i) => i === 0
        ? word.toLowerCase()
        : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join('')
        .replace(/^[0-9]/, '_$&') || 'Untitled';
}
/**
 * Stable signature of a project's node graph (labels, descriptions, types,
 * languages, edges, target OS), normalized so equal graphs always produce the
 * same signature regardless of array order. Used to reuse a cached generation
 * result when the canvas hasn't changed since it was generated.
 *
 * WHY: /api/generate/:id/files and /api/export/:id/per-file-scaffold both run
 * the LLM. Regenerating on export produced a DIFFERENT (non-deterministic)
 * codebase than the one the user just saw, and the scaffold's entry point
 * could import symbols that never appeared in the exported files. Caching the
 * last generation per project makes exports reuse exactly what was generated.
 */
export function projectGraphSignature(project) {
    const nodes = (project.nodes || [])
        .map((n) => ({
        id: n.id ?? '',
        label: n.data?.label ?? n.label ?? '',
        description: n.data?.description ?? '',
        type: n.data?.type ?? n.type ?? '',
        language: n.data?.language ?? '',
        // Tree membership is part of the graph: moving a node between app trees
        // changes which app it is generated into, so it must invalidate the cache.
        treeId: n.data?.treeId ?? '',
    }))
        .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    // Edges carry the cross-app payload too: re-wiring "login session" to
    // "database records" between the same two nodes produces a DIFFERENT bridge
    // module, so a bare source->target key would serve the stale one from cache.
    const edges = (project.edges || [])
        .map((e) => {
        const d = e.data || {};
        const xt = d.kind === 'cross-tree'
            ? `|cross-tree|${d.payloadType ?? ''}|${d.payloadLabel ?? ''}|${d.payloadDetail ?? ''}|${d.description ?? ''}`
            : `${d.semantic ? '|semantic' : ''}|${d.label ?? ''}`;
        return `${e.source ?? ''}->${e.target ?? ''}${xt}`;
    })
        .sort();
    // The app trees themselves (name, goal, root) — renaming a tree or changing
    // its goal changes the bridge prompts, so it belongs in the key as well.
    const trees = (project.trees || [])
        .map((t) => ({
        id: t?.id ?? '',
        name: t?.name ?? '',
        goal: t?.goal ?? '',
        rootNodeId: t?.rootNodeId ?? '',
    }))
        .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    // The master node's goal/purpose/scale MUST be part of the signature: the
    // cache is keyed per project id, and a project whose goal changed ("chess"
    // → "countdown timer") but whose node labels stayed the same used to reuse
    // the stale cached generation verbatim — the countdown build shipped chess
    // config code. Same for the project name.
    const master = (project.nodes || []).find((n) => n.type === 'master');
    const md = master?.data ?? {};
    return JSON.stringify({
        nodes,
        edges,
        trees,
        targetOS: project.targetOS ?? '',
        name: project.name ?? '',
        goal: md.appGoal ?? '',
        purpose: md.appPurpose ?? '',
        scale: md.scale ?? '',
    });
}
/**
 * Build an import statement for one file depending on another.
 *
 * @param sourceFileName - The sanitized file name (e.g. "types-go")
 * @param sourceExports - Exported symbols from the source file
 * @param language - Target language
 * @param moduleName - Optional module/package name (required for Go to generate valid import paths)
 *                     e.g. "chess-game" → import "chess-game/src/types-go"
 */
/**
 * Sanitize a project name into a valid Go module path segment — must match the
 * scaffolder's go.mod module name (lowercase slug). Using the raw project
 * title (spaces, commas) produced `malformed import path ... invalid char ' '`
 * on every exported Go project.
 */
// Re-exported from the neutral shared module (the chat write path uses the
// same sanitizer so the export's import paths match its go.mod).
export { sanitizeGoModuleName };
export function buildImportStatement(sourceFileName, sourceExports, language, moduleName) {
    const ext = getFileExtension(language);
    const names = sourceExports.names || [];
    const exportsStr = names.length > 0
        ? `{ ${names.join(', ')} }`
        : '*';
    switch (language?.toLowerCase()) {
        case 'typescript':
        case 'javascript': {
            // IMPORTANT: node files live in PER-NODE subdirectories
            // (src/<node-label>/<file>.ts), so a cross-node import must walk UP one
            // level and into the dependency's directory: `../<dep>/<dep>.ts`.
            // A flat `./<dep>.ts` (relative to the importing node's own directory)
            // fails with TS2307 "Cannot find module" because the sibling module does
            // not live there.
            const tsPath = `../${sourceFileName}/${sourceFileName}.${ext}`;
            // A dependency that only default-exports must be imported as
            // `import X from '…'` — `import { X }` fails with TS2614. A dependency
            // with NO exports at all is imported for its side effects
            // (`import '…'`), never `import * from '…'` (a TS1005 syntax error).
            if (sourceExports.defaultName && names.length === 0) {
                return `import ${sourceExports.defaultName} from '${tsPath}';`;
            }
            if (sourceExports.defaultName) {
                return `import ${sourceExports.defaultName}, ${exportsStr} from '${tsPath}';`;
            }
            if (names.length === 0) {
                return `import '${tsPath}';`;
            }
            return `import ${exportsStr} from '${tsPath}';`;
        }
        case 'python':
            // Python can't import hyphenated directory names — convert to underscores
            const pyMod = sourceFileName.replace(/-/g, '_');
            if (names.length > 0) {
                return `from ${pyMod} import ${names.join(', ')}`;
            }
            return `from ${pyMod} import *`;
        case 'go':
            // Go requires full module import paths for subdirectories
            // e.g. import "chess-game/src/types-go"
            if (moduleName) {
                return `import "${moduleName}/src/${sourceFileName}"`;
            }
            return `import "${sourceFileName}"`;
        case 'rust':
            // Rust uses `use crate::mod_name::Export;` for cross-module imports.
            // The module name is derived from the source file name (hyphens → underscores).
            // Multiple exports must be wrapped in braces: `use crate::mod::{A, B, C};`
            const rustMod = sourceFileName.replace(/-/g, '_');
            if (names.length === 0) {
                return `use crate::${rustMod};`;
            }
            else if (names.length === 1) {
                return `use crate::${rustMod}::${names[0]};`;
            }
            else {
                return `use crate::${rustMod}::{${names.join(', ')}};`;
            }
        default:
            return `// import from ${sourceFileName}.${ext}`;
    }
}
/**
 * Post-write contract verifier for the CANVAS path: statically scan a
 * generated file's FINAL assembled code and verify every cross-file import
 * against the REAL export contracts of its dependencies (the fileExports map,
 * populated from the already-generated files it imports). Mirrors the
 * codePlanner post-write verifier, but the canvas path has no declared plan —
 * the dependency exports ARE the contract source of truth.
 *
 * Two violation classes, both rendered in the same TSxxxx format the repair
 * loop already feeds the model, so they flow into the existing fix pipeline
 * verbatim:
 *   - TS2307: imports a module that is not one of this file's dependencies
 *     (the AI importing a wrong sibling). Only flagged when the reference is
 *     UNAMBIGUOUSLY project-local (relative `../x`, `from .x`, `crate::x`,
 *     generator-layout Go paths) so stdlib/third-party imports can never
 *     false-positive.
 *   - TS2614: imports a member the target neither exports nor declares.
 *
 * Pure + best-effort (regex, not a compiler) — violations feed a repair pass,
 * they never hard-fail a build. For Python/Go/Rust, which have no live tsc
 * gate, this is the only static cross-file check the canvas path runs; for
 * TS/JS it is defense-in-depth on top of the tsc gate.
 */
export function verifyGeneratedCodeContracts(code, language, deps, fileExports) {
    if (!deps.length)
        return [];
    const violations = [];
    // Comment-free scan copy so JSDoc/example comments mentioning imports can
    // never register a false hit (same discipline as findInventedMembers).
    const lang = language?.toLowerCase();
    let scanCode = code
        .replace(/\/\/[^\n]*/g, '')
        .replace(/\/\*[\s\S]*?\*\//g, '');
    // Per-language string handling so embedded code samples / docstrings can
    // never register a false import hit WITHOUT eating the quoted specifiers of
    // real imports (TS/JS and Go import paths are quoted strings — their quotes
    // are never stripped). Import regexes below are additionally anchored to
    // line start, matching where real import statements live in final code.
    if (lang === 'python') {
        // Python imports contain no quotes, so all string literals are safe to
        // strip (docstrings included); `#` comments are Python's comment syntax.
        scanCode = scanCode
            .replace(/#[^\n]*/g, '')
            .replace(/"""(?:[^"\\]|\\.|"(?!""))*"""/g, ' ')
            .replace(/'''(?:[^'\\]|\\.|'(?!''))*'''/g, ' ')
            .replace(/"(?:[^"\\]|\\.)*"/g, ' ')
            .replace(/'(?:[^'\\]|\\.)*'/g, ' ');
    }
    else if (lang === 'typescript' || lang === 'javascript') {
        // Only template literals (the common code-sample vehicle) — single-line
        // quoted strings stay, but their mid-line `import` text can't match the
        // line-anchored regexes below.
        scanCode = scanCode.replace(/`[^`]*`/g, ' ');
    }
    else if (lang === 'rust') {
        // `use` statements contain no quotes, so double-quoted strings are safe
        // to strip.
        scanCode = scanCode.replace(/"(?:[^"\\]|\\.)*"/g, ' ');
    }
    // Module token per dependency, in the form imports reference each language's
    // files: TS/JS `../<dep>/<dep>.ts` → `<dep>`; python/rust `-`→`_`; go the
    // last path segment of `"<module>/src/<dep>"`.
    const tokenToDep = new Map();
    for (const dep of deps) {
        const fileName = labelToFileName(dep);
        const mod = lang === 'python' || lang === 'rust' ? fileName.replace(/-/g, '_') : fileName;
        if (!tokenToDep.has(mod))
            tokenToDep.set(mod, dep);
    }
    const flagUnknownModule = (mod) => {
        violations.push(`TS2307: Cannot find module '${mod}' — it is not a declared dependency of this file. Import ONLY from the dependencies listed in IMPORT TARGETS.`);
    };
    const flagMissingMember = (mod, member) => {
        const dep = tokenToDep.get(mod);
        const info = dep ? fileExports.get(dep) : undefined;
        const available = info?.names?.length ? info.names.join(', ') : '(nothing — do not import from it)';
        violations.push(`TS2614: Module '${mod}' has no exported member '${member}'. ONLY these are exported: ${available}. Import a member that exists, or implement '${member}' locally.`);
    };
    const checkMembers = (mod, members) => {
        const dep = tokenToDep.get(mod);
        if (!dep)
            return;
        const info = fileExports.get(dep);
        const provided = new Set(info?.names || []);
        for (const raw of members) {
            // Normalize `A as B` → `A` so aliased imports verify by real name.
            const member = raw.trim().split(/\s+as\s+/)[0]?.trim();
            if (member && member !== '*' && member !== 'default' && !provided.has(member)) {
                flagMissingMember(mod, member);
            }
        }
    };
    if (lang === 'typescript' || lang === 'javascript') {
        // Named imports (auto-built, plus any AI import that survived stripping):
        // `import { A, B } from '../dep/dep.ts'`, `import X, { A } from '...'`,
        // `import type { A } from '...'`.
        for (const m of scanCode.matchAll(/^\s*import\s*(?:type\s+)?(?:[A-Za-z_$][\w$]*\s*,\s*)?\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/gm)) {
            const mod = m[2].split('/').pop().replace(/\.(ts|js|mjs|cjs)$/i, '');
            if (!tokenToDep.has(mod)) {
                flagUnknownModule(mod);
                continue;
            }
            checkMembers(mod, m[1].split(','));
        }
        // Default / namespace imports: `import X from '...'`, `import * as X from '...'`.
        // Members are never checked here (a default import is valid whenever the
        // target default-exports; the tsc gate is the authority for that), only the
        // module must be a declared dependency.
        for (const m of scanCode.matchAll(/^\s*import\s*(?:type\s+)?(?:\*\s+as\s+)?[A-Za-z_$][\w$]*\s+from\s*['"]([^'"]+)['"]/gm)) {
            const mod = m[1].split('/').pop().replace(/\.(ts|js|mjs|cjs)$/i, '');
            if (!tokenToDep.has(mod))
                flagUnknownModule(mod);
        }
    }
    else if (lang === 'python') {
        // Member checks on `from <mod> import ...` when <mod> IS a known dep
        // (covers auto-built imports + surviving AI imports of real deps).
        for (const m of scanCode.matchAll(/^from\s+([\w.]+)\s+import\s+([\s\S]*?)$/gm)) {
            const mod = m[1].split('.')[0];
            if (!tokenToDep.has(mod))
                continue; // stdlib/external — never flagged
            const items = m[2].trim();
            if (items === '*' || items.startsWith('('))
                continue;
            checkMembers(mod, items.split(','));
        }
        // Unambiguous unknown-module: relative `from .x` / `from ..x` only.
        for (const m of scanCode.matchAll(/^from\s+(\.+[\w.]+)\s+import/gm)) {
            const mod = m[1].replace(/^\.+/, '').split('.')[0];
            if (mod && !tokenToDep.has(mod))
                flagUnknownModule(mod);
        }
    }
    else if (lang === 'rust') {
        // `use crate::game;` | `use crate::game::ChessGame;` | `use crate::game::{A, B};`
        for (const m of scanCode.matchAll(/^\s*use\s+crate::([a-zA-Z_][\w]*)(?:::\{([^}]*)\}|::([a-zA-Z_][\w]*))?;?/gm)) {
            const mod = m[1];
            if (!tokenToDep.has(mod)) {
                flagUnknownModule(mod);
                continue;
            }
            const members = m[2] ? m[2].split(',') : m[3] ? [m[3]] : [];
            checkMembers(mod, members);
        }
    }
    else if (lang === 'go') {
        // `import "path"` and `import ( "a" "b" )`. Only the generator's own
        // `<module>/src/<dep>` layout is unambiguous — bare `"fmt"` / `"encoding/json"`
        // imports can never be flagged.
        for (const m of scanCode.matchAll(/^\s*import\s+((?:"[^"]+")|\(\s*(?:"[^"]*"\s*,?\s*)+\))/gm)) {
            for (const q of m[1].matchAll(/"([^"]+)"/g)) {
                const spec = q[1];
                if (!/\/src\//.test(spec))
                    continue;
                const mod = spec.split('/').pop().replace(/\.go$/, '');
                if (!tokenToDep.has(mod))
                    flagUnknownModule(mod);
            }
        }
    }
    return violations;
}
/**
 * Post-process TypeScript/JavaScript node code: strip AI-generated import
 * statements.
 *
 * The AI repeatedly emits its own sibling imports despite the prompt forbidding
 * them. Symptoms: the same module imported twice (TS2300 duplicate identifier),
 * extensionless relative paths (TS2307), and imports of files that do not exist
 * (TS2307). The build system adds dependency imports automatically, so ALL
 * top-level import statements are stripped — the auto-generated import section
 * is the single source of truth for cross-file imports.
 *
 * Hardened vs. the original "leading-run only" stripper, which let two failure
 * modes through (both observed in live builds):
 *   - `import{...}` without a space (the old /^import\s/ regex required one)
 *   - imports placed AFTER the first non-import statement (mid-file imports
 *     from the wrong sibling, e.g. importing a symbol from a file that does
 *     not export it)
 * Now any column-0 import statement is stripped (plus the full leading run),
 * and multi-line block imports (`import {` … `} from '...';`) are consumed
 * through their terminating `;`. Indented lines are left untouched so
 * template-literal / string content that merely contains the word "import"
 * is never corrupted.
 */
/**
 * Deterministic import-collision guard: collect every top-level name a TS/JS
 * file declares itself (`export class/interface/enum/function/const/let/type X`
 * or a bare `class/interface/enum/function/const/let/type X` at column 0).
 * assembleTsJs uses this to skip auto-importing the same name from a sibling
 * file — importing a name the file already declares breaks tsc with
 * TS2440/TS2395/TS2300, and the local declaration is the one other files will
 * import from anyway.
 *
 * Matches declaration keywords at line start (after optional `export` /
 * `declare` / `abstract`), so `const x = ...` inside a function body is never
 * mistaken for a top-level declaration.
 */
export function findLocalDeclaredNames(code) {
    const names = new Set();
    // export class Foo / export interface Foo / export function foo / export const foo / export type Foo / export enum Foo
    const declRe = /^(?:export\s+)?(?:declare\s+)?(?:abstract\s+)?(?:class|interface|enum|function|type|const|let|var)\s+([A-Za-z_$][\w$]*)/gm;
    let m;
    while ((m = declRe.exec(code)) !== null) {
        names.add(m[1]);
    }
    // Also handle `export { Foo, Bar }` re-export blocks (names still collide if
    // the file imports the same names).
    const reexportRe = /^export\s*\{[^}]*\}/gm;
    while ((m = reexportRe.exec(code)) !== null) {
        for (const nm of m[0].matchAll(/[A-Za-z_$][\w$]*/g)) {
            if (nm[0] !== 'export')
                names.add(nm[0]);
        }
    }
    return names;
}
export function findScopeLeaks(code, ctx) {
    const errors = [];
    const stripped = stripStringsAndComments(code);
    // 1) Inline event-handler scope (classic seq 13): onclick="fn(...)" strings
    //    inside template literals reference module-local functions that the
    //    browser evaluates in GLOBAL scope — they throw ReferenceError at
    //    runtime and tsc can't see it. Scan the RAW code (handlers live inside
    //    template literals) for handler attribute names.
    const handlerRe = /\bon(?:click|change|input|submit|keyup|keydown|keypress|load|focus|blur|dblclick|contextmenu|mouseover|mouseout|mousedown|mouseup|select|scroll|toggle)\s*=\s*["']([A-Za-z_$][\w$]*)\s*\(/gi;
    const topDecls = collectTopLevelDecls(stripped);
    let hm;
    while ((hm = handlerRe.exec(code)) !== null) {
        const fn = hm[1];
        if (GLOBAL_NAMES.has(fn) || topDecls.has(fn))
            continue;
        errors.push(`TS2304: Cannot find name '${fn}' — inline ${hm[0].split('=')[0].trim()} handler references a function that is NOT visible from the HTML attribute (inline handlers run in GLOBAL scope; '${fn}' is module-local inside this file). Attach the listener programmatically inside render() with addEventListener (e.g. btn.addEventListener('click', () => ${fn}(...))) instead of an inline onclick attribute.`);
    }
    // 2) Scope containment (block-tree): an identifier referenced at a position
    //    is a leak when no declaration of that name is visible from that
    //    position. Visibility = declarations in the same block, any ANCESTOR
    //    block, or module scope; sibling blocks CANNOT see each other's locals
    //    (seq 12 stopwatch: timerInterval/elapsedTime declared in the Start
    //    handler, referenced from Stop/Reset/Lap). Never-declared names are the
    //    seq 8 class (boardState/currentPlayer as implicit globals); a module-
    //    scope reference to a function-local is the seq 9 class.
    const blocks = buildBlockTree(stripped);
    const moduleDecls = blocks.length ? blocks[0].decls : collectTopLevelDecls(stripped);
    const refs = collectRefsWithPos(stripped);
    for (const ref of refs) {
        if (GLOBAL_NAMES.has(ref.name) || TS_KEYWORDS.has(ref.name))
            continue;
        if (moduleDecls.has(ref.name))
            continue;
        // Walk the reference's ancestor chain (innermost block → … → module root).
        // The name is visible iff ANY ancestor-or-self block declares it — a local
        // in the same function, a sibling scope, or a module-level declaration.
        // Sibling FUNCTION bodies never share an ancestor below the module, so a
        // name declared only in one handler and used in another is NOT visible.
        const refBlock = innermostBlockAt(blocks, ref.pos);
        const declaringBlocks = [];
        for (const b of blocks)
            if (b.decls.has(ref.name))
                declaringBlocks.push(b.id);
        const visible = refBlock
            ? declaringBlocks.some((id) => isAncestor(blocks, id, refBlock.id))
            : false;
        if (visible)
            continue;
        if (declaringBlocks.length > 0) {
            errors.push(`TS2451: '${ref.name}' is referenced here but declared in a different scope (${describeScope(blocks, declaringBlocks[0], ref.pos, stripped)}) — it is out of scope where it is used. Hoist the declaration to module scope, or receive it via a function parameter/return value instead of relying on a leaked local.`);
        }
        else {
            // Trace the name to a sibling module's exports so the guidance is exact:
            // "import it" if a DEPENDENCY exports it, "you cannot import it" if only
            // a non-dependency sibling does (seq 14: data-store.ts calls `convert`
            // from core-engine.ts, which is NOT one of its wiring deps — telling the
            // model to "declare it locally" just made it re-emit the same call).
            const self = ctx?.selfLabel;
            const depSet = new Set(ctx?.deps || []);
            const exportedBy = (ctx?.allExports
                ? [...ctx.allExports.entries()].filter(([label, names]) => label !== self && (names || []).includes(ref.name))
                : []);
            const depHit = exportedBy.find(([label]) => depSet.has(label));
            if (depHit) {
                errors.push(`TS2304: Cannot find name '${ref.name}' — it IS exported by your dependency ${labelToFileName(depHit[0])}.ts but you never imported it. WRITE the import for it (imports to dependency modules are allowed and the build dedupes them) or add it to your existing import from that module (see IMPORT TARGETS for its exact signature).`);
            }
            else if (exportedBy.length > 0) {
                const owners = [...new Set(exportedBy.map(([label]) => labelToFileName(label) + '.ts'))].join(', ');
                const depNames = (ctx?.deps || []).map(labelToFileName).join(', ');
                errors.push(`TS2304: Cannot find name '${ref.name}' — it is exported by ${owners}, but that module is NOT one of this file's dependencies (dependencies: ${depNames || 'none'}), so you CANNOT import it. If your logic duplicates what that module does, REMOVE this code and use a function from your actual dependencies (see IMPORT TARGETS) or implement '${ref.name}' locally.`);
            }
            else {
                errors.push(`TS2304: Cannot find name '${ref.name}' — it is referenced but never declared, imported, or received anywhere in this file. This is a multi-file app: you cannot rely on implicit globals. Declare it locally or pass it in as a function parameter.`);
            }
        }
    }
    return errors;
}
/**
 * Build the brace-block tree of the string-stripped code. Every `{...}` block
 * (function bodies, arrow bodies, control-flow bodies, object literals) is a
 * scope node; the module itself is the root (id 0, the whole code). Declarations
 * directly inside each block (const/let/var/function/class + params of the
 * enclosing function) are attached to it.
 */
function buildBlockTree(code) {
    // Import statements are module-level declarations, NOT scopes — their
    // `{ AIController }` braces must not create blocks (that would blank the
    // import and hide the name from the root decls). Blank the whole import line
    // for the brace scan; the names are collected separately for the root.
    let scanCode = code;
    const importNames = [];
    const importRe = /^\s*import[^\n;]*;?/gm;
    let im;
    while ((im = importRe.exec(code)) !== null) {
        const seg = im[0];
        for (const nm of seg.matchAll(/[A-Za-z_$][\w$]*/g)) {
            if (!['import', 'from', 'type', 'as'].includes(nm[0]))
                importNames.push(nm[0]);
        }
        scanCode = scanCode.slice(0, im.index) + ' '.repeat(seg.length) + scanCode.slice(im.index + seg.length);
    }
    const blocks = [
        { id: 0, start: 0, end: code.length, parent: null, decls: new Set(importNames) },
    ];
    let nextId = 1;
    const stack = [0];
    // Destructuring patterns (`const { a, b } = ...`) must NOT become scope
    // blocks: a `{` that opens a binding pattern has no declarations of its own,
    // and treating it as a block blanks the destructured names from the parent
    // block's direct text — so `state`/`events` in
    // `const { state, events } = stateAndEvents;` were declared NOWHERE and
    // every use was a false TS2304/TS2451 (observed on the tsc-verified
    // todo_list data-store.ts). collectAllDecls' destrRe then declares the names
    // in the ENCLOSING block, which is their true scope. Only the const/let/var
    // statement form is skipped (object literals after `=`/`return`/`(` still
    // create blocks; function-param destructuring is rarer in generated code).
    let skipDepth = 0;
    for (let i = 0; i < scanCode.length; i++) {
        const c = scanCode[i];
        if (skipDepth > 0) {
            if (c === '{')
                skipDepth++;
            else if (c === '}')
                skipDepth--;
            continue;
        }
        if (c === '{') {
            // `const {` / `let {` / `var {` as the last tokens before this brace =
            // a destructuring binding pattern, not a scope.
            const prelude = scanCode.slice(Math.max(0, i - 60), i);
            if (/(?:^|[;{}])\s*(?:const|let|var)\s*$/.test(prelude)) {
                skipDepth = 1;
                continue;
            }
            const parent = stack[stack.length - 1] ?? 0;
            const id = nextId++;
            blocks.push({ id, start: i, end: i, parent, decls: new Set() });
            stack.push(id);
        }
        else if (c === '}') {
            const id = stack.pop() ?? 0;
            if (id !== 0)
                blocks[id].end = i;
        }
    }
    // Attach DIRECT declarations to each block: the block's body with every
    // DESCENDANT block blanked out, so a `let` in a nested function is never
    // counted as a declaration of the outer block (that would make sibling leaks
    // invisible — the outer block must not claim its children's locals). The
    // block's OWN span stays intact (only strictly-inner blocks are blanked).
    const blanked = code.split('');
    for (const b of blocks) {
        if (b.id === 0)
            continue;
        for (let i = b.start + 1; i <= b.end; i++)
            blanked[i] = ' ';
    }
    // Per-block DIRECT text: the block's body with every STRICT descendant
    // blanked out (a nested arrow's locals must never count as the outer block's
    // declarations — that would make sibling leaks invisible). Built by copying
    // the block's own chars and blanking any position inside a child block.
    const directText = (b) => {
        const chars = code.slice(b.start + 1, b.end).split('');
        for (const child of blocks) {
            if (child.id === b.id || child.id === 0)
                continue;
            if (child.start > b.start && child.end < b.end) {
                for (let i = child.start - (b.start + 1); i < child.end - (b.start + 1); i++) {
                    if (i >= 0 && i < chars.length)
                        chars[i] = ' ';
                }
            }
        }
        return chars.join('');
    };
    for (const b of blocks) {
        const text = b.id === 0
            ? code.split('').map((_, i) => (blocks.some((c) => c.id !== 0 && c.start <= i && i <= c.end) ? ' ' : code[i])).join('')
            : directText(b);
        for (const d of collectAllDecls(text, b.id === 0))
            b.decls.add(d);
    }
    // Class-member methods: run the method scanner on the RAW class body (the
    // blanked direct text destroys line structure — `  public handleMove(...)`
    // becomes one long line when nested bodies are blanked, breaking the
    // line-start anchor). A block whose prelude is `class Name` is a class body;
    // collect its member names + params from the original code.
    for (const b of blocks) {
        if (b.id === 0)
            continue;
        const prelude = code.slice(Math.max(0, b.start - 80), b.start);
        if (!/\bclass\s+[A-Za-z_$][\w$]*\s*$/.test(prelude))
            continue;
        const rawBody = code.slice(b.start + 1, b.end);
        const methodRe = /^\s*(?:(?:public|private|protected|static|readonly|async|declare|abstract)\s+)*(?:get\s+|set\s+|async\s+)?([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?::[^;{=]*)?/gm;
        let mm;
        while ((mm = methodRe.exec(rawBody)) !== null) {
            const params = mm[2];
            const hasTypedParam = /[A-Za-z_$][\w$]*\s*:\s*[A-Za-z_$][\w$]*/.test(params);
            const hasReturnType = /:\s*[A-Za-z_$][\w$<>\[\]|]*\s*$/.test(mm[0]);
            if (hasTypedParam || hasReturnType || params.trim() === '') {
                b.decls.add(mm[1]);
                // NOTE: method PARAMS are deliberately NOT added to the class block —
                // the param-attachment loop below declares them in the method BODY
                // block (the correct scope). Adding them here too made a param name
                // (e.g. `task` in `addTask(task: Task)`) a CLASS-scope declaration,
                // so an unrelated same-named property in another interface (e.g.
                // `task?: Task` in TaskRequest) was flagged TS2451 "declared in a
                // different scope" — a false positive on tsc-clean code (observed on
                // the verified todo_list build, all 5 files).
            }
        }
    }
    // Params: for each function-ish block `name(...) {` / `(...) => {` / arrow
    // `x => {`, the names inside the parens are visible throughout that block.
    // The paren must be a FUNCTION SIGNATURE (followed by `{` or `=>` directly),
    // never a call like `foo(x);` (whose block it does not start).
    for (const b of blocks) {
        if (b.id === 0)
            continue;
        const before = code.slice(Math.max(0, b.start - 140), b.start);
        // Find the LAST `(` ... `)` directly before the `{`, optionally followed by
        // `=>` (arrow: `(a, b) => {`), OR a bare arrow param `x => {`. Allow an
        // optional RETURN TYPE between `)` and `{` (`f(x: string): number {`) —
        // without it, function params on exported functions with return types are
        // never collected and every use is a false "never declared" leak.
        const m = before.match(/\(([^()]*)\)(?:\s*:\s*[^{()]*)?\s*(=>)?\s*$/);
        if (m) {
            const afterParen = code.slice(b.start, b.start + 1); // the `{`
            const prelude = before.slice(0, Math.max(0, before.length - m[0].length));
            // The `=>` may be captured INSIDE the match (m[2]) for `(...) => {`, or
            // in the prelude for `=> {` after a paren-less head.
            const isArrow = !!m[2] || /=>\s*$/.test(prelude);
            const isFnSig = afterParen === '{' && (isArrow ||
                /\bfunction\s+[A-Za-z_$][\w$]*\s*$/.test(prelude) ||
                // method or named arrow: `name(...) {` where name is preceded by a
                // statement boundary (never `.` = a call like obj.foo(...) { }
                /(?:^|[;{}])\s*(?:(?:public|private|protected|static|readonly|async|declare)\s+)*(?:get\s+|set\s+|async\s+)?[A-Za-z_$][\w$]*\s*$/.test(prelude));
            if (isFnSig) {
                for (const p of m[1].matchAll(/[A-Za-z_$][\w$]*/g)) {
                    if (!TS_KEYWORDS.has(p[0]))
                        b.decls.add(p[0]);
                }
                continue;
            }
        }
        // Bare arrow param: `forEach(btn => {` — a single identifier followed by
        // `=> {` directly before this block.
        const bare = before.match(/([A-Za-z_$][\w$]*)\s*=>\s*$/);
        if (bare && !TS_KEYWORDS.has(bare[1]))
            b.decls.add(bare[1]);
    }
    // Expression-bodied arrows (`x => expr` / `(a, b) => expr`): they create NO
    // `{` block, so their params would be declared NOWHERE and every use inside
    // the expression — e.g. `t` in `list.findIndex(t => t.id === id)` — is a
    // false TS2304 "Cannot find name 't'". Register the params in the innermost
    // enclosing block: the arrow sits inside it, so that block is the practical
    // visibility scope (a heuristic — a same-named real leak in that block is
    // still caught by the tsc gate, the lint is a repair hint, not the verdict).
    const exprArrowRe = /(?:\(([^()]*)\)|([A-Za-z_$][\w$]*))\s*=>\s*(?![\s{])/g;
    let ea;
    while ((ea = exprArrowRe.exec(code)) !== null) {
        const params = ea[1] !== undefined ? ea[1] : ea[2];
        const block = innermostBlockAt(blocks, ea.index);
        if (block) {
            for (const p of params.matchAll(/[A-Za-z_$][\w$]*/g)) {
                if (!TS_KEYWORDS.has(p[0]))
                    block.decls.add(p[0]);
            }
        }
    }
    // catch (e) bindings — the exception variable is a local, never a leak.
    const catchRe = /\bcatch\s*\(([^()]*)\)/g;
    let cm;
    while ((cm = catchRe.exec(code)) !== null) {
        for (const c of cm[1].matchAll(/[A-Za-z_$][\w$]*/g)) {
            if (!TS_KEYWORDS.has(c[0]))
                blocks[0].decls.add(c[0]);
        }
    }
    return blocks;
}
/** Innermost block containing `pos` (smallest span wins). */
function innermostBlockAt(blocks, pos) {
    let best;
    for (const b of blocks) {
        if (b.start <= pos && pos <= b.end && (!best || b.end - b.start < best.end - best.start))
            best = b;
    }
    return best;
}
/** Is block `ancestorId` an ancestor-or-self of block `id` in the tree? */
function isAncestor(blocks, ancestorId, id) {
    let cur = id;
    while (cur !== null) {
        if (cur === ancestorId)
            return true;
        cur = blocks.find((b) => b.id === cur)?.parent ?? null;
    }
    return false;
}
function describeScope(blocks, declId, refPos, code) {
    const decl = blocks.find((b) => b.id === declId);
    const ref = innermostBlockAt(blocks, refPos);
    const where = (b) => {
        if (!b || b.id === 0)
            return 'module scope';
        const line = code.slice(0, b.start).split('\n').length;
        const sample = code.slice(b.start, b.start + 60).split('\n')[0].trim().slice(0, 50);
        return `block starting at line ${line} (${sample || 'a function body'})`;
    };
    return `declared in ${where(decl)} but used at ${where(ref)}`;
}
/**
 * All identifier references in the file with their positions, excluding
 * property accesses (obj.name), type annotations (name: T), and keywords.
 */
function collectRefsWithPos(code) {
    const refs = [];
    const re = /[A-Za-z_$][A-Za-z0-9_$]*/g;
    let m;
    while ((m = re.exec(code)) !== null) {
        const prev = m.index > 0 ? code[m.index - 1] : '';
        const after = code.slice(m.index + m[0].length, m.index + m[0].length + 5);
        if (prev === '.' || prev === ':')
            continue; // property / type position
        if (/^\??\s*:/.test(after))
            continue; // annotation `x: Foo` / optional `x?: Foo` (the `?` previously defeated the skip)
        if (/^\s*=>/.test(after))
            continue; // arrow param `x => {` / `x=>{`
        if (prev === '(' && /^\s*\)\s*=>/.test(after))
            continue; // `(x) => {`
        if (TS_KEYWORDS.has(m[0]) || GLOBAL_NAMES.has(m[0]))
            continue;
        refs.push({ name: m[0], pos: m.index });
    }
    return refs;
}
/** Known browser/node globals + DOM + built-in APIs — never flagged as leaks. */
const GLOBAL_NAMES = new Set([
    // JS built-ins
    'Object', 'Array', 'String', 'Number', 'Boolean', 'Math', 'JSON', 'Date', 'RegExp',
    'Promise', 'Symbol', 'Map', 'Set', 'WeakMap', 'WeakSet', 'Error', 'TypeError',
    'RangeError', 'ReferenceError', 'SyntaxError', 'parseInt', 'parseFloat', 'isNaN',
    'isFinite', 'NaN', 'Infinity', 'undefined', 'null', 'BigInt', 'Intl', 'Reflect',
    'Proxy', 'Function', 'globalThis', 'arguments', 'eval', 'decodeURI', 'encodeURI',
    'decodeURIComponent', 'encodeURIComponent', 'ArrayBuffer', 'DataView', 'Uint8Array',
    'Uint16Array', 'Uint32Array', 'Int8Array', 'Int16Array', 'Int32Array', 'Float32Array',
    'Float64Array', 'Uint8ClampedArray', 'structuredClone', 'queueMicrotask',
    // browser / DOM
    'document', 'window', 'navigator', 'location', 'history', 'screen', 'localStorage',
    'sessionStorage', 'console', 'alert', 'confirm', 'prompt', 'fetch', 'XMLHttpRequest',
    'WebSocket', 'requestAnimationFrame', 'cancelAnimationFrame', 'setTimeout',
    'setInterval', 'clearTimeout', 'clearInterval', 'addEventListener', 'Event',
    'MouseEvent', 'KeyboardEvent', 'TouchEvent', 'CustomEvent', 'HTMLElement',
    'HTMLInputElement', 'HTMLButtonElement', 'HTMLDivElement', 'HTMLSpanElement',
    'HTMLTableElement', 'HTMLCanvasElement', 'Element', 'Node', 'Document', 'Text',
    'Comment', 'URL', 'URLSearchParams', 'Blob', 'File', 'FileReader', 'FormData',
    'Image', 'Audio', 'crypto', 'performance', 'matchMedia', 'ResizeObserver',
    'IntersectionObserver', 'MutationObserver', 'CanvasRenderingContext2D',
    'AudioContext', 'requestIdleCallback', 'cancelIdleCallback', 'atob', 'btoa',
    'origin', 'scrollTo', 'localStorage', 'event', 'getComputedStyle',
    // node
    'require', 'module', 'exports', 'process', 'Buffer', 'global', '__dirname',
    '__filename', 'setImmediate', 'clearImmediate', 'console',
]);
/** TS keywords / primitive type names that are never identifier references. */
const TS_KEYWORDS = new Set([
    'return', 'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'break',
    'continue', 'function', 'class', 'const', 'let', 'var', 'new', 'typeof',
    'instanceof', 'in', 'of', 'void', 'delete', 'try', 'catch', 'finally', 'throw',
    'this', 'super', 'yield', 'await', 'async', 'export', 'import', 'default',
    'static', 'get', 'set', 'extends', 'implements', 'interface', 'type', 'enum',
    'namespace', 'public', 'private', 'protected', 'readonly', 'abstract', 'as',
    'is', 'keyof', 'infer', 'satisfies', 'unknown', 'never', 'any', 'string',
    'number', 'boolean', 'object', 'symbol', 'bigint', 'true', 'false', 'null',
    'undefined', 'from', 'to', 'of', 'constructor', 'DOMContentLoaded', 'void',
]);
/**
 * Replace string/template/comment contents with spaces (preserving newlines
 * so line-relative regexes still align) so identifier scans never match words
 * inside string literals, template interpolations, or comments.
 */
function stripStringsAndComments(code) {
    let out = '';
    let i = 0;
    const n = code.length;
    while (i < n) {
        const c = code[i];
        const nx = code[i + 1];
        if (c === '/' && nx === '/') {
            while (i < n && code[i] !== '\n') {
                out += ' ';
                i++;
            }
            continue;
        }
        if (c === '/' && nx === '*') {
            out += '  ';
            i += 2;
            while (i < n && !(code[i] === '*' && code[i + 1] === '/')) {
                out += code[i] === '\n' ? '\n' : ' ';
                i++;
            }
            out += '  ';
            i += 2;
            continue;
        }
        if (c === '"' || c === "'" || c === '`') {
            const q = c;
            out += ' ';
            i++;
            while (i < n && code[i] !== q) {
                if (code[i] === '\\') {
                    i++;
                    out += ' ';
                }
                if (i < n) {
                    out += code[i] === '\n' ? '\n' : ' ';
                    i++;
                }
            }
            if (i < n) {
                out += ' ';
                i++;
            }
            continue;
        }
        // Regex literal: `/.../ ` where the `/` follows `(`, `,`, `=`, `:`, `[`, `!`,
        // or `return` — not a division. Blank it so words inside a regex (e.g.
        // /^Generated Password:\s*/) are never treated as identifier references.
        if (c === '/' && i > 0 && /[=(:,![?&|+\-*<>]|\breturn\s*$/.test(out.slice(-8))) {
            out += ' ';
            i++;
            let escaped = false;
            while (i < n) {
                if (!escaped && code[i] === '/') {
                    i++;
                    break;
                }
                if (!escaped && code[i] === '\n')
                    break; // unterminated — stop
                escaped = !escaped && code[i] === '\\';
                out += code[i] === '\n' ? '\n' : ' ';
                i++;
            }
            continue;
        }
        out += c;
        i++;
    }
    return out;
}
/**
 * Names declared at module scope (brace depth 0): export/function/class/const/
 * let/var/type/interface/enum declarations whose keyword sits at depth 0, plus
 * import binding names. Used to know which names inline handlers CAN see
 * (top-level functions are global-ish via the bundler's module wrapper — the
 * lint is conservative and only complains when the name is clearly local).
 */
function collectTopLevelDecls(code) {
    const names = new Set();
    const re = /^(?:export\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?(?:function|class|interface|enum|type|const|let|var)\s+([A-Za-z_$][\w$]*)/gm;
    let m;
    while ((m = re.exec(code)) !== null)
        names.add(m[1]);
    const importRe = /import\s*(?:type\s*)?(?:\{[^}]*\}|[A-Za-z_$][\w$]*|\*\s*as\s+[A-Za-z_$][\w$]*)\s*from/g;
    let im;
    while ((im = importRe.exec(code)) !== null) {
        const seg = im[0];
        for (const nm of seg.matchAll(/[A-Za-z_$][\w$]*/g)) {
            if (nm[0] !== 'import' && nm[0] !== 'from' && nm[0] !== 'type' && nm[0] !== 'as')
                names.add(nm[0]);
        }
    }
    return names;
}
/** Every declared name in the file regardless of scope (locals, params, destructure).
 *  When `moduleScope` is true, function params of top-level declarations are NOT
 *  counted (a render(container) param is body-scoped, never module-visible). */
function collectAllDecls(code, moduleScope = false) {
    const names = new Set();
    // const/let/var + function/class/type/interface/enum.
    const declRe = /(?:const|let|var|function|class|interface|enum|type)\s+([A-Za-z_$][\w$]*)/g;
    let m;
    while ((m = declRe.exec(code)) !== null)
        names.add(m[1]);
    if (!moduleScope) {
        // Function/arrow params ONLY — never call arguments. A param list is a `(`
        // immediately preceded by `function NAME`, an arrow `=>`, or a name that is
        // a declaration (method/function). A call like clearInterval(timerInterval)
        // must never declare timerInterval.
        const fnParamRe = /(?:\bfunction\s+[A-Za-z_$][\w$]*\s*|\([^()]*\)\s*=>|(?:^|[^\w$])(?:[A-Za-z_$][\w$]*)\s*)\(([^()]*)\)/g;
        let p;
        while ((p = fnParamRe.exec(code)) !== null) {
            // Only treat as params when this paren is a function signature: followed
            // by `=>`, `{`, or a return type `:`. A plain call `name(args);` or
            // `obj.name(args)` is not.
            const after = code.slice(p.index + p[0].length, p.index + p[0].length + 30);
            const isFnSig = /^\s*(?:=>|\{|:\s*[A-Za-z_$][\w$<>\[\]|]*\s*\{)/.test(after) ||
                /\bfunction\b/.test(code.slice(Math.max(0, p.index - 60), p.index));
            if (isFnSig) {
                for (const pn of p[1].matchAll(/[A-Za-z_$][\w$]*/g)) {
                    if (!TS_KEYWORDS.has(pn[0]))
                        names.add(pn[0]);
                }
            }
        }
    }
    const destrRe = /\{\s*([A-Za-z_$][\w$]*\s*(?::\s*[A-Za-z_$][\w$]*)?\s*(?:,\s*[A-Za-z_$][\w$]*\s*(?::\s*[A-Za-z_$][\w$]*)?)*)\s*}/g;
    let dm;
    while ((dm = destrRe.exec(code)) !== null) {
        for (const nm of dm[1].matchAll(/[A-Za-z_$][\w$]*/g))
            names.add(nm[0]);
    }
    // Class member methods: `save(k: string, v: number) { ... }` — the method
    // NAME is a declaration, not a reference (a `ds.save(...)` call must never
    // be flagged as an undeclared identifier). Methods almost always carry typed
    // params or a return type, so we require the parameter list to contain a type
    // annotation — a plain untyped call `foo(x)` is not treated as a method.
    // Class member methods — match at LINE START (direct text keeps newlines even
    // after blanking, so `[;{}]` boundaries are unreliable). `name(...)` whose
    // line begins with optional modifiers/access modifiers. Requires typed params,
    // a return type, or an empty param list (a bare call like `foo(x)` mid-line
    // is not a declaration). A line-start CALL like `handleSomething();` must not
    // match: after the parens the next non-space char must NOT be `;` or `=`
    // (a call/assignment — the method body `{` is blanked to a space in direct
    // text, so it shows up as nothing, which is what we want to allow).
    const methodRe = /^\s*(?:(?:public|private|protected|static|readonly|async|declare|abstract)\s+)*(?:get\s+|set\s+|async\s+)?([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?::[^;{=]*)?(?!\s*[;=])/gm;
    let mm;
    while ((mm = methodRe.exec(code)) !== null) {
        const params = mm[2];
        const hasTypedParam = /[A-Za-z_$][\w$]*\s*:\s*[A-Za-z_$][\w$]*/.test(params);
        const hasReturnType = /:\s*[A-Za-z_$][\w$<>\[\]|]*\s*$/.test(mm[0]);
        const isMethodLike = hasTypedParam || hasReturnType || params.trim() === '';
        if (isMethodLike)
            names.add(mm[1]);
    }
    const importRe = /import\s*(?:type\s*)?(?:\{[^}]*\}|[A-Za-z_$][\w$]*|\*\s*as\s+[A-Za-z_$][\w$]*)\s*from/g;
    let im;
    while ((im = importRe.exec(code)) !== null) {
        for (const nm of im[0].matchAll(/[A-Za-z_$][\w$]*/g)) {
            if (!['import', 'from', 'type', 'as'].includes(nm[0]))
                names.add(nm[0]);
        }
    }
    return names;
}
/**
 * Position-insensitive normalization of a generated-file compile error —
 * strips the trailing `(line N)` so a repair that merely MOVES an error to a
 * new line still counts as the same underlying issue. Mirrors codePlanner's
 * normalizeTscError for the fileGenerator error format (`TSxxxx: msg (line N)`).
 */
export function normalizeGenError(e) {
    return e.replace(/\(line \d+\)/g, '').trim();
}
/**
 * Error-CLASS normalization: strips quoted identifiers in addition to line
 * numbers, so `TS2339: Property 'push' does not exist on type 'Task'` and
 * `TS2339: Property 'find' does not exist on type 'Task'` collapse to the
 * SAME signature. Observed live (R9 audit): the 14B's repair rounds didn't
 * fix the failure CLASS — they just re-invented a DIFFERENT member each
 * round (push → some → find on the same Task type), so an exact-text
 * signature never matched and the loop ran all 3 slow rounds. Same error
 * class on the same file = no progress, even if the member name moved.
 */
export function normalizeGenErrorClass(e) {
    return normalizeGenError(e).replace(/['"][^'"]*['"]/g, "''").replace(/\s+/g, ' ').trim();
}
/**
 * Deterministic signature of ONE file's error set — position-insensitive AND
 * order-insensitive (errors sorted), and CLASS-aware (member/type names
 * stripped via normalizeGenErrorClass), so a repair that merely re-invents a
 * DIFFERENT broken member on the same type counts as stalled. Used by
 * compileCheckAndFix's per-file stall detection: a file whose error CLASS
 * set is unchanged is given up on instead of re-spending slow 14B rounds.
 */
export function genErrorSignature(errs) {
    return errs.map(normalizeGenErrorClass).sort().join('|');
}
/**
 * Deterministic signature of the WHOLE round's error map (file → errors),
 * sorted by file label. Used by compileCheckAndFix's GLOBAL no-progress
 * detection: when this is identical to the previous round's, no file moved
 * and the repair loop stops instead of re-spending slow 14B regenerations.
 */
export function genRoundSignature(errorsByLabel) {
    return [...errorsByLabel.entries()]
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([k, v]) => `${k}|${genErrorSignature(v)}`).join('\n');
}
/**
 * Truncation detector: a file cut off mid-generation (output token cap)
 * almost always ends with more opening `{` than closing `}`. Counts braces
 * outside strings/comments/template literals so inline `{` in code text never
 * trips it. Returns null when balanced, else the {open, close} counts.
 */
export function findTruncation(code) {
    let open = 0;
    let close = 0;
    let inString = null;
    let inTemplate = false;
    let inLineComment = false;
    let inBlockComment = false;
    for (let i = 0; i < code.length; i++) {
        const ch = code[i];
        const next = code[i + 1];
        if (inLineComment) {
            if (ch === '\n')
                inLineComment = false;
            continue;
        }
        if (inBlockComment) {
            if (ch === '*' && next === '/') {
                inBlockComment = false;
                i++;
            }
            continue;
        }
        if (inString) {
            if (ch === '\\') {
                i++;
                continue;
            }
            if (ch === inString)
                inString = null;
            continue;
        }
        if (inTemplate) {
            if (ch === '\\') {
                i++;
                continue;
            }
            if (ch === '`')
                inTemplate = false;
            continue;
        }
        if (ch === '/' && next === '/') {
            inLineComment = true;
            i++;
            continue;
        }
        if (ch === '/' && next === '*') {
            inBlockComment = true;
            i++;
            continue;
        }
        if (ch === '"' || ch === "'") {
            inString = ch;
            continue;
        }
        if (ch === '`') {
            inTemplate = true;
            continue;
        }
        if (ch === '{')
            open++;
        else if (ch === '}')
            close++;
    }
    if (open === close)
        return null;
    return { open, close };
}
export function postProcessTsJsCode(code, opts) {
    const keepSiblingImports = !!opts?.keepSiblingImports;
    const lines = code.split('\n');
    const out = [];
    let inLeadingBlock = true;
    let i = 0;
    while (i < lines.length) {
        const line = lines[i];
        const t = line.trim();
        const atCol0 = line.length > 0 && line[0] !== ' ' && line[0] !== '\t';
        // Import statement anywhere at column 0 (or anywhere in the leading block).
        // Matches `import x`, `import{ x`, `import type {` and multi-line blocks.
        if (/^import(\s|\{)/.test(t) && (inLeadingBlock || atCol0)) {
            // Consume through the terminating `;` (multi-line block form), bounded
            // so a runaway match can never swallow the rest of the file.
            let stmt = line;
            let guard = 1;
            let terminated = false;
            i++;
            while (i < lines.length && !/;\s*$/.test(stmt.trim()) && guard < 8) {
                stmt += '\n' + lines[i];
                i++;
                guard++;
            }
            terminated = /;\s*$/.test(stmt.trim());
            // Only a REAL import statement is stripped: it must either contain
            // `from '...'` (named/default/namespace form) or be `import '...'`.
            // This keeps template-literal content at column 0 — a line starting
            // with the word "import" inside a string — from being eaten.
            const isImport = terminated && (/\bfrom\b/.test(stmt) || /^import\s*['"]/.test(stmt.trim()));
            if (!isImport) {
                // Not an import statement after all (or the bound tripped) — restore
                // every consumed line so no legitimate content is ever dropped.
                out.push(...stmt.split('\n'));
                inLeadingBlock = false;
                continue;
            }
            // Multi-file mode (keepSiblingImports): KEEP imports of sibling modules
            // (relative specifiers — `./` or `../`), because cross-module types must
            // be visible IN the file for the model to code against real shapes and
            // to satisfy the scope-leak lint's "add the import" instruction (the
            // auto-import section dedupes against them). Bare/package imports
            // (third-party, never installed) are still stripped.
            if (keepSiblingImports && /from\s*['"]\.{1,2}\//.test(stmt)) {
                out.push(stmt.trimEnd());
                continue;
            }
            continue; // strip the whole statement
        }
        if (inLeadingBlock && (t === '' || t.startsWith('//') || t.startsWith('/*') || t.startsWith('*'))) {
            out.push(line); // keep comments/blank lines in the leading block
            i++;
            continue;
        }
        inLeadingBlock = false;
        out.push(line);
        i++;
    }
    return out.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}
/**
 * Collect the member names imported by a file's relative (sibling-module)
 * import statements — `import { A, B } from '../x/x.ts'`, default/namespace
 * forms, and multi-line blocks. The auto-import section uses this to skip
 * names the model already imported itself, so a kept model import never
 * produces a duplicate (TS2300/TS2440). Never matches `import 'pkg'` side
 * effects or bare packages (they are stripped before assembly anyway).
 */
export function findImportedNames(code) {
    const names = new Set();
    const importRe = /^\s*import\s+(?:type\s+)?(?!\.)([^;]*?)\s+from\s*['"]\.{1,2}\//gm;
    let m;
    while ((m = importRe.exec(code)) !== null) {
        const clause = m[1];
        // Default + named: `import Foo, { A, B } from`
        // Named block: `import { A, B } from`
        // Namespace: `import * as NS from`
        const blockMatch = clause.match(/\{([^}]*)\}/);
        if (blockMatch) {
            for (const nm of blockMatch[1].matchAll(/[A-Za-z_$][\w$]*/g)) {
                if (!['as', 'type'].includes(nm[0]))
                    names.add(nm[0]);
            }
        }
        const defaultMatch = clause.match(/^(\w+)\b/);
        if (defaultMatch && !clause.includes('* as'))
            names.add(defaultMatch[1]);
        const nsMatch = clause.match(/\*\s+as\s+([A-Za-z_$][\w$]*)/);
        if (nsMatch)
            names.add(nsMatch[1]);
    }
    return names;
}
/**
 * Post-process Go code generated by AI to fix structural issues.
 *
 * The AI often:
 * 1. Places import statements BEFORE the package declaration
 * 2. Generates its own import statements despite being told not to
 * 3. Generates duplicate func main() functions
 * 4. Uses invalid package names that shadow stdlib packages
 *
 * This function:
 * - Extracts the package declaration and moves it to line 1
 * - Strips AI-generated import statements (auto-generated imports are added separately)
 * - Removes any func main() from generated node files (only the root main.go should have it)
 * - Strips Go compilation comments/pseudo-code the AI sometimes inserts
 */
function postProcessGoCode(code) {
    let cleaned = code.trim();
    // Step 1: Strip any Go compilation comments or pseudo-code annotations
    // that sometimes appear (e.g., "GO Code:", "```go", etc.)
    cleaned = cleaned.replace(/^(?:GO\s+Code|Go\s+Code|```(?:go)?)\s*:?\s*\n*/i, '');
    cleaned = cleaned.replace(/\n*```\s*$/i, '');
    cleaned = cleaned.trim();
    // Step 2: Extract the package declaration
    const packageMatch = cleaned.match(/^\s*package\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*$/m);
    let packageName = 'main'; // default fallback
    let codeWithoutPackage = cleaned;
    if (packageMatch) {
        packageName = packageMatch[1];
        // Remove the package line from its current position
        codeWithoutPackage = cleaned.replace(/^\s*package\s+[a-zA-Z_][a-zA-Z0-9_]*\s*$/m, '').trim();
    }
    // Step 3: Strip ALL import statements that appear at the top level
    // These are the AI-generated imports — they conflict with auto-generated imports
    codeWithoutPackage = codeWithoutPackage.replace(/^import\s+"[^"]+"\s*\n*/gm, '');
    codeWithoutPackage = codeWithoutPackage.replace(/^import\s+\([^)]*\)\s*\n*/gm, '');
    codeWithoutPackage = codeWithoutPackage.trim();
    // Step 4: Remove func main() { ... } with proper brace matching
    // The AI sometimes generates these in non-entry-point files
    codeWithoutPackage = removeGoMainFunction(codeWithoutPackage);
    // Step 5: Rebuild the file with proper structure
    const lines = [];
    lines.push(`package ${packageName}`);
    lines.push('');
    lines.push(codeWithoutPackage);
    return lines.join('\n');
}
/**
 * Remove a top-level `func main() { ... }` block from Go code
 * using brace counting to handle nested braces properly.
 * Only removes the FIRST occurrence.
 */
function removeGoMainFunction(code) {
    // Match `func main()` with optional receiver and whitespace
    const mainRegex = /^func\s+main\s*\([^)]*\)\s*\{/m;
    const match = mainRegex.exec(code);
    if (!match)
        return code;
    const startIdx = match.index;
    let braceCount = 0;
    let endIdx = startIdx;
    let foundOpen = false;
    for (let i = startIdx; i < code.length; i++) {
        const ch = code[i];
        if (ch === '{') {
            braceCount++;
            foundOpen = true;
        }
        else if (ch === '}') {
            braceCount--;
            if (foundOpen && braceCount === 0) {
                endIdx = i + 1; // include the closing brace
                break;
            }
        }
    }
    // Remove from startIdx to endIdx, then clean up extra whitespace
    const before = code.substring(0, startIdx).trimEnd();
    const after = code.substring(endIdx).trimStart();
    return (before + '\n' + after).trim();
}
/**
 * Post-process Rust code generated by AI to fix structural issues.
 *
 * The AI often:
 * 1. Generates its own `use` statements despite being told not to
 * 2. Generates `fn main()` in non-entry-point files
 * 3. Forgets `pub` visibility on exports
 * 4. Wraps code in markdown fences
 *
 * This function:
 * - Strips markdown fences and pseudo-code annotations
 * - Strips AI-generated `use` statements (auto-generated via buildImportStatement)
 * - Strips any `mod` declarations (handled by the entry point)
 * - Removes `fn main()` from non-entry-point files
 */
function postProcessRustCode(code) {
    let cleaned = code.trim();
    // Step 1: Strip markdown fences and Rust compilation annotations
    cleaned = cleaned.replace(/^(?:```(?:rust)?)\s*\n*/i, '');
    cleaned = cleaned.replace(/\n*```\s*$/i, '');
    cleaned = cleaned.trim();
    // Step 2: Strip any AI-generated `use` statements at the top of the file.
    // These conflict with the auto-generated use statements from buildImportStatement.
    cleaned = cleaned.replace(/^use\s+.+;\s*\n*/gm, '');
    cleaned = cleaned.trim();
    // Step 3: Strip any `mod` declarations — these are handled by the root entry point.
    cleaned = cleaned.replace(/^mod\s+[a-zA-Z_][a-zA-Z0-9_]*\s*(?:;|\{[^}]*\})\s*\n*/gm, '');
    cleaned = cleaned.trim();
    // Step 4: Remove `fn main() { ... }` with proper brace matching.
    // Only the root main.rs should have fn main().
    cleaned = removeRustMainFunction(cleaned);
    // Step 5: Ensure `pub` visibility on top-level declaration items.
    // AI often forgets to make items public, which breaks cross-module access.
    // We add `pub` before specific Rust declaration keywords at the start of a line.
    // This is SAFE because:
    //   - We only match lines starting with declaration keywords (fn, struct, enum, etc.)
    //   - We DON'T match closing braces, impl blocks, control flow, etc.
    //   - We DON'T match lines that already have `pub`
    cleaned = cleaned.replace(/^(?!pub\b)(fn|struct|enum|trait|type|const|static|union)\s/mg, 'pub $&');
    return cleaned;
}
/**
 * Remove a top-level `fn main() { ... }` block from Rust code
 * using brace counting to handle nested braces properly.
 * Only removes the FIRST occurrence.
 */
function removeRustMainFunction(code) {
    // Match `fn main() { ... }` or `fn main() -> Result<...> { ... }`
    const mainRegex = /^fn\s+main\s*\([^)]*\)\s*(?:->\s*[^{]+)?\s*\{/m;
    const match = mainRegex.exec(code);
    if (!match)
        return code;
    const startIdx = match.index;
    let braceCount = 0;
    let endIdx = startIdx;
    let foundOpen = false;
    for (let i = startIdx; i < code.length; i++) {
        const ch = code[i];
        if (ch === '{') {
            braceCount++;
            foundOpen = true;
        }
        else if (ch === '}') {
            braceCount--;
            if (foundOpen && braceCount === 0) {
                endIdx = i + 1; // include the closing brace
                break;
            }
        }
    }
    // Remove from startIdx to endIdx, then clean up extra whitespace
    const before = code.substring(0, startIdx).trimEnd();
    const after = code.substring(endIdx).trimStart();
    return (before + '\n' + after).trim();
}
/**
 * Post-process Python code generated by AI to fix structural issues.
 *
 * The AI often:
 * 1. Generates `import` statements despite being told not to
 * 2. Generates `if __name__ == "__main__":` blocks with testing code
 * 3. Wraps code in markdown fences
 *
 * This function:
 * - Strips markdown fences
 * - Strips AI-generated `import` statements
 * - Removes `if __name__ == "__main__":` blocks (belongs in entry point only)
 * - Strips Python pseudo-code annotations
 */
function postProcessPythonCode(code) {
    let cleaned = code.trim();
    // Step 1: Strip markdown fences and Python annotations
    cleaned = cleaned.replace(/^(?:```(?:python)?)\s*\n*/i, '');
    cleaned = cleaned.replace(/\n*```\s*$/i, '');
    cleaned = cleaned.trim();
    // Step 2: Strip AI-generated import statements at the top of the file.
    // These conflict with the auto-generated imports from buildImportStatement.
    cleaned = cleaned.replace(/^import\s+[\w.]+(?:\s+as\s+\w+)?\s*\n*/gm, '');
    cleaned = cleaned.replace(/^from\s+[\w.]+\s+import\s+.+\s*\n*/gm, '');
    cleaned = cleaned.trim();
    // Step 3: Remove `if __name__ == "__main__":` blocks with proper indentation tracking.
    // These belong only in the entry point, not in node files.
    cleaned = removePythonIfMainBlock(cleaned);
    return cleaned;
}
/**
 * Remove a top-level `if __name__ == "__main__":` block from Python code.
 * Uses indentation tracking to find the matching end of the block.
 * Only removes the FIRST occurrence.
 */
function removePythonIfMainBlock(code) {
    // Match `if __name__ == "__main__":` or `if __name__ == '__main__':` at line start
    const mainRegex = /^if\s+__name__\s*==\s*["']__main__["']\s*:\s*$/m;
    const match = mainRegex.exec(code);
    if (!match)
        return code;
    const startIdx = match.index;
    const lineEndIdx = code.indexOf('\n', startIdx);
    if (lineEndIdx === -1) {
        // Single line if-block with no body — just remove it
        return code.substring(0, startIdx).trimEnd();
    }
    // The body starts on the next line — determine indentation
    const bodyStart = lineEndIdx + 1;
    const rest = code.substring(bodyStart);
    const bodyIndentMatch = rest.match(/^(\s+)\S/);
    if (!bodyIndentMatch) {
        // No body content — just remove the if line
        return code.substring(0, startIdx).trimEnd();
    }
    const bodyIndent = bodyIndentMatch[1];
    // Find end of the if-block: stop at a line with the same or less indentation as the `if`
    // The `if` itself is at indentation 0 (start of line)
    let endIdx = bodyStart;
    const lines = rest.split('\n');
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        // Skip empty lines and lines within the body (more indented than the body)
        if (line.trim() === '') {
            endIdx = bodyStart + lines.slice(0, i + 1).join('\n').length + 1;
            continue;
        }
        // Check if this line is at the same indentation as the `if` (0) or less
        const indent = line.match(/^(\s*)\S/);
        if (indent) {
            if (indent[1].length <= 0) {
                // Back to top-level — stop here
                break;
            }
            endIdx = bodyStart + lines.slice(0, i + 1).join('\n').length + 1;
        }
    }
    // Remove from startIdx to endIdx
    const before = code.substring(0, startIdx).trimEnd();
    const after = code.substring(endIdx).trimStart();
    return (before + '\n' + after).trim();
}
export class FileGenerator {
    ai;
    sandbox;
    /**
     * Actual generated source per node label, populated as files complete
     * (batch loop + repair loop). The per-file generation prompt injects the
     * REAL source of a file's dependencies (not just export names) so the model
     * codes against the actual shapes — the A/B tests showed 7B AND 14B models
     * fail cross-file contracts (private members, wrong shapes) purely because
     * they never see the dependency's code.
     */
    depSourceCache = new Map();
    constructor() {
        this.ai = new AITranslator();
        this.sandbox = new SandboxRunner();
    }
    /**
     * Generate individual files for each node in the project.
     * Each file gets standalone code with proper imports from dependency nodes.
     *
     * @param skipValidation - If true, skip sandbox validation on each generated file
     *                         (saves ~2-5s per file during preview builds)
     * @param onProgress - Optional callback invoked after each batch with progress info
     *                     (streams real-time generation status to the frontend via socket.IO)
     */
    async generateFiles(project, skipValidation, onProgress) {
        const nonMasterNodes = project.nodes.filter(n => n.type !== 'master');
        const masterNode = project.nodes.find(n => n.type === 'master');
        if (nonMasterNodes.length === 0) {
            return {
                files: [],
                totalChars: 0,
                totalErrors: 0,
                validatedCount: 0,
                failedCount: 0,
                importGraph: {},
                tsCompileClean: true, // no files at all → vacuously clean
                contractViolations: 0,
                languageGates: [],
            };
        }
        // ── Tree Mode: where one app ends and the next begins ──
        // An intra-tree edge is a FILE IMPORT. A cross-tree edge is a data handoff
        // between two SEPARATE programs and must never become an import — feeding
        // both kinds to the dependency graph made app B's source import app A's
        // file. The scope resolves membership (deriving a single tree for
        // pre-Tree-Mode projects, so the ordinary single-app build is unchanged),
        // splits the edge kinds, and plans the bridge modules that realize the
        // handoffs.
        const treeScope = resolveTreeScopes(project);
        const bridges = planBridges(treeScope);
        // Several app trees in one project are several APPS: each one is exported
        // into its own directory (with its own entry point and project config)
        // instead of being merged into one flat `src/`. A single-tree project keeps
        // the flat layout, so ordinary exports are byte-identical to before.
        const layout = planExportLayout(treeScope.trees);
        if (bridges.length > 0) {
            console.log(`[fileGenerator] Tree Mode: ${treeScope.trees.length} app tree(s), ` +
                `${treeScope.links.length} cross-app connection(s) → ${bridges.length} bridge module(s)`);
        }
        if (layout.separateApps) {
            console.log(`[fileGenerator] Tree Mode: exporting ${treeScope.trees.length} separate apps — ` +
                treeScope.trees.map((t) => `"${t.name}" → apps/${layout.appDirByTree[t.id] ?? 'app'}`).join(', '));
        }
        // Build dependency graph from edges (cross-tree edges excluded — see above)
        const depGraph = buildDependencyGraph(nonMasterNodes.map(n => ({ id: n.id, data: { label: n.data.label } })), treeScope.intraEdges);
        // Determine topological order for generation (dependencies first)
        const sortedNodes = this.topologicalSort(nonMasterNodes, depGraph);
        // ── Generate GUI widgets for UI/gui-layout nodes ──
        let guiWidgetOutput = null;
        const hasUINodes = sortedNodes.some(n => n.type === 'ui' || n.type === 'gui-layout');
        if (hasUINodes) {
            try {
                guiWidgetOutput = await this.generateGuiWidgets(project, sortedNodes);
            }
            catch (err) {
                console.warn('[fileGenerator] GUI widget generation failed (non-fatal):', err);
            }
        }
        // Generate files in dependency order — parallelized by topological batches
        const generatedFiles = [];
        const fileExports = new Map(); // label → export info
        let contractViolationCount = 0;
        // Batch nodes by topological depth: nodes in the same batch have NO
        // dependencies on each other and can be generated simultaneously.
        // ── Generation scheduler (dependency-aware worker pool) ──
        // The OLD scheduler used strict topological LEVELS and awaited every level
        // before starting the next. On a chain-shaped blueprint (each module layers
        // on the one below) a level contains exactly ONE node, so N modules cost N
        // strictly sequential LLM calls. Measured on a real tic-tac-toe build:
        //   "Generating 5 files in 5 parallel batch(es): batch 1: 1 nodes … batch 5:
        //    1 nodes"  →  10.8s + 29.6s + 35.1s + 17.1s + 36.1s ≈ 129s of pure
        //   serialisation before a single repair round even started.
        //
        // NOW: a bounded worker pool over the same topological order. A node starts
        // as soon as the pool has room, so nodes at DIFFERENT depths overlap. When
        // one of a node's dependencies is still in flight, the prompt carries that
        // dependency's PLANNED CONTRACT (node.data.contractContext, derived
        // deterministically from the wiring graph) instead of a misleading
        // "(none)", and the auto-import line for it is omitted so the model writes
        // its own import against the promised exports. The live compile-check loop
        // then reconciles any drift against the REALIZED exports.
        //
        // Concurrency genuinely pays here: DSpark serves concurrent completions in
        // parallel, not queued (measured 8.4s for one 220-token completion vs 9.4s
        // for two at the same time — ~1.1x for 2x the work).
        const MAX_PARALLEL_GENERATIONS = MAX_PARALLEL_MODEL_CALLS;
        const plannedContractByLabel = new Map();
        for (const n of sortedNodes) {
            const cc = n.data?.contractContext;
            if (typeof cc === 'string' && cc.trim()) {
                plannedContractByLabel.set(n.data.label || n.id, cc.trim());
            }
        }
        console.log(`[fileGenerator] Generating ${sortedNodes.length} file(s) — dependency-aware pool, up to ${MAX_PARALLEL_GENERATIONS} concurrent (planned contracts available for ${plannedContractByLabel.size})`);
        // Per-node generation body, hoisted out of the old level loop so any node
        // can run as soon as the pool has room. Unchanged apart from the
        // dependency-context fallback above and the progress reporting below.
        const generateOne = async (node) => {
            {
                const nodeLabel = node.data.label || node.id;
                const fileName = labelToFileName(nodeLabel);
                const language = node.data.language || 'typescript';
                const ext = getFileExtension(language);
                // Determine dependencies for this node (from PREVIOUS batches only)
                const deps = depGraph.get(nodeLabel) || [];
                // Build import section from already-completed dependency exports
                let importSection = '';
                const resolvedDeps = [];
                for (const depLabel of deps) {
                    const depExports = fileExports.get(depLabel);
                    if (depExports) {
                        const depFile = labelToFileName(depLabel);
                        // Pass the project name as the Go module name for correct import paths
                        importSection += buildImportStatement(depFile, depExports, language, sanitizeGoModuleName(project.name)) + '\n';
                        resolvedDeps.push(depLabel);
                    }
                }
                // Generate AI code for this node as a standalone file
                const isUINode = node.type === 'ui' || node.type === 'gui-layout';
                // Pass ALL declared deps (not just the already-resolved ones) so a
                // dependency still in flight is still described via its planned
                // contract. `resolvedDeps` stays the import-accurate list used by the
                // contract verifier below.
                const code = await this.generateNodeFile(node, project, deps, fileExports, isUINode ? guiWidgetOutput : null, undefined, { plannedContracts: plannedContractByLabel }, { scope: treeScope, bridges });
                // Determine what this file exports (named symbols + optional default)
                const exportInfo = this.extractExports(code, language);
                // ── Language-specific code assembly ──
                let fullCode;
                const lang = language?.toLowerCase();
                if (lang === 'go') {
                    // For Go: post-process AI code first, then properly interleave imports
                    const processedCode = postProcessGoCode(code);
                    if (importSection) {
                        // Insert auto-generated imports after the package declaration
                        fullCode = processedCode.replace(/^(package\s+\S+\s*)$/m, '$1\n\n' + importSection);
                    }
                    else {
                        fullCode = processedCode;
                    }
                }
                else if (lang === 'rust') {
                    // For Rust: post-process AI code, then prepend auto-generated use statements
                    const processedCode = postProcessRustCode(code);
                    fullCode = importSection
                        ? importSection + '\n' + processedCode
                        : processedCode;
                }
                else if (lang === 'python') {
                    // For Python: post-process AI code, then prepend auto-generated imports
                    const processedCode = postProcessPythonCode(code);
                    fullCode = importSection
                        ? importSection + '\n' + processedCode
                        : processedCode;
                }
                else {
                    // TS/JS: keep the model's sibling-module imports (multi-file mode —
                    // cross-module types must be visible in-file), strip everything
                    // else; the auto-import section below fills in anything missing.
                    const tsCode = postProcessTsJsCode(code, { keepSiblingImports: true });
                    if (deps.length > 0) {
                        // Deterministic import-collision fix (mirror of assembleTsJs): if
                        // this file declares a name locally OR already imported it itself,
                        // drop it from the auto-import so it never collides
                        // (TS2440/TS2395/TS2300). Also dedupes names exported by two
                        // different dependencies (TS2300 duplicate).
                        const localNames = findLocalDeclaredNames(tsCode);
                        const importedNames = findImportedNames(tsCode);
                        const seenNames = new Set();
                        let filteredSection = '';
                        const filteredDeps = [];
                        for (const depLabel of deps) {
                            const depExports = fileExports.get(depLabel);
                            if (!depExports)
                                continue;
                            const names = (depExports.names || []).filter(n => !localNames.has(n) && !importedNames.has(n) && !seenNames.has(n));
                            for (const n of names)
                                seenNames.add(n);
                            if (names.length === 0 && !depExports.defaultName)
                                continue;
                            const filtered = { ...depExports, names };
                            filteredSection += buildImportStatement(labelToFileName(depLabel), filtered, language, sanitizeGoModuleName(project.name)) + '\n';
                            filteredDeps.push(depLabel);
                        }
                        importSection = filteredSection;
                        // resolvedDeps is used by the contract verifier below — keep it in
                        // sync with what actually got imported.
                        resolvedDeps.length = 0;
                        resolvedDeps.push(...filteredDeps);
                    }
                    fullCode = importSection
                        ? importSection + '\n' + tsCode
                        : tsCode;
                }
                // Run sandbox validation on the file (skippable for preview builds)
                let errors = [];
                let validated = false;
                if (!skipValidation) {
                    try {
                        const validation = await this.sandbox.run(fullCode, language);
                        errors = validation.errors || [];
                        validated = validation.success;
                    }
                    catch {
                        errors = ['Sandbox validation unavailable'];
                    }
                }
                // ── Post-write contract verification (all languages) ──
                // Statically verify the FINAL assembled code's cross-file imports
                // against the real export contracts of its dependencies. For TS/JS
                // the compile-check loop below repairs violations; Python/Go/Rust
                // have no tsc gate, so a violation marks the file failed and keeps
                // it out of the verified-training capture.
                const contractViolations = verifyGeneratedCodeContracts(fullCode, language, resolvedDeps, fileExports);
                if (contractViolations.length > 0) {
                    errors.push(...contractViolations);
                    validated = false;
                    contractViolationCount += contractViolations.length;
                    console.log(`[fileGenerator]   ⚠️ contract verifier: ${contractViolations.length} violation(s) on "${nodeLabel}" (e.g. ${contractViolations[0].slice(0, 90)}…)`);
                }
                // ── Contract check (report-only): the codegen contract bans default
                // exports ("named exports only"). Counted into contractViolations as a
                // quality signal but deliberately NOT fed to the repair loop or marked
                // as a failure — the import builder and scaffolder handle default
                // exports correctly, so flagging them as errors would just burn LLM
                // repair rounds without changing the build outcome.
                if (lang === 'typescript' || lang === 'javascript') {
                    const defaultExportCount = (fullCode.match(/export\s+default/g) || []).length;
                    if (defaultExportCount > 0) {
                        contractViolationCount += defaultExportCount;
                        console.log(`[fileGenerator]   ℹ️ contract check: ${defaultExportCount} default export(s) on "${nodeLabel}" (contract prefers named exports)`);
                    }
                }
                // Use extension override from label ONLY if it matches the language
                const { extOverride } = stripLabelExtension(nodeLabel);
                const fileExt = (extOverride && extensionMatchesLanguage(extOverride, language)) ? extOverride : ext;
                // Record the finished source so LATER files (next batches) can see
                // this file's REAL code when it is one of their dependencies.
                this.depSourceCache.set(nodeLabel, fullCode);
                return {
                    generatedFile: {
                        fileName: `${fileName}.${fileExt}`,
                        language,
                        code: fullCode,
                        nodeId: node.id,
                        nodeLabel,
                        treeId: treeScope.treeIdByNode.get(node.id),
                        ...(layout.separateApps
                            ? { appDir: `apps/${layout.appDirByTree[treeScope.treeIdByNode.get(node.id) || ''] ?? 'app'}` }
                            : {}),
                        dependencies: resolvedDeps,
                        exports: exportInfo.names,
                        errors,
                        validated,
                    },
                    label: nodeLabel,
                    exportSymbols: exportInfo,
                };
            }
        };
        // ── Run the pool ──
        // Workers pull from the shared topological queue; completion order is
        // whatever finishes first, which is the point. `allSettled` semantics are
        // preserved — one failing node never loses the rest of the build.
        const poolResults = [];
        let queueCursor = 0;
        const totalNodes = sortedNodes.length;
        const poolWorker = async () => {
            while (true) {
                const idx = queueCursor++;
                if (idx >= totalNodes)
                    return;
                try {
                    const value = await generateOne(sortedNodes[idx]);
                    poolResults.push({ ok: true, value });
                }
                catch (reason) {
                    poolResults.push({ ok: false, reason });
                }
            }
        };
        const poolStart = Date.now();
        await Promise.all(Array.from({ length: Math.max(1, Math.min(MAX_PARALLEL_GENERATIONS, totalNodes)) }, () => poolWorker()));
        // Collect results — this populates fileExports for everything downstream.
        let batchFailures = 0;
        for (const r of poolResults) {
            if (r.ok && r.value) {
                generatedFiles.push(r.value.generatedFile);
                fileExports.set(r.value.label, r.value.exportSymbols);
            }
            else {
                batchFailures++;
                console.warn('[fileGenerator] Node generation failed in pool:', r.reason);
            }
        }
        if (batchFailures > 0) {
            console.warn(`[fileGenerator] ${batchFailures}/${totalNodes} node(s) failed during generation`);
        }
        console.log(`[fileGenerator] Pool finished ${totalNodes} node(s) in ${Date.now() - poolStart}ms (max ${MAX_PARALLEL_GENERATIONS} concurrent)`);
        // Progress: report the node list once the pool drains. The old per-level
        // reporting is meaningless now that levels overlap.
        if (onProgress) {
            onProgress({
                batch: Math.max(0, totalNodes - 1),
                totalBatches: totalNodes,
                batchSize: totalNodes,
                generatingNodes: poolResults
                    .filter(r => r.ok && r.value)
                    .map(r => r.value.generatedFile.nodeLabel),
                percent: 100,
                phase: 'done',
            });
        }
        // ── Tree Mode: generate the bridge module(s) ──
        // One module per (giving app → receiving app, payload) contract. It is the
        // ONLY integration point between those two apps: they are separate
        // programs and cannot import each other, so without this the handoff the
        // user described would exist as a prompt instruction and nothing else.
        // Generated BEFORE the compile gate on purpose — the compile loop never
        // regenerates a file with no node behind it, so a bridge that does not
        // compile surfaces as a compile failure (honest ⚠️) instead of shipping
        // silently under a green build.
        for (const bridge of bridges) {
            try {
                const bridgeFile = await this.generateBridgeModule(project, bridge);
                if (bridgeFile)
                    generatedFiles.push(bridgeFile);
            }
            catch (err) {
                console.warn(`[fileGenerator] bridge module "${bridge.name}" failed (non-fatal):`, err?.message || err);
            }
        }
        // ── Live compile-check-retry loop (generate → tsc → feed errors back → retry) ──
        // Mirrors the offline campaign repair loop, but runs LIVE during generation:
        // failing files are regenerated with the exact tsc errors as corrective
        // context, so the user gets compiling code on the first pass. Skipped for
        // fast preview builds (skipValidation=true) — the same builds that skip
        // sandbox validation.
        let compileFailures = 0;
        // True only when the live tsc loop ran to completion. If it was skipped
        // (no TS files, TSC_BIN missing, or a thrown error) the tsCompileClean
        // stamp must NOT be trusted for the training capture below.
        let compileCheckRan = false;
        if (!skipValidation) {
            try {
                compileFailures = await this.compileCheckAndFix(project, generatedFiles, fileExports, sortedNodes, depGraph, guiWidgetOutput);
                compileCheckRan = true;
            }
            catch (err) {
                console.warn('[fileGenerator] Live compile-check loop failed (non-fatal):', err);
            }
            if (compileFailures > 0) {
                console.warn(`[fileGenerator] ${compileFailures} file(s) still fail tsc after live compile-check retries`);
            }
            else {
                console.log('[fileGenerator] Live compile-check: all TS/JS files compile clean');
            }
        }
        // ── Generate a preview HTML wrapper that assembles all files into a runnable GUI ──
        const previewHtml = this.generatePreviewHtml(project, generatedFiles, fileExports);
        if (previewHtml) {
            generatedFiles.push(previewHtml);
        }
        // Same white-window fix as the chat path: the canvas GUI entry (index.html)
        // may reference external <script src>/<link href> files that the srcdoc
        // preview iframe cannot load. Inline them deterministically from the
        // sibling generated files so canvas GUI builds are previewable too.
        const inlinable = generatedFiles.map((f) => ({ path: f.fileName, content: f.code }));
        inlineExternalScriptRefs(inlinable);
        inlinable.forEach((m, i) => {
            generatedFiles[i].code = m.content;
        });
        // ── Non-TS compile gate + stub gate + CONTRACT-AWARE gate, WITH a bounded
        //    repair loop (shared with the chat path, sandbox/nonTsRepair.ts). The
        //    canvas path used to only RUN the gates and mark failures — it could
        //    never repair a non-TS compile failure or an unimplemented/stub body.
        //    The deterministic sanitizer (bare Java imports, truncation) is inside. ──
        let languageGates = [];
        let stubFailures = [];
        if (!skipValidation) {
            // Stage through scaffoldRelPath — the SAME layout tsc and the export use.
            // Passing the bare fileName put every node in ONE directory, so a Go/Java/
            // C# build with more than one package failed the gate with "found packages
            // X and Y in <dir>" no matter how correct the code was.
            const gateSources = generatedFiles
                .filter((f) => f.nodeLabel !== 'App Preview (Auto-generated)' && !f.nodeLabel.includes('Auto-generated'))
                .map((f) => ({ path: this.scaffoldRelPath(f), content: f.code }));
            const gateContracts = gateSources.map((s) => {
                const g = generatedFiles.find((f) => this.scaffoldRelPath(f) === s.path);
                return { path: s.path, summary: g.description || '', language: g.language, exports: g.exports };
            });
            const gateTmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-nonts-'));
            try {
                const res = await runNonTsGatesWithRepair({
                    request: masterNode?.data?.appGoal || project.name || 'the requested app',
                    files: gateSources,
                    contractFiles: gateContracts,
                    exportDir: gateTmp,
                    timeoutMs: 120_000,
                    // These are NODE files: the scaffolder writes the program's entry
                    // point (main.swift / Program.cs / …) afterwards, so the gate must
                    // not demand that one of THESE declares it. Otherwise a generated
                    // Swift app of pure declarations is rejected as a library even
                    // though `swiftc` builds it and it runs (measured live).
                    scaffoldSuppliesEntry: true,
                    canRepair: () => true,
                    consumeRepair: () => { },
                    repairCall: async (prompt) => {
                        const raw = await this.ai.reason(prompt, undefined, { maxTokens: 8192, temperature: 0.2, role: 'codeGeneration' });
                        return raw.replace(/^```(?:\w+)?\s*\n?/i, '').replace(/\n?```\s*$/i, '').trim();
                    },
                });
                languageGates = res.languageGates;
                stubFailures = res.stubFailures;
                // Write repairs back onto the generated files so the export, the
                // training capture, and the user all see the repaired code.
                for (const s of gateSources) {
                    const g = generatedFiles.find((f) => this.scaffoldRelPath(f) === s.path);
                    if (g && g.code !== s.content) {
                        g.code = s.content;
                        console.log(`[fileGenerator] non-TS gate repaired "${g.nodeLabel}" (${s.path})`);
                    }
                }
            }
            catch (err) {
                console.warn('[fileGenerator] non-TS gate/repair failed (non-fatal):', err);
            }
            finally {
                try {
                    fs.rmSync(gateTmp, { recursive: true, force: true });
                }
                catch { /* noop */ }
            }
        }
        // Mark stub/unimplemented files unvalidated (a failure string may be a bare
        // path or `path: detail`).
        const stubPaths = new Set(stubFailures.map((s) => pathFromGateFailure(s) || s));
        for (const f of generatedFiles) {
            // The gate reports scaffold-relative paths; accept the bare fileName too
            // so a gate that only echoes a basename still maps back to its file.
            if (!stubPaths.has(this.scaffoldRelPath(f)) && !stubPaths.has(f.fileName))
                continue;
            if (f.validated)
                f.validated = false;
            if (!f.errors.some((e) => e.includes('Stub/placeholder'))) {
                f.errors.push(`Stub/placeholder or unimplemented body detected — code does not implement the node's contract`);
            }
            console.warn(`[fileGenerator] ⚠️ stub/unimplemented body in "${f.nodeLabel}" — marked unvalidated`);
        }
        if (stubFailures.length > 0) {
            console.warn(`[fileGenerator] ${stubFailures.length} stub/unimplemented file(s) rejected`);
        }
        // ── Behavioral smoke gate (the last chat/canvas unification gap) ──
        // tsc sees types, the language gates see compiles — neither sees "loads but
        // crashes on click" / "static board" / "CLI prints nothing". The chat path
        // has always run the behavioral smoke gate WITH a bounded repair loop; the
        // canvas path only ran the one-shot TS browser engine (non-fatal, no
        // repair), so a canvas GUI/game build could ship broken. Stage the files in
        // a temp dir and run the SAME shared gate, letting it rewrite the failing
        // entry via the generator's own AI. Skipped for fast preview builds.
        let renderSmoke = null;
        let cliSmoke = null;
        if (!skipValidation) {
            try {
                const smokeFiles = generatedFiles.map((f) => ({ path: f.fileName, content: f.code }));
                const goal = masterNode?.data?.appGoal || project.name || 'the requested app';
                const contractFiles = generatedFiles.map((f) => ({
                    path: f.fileName,
                    summary: f.description || '',
                    language: f.language,
                }));
                const staged = await runStagedBehavioralSmoke({
                    files: smokeFiles,
                    request: goal,
                    contractFiles,
                    timeoutMs: 35_000,
                    tag: 'canvas',
                    repairCall: async (prompt) => {
                        const raw = await this.ai.reason(prompt, undefined, { maxTokens: 8192, temperature: 0.2, role: 'codeGeneration' });
                        return raw.replace(/^```(?:\w+)?\s*\n?/i, '').replace(/\n?```\s*$/i, '').trim();
                    },
                });
                renderSmoke = staged.renderSmoke;
                cliSmoke = staged.cliSmoke;
                // Write repairs back onto the generated files so the export, the
                // training capture, and the user all see the verified code.
                for (const sf of smokeFiles) {
                    const g = generatedFiles.find((f) => f.fileName === sf.path);
                    if (g && g.code !== sf.content) {
                        g.code = sf.content;
                        console.log(`[fileGenerator] behavioral smoke repaired "${g.nodeLabel}" (${sf.path})`);
                    }
                }
            }
            catch (err) {
                console.warn('[fileGenerator] Behavioral smoke gate failed (non-fatal):', err);
            }
        }
        // Re-verify the non-TS gate on the FINAL code: the behavioral smoke's repair
        // loop rewrites files AFTER the compile gate ran and can re-introduce a
        // compile error (observed live in the chat path: a CLI smoke repair added a
        // second `class Board` → `javac: duplicate class`). Without this, the
        // canvas build reports a clean language gate for code that does not compile.
        // Repair is DISABLED — verdict refresh only. Skipped for fast preview builds.
        if (!skipValidation && languageGates.length > 0) {
            const reSources = generatedFiles
                .filter((f) => f.nodeLabel !== 'App Preview (Auto-generated)' && !f.nodeLabel.includes('Auto-generated'))
                .map((f) => ({ path: this.scaffoldRelPath(f), content: f.code }));
            const reContracts = reSources.map((s) => {
                const g = generatedFiles.find((f) => this.scaffoldRelPath(f) === s.path);
                return { path: s.path, summary: g.description || '', language: g.language, exports: g.exports };
            });
            const reTmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-nonts-post-'));
            try {
                const res = await runNonTsGatesWithRepair({
                    request: masterNode?.data?.appGoal || project.name || 'the requested app',
                    files: reSources,
                    contractFiles: reContracts,
                    exportDir: reTmp,
                    timeoutMs: 120_000,
                    // Same node-file-only file set as the gate above (verdict refresh).
                    scaffoldSuppliesEntry: true,
                    canRepair: () => false,
                    consumeRepair: () => { },
                    repairCall: async () => '',
                });
                languageGates = res.languageGates;
                stubFailures = res.stubFailures;
            }
            catch (err) {
                console.warn('[fileGenerator] post-smoke non-TS re-verify failed (non-fatal):', err);
            }
            finally {
                try {
                    fs.rmSync(reTmp, { recursive: true, force: true });
                }
                catch { /* noop */ }
            }
        }
        const hasTsJs = generatedFiles.some((f) => f.language === 'typescript' || f.language === 'javascript');
        // Map the canvas compile state onto the SHARED verdict vocabulary, then read
        // the SAME verdict the chat path reads. A build only counts as clean when a
        // gate actually PASSED (tsc clean, a clean non-TS gate, or — once the smoke
        // gate is wired here — a passed behavioral smoke). "Nothing failed" alone is
        // no longer sufficient: unverified output must not be captured or learned.
        const tscStatus = hasTsJs
            ? (!compileCheckRan || !fs.existsSync(TSC_BIN) ? 'unavailable' : (compileFailures === 0 ? 'clean' : 'errors'))
            : 'skipped';
        const verdict = deriveBuildVerdict({
            tscStatus,
            tscErrors: compileFailures,
            languageGates,
            stubFailures,
            renderSmoke,
            cliSmoke,
        });
        const tsCompileClean = verdict.clean;
        // Blueprint-driven builds (POST /api/blueprint/build) capture their OWN
        // blueprint-enriched rows in the route, so the generic capture is skipped
        // for them (master data flag set by blueprintToProject) — one capture per
        // build, no duplicate rows with different instructions.
        const captureDisabled = masterNode?.data?.skipVerifiedCapture === true;
        if (!skipValidation && !captureDisabled && tsCompileClean) {
            try {
                const cap = await captureVerifiedGeneration(project, generatedFiles, { tsCompileClean: true });
                if (cap.captured > 0) {
                    console.log(`[fileGenerator] Captured ${cap.captured} verified file(s) into training dataset (${cap.filePath})`);
                }
            }
            catch (err) {
                console.warn('[fileGenerator] Verified-generation capture failed (non-fatal):', err);
            }
        }
        // ── Close the knowledge-store learning loop (same verified gate as the
        //    training capture above — broken output never enters the store; the
        //    poison-loop quarantine's core principle). The OLD per-file hook
        //    passed raw pre-assembly model output and ran BEFORE generatedCode
        //    was written back to the project nodes, so learnFromProject's node
        //    loop always found empty code and silently no-oped — nothing was
        //    ever captured from the canvas path. Learn ONCE here, from the final
        //    assembled files, populating each node exactly like the frontend does
        //    after generation (updateNodeStatus). Shared helper (learnFromGeneratedFiles)
        //    so the blueprint build route — which skips this generic capture while
        //    skipVerifiedCapture is set — closes the same loop itself. ──
        if (!skipValidation && !captureDisabled && tsCompileClean) {
            try {
                const entries = learningEngine.learnFromGeneratedFiles(project, generatedFiles);
                if (entries.length > 0) {
                    console.log(`[fileGenerator] Learned ${entries.length} pattern(s) from project "${project.name}"`);
                }
            }
            catch (err) {
                console.warn('[fileGenerator] Knowledge-store learning failed (non-fatal):', err);
            }
        }
        // Build the import graph
        const importGraph = {};
        for (const file of generatedFiles) {
            importGraph[file.nodeId] = {
                entryFile: file.fileName,
                dependencies: file.dependencies,
                exports: file.exports,
            };
        }
        const totalChars = generatedFiles.reduce((sum, f) => sum + f.code.length, 0);
        const totalErrors = generatedFiles.reduce((sum, f) => sum + f.errors.length, 0);
        const validatedCount = generatedFiles.filter(f => f.validated).length;
        const failedCount = generatedFiles.filter(f => f.errors.length > 0).length;
        return {
            files: generatedFiles,
            totalChars,
            totalErrors,
            validatedCount,
            failedCount,
            importGraph,
            tsCompileClean,
            contractViolations: contractViolationCount,
            languageGates,
            // The behavioral smoke verdicts (canvas path), so callers can see WHY a
            // build was or wasn't trusted instead of only the fused tsCompileClean.
            renderSmoke,
            cliSmoke,
        };
    }
    /**
     * Generate GUI widget data for UI/gui-layout nodes using the GuiBuilderTool.
     * Returns a structured GUI output that gets injected into UI node prompts.
     */
    async generateGuiWidgets(project, nodes) {
        try {
            const registry = getRegistry();
            const guiBuilderTool = registry.get('gui_builder');
            if (!guiBuilderTool)
                return null;
            const masterNode = project.nodes.find((n) => n.type === 'master');
            const goal = masterNode?.data?.appGoal || project.name || 'Untitled';
            const purpose = masterNode?.data?.appPurpose || '';
            const uiNodes = nodes
                .filter(n => n.type === 'ui' || n.type === 'gui-layout')
                .map(n => ({
                label: n.data.label || n.id,
                description: n.data.description || '',
                type: (n.type === 'gui-layout' ? 'ui' : n.type),
                language: n.data.language || 'typescript',
            }));
            // Pattern stores are ON by default in GuiBuilderTool and were previously
            // hard-disabled here, starving the GUI layout of the UIVerse HTML/CSS
            // component library (data/ui-patterns/patterns.json) and the Rico real-
            // world screens dataset. Enabling them injects real UI component examples
            // into the design prompt, so generated GUIs follow proven patterns.
            // (Both stores degrade gracefully when the dataset files are absent.)
            // Web research stays off — it is slow and network-dependent; the local
            // pattern stores are the deterministic knowledge source for GUIs.
            const result = await guiBuilderTool.call({
                goal,
                purpose,
                targetOS: project.targetOS || 'linux',
                nodes: uiNodes,
                includeResearch: false,
                includeRicoPatterns: true,
                includeUiPatterns: true,
                widgetCount: Math.min(uiNodes.length * 3, 12),
            }, {});
            if (result.success && result.data) {
                return result.data;
            }
            return null;
        }
        catch (err) {
            console.warn('[fileGenerator] GuiBuilderTool call failed:', err);
            return null;
        }
    }
    /**
     * Live compile-check-retry loop: scaffold the generated TS/JS files to a
     * temp directory (mirroring the per-file scaffolder layout so cross-node
     * `../<dep>/<dep>.ts` imports resolve), run `tsc --noEmit`, and for every
     * file that fails, feed the compiler errors back to the model and regenerate
     * that file. Repeats for up to `maxRounds` rounds.
     *
     * This is the live version of the offline campaign repair loop — it fixes
     * files BEFORE the user ever sees them, instead of in a post-hoc repair pass.
     *
     * Mutates `generatedFiles` entries in place (code, exports, errors,
     * validated) and updates `fileExports` so later rounds and the preview use
     * the corrected exports. Returns the number of files still failing after all
     * rounds.
     */
    /**
     * Re-assemble one node's raw LLM output into a final TS/JS file: strip
     * AI-written imports, then prepend the auto-generated dependency imports.
     * Shared by every compile-check repair-loop code path (failing files AND
     * contract-changed dependents) so they can never drift apart. The batch
     * loop pre-computes its import section before the AI call, so it keeps its
     * own inline assembly.
     */
    assembleTsJs(code, deps, fileExports, language, moduleName) {
        // keepSiblingImports: repair regenerations may now write their own imports
        // to sibling modules (the scope-leak lint tells them to) — keep those, and
        // dedupe the auto-import below against them.
        const tsCode = postProcessTsJsCode(code, { keepSiblingImports: true });
        // Deterministic import-collision fix: this file's body may itself declare
        // a name (export class/interface/enum/function/const X) that a sibling
        // ALSO exports. Auto-importing that name then collides with the local
        // declaration → TS2440/TS2395/TS2300 ("Import declaration conflicts with
        // local declaration"). The local declaration wins (it is the file's own
        // contract, and other files import from THIS file's export list) — so drop
        // the colliding name from the auto-import. This is the types.ts failure
        // class from the triage builds, fixed without the LLM. Names the model
        // imported itself are skipped the same way (no duplicate imports).
        const localNames = findLocalDeclaredNames(tsCode);
        const importedNames = findImportedNames(tsCode);
        let importSection = '';
        const resolvedDeps = [];
        // Cross-dep dedupe: when two dependencies both export the same name (e.g.
        // config.ts and main.ts both export `Config`), importing both breaks tsc
        // with TS2300 "Duplicate identifier". Keep the FIRST dependency's copy and
        // drop the name from the others — the first importer is the dependency
        // this file's plan lists first, so its contract wins.
        const seenNames = new Set();
        for (const depLabel of deps) {
            const depExports = fileExports.get(depLabel);
            if (!depExports)
                continue;
            const names = (depExports.names || []).filter(n => !localNames.has(n) && !importedNames.has(n) && !seenNames.has(n));
            for (const n of names)
                seenNames.add(n);
            // Skip a dependency entirely when every export it offers is shadowed by a
            // local declaration (importing nothing from it is the only correct move).
            if (names.length === 0 && !depExports.defaultName)
                continue;
            const filtered = { ...depExports, names };
            importSection += buildImportStatement(labelToFileName(depLabel), filtered, language, moduleName) + '\n';
            resolvedDeps.push(depLabel);
        }
        return {
            fullCode: importSection ? importSection + '\n' + tsCode : tsCode,
            resolvedDeps,
        };
    }
    /**
     * "Import targets" block for a repair prompt: what this file's dependencies
     * actually export — the model may ONLY reference these members. Prevents the
     * classic cross-file drift where the model invents methods/types that the
     * dependency never declared (TS2339/TS2304).
     */
    buildImportTargets(deps, fileExports, language) {
        const MAX_DEP_SOURCE_CHARS = 4000;
        return deps
            .map(depLabel => {
            const src = this.depSourceCache.get(depLabel);
            const header = `  - ${labelToFileName(depLabel)}.${getFileExtension(language)} exports: ${describeExports(fileExports.get(depLabel))}`;
            if (src && src.trim().length > 10) {
                const capped = src.trim().length > MAX_DEP_SOURCE_CHARS
                    ? src.trim().substring(0, MAX_DEP_SOURCE_CHARS) + '\n// ... (dependency truncated)'
                    : src.trim();
                return `${header}\n    REAL SOURCE of ${labelToFileName(depLabel)}.${getFileExtension(language)} (fix against these EXACT shapes):\n    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n${capped}\n    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`;
            }
            return header;
        })
            .join('\n');
    }
    /**
     * Static invented-member scan: for every class/interface this file imports
     * (whose member whitelist we know), flag `obj.member(` calls where `member`
     * is NOT in that type's whitelist. This catches TS2339-style drift BEFORE
     * tsc (and even when the model typed the variable loosely, so tsc missed it).
     * Returns TS2339-formatted error lines (consumed by the fix loop).
     */
    findInventedMembers(code, deps, fileExports) {
        const errors = [];
        // Scan a comment-free copy so JSDoc/example comments mentioning
        // `TypeName.member(` can never produce a false "invented member" hit.
        const scanCode = code
            .replace(/\/\/[^\n]*/g, '')
            .replace(/\/\*[\s\S]*?\*\//g, '');
        for (const depLabel of deps) {
            const info = fileExports.get(depLabel);
            if (!info?.members)
                continue;
            for (const [typeName, allowedMembers] of Object.entries(info.members)) {
                const allowed = new Set(allowedMembers);
                // Static calls on the type itself: `GameRulesEngine.parseFenString(`
                // (the build invented static members on whitelisted types too).
                const staticRe = new RegExp(`\\b${typeName}\\.([a-zA-Z_$][\\w$]*)\\s*\\(`, 'g');
                let sm;
                while ((sm = staticRe.exec(scanCode)) !== null) {
                    if (!allowed.has(sm[1])) {
                        errors.push(`TS2339: Property '${sm[1]}' does not exist on type 'typeof ${typeName}'. ` +
                            `ONLY these members exist: ${allowedMembers.join(', ') || '(none — call nothing on this type)'}. ` +
                            `Implement '${sm[1]}' locally with the whitelisted members (or drop the call).`);
                    }
                }
                // Find variables/params typed as this class/interface:
                // `foo: TypeName`, `(param: TypeName)`, `: TypeName =`
                const typedRe = new RegExp(`(?:^|[^\\w$])([a-zA-Z_$][\\w$]*)\\s*:\\s*${typeName}\\b`, 'g');
                const typedVars = new Set();
                let m;
                while ((m = typedRe.exec(scanCode)) !== null) {
                    typedVars.add(m[1]);
                }
                if (typedVars.size === 0)
                    continue;
                // Now flag `var.member(` where member is not whitelisted.
                const accessRe = new RegExp(`\\b(${[...typedVars].join('|')})\\.([a-zA-Z_$][\\w$]*)\\s*\\(`, 'g');
                let am;
                while ((am = accessRe.exec(scanCode)) !== null) {
                    const member = am[2];
                    if (!allowed.has(member)) {
                        errors.push(`TS2339: Property '${member}' does not exist on type '${typeName}'. ` +
                            `ONLY these members exist: ${allowedMembers.join(', ') || '(none — call nothing on this type)'}. ` +
                            `Implement '${member}' locally with the whitelisted members (or drop the call).`);
                    }
                }
            }
        }
        return errors;
    }
    /**
     * Deterministic same-name collision lint: inside one class body, a field and
     * a method with the same name (or a method and a getter, etc.) break tsc
     * with TS2300/TS2391 ("Duplicate identifier"). The 7B model regularly emits
     * `winner: string | null` as a field AND `winner()` as a method (the
     * tic-tac-toe grid.ts failure class). Returns TS2300-formatted errors fed
     * into the same fix loop, with the exact rename so the model doesn't have to
     * guess. Best-effort brace matching — never hard-fails, only feeds repair.
     */
    findSameNameCollisions(code) {
        const errors = [];
        const classRe = /(?:^|[^\w$])class\s+([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*\{/g;
        let cm;
        while ((cm = classRe.exec(code)) !== null) {
            const className = cm[1];
            // extractBraceBody expects `start` to point just PAST the opening `{`
            // (its depth counter starts at 1 for the body itself).
            const body = extractBraceBody(code, cm.index + cm[0].length);
            if (!body)
                continue;
            const fields = new Set();
            const methods = new Set();
            // Fields: `name: Type`, `name = value`, `name;` at member level
            for (const m of body.matchAll(/^(?:private|public|protected|readonly|static|declare|\s)*(?:#)?([A-Za-z_$][\w$]*)\s*(?::[^=;\n]+|=|;)/gm)) {
                fields.add(m[1]);
            }
            // Methods: `name(` / `get name(` / `set name(` at member level
            for (const m of body.matchAll(/^(?:private|public|protected|static|\s)*(?:async\s+)?(?:get|set)?\s*([A-Za-z_$][\w$]*)\s*\(/gm)) {
                methods.add(m[1]);
            }
            // A constructor is a method too but never collides as a field — ignore it
            methods.delete('constructor');
            for (const name of fields) {
                if (methods.has(name)) {
                    errors.push(`TS2300: Duplicate identifier '${name}' — class '${className}' declares it as BOTH a property and a method. ` +
                        `Rename the FIELD to '${name}Value' (or the method) so each identifier is unique, and update all references.`);
                }
            }
        }
        return errors;
    }
    /**
     * Deterministic zero-LLM repair chain, ported from codePlanner's tsc gate so
     * canvas/blueprint builds resolve the same mechanical error classes the chat
     * path fixes without burning a slow 14B regeneration: TS2307 phantom npm
     * imports + wrong sibling paths, TS2459 missing exports (patches the CAUSING
     * file — a different one than the failing importer), TS5097 import
     * extensions, TS2345 partial-object call sites, TS2355/TS7030 missing
     * returns, TS2322 void returns, TS2304/2503/2552 content-driven import
     * insertion, TS2451 local collisions. Each fixer is idempotent and re-
     * verified by the round's tsc re-check; anything they can't safely touch
     * falls through to the LLM regeneration below. Returns true when a fix was
     * applied (the caller must NOT spend an LLM call on this file this round).
     */
    applyDeterministicRepair(file, errs, scaffoldSelfPath, scaffoldFiles, tsFiles, fileExports, regenerated, contractsChanged) {
        // DEBUG: ground truth on why the deterministic chain declines
        console.log(`[fileGenerator]   🔧 deterministic repair for "${file.nodeLabel}" — ${errs.length} err(s): TS2307=${errs.some(e => /\bTS2307/.test(e))} TS2459=${errs.some(e => /\bTS2459/.test(e))} TS2304=${errs.some(e => /\bTS2304/.test(e))} | first: ${(errs[0] || '').slice(0, 130)}`);
        const applyToSelf = (newContent) => {
            if (newContent === file.code)
                return false;
            file.code = newContent;
            const info = this.extractExports(newContent, file.language);
            if (!sameExports(fileExports.get(file.nodeLabel), info))
                contractsChanged.add(file.nodeLabel);
            file.exports = info.names;
            fileExports.set(file.nodeLabel, info);
            this.depSourceCache.set(file.nodeLabel, newContent);
            regenerated.add(file.nodeLabel);
            return true;
        };
        // The missing-export fixer patches the CAUSING file (a sibling that
        // declares the imported name without exporting it), which is a DIFFERENT
        // file than the one being repaired — locate it by scaffold path and apply
        // there so its dependents re-import the now-exported member.
        const applyToTarget = (target) => {
            const t = tsFiles.find(f => this.scaffoldRelPath(f) === target.path);
            if (!t)
                return false;
            if (t.code === target.content)
                return false;
            t.code = target.content;
            const info = this.extractExports(target.content, t.language);
            if (!sameExports(fileExports.get(t.nodeLabel), info))
                contractsChanged.add(t.nodeLabel);
            t.exports = info.names;
            fileExports.set(t.nodeLabel, info);
            this.depSourceCache.set(t.nodeLabel, target.content);
            regenerated.add(t.nodeLabel);
            return true;
        };
        // (Mirrors codePlanner's gate ordering: TS2307 phantom strip first, then
        // sibling-path, then the cross-file/call-site/return classes.)
        // Circular SELF-import (TS2303/TS2459 when the model "imports" a
        // hallucinated name from its OWN file) is a whole-file poison — strip it
        // first so the body's usage degrades to a clean TS2304 the other fixers
        // can see.
        if (errs.some(e => /\bTS2303/.test(e))) {
            const selfStripped = stripCircularSelfImports(file.code, scaffoldSelfPath);
            if (selfStripped && applyToSelf(selfStripped)) {
                console.log(`[fileGenerator]   ⚙️ ${file.nodeLabel} circular self-import stripped deterministically (no LLM call)`);
                return true;
            }
        }
        if (errs.some(e => /\bTS2307/.test(e))) {
            const stripped = stripPhantomPackageImports(file.code);
            if (stripped && applyToSelf(stripped)) {
                console.log(`[fileGenerator]   ⚙️ ${file.nodeLabel} TS2307 phantom npm imports stripped deterministically (no LLM call)`);
                return true;
            }
            const pathFixed = applyDeterministicSiblingPathFix(file.code, scaffoldSelfPath, scaffoldFiles, errs);
            if (pathFixed === null)
                console.log(`[fileGenerator]     ↪ sibling-path fixer DECLINED for "${file.nodeLabel}" (self=${scaffoldSelfPath}, files=${scaffoldFiles.length})`);
            else
                console.log(`[fileGenerator]     ↪ sibling-path fixer PROPOSED a change for "${file.nodeLabel}"`);
            if (pathFixed && applyToSelf(pathFixed)) {
                console.log(`[fileGenerator]   ⚙️ ${file.nodeLabel} TS2307 sibling import paths fixed deterministically (no LLM call)`);
                return true;
            }
        }
        // Export NAME mismatch (TS2724/TS2614/TS2305 with tsc's "Did you mean"):
        // the importer used a different casing/name than the module exports
        // (`GameState` vs the file's `gameState`). tsc tells us the exact member to
        // use, so patch the import instead of paying a full regeneration.
        if (errs.some(e => /\bTS(2724|2614|2305)\b/.test(e))) {
            const nameFixed = applyDeterministicExportNameFix(file.code, errs);
            if (nameFixed && applyToSelf(nameFixed)) {
                console.log(`[fileGenerator]   ⚙️ ${file.nodeLabel} TS2724/TS2614 export-name mismatch fixed deterministically (no LLM call)`);
                return true;
            }
        }
        if (errs.some(e => /\bTS2459/.test(e))) {
            const exportFix = applyDeterministicMissingExportFix(scaffoldSelfPath, scaffoldFiles, errs);
            if (exportFix && applyToTarget(exportFix)) {
                console.log(`[fileGenerator]   ⚙️ ${exportFix.path} TS2459 missing-export fixed deterministically (export added) (no LLM call)`);
                return true;
            }
        }
        if (errs.some(e => /\bTS2341/.test(e))) {
            const privateFix = applyDeterministicPrivateAccessFix(scaffoldSelfPath, scaffoldFiles, errs);
            if (privateFix && applyToTarget(privateFix)) {
                console.log(`[fileGenerator]   ⚙️ ${privateFix.path} TS2341 private member made public deterministically (no LLM call)`);
                return true;
            }
        }
        if (errs.some(e => /\bTS5097/.test(e))) {
            const extFixed = normalizeImportExtensions(file.code, scaffoldSelfPath, scaffoldFiles);
            if (extFixed && applyToSelf(extFixed)) {
                console.log(`[fileGenerator]   ⚙️ ${file.nodeLabel} TS5097 import extensions stripped deterministically (no LLM call)`);
                return true;
            }
        }
        if (errs.some(e => /\bTS2345/.test(e))) {
            const partialFixed = applyDeterministicPartialObjectFix(file.code, scaffoldSelfPath, scaffoldFiles, errs);
            if (partialFixed && applyToSelf(partialFixed)) {
                console.log(`[fileGenerator]   ⚙️ ${file.nodeLabel} TS2345 partial-object call sites fixed deterministically (no LLM call)`);
                return true;
            }
        }
        if (errs.some(e => /\bTS(2355|7030)/.test(e))) {
            const missingRet = applyDeterministicMissingReturnFix(file.code, errs);
            if (missingRet && applyToSelf(missingRet)) {
                console.log(`[fileGenerator]   ⚙️ ${file.nodeLabel} TS2355/TS7030 missing-return fixed deterministically (no LLM call)`);
                return true;
            }
        }
        if (errs.some(e => /\bTS2322:.*not assignable to type '(Promise<)?void'/.test(e))) {
            const voidRet = applyDeterministicVoidReturnFix(file.code, errs);
            if (voidRet && applyToSelf(voidRet)) {
                console.log(`[fileGenerator]   ⚙️ ${file.nodeLabel} TS2322-void return fixed deterministically (no LLM call)`);
                return true;
            }
        }
        if (errs.some(e => /\bTS(2304|2503|2552|2307)/.test(e))) {
            const contentPatched = applyContentDrivenImportFix(file.code, scaffoldSelfPath, scaffoldFiles, errs);
            if (contentPatched && applyToSelf(contentPatched)) {
                console.log(`[fileGenerator]   ⚙️ ${file.nodeLabel} missing-import errors fixed by CONTENT-DRIVEN import insert (no LLM call)`);
                return true;
            }
            const collisionFixed = applyDeterministicLocalCollisionFix(file.code, errs);
            if (collisionFixed && applyToSelf(collisionFixed)) {
                console.log(`[fileGenerator]   ⚙️ ${file.nodeLabel} TS2451 local-collision fixed deterministically (no LLM call)`);
                return true;
            }
        }
        return false;
    }
    async compileCheckAndFix(project, generatedFiles, fileExports, sortedNodes, depGraph, guiWidgetOutput, maxRounds = 3) {
        const tsFiles = generatedFiles.filter(f => f.language === 'typescript' || f.language === 'javascript');
        if (tsFiles.length === 0)
            return 0;
        if (!fs.existsSync(TSC_BIN)) {
            console.warn('[fileGenerator] tsc not found — skipping live compile check');
            return 0;
        }
        // Files regenerated this pass — their sandbox result from the batch loop is
        // stale (it validated the PRE-fix code), so reset errors/validated from the
        // authoritative tsc result at the end.
        const regenerated = new Set();
        // ── Stall detection (mirrors codePlanner's tsc gate) ────────────────────
        // This loop used to regenerate EVERY failing file EVERY round with no
        // progress check — on the 14B (~18 tok/s) a file the model can't fix (it
        // re-emits the same broken style) burned a full regeneration (~1-3 min)
        // in every one of the 3 rounds, so an unfixable 5-file blueprint build
        // crawled 20+ minutes and still failed (observed in the R9 claims audit:
        // round 1/2/3 identical 5-file failures; /api/blueprint/build timed out
        // at 180s and at 900s). Two bounded stops, mirroring codePlanner's
        // stalledRounds/sameErrors:
        //   (a) GLOBAL — if the whole error map is identical to the previous
        //       round's, NO file moved: stop the loop immediately (round N+1
        //       would just re-run tsc on the same broken code).
        //   (b) PER-FILE — a file whose error signature is unchanged for 2
        //       consecutive rounds is given up on (its 2 fair repair attempts
        //       are spent) while the other files keep being chased.
        // Errors are compared position-insensitively (`(line N)` stripped) so a
        // repair that merely MOVES an error to a new line still counts as the
        // same underlying issue (same semantic as normalizeTscError).
        // Consecutive rounds a file's error signature may stay UNCHANGED before
        // the repair loop stops re-generating it (and lets the other files keep
        // being chased). Set to 1 = one fair repair pass per file: the repair
        // prompt already carries the exact tsc errors, the file's own previous
        // content, and the real sibling contracts, so a second regeneration that
        // reproduces the identical error signature is far more likely to reproduce
        // it again than to fix it — and on the 14B each wasted pass costs 30-100s.
        // Measured on a real 5-node build: rounds 1 and 2 each re-generated all 5
        // failing files (10 full generations) before the global stall check fired
        // at round 3, which is where most of the 5-7 minute wall time went.
        const REPAIR_STALL_ROUNDS = 1;
        const prevSignatures = new Map();
        const stalledCount = new Map();
        let lastRoundSig = null;
        for (let round = 1; round <= maxRounds; round++) {
            const errorsByLabel = await this.runTscCheck(tsFiles);
            // Static invented-member scan: flags `board.makeMove()` on whitelisted
            // types even when tsc misses it (loose typing). Merge into the same map
            // so the fix loop regenerates those files with the whitelist in the prompt.
            for (const f of tsFiles) {
                const deps = depGraph.get(f.nodeLabel) || [];
                const invented = this.findInventedMembers(f.code, deps, fileExports);
                if (invented.length > 0) {
                    const existing = errorsByLabel.get(f.nodeLabel) || [];
                    errorsByLabel.set(f.nodeLabel, [...existing, ...invented]);
                    console.log(`[fileGenerator]   ⚠️ invented-member scan: ${invented.length} on "${f.nodeLabel}" (e.g. ${invented[0].slice(0, 90)}…)`);
                }
                // Deterministic same-name collision lint: a field and method sharing a
                // name in one class (TS2300) — the model cannot fix this blind because
                // tsc's error doesn't tell it which one to rename. The lint says it.
                const collisions = this.findSameNameCollisions(f.code);
                if (collisions.length > 0) {
                    const existing = errorsByLabel.get(f.nodeLabel) || [];
                    errorsByLabel.set(f.nodeLabel, [...existing, ...collisions]);
                    console.log(`[fileGenerator]   ⚠️ same-name collision lint: ${collisions.length} on "${f.nodeLabel}" (e.g. ${collisions[0].slice(0, 90)}…)`);
                }
                // Truncation lint: a generation that hit the token cap ends mid-function
                // with unbalanced braces (more { than }, and typically the file simply
                // stops without closing its outermost blocks). The 14B hit exactly this
                // on the calculator build (seq 11: 418-line UI file, 33 { vs 31 }, cut
                // inside a forEach callback — tsc reported only TS1005 '}' expected).
                // tsc's TS1005 does NOT tell the model it was truncated, so blind
                // repair re-emits the same truncated file; this lint names the cause.
                const trunc = findTruncation(f.code);
                if (trunc) {
                    const existing = errorsByLabel.get(f.nodeLabel) || [];
                    errorsByLabel.set(f.nodeLabel, [...existing,
                        `TRUNCATION: this file is INCOMPLETE — it was cut off mid-generation (${trunc.open} opening braces vs ${trunc.close} closing braces; it ends without closing its outermost blocks). The generation hit the output token limit. RE-GENERATE the COMPLETE file: every function, statement, and closing brace must be present. Do NOT leave the code mid-expression — finish the file to its natural end.`
                    ]);
                    console.log(`[fileGenerator]   ⚠️ truncation lint: unbalanced braces ${trunc.open}/${trunc.close} on "${f.nodeLabel}" (file ends mid-block)`);
                }
                // Hallucinated-runtime lint: the 7B model sometimes emits Deno./Bun.
                // globals (Deno.writeTextFile, Bun.serve) in plain TS intended for
                // node/browser — tsc errors TS2304 'Cannot find name Deno'. Flag it
                // explicitly so the repair prompt replaces the call with a node/browser
                // equivalent instead of guessing. Comment-free scan like the others.
                const runtimeRe = /\b(?:Deno|Bun)\.[A-Za-z_$][\w$]*/g;
                const runtimeHits = f.code.replace(/\/\/[^\n]*/g, '').match(runtimeRe) || [];
                if (runtimeHits.length > 0) {
                    const existing = errorsByLabel.get(f.nodeLabel) || [];
                    errorsByLabel.set(f.nodeLabel, [...existing, ...new Set(runtimeHits).values()].map(h => `TS2304: Cannot find name '${h.split('.')[0]}' — this is a ${h.split('.')[0]} runtime API (${h}), but this project targets node/browser. Replace it with the standard node/browser equivalent (fs.writeFileSync / fetch / localStorage, etc.).`));
                    console.log(`[fileGenerator]   ⚠️ runtime-hallucination lint: ${runtimeHits.length} on "${f.nodeLabel}" (${runtimeHits[0]})`);
                }
                // Scope-leak lint: the single-file-mode failure class — identifiers
                // referenced from a scope where they are never declared (undeclared
                // globals, render-local state used at module scope, module-local
                // functions called from inline onclick="..." attributes). tsc's TS2304
                // says only "Cannot find name 'X'" — this lint says WHERE and WHY so
                // the repair loop fixes the structure instead of re-emitting the same
                // leaked-global style.
                // Pass sibling-export context so a leaked name can be traced to the
                // module that owns it: "import it" when a dependency exports it,
                // "you cannot import it" when only a non-dependency sibling does.
                const allExports = new Map();
                for (const [label, info] of fileExports)
                    allExports.set(label, info?.names || []);
                const scopeLeaks = findScopeLeaks(f.code, {
                    selfLabel: f.nodeLabel,
                    deps: depGraph.get(f.nodeLabel) || [],
                    allExports,
                });
                if (scopeLeaks.length > 0) {
                    const existing = errorsByLabel.get(f.nodeLabel) || [];
                    errorsByLabel.set(f.nodeLabel, [...existing, ...scopeLeaks]);
                    console.log(`[fileGenerator]   ⚠️ scope-leak lint: ${scopeLeaks.length} on "${f.nodeLabel}" (e.g. ${scopeLeaks[0].slice(0, 90)}…)`);
                }
                // Post-write contract verifier (import-level drift): imports of
                // non-dependencies, or of members the target never exports. Merged
                // into the same map so the repair loop regenerates the file with both
                // feeds — the generated code must honor the contracts, not just the
                // plan.
                const contractDrift = verifyGeneratedCodeContracts(f.code, f.language, deps, fileExports);
                if (contractDrift.length > 0) {
                    const existing = errorsByLabel.get(f.nodeLabel) || [];
                    errorsByLabel.set(f.nodeLabel, [...existing, ...contractDrift]);
                    console.log(`[fileGenerator]   ⚠️ contract verifier: ${contractDrift.length} violation(s) on "${f.nodeLabel}" (e.g. ${contractDrift[0].slice(0, 90)}…)`);
                }
                // Anti-stub lint (the Brain Doctrine's unforgivable sin): a body that
                // never implements its node's contract — TODO/"Implement" fallbacks,
                // comment-only files, echoed prompt scaffolding. The final stub gate
                // below only FLAGS these; feeding them into THIS repair loop makes the
                // model REWRITE them with a real implementation (fixSection names the
                // failure and the VACA_BRAIN_DOCTRINE in the prompt forbids stubs), so
                // a stub ships only if all repair rounds genuinely fail to replace it.
                if (isStubBody(f.code)) {
                    const existing = errorsByLabel.get(f.nodeLabel) || [];
                    errorsByLabel.set(f.nodeLabel, [...existing,
                        `STUB/PLACEHOLDER BODY: this file does not implement its node's contract — it is a stub (TODOs, empty/skeleton methods, placeholder scaffolding). REWRITE the COMPLETE file with the REAL implementation: every declared export must do its actual work with real logic, real method bodies, and proper error handling. The smallest working implementation always beats an empty promise.`
                    ]);
                    console.log(`[fileGenerator]   ⚠️ anti-stub lint: "${f.nodeLabel}" is a stub — routing to rewrite`);
                }
            }
            if (errorsByLabel.size === 0) {
                // Whole-project tsc passed clean on this round. Still sync the per-file
                // `validated`/`errors` from the authoritative tsc result — the batch
                // loop's per-file sandbox errors (validated in isolation, so a correct
                // sibling import raises a FALSE TS2307) are stale and must be cleared.
                // Previously this early-return skipped the final sync loop below, so a
                // clean build kept its stale sandbox errors → FAIL with
                // tsCompileClean:true (teacher-build seq 10: calculator, tscClean=True
                // but validated 2/3, the one error being the false index.ts TS2307).
                this.syncValidatedFromTsc(tsFiles, new Map());
                return 0;
            }
            // (a) Global stall: the error map is identical to the previous round's
            // (CLASS-aware: same error classes on the same files, positions and
            // member names stripped) — the last round's regenerations changed
            // NOTHING, so further rounds would only re-spend slow 14B calls on the
            // same broken code. Stop now; the final tsc check below reports the
            // real remaining errors.
            const roundSig = genRoundSignature(errorsByLabel);
            if (round > 1 && roundSig === lastRoundSig) {
                console.warn(`[fileGenerator] Compile-check round ${round}: error set unchanged from round ${round - 1} — stopping repair loop (no progress)`);
                break;
            }
            lastRoundSig = roundSig;
            console.log(`[fileGenerator] Compile-check round ${round}: ${errorsByLabel.size} file(s) failing — regenerating with compiler feedback`);
            // Files whose export CONTRACT changed this round — their dependents' auto
            // imports are built from that contract, so those dependents must be
            // regenerated too (otherwise they keep importing dead members).
            const contractsChanged = new Set();
            let regeneratedThisRound = 0;
            // PASS 1 (synchronous, cheap): stall gate + deterministic zero-LLM repair
            // chain. Files a fixer can handle are repaired here for free; the rest are
            // COLLECTED and regenerated together in pass 2. The old code did all of
            // this inside one `for … await` loop, so N failing files cost N sequential
            // model round-trips (a 5-file round at 20-30s each ≈ 2 minutes of serial
            // 14B time per round).
            const needsLlmRegen = [];
            for (const [label, errs] of errorsByLabel) {
                const file = generatedFiles.find(f => f.nodeLabel === label);
                const node = sortedNodes.find(n => (n.data?.label || n.id) === label);
                if (!file || !node)
                    continue;
                // (b) Per-file stall: same error signature as the previous round means
                // the last regeneration didn't move it. After 2 consecutive unchanged
                // rounds, give up on THIS file (skip regenerating it) so it can't
                // consume the remaining rounds, while the others keep being chased.
                const sig = genErrorSignature(errs);
                const sameAsBefore = prevSignatures.get(label) === sig;
                stalledCount.set(label, sameAsBefore ? (stalledCount.get(label) || 0) + 1 : 0);
                prevSignatures.set(label, sig);
                if (sameAsBefore && (stalledCount.get(label) || 0) >= REPAIR_STALL_ROUNDS) {
                    console.warn(`[fileGenerator]   ⏭️ "${label}" errors unchanged for ${stalledCount.get(label)} round(s) — skipping (stalled repair)`);
                    continue;
                }
                // ── Deterministic zero-LLM repair chain (ported from codePlanner's
                // tsc gate) ── Before spending a slow 14B regeneration on a failing
                // file, try the mechanical fixers the chat path has: TS2307 phantom
                // npm imports + wrong sibling paths, TS2459 missing exports (patches
                // the CAUSING file), TS5097 import extensions, TS2345 partial-object
                // call sites, TS2355/TS7030 missing returns, TS2322 void returns,
                // TS2304 content-driven imports, TS2451 local collisions. Each fix is
                // idempotent and re-verified by the round's tsc re-check; only files
                // no fixer can safely touch fall through to the regeneration below.
                // Scaffold paths mirror runTscCheck's layout (`src/<safe>/<file>`) so
                // the fixers resolve relative specifiers against the same tree tsc
                // sees.
                const scaffoldSelfPath = this.scaffoldRelPath(file);
                const scaffoldFiles = tsFiles.map(f => ({
                    path: this.scaffoldRelPath(f),
                    content: f.code,
                }));
                if (this.applyDeterministicRepair(file, errs, scaffoldSelfPath, scaffoldFiles, tsFiles, fileExports, regenerated, contractsChanged)) {
                    regeneratedThisRound += 1;
                    continue; // re-check after the loop — no LLM call spent on this file
                }
                regeneratedThisRound += 1;
                needsLlmRegen.push({ label, errs, file, node });
            }
            // PASS 2: regenerate every file the deterministic fixers could not touch —
            // CONCURRENTLY. These files are independent: each carries its own error
            // list, previous content, and dependency contracts.
            const regenOutcomes = await mapWithConcurrency(needsLlmRegen, MAX_PARALLEL_MODEL_CALLS, async ({ label, errs, file, node }) => {
                const deps = depGraph.get(label) || [];
                const code = await this.generateNodeFile(node, project, deps, fileExports, guiWidgetOutput, errs, {
                    // Feed the file's own previous content + the real export contracts of
                    // its import targets so the model repairs WITH context instead of
                    // regenerating blind (mirrors codePlanner's buildRepairPrompt).
                    previousContent: file.code,
                    importTargets: this.buildImportTargets(deps, fileExports, file.language),
                });
                const { fullCode, resolvedDeps } = this.assembleTsJs(code, deps, fileExports, file.language, project.name);
                const newInfo = this.extractExports(fullCode, file.language);
                return { label, file, fullCode, resolvedDeps, newInfo };
            });
            // PASS 3: apply outcomes in a deterministic order so fileExports /
            // depSourceCache stay coherent for the dependents pass below.
            for (const outcome of regenOutcomes) {
                if (!outcome.ok) {
                    console.warn('[fileGenerator] repair regeneration failed:', outcome.reason);
                    continue;
                }
                const { label, file, fullCode, resolvedDeps, newInfo } = outcome.value;
                if (!sameExports(fileExports.get(label), newInfo))
                    contractsChanged.add(label);
                file.code = fullCode;
                file.dependencies = resolvedDeps;
                file.exports = newInfo.names;
                fileExports.set(label, newInfo);
                this.depSourceCache.set(label, fullCode);
                regenerated.add(label);
            } // Regenerate dependents of changed contracts so the whole graph converges.
            if (contractsChanged.size > 0) {
                for (const file of tsFiles) {
                    if (errorsByLabel.has(file.nodeLabel) || regenerated.has(file.nodeLabel))
                        continue;
                    const deps = depGraph.get(file.nodeLabel) || [];
                    if (!deps.some(d => contractsChanged.has(d)))
                        continue;
                    const node = sortedNodes.find(n => (n.data?.label || n.id) === file.nodeLabel);
                    if (!node)
                        continue;
                    console.log(`[fileGenerator]   └─ regenerating dependent "${file.nodeLabel}" (its dependency exports changed)`);
                    const code = await this.generateNodeFile(node, project, deps, fileExports, guiWidgetOutput, [
                        // Synthetic hint so the repair prompt (fixSection) renders with the
                        // dependency contract context and the model re-imports correctly.
                        `A dependency this file imports from changed its exported symbols. Re-import ONLY the members listed in IMPORT TARGETS below, and update your references to the renamed/removed ones.`,
                    ], {
                        previousContent: file.code,
                        importTargets: this.buildImportTargets(deps, fileExports, file.language),
                    });
                    const { fullCode, resolvedDeps } = this.assembleTsJs(code, deps, fileExports, file.language, project.name);
                    const info = this.extractExports(fullCode, file.language);
                    file.code = fullCode;
                    file.dependencies = resolvedDeps;
                    file.exports = info.names;
                    fileExports.set(file.nodeLabel, info);
                    this.depSourceCache.set(file.nodeLabel, fullCode);
                    regenerated.add(file.nodeLabel);
                }
            }
            // Global no-progress hard stop: if EVERY failing file was skipped as
            // stalled (nothing was regenerated at all), another round is pointless.
            if (regeneratedThisRound === 0) {
                console.warn('[fileGenerator] Compile-check: no file was regenerated this round — stopping repair loop');
                break;
            }
        }
        // Final check: mark which files still fail so the summary reflects reality.
        // Regenerated files that now pass get their stale pre-fix sandbox errors
        // cleared; still-failing files get the authoritative tsc errors.
        const finalErrors = await this.runTscCheck(tsFiles);
        this.syncValidatedFromTsc(tsFiles, finalErrors);
        return finalErrors.size;
    }
    /**
     * Sync each TS file's `validated`/`errors` from the WHOLE-PROJECT tsc result
     * — the authoritative gate (it compiles every file together, so sibling
     * imports resolve). The batch loop's per-file sandbox validation runs each
     * file in isolation (`tsc index.ts` standalone), so a correct sibling import
     * (`../core-engine/core-engine.ts`) can never resolve there and produces a
     * FALSE TS2307. When the whole-project tsc passes a file, clear those stale
     * sandbox errors and validate it; still-failing files get the authoritative
     * errors.
     */
    syncValidatedFromTsc(tsFiles, finalErrors) {
        for (const f of tsFiles) {
            const errs = finalErrors.get(f.nodeLabel);
            if (errs && errs.length > 0) {
                f.errors = errs;
                f.validated = false;
            }
            else {
                f.errors = [];
                f.validated = true;
            }
        }
    }
    /**
     * Directory name a generated file's module folder gets: the label slugged the
     * same way the emitted import paths are, with underscores for Python (a
     * hyphenated directory cannot be imported by a Python module name).
     */
    safeDirName(file) {
        const safe = labelToFileName(file.nodeLabel);
        return (file.language || '').toLowerCase() === 'python' ? safe.replace(/-/g, '_') : safe;
    }
    /**
     * Project-relative POSIX path a generated file is scaffolded at — the ONE
     * place the export layout is encoded. The compile gates, the deterministic
     * repair fixers (they resolve relative specifiers against this tree) and
     * PerFileScaffolder all go through here, so what a fixer reasons about is
     * exactly what tsc compiles and exactly what the user receives. Tree Mode
     * moves a multi-app build into `apps/<app>/src/…` + `bridge/`; a single-app
     * build is the flat `src/<safeName>/<file>` it always was.
     */
    scaffoldRelPath(file) {
        return path.posix.join(exportDirFor(file, this.safeDirName(file)), file.fileName);
    }
    /**
     * Scaffold the given TS/JS files into a temp dir (layout mirrors
     * PerFileScaffolder via scaffoldRelPath) and run
     * `tsc --noEmit --allowImportingTsExtensions -p <dir>`.
     * Returns Map<nodeLabel, string[]> of `TSxxxx: message (line N)` per failing
     * file (empty map = all compile clean).
     */
    async runTscCheck(tsFiles) {
        // SHARED compiler gate (sandbox/buildVerification.ts). This is the SAME
        // implementation the chat pipeline (codePlanner.runTscCheck) now calls, so
        // the two generation pipelines can no longer compile against different
        // strictness/layout rules and drift apart.
        const entries = tsFiles.map((f) => ({
            label: f.nodeLabel,
            relPath: this.scaffoldRelPath(f),
            code: f.code,
        }));
        const res = await runTscGate(entries, { timeoutMs: 180_000 });
        return res.errorsByLabel;
    }
    /**
     * Generate a single file for one node (public, for hot-swap regeneration).
     * Builds dependency context and calls the private generator.
     */
    /**
     * Generate ONE cross-app bridge module (Tree Mode).
     *
     * The bridge carries a single payload between two SEPARATE apps built from
     * this one project: it exports the agreed data shape plus a small API for
     * the giving and the receiving side. Returns null when the model produced
     * nothing usable, so the caller skips it rather than shipping an empty file.
     */
    async generateBridgeModule(project, bridge) {
        const byId = new Map((project.nodes || []).map((n) => [n.id, n]));
        const describeNode = (id) => {
            const n = byId.get(id);
            if (!n)
                return null;
            return {
                label: n.data?.label || n.id,
                type: n.data?.type || n.type,
                description: n.data?.description,
                language: n.data?.language,
            };
        };
        const sourceNodes = bridge.links
            .map((l) => describeNode(l.sourceNodeId))
            .filter(Boolean);
        const targetNodes = bridge.links
            .map((l) => describeNode(l.targetNodeId))
            .filter(Boolean);
        // The bridge joins two trees, so there is no single language to inherit.
        // Use the giving side's (it implements the export half) and fall back to
        // TypeScript — the language most VACA apps are built in.
        const language = sourceNodes.find((n) => n.language)?.language || 'typescript';
        const prompt = buildBridgePrompt({
            bridge,
            projectName: project.name,
            targetOS: project.targetOS,
            sourceNodes,
            targetNodes,
        });
        const raw = await this.ai.reason(prompt, BRIDGE_SYSTEM_PROMPT, { maxTokens: 2048, timeoutMs: 180_000 });
        const code = parseBridgeResponse(raw);
        if (!code || code.trim().length < 20) {
            console.warn(`[fileGenerator] bridge "${bridge.name}" produced no usable module — skipped`);
            return null;
        }
        const exportInfo = this.extractExports(code, language);
        // Same sandbox validation every other file gets — a bridge is held to the
        // same standard as the app code it connects.
        let errors = [];
        let validated = false;
        try {
            const validation = await this.sandbox.run(code, language);
            errors = validation.errors || [];
            validated = validation.success;
        }
        catch {
            errors = ['Sandbox validation unavailable'];
        }
        console.log(`[fileGenerator] 🌉 bridge "${bridge.name}" — ${bridge.payloadLabel}: ` +
            `${bridge.sourceTreeName} → ${bridge.targetTreeName} (${code.length} chars, ${exportInfo.names.length} export(s))`);
        return {
            fileName: bridgeFileName(bridge, language),
            language,
            code,
            nodeId: `bridge:${bridge.key}`,
            nodeLabel: bridge.name,
            isBridge: true,
            treeIds: [bridge.sourceTreeId, bridge.targetTreeId],
            dependencies: [],
            exports: exportInfo.names,
            errors,
            validated,
        };
    }
    async generateSingleFile(node, project, dependencyLabels) {
        const fileExports = new Map();
        const code = await this.generateNodeFile(node, project, dependencyLabels, fileExports, null);
        return code;
    }
    /**
     * Determine which model tier to use for generating this node's code.
     * Simple/trivial files (configs, types, CSS, etc.) go to the fast coder model,
     * while complex logic (business logic, APIs, databases) stays on the primary model.
     */
    pickModelTier(node, dependencyLabels) {
        // Blueprint-driven modules (contractContext present) ALWAYS go to the
        // primary (strongest) model — the fast 0.5B/1.5B coder cannot handle
        // cross-file contracts. Measured failure (teacher-build seq 2): the
        // classifier's `logic && isShortDesc && noDeps` rule routed ALL chess
        // modules to the fast tier (blueprint descriptions are <300 chars, deps
        // ≤1), and the 0.5B produced skeleton stubs: 'Placeholder' comments,
        // `fs.writeFileSync` in a browser app (TS2304 fs), undeclared globals
        // (initialGameState, player, gameState, Result, Request), and a void-typed
        // function with no return (TS2355) — 9 tsc errors, 2/6 validated. Only
        // truly standalone files with NO contract and NO cross-file wiring are
        // eligible for the fast tier.
        if (node.data?.contractContext) {
            return 'primary';
        }
        return classifyCodeComplexity(node.data?.label || node.id || '', node.data?.description || '', node.type || 'logic', node.data?.language || 'typescript', dependencyLabels.length);
    }
    /**
     * Generate code for a single node as an independent file.
     * The code includes the node's logic with proper function signatures
     * and exports so other files can import from it.
     *
     * Automatically routes simple files to the fast coder model (0.5B/1.5B)
     * and complex files to the primary model (7B).
     */
    async generateNodeFile(node, project, dependencyLabels, fileExports, guiWidgetOutput, fixErrors, fixContext, 
    /**
     * Tree Mode: which app tree this node is in, and the bridges that carry
     * payloads out of it. Omitted by callers that have no tree context (the
     * single-file path), which keeps those builds byte-identical.
     */
    treeContext) {
        const nodeLabel = node.data.label || node.id;
        const language = node.data.language || 'typescript';
        const ext = getFileExtension(language);
        // Build context about what dependencies this node can use. Empty export
        // contracts render as an explicit NONE so the model never reads "exports:"
        // and invents imports from a file that exposes nothing.
        //
        // When a dependency's REAL source is available (generated in an earlier
        // batch or fixed in an earlier repair round), embed it directly — the model
        // must code against the ACTUAL shapes, not guessed ones. The A/B tests
        // showed 7B AND 14B models fail cross-file contracts (private members,
        // wrong member shapes) purely because they never see the dependency code:
        // the 14B wrote `private cells` in grid.ts and ai.ts then hit TS2341 on
        // game.cells. Source is capped per file to keep prompts in context.
        const MAX_DEP_SOURCE_CHARS = 4000;
        const depContext = dependencyLabels.length > 0
            ? `\n\nThis file can import from these sibling files (ONLY the declared exports — never invent members):\n${dependencyLabels.map(l => {
                const src = this.depSourceCache.get(l);
                const realized = fileExports.get(l);
                const planned = fixContext?.plannedContracts?.get(l);
                // Dependency still IN FLIGHT (concurrent pool): its realized exports
                // do not exist yet. A blank "(none)" would read as "this module
                // exports nothing", so hand over its PLANNED contract from the
                // wiring graph instead — that is what the compile-check loop then
                // reconciles against the real exports.
                if (!realized && !src && planned) {
                    const indented = planned.split('\n').map(s => `    ${s}`).join('\n');
                    return `  - ${labelToFileName(l)}.${ext} — NOT GENERATED YET. Its PLANNED CONTRACT below is authoritative: import ONLY the exports it promises, using exactly those names.\n${indented}`;
                }
                const header = `  - ${labelToFileName(l)}.${ext} (exports: ${describeExports(realized)})`;
                if (src && src.trim().length > 10) {
                    const capped = src.trim().length > MAX_DEP_SOURCE_CHARS
                        ? src.trim().substring(0, MAX_DEP_SOURCE_CHARS) + '\n// ... (dependency truncated)'
                        : src.trim();
                    return `${header}\n    REAL SOURCE OF ${labelToFileName(l)}.${ext} (code against these exact shapes — members, fields, visibility, types):\n    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n${capped}\n    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`;
                }
                return header;
            }).join('\n')}\n\nMEMBER WHITELIST RULE: on every class/interface imported from a sibling, you may ONLY call the members shown in braces (e.g. ChessBoard { getPiece, setPiece, clone }) or visible in the REAL SOURCE above. NEVER invent a method that is not listed (no board.makeMove(), board.evaluate(), etc.) — if you need that behavior, implement it locally as your own function using the whitelisted members. If a dependency shows NO braces and NO source, call nothing on it.`
            : '';
        // ── Client-only guard ──
        // Browser apps (ui node, no api/database nodes) must never get server-side
        // config hallucinated into them. The 2026-08-13 tic-tac-toe build shipped
        // DATABASE_URL/SECRET_KEY/API_KEY placeholders in config.ts — this prompt
        // constraint is the first line of defense; the security scan is the second.
        const hasUiNode = (project.nodes || []).some((n) => n.type === 'ui' || n.type === 'gui-layout');
        const hasServerNode = (project.nodes || []).some((n) => n.type === 'api' || n.type === 'database');
        const clientOnlySection = hasUiNode && !hasServerNode
            ? `\n\nIMPORTANT — CLIENT-ONLY APP: this project runs entirely in the browser (no server, no database).\n  - NEVER add server-side configuration: no DATABASE_URL, SECRET_KEY, API_KEY, API_PREFIX, process.env, or DB connections.\n  - NO placeholder values (yourApiKeyHere, yourSecretKeyHere, '...example', empty strings as real config).\n  - Any config constants must be REAL values the app actually uses (board size, theme colors, etc.).`
            : '';
        // ── Inject semantic connections (user-described wiring from a merge) ──
        // Edges created by the Connect & Describe dialog carry data.semantic with
        // the interpreted label/relation/codeHint. They create the import
        // dependency above AND tell the model HOW to implement the wiring, so the
        // two merged modules genuinely interoperate instead of merely importing.
        // Cross-tree edges are NOT sibling wiring: their endpoints live in
        // different apps, and rendering them here would invite the model to import
        // the other app's file. Only intra-tree edges describe wiring inside this
        // app, so the cross-tree ones are filtered out of this section and handled
        // by the boundary section below instead.
        const semanticSection = buildSemanticSection(node, treeContext ? { ...project, edges: treeContext.scope.intraEdges } : project);
        // The APP BOUNDARY this node sits on, if any — how to hand its data to the
        // app tree beside it (through the named bridge module, never an import).
        // Empty for a node on no boundary, so ordinary builds are unaffected.
        const crossTreeSection = treeContext
            ? buildCrossTreeBoundarySection(node.id, treeContext.scope, treeContext.bridges)
            : '';
        // ── Inject GUI widget context for UI nodes ──
        let guiContext = '';
        const isUINode = node.type === 'ui' || node.type === 'gui-layout';
        if (isUINode && guiWidgetOutput) {
            const widgetLines = [];
            widgetLines.push('');
            widgetLines.push('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
            widgetLines.push('📋 GENERATED GUI WIDGET LAYOUT');
            widgetLines.push('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
            widgetLines.push(`App: ${guiWidgetOutput.appName || 'Untitled'}`);
            widgetLines.push(`Layout: ${guiWidgetOutput.layout || 'single-page'}`);
            widgetLines.push(`Theme: ${guiWidgetOutput.theme || 'Default'}`);
            widgetLines.push('');
            if (guiWidgetOutput.colorScheme) {
                const cs = guiWidgetOutput.colorScheme;
                widgetLines.push('Color Scheme:');
                widgetLines.push(`  Primary: ${cs.primary || '#4a9eff'}`);
                widgetLines.push(`  Background: ${cs.background || '#1a1a2e'}`);
                widgetLines.push(`  Surface: ${cs.surface || '#16213e'}`);
                widgetLines.push(`  Text: ${cs.text || '#e0e0e0'}`);
                widgetLines.push(`  Accent: ${cs.accent || '#0f3460'}`);
                widgetLines.push('');
            }
            const widgets = guiWidgetOutput.widgets || [];
            if (widgets.length > 0) {
                widgetLines.push(`Generated ${widgets.length} UI widgets:`);
                for (const w of widgets.slice(0, 15)) {
                    widgetLines.push(`  [${w.type}] ${w.label} — ${w.description || ''} (${w.zone || 'main'})`);
                    if (w.bind?.onClick)
                        widgetLines.push(`    onClick → ${w.bind.onClick}`);
                    if (w.bind?.onChange)
                        widgetLines.push(`    onChange → ${w.bind.onChange}`);
                }
                if (widgets.length > 15) {
                    widgetLines.push(`  ... and ${widgets.length - 15} more widgets`);
                }
            }
            widgetLines.push('');
            widgetLines.push('INSTRUCTIONS: Generate UI component code that implements the widgets above.');
            widgetLines.push('Use the color scheme and layout as design guidelines.');
            widgetLines.push('Export a single function named `render` (or `init`) that accepts a container HTMLElement');
            widgetLines.push('and renders the UI into it. Do NOT use a default export — the preview wrapper calls');
            widgetLines.push('the named `render`/`init` function with the \'#app-container\' element.');
            widgetLines.push('');
            widgetLines.push('━━━ CONCRETE WIDGET TEMPLATES (build the SAME structure with document.createElement — never invent element types) ━━━');
            widgetLines.push(GUI_WIDGET_SECTION.trim());
            widgetLines.push(APP_QUALITY_RULES.trim());
            widgetLines.push('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
            guiContext = widgetLines.join('\n');
        }
        // Check for label/language extension mismatch (e.g., label "main.go" but language is "rust")
        const { extOverride } = stripLabelExtension(nodeLabel);
        const extMismatch = extOverride && !extensionMatchesLanguage(extOverride, language);
        const extClarification = extMismatch
            ? `

NOTE: The label "${nodeLabel}" has a .${extOverride} extension, but the selected language is ${language}.
The file will be saved as a .${ext} file containing ${language} code.
Generate ONLY ${language} syntax — do NOT use ${extOverride} syntax.`
            : '';
        // Determine language-specific hints for the AI prompt
        let languageHint = '';
        if (language?.toLowerCase() === 'go') {
            // Each Go file in a per-file architecture gets a package name based on its directory.
            // The sanitized label becomes both the directory name AND the Go package name.
            // IMPORTANT: Go does NOT allow multiple files in different directories with the same package name.
            const goPackageName = labelToFileName(nodeLabel).replace(/-/g, '');
            languageHint = `\n\nIMPORTANT — Go-specific rules:\n  - Start with: package ${goPackageName}\n  - The package name is "${goPackageName}" — derived from the node label.\n  - DO NOT use "package main" — each node file is its own package in its own directory.\n  - DO NOT include ANY import statements — they will be added automatically by the build system.\n  - DO NOT include func main() — this is not an entry point file.\n  - Start DIRECTLY with the package declaration, no text before it.`;
        }
        else if (language?.toLowerCase() === 'rust') {
            // Rust files in the per-file architecture are separate modules.
            // Each file is declared via #[path] in the root main.rs.
            // Cross-module access requires `pub` visibility on all exported items.
            languageHint = `\n\nIMPORTANT — Rust-specific rules:\n  - This file will be a separate Rust module, declared via #[path] in main.rs.\n  - Every function, struct, enum, trait, const, or type that other files need MUST be marked \`pub\`.\n  - Without \`pub\`, the item is private to this module and cannot be imported elsewhere.\n  - DO NOT include \`use\` statements — they will be added automatically by the build system.\n  - DO NOT include \`mod\` declarations — those are handled by the root main.rs.\n  - DO NOT include \`fn main()\` — this is not an entry point file.\n  - Use Rust 2021 edition syntax throughout.`;
        }
        else if (language?.toLowerCase() === 'python') {
            // Python files in the per-file architecture are separate packages.
            // Each node directory has an __init__.py that re-exports the main file.
            // The directory name uses underscores (not hyphens) for valid Python module naming.
            const pyModName = labelToFileName(nodeLabel).replace(/-/g, '_');
            languageHint = `\n\nIMPORTANT — Python-specific rules:\n  - This file will be a Python module inside a package directory named "${pyModName}".\n  - An __init__.py will re-export your definitions via \`from .${labelToFileName(nodeLabel)} import *\`.\n  - Define functions and classes that other modules can import.\n  - DO NOT include \`import\` or \`from ... import\` statements — they will be added automatically.\n  - DO NOT include \`if __name__ == \"__main__\":\` blocks — they belong in the entry point only.\n  - DO NOT include module docstrings at the top level (the __init__.py handles that).\n  - Start directly with your function/class/constant definitions.`;
        }
        else if ((language?.toLowerCase() === 'typescript' || language?.toLowerCase() === 'javascript') && isUINode) {
            // UI files are saved as plain .ts/.js (never .tsx/.jsx). Generated previews
            // inline the raw source, so JSX would fail both tsc and the browser.
            languageHint = `\n\nIMPORTANT — plain TS/JS rules for UI files:\n  - This file is a .${ext} file, NOT .tsx/.jsx.\n  - DO NOT use JSX syntax (no <div>, <button>, <li key=...>, etc.).\n  - Build DOM with document.createElement(), textContent, className, and appendChild().\n  - You may set innerHTML with static markup strings, but never from user input.\n  - You MAY include \`import\` statements for the sibling modules listed in this file's import context (the build keeps them and adds any missing ones) — never import anything else.\n  - Export ONE function named \`render\` (or \`init\`) that accepts a container HTMLElement and renders the UI into it. The preview wrapper calls it with the '#app-container' element.`;
        }
        // ── Compiler-feedback section (compile-check-retry loop) ──
        // When the previous attempt failed `tsc --noEmit`, feed the exact errors
        // back so the model can fix them on the retry, PLUS its own previous
        // content and the real export contracts of its import targets (mirrors
        // codePlanner's buildRepairPrompt). Without that context the model repairs
        // blind — it cannot fix cross-file drift ("Property 'x' does not exist on
        // type 'Y'") when the fix lives in the OTHER file's contract. The error
        // list is capped to keep the prompt small and focused.
        const fixSection = fixErrors && fixErrors.length > 0
            ? `\n\n⚠️ THE PREVIOUS VERSION OF THIS FILE FAILED TO COMPILE.\n${fixContext?.previousContent
                ? `\n━━━ CURRENT CONTENT (previous attempt) ━━━\n${fixContext.previousContent.substring(0, 6000)}\n`
                : ''}${fixContext?.importTargets
                ? `\n━━━ IMPORT TARGETS (may ONLY reference these declared exports) ━━━\n${fixContext.importTargets}\n`
                : ''}\n━━━ TSC ERRORS (fix ALL of them) ━━━\n${fixErrors.slice(0, 12).map(e => `  - ${e}`).join('\n')}\n\nRules for the corrected file:\n  - Keep the SAME exported symbol names (other files import them).\n  - This is a .${ext} file, NOT .tsx/.jsx — do NOT use JSX syntax (<div>, <button>).\n  - Build the DOM with document.createElement(), textContent, className, appendChild().\n  - You MAY add import statements for the modules listed in IMPORT TARGETS above (the build dedupes them) — importing a member the lint says a dependency exports is the RIGHT fix; never import anything else.\n  - Do NOT include markdown, prose, or fences — code only.\n  - TypeScript: every variable/parameter/return must have a valid type; remove 'any' casts that break the code.\n  - Do NOT use TypeScript features the target doesn't support (e.g. JSX in .ts).\n  - If an error says a member does not exist on an imported type (TS2339), do NOT cast to 'any' and do NOT invent the member — call ONLY the members listed in braces in IMPORT TARGETS (import them if the dependency exports them), or implement the behavior locally as your own helper using those whitelisted members.
  - If an error says a NAME is not found (TS2304 Cannot find name 'X' / TS2451 redeclared / TS2339 on a symbol), the name is defined NOWHERE in this file. If IMPORT TARGETS exports it, WRITE the import for it (imports to IMPORT TARGETS modules are allowed). Otherwise define it LOCALLY in this file (exported interface/type/const) or receive it via a function parameter — never reference an undefined symbol, never rely on implicit globals, and never duplicate a class that a dependency module already exports (use the dependency's export instead).`
            : '';
        // Program scale from the master node (the size the user picked) — tailors
        // this file's depth to the target program size.
        const masterScale = project.nodes.find(n => n.type === 'master')?.data?.scale;
        const scaleSection = buildScaleSection(masterScale);
        // Blueprint bible constraints (blueprint-driven builds): the fused
        // checklist + wiring-graph section stored on the master node. Forces this
        // file to implement exactly its own checklist module and to use the wiring
        // contract names verbatim so sibling files connect without drift.
        const masterBlueprint = project.nodes.find(n => n.type === 'master')?.data?.blueprintContext;
        const blueprintSection = masterBlueprint
            ? `\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nBLUEPRINT CONSTRAINTS (MANDATORY)\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n${masterBlueprint}\nTHIS FILE'S MODULE: "${nodeLabel}"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`
            : '';
        // Per-module contract stub (blueprint builds): derived deterministically
        // from the wiring graph — WHO imports this module (its required exports),
        // WHO it imports from (its only legal call targets), and the
        // anti-single-file-mode rules (state via parameters, never globals, no DOM
        // in non-UI modules). This is the direct fix for the ladder's #1 measured
        // failure mode. Injected into BOTH generation and repair prompts (repair
        // prompts reuse this same builder via generateNodeFile).
        const contractStub = node.data.contractContext;
        const contractSection = contractStub
            ? `\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nMODULE CONTRACT (MANDATORY — REQUIRED EXPORTS)\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n${contractStub}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`
            : '';
        // ── Type ownership (graph-free prevention) ──
        // The duplicate-class defect this guards against (one shared domain type
        // declared by two nodes) is only half fixed by resolving it after the fact:
        // stating the rule up front stops it being generated. Emitted whether or
        // not a MODULE CONTRACT exists — the contract's own ownership rule needs a
        // wiring edge, and a canvas build has none.
        const ownershipSiblings = (project.nodes || [])
            .filter((n) => n.type !== 'master' && (n.data?.label || n.id) !== nodeLabel)
            .map((n) => ({ label: n.data?.label || n.id, description: String(n.data?.description || '') }));
        const ownershipSection = buildTypeOwnershipSection(nodeLabel, ownershipSiblings);
        // ── Full-picture context (the whole scaffold, not just this node's deps) ──
        // Per-node prompts only showed the node's DIRECT dependencies, so the model
        // wrote each file without knowing the app it belongs to (the 14B's
        // "forest for the trees" drift: wrong module names, invented siblings,
        // CLI-flavored plans for browser apps). Inject the COMPLETE node graph —
        // every sibling file + every edge — capped so large plans stay in context,
        // so each chunk is built in context of the whole design. Edge direction
        // mirrors the graph convention: an edge "X → Y" means Y imports from X.
        const MAX_PICTURE_NODES = 30;
        const pictureLabelById = new Map();
        for (const n of project.nodes || [])
            pictureLabelById.set(n.id, n.data?.label || n.id);
        const pictureSiblings = (project.nodes || []).filter((n) => (n.data?.label || n.id) !== nodeLabel);
        const pictureLines = [];
        pictureLines.push('━━━ PROJECT ARCHITECTURE (FULL PICTURE — the whole app this file belongs to) ━━━');
        if (pictureSiblings.length === 0) {
            pictureLines.push('  (single-file app — this is the only file)');
        }
        else {
            for (const n of pictureSiblings.slice(0, MAX_PICTURE_NODES)) {
                const lbl = n.data?.label || n.id;
                const desc = String(n.data?.description || '').replace(/\s+/g, ' ').trim();
                pictureLines.push(`  - ${lbl} (${n.type || 'logic'}) — ${desc.slice(0, 90)}${desc.length > 90 ? '…' : ''}`);
            }
            if (pictureSiblings.length > MAX_PICTURE_NODES) {
                pictureLines.push(`  ... and ${pictureSiblings.length - MAX_PICTURE_NODES} more files`);
            }
            const pictureEdges = (project.edges || []).filter((e) => e.source && e.target && e.source !== e.target);
            if (pictureEdges.length > 0) {
                pictureLines.push('  CONNECTIONS (an edge "X → Y" means Y imports from X):');
                for (const e of pictureEdges.slice(0, 40)) {
                    const src = pictureLabelById.get(e.source) || e.source;
                    const tgt = pictureLabelById.get(e.target) || e.target;
                    if (src === nodeLabel || tgt === nodeLabel)
                        continue;
                    pictureLines.push(`    ${src} → ${tgt}`);
                }
            }
        }
        const pictureSection = `\n\n${pictureLines.join('\n')}`;
        // Build the prompt for a standalone file
        const prompt = `You are an expert ${language} developer${isUINode ? ' and UI/UX designer' : ''}. Generate a SINGLE standalone source file for the node "${nodeLabel}".

${VACA_BRAIN_DOCTRINE}

THIS FILE'S PLACE IN THE APP: ${nodeLabel} is one node of the VACA node graph below — build it to fit THIS app, not a generic module of that name.

NODE DESCRIPTION:
${node.data.description || 'No description provided'}

NODE TYPE: ${node.type || 'logic'}
PROJECT: ${project.name}
TARGET OS: ${project.targetOS}
${scaleSection}${blueprintSection}${contractSection}${ownershipSection}${pictureSection}
${depContext}${semanticSection}${crossTreeSection}
${guiContext}${extClarification}${languageHint}${clientOnlySection}${fixSection}

REQUIREMENTS:
1. Generate COMPLETE, PRODUCTION-READY ${language} code for this specific node
2. The file should be a self-contained module with proper function/class definitions
3. Export the main functionality so other files can import it
4. Include type definitions/interfaces where appropriate
5. Include error handling and edge cases
6. Add clear comments for complex logic
7. IMPORT STATEMENTS: you MAY write import statements for sibling modules listed in this file's import context (e.g. \`import { Task } from '../core-engine/core-engine.ts'\`) — the build system keeps them and adds any missing ones, never duplicating yours. NEVER import anything other than those listed sibling modules, and NEVER import third-party packages. (Single-file apps: no imports needed.)
8. The generated code will be the FILE BODY — define exports, classes, and functions only
9. Use NAMED exports only (export function/class/const Name). NEVER use \`export default\` — sibling files import your symbols by name, and a default export breaks their imports
10. Write the ACTUAL implementation — real logic, real method bodies. NO placeholder comments ('// TODO', '// define your properties here', '// add more methods as needed'), no empty stubs, no skeleton methods
11. Use ONLY built-in language/platform APIs and the standard library. NO third-party packages or frameworks (express, prisma, lodash, axios, react, better-sqlite3, node:assert, etc.) — nothing is installed and nothing can be imported. Implement persistence with plain in-memory structures, JSON, or built-in file APIs. If you need a library feature, implement a small local equivalent instead.
12. If this is a TEST file (*.test.ts / *.spec.ts / __tests__/): the test runner globals (describe, it, test, expect, beforeEach, afterEach, beforeAll, afterAll, vi) are ALREADY DECLARED by the platform — use them DIRECTLY as bare globals, never import or require a test framework or test-utility package (jest, vitest, mocha, node:test, @testing-library/*, sinon, chai, supertest, enzyme, react-test-renderer, @types/*) — nothing else is available, so write assertions with the declared globals and plain DOM/Node APIs only.

Return ONLY the code — no markdown, no explanations, no code fences.`;
        try {
            // ── Pick the right model tier for this file ──
            // Compiler-error fixes ALWAYS go to the primary (strongest) model — the
            // fast 0.5B/1.5B coder is too weak to repair tsc errors reliably.
            const tier = (fixErrors && fixErrors.length > 0)
                ? null
                : this.pickModelTier(node, dependencyLabels);
            let code;
            if (tier === 'fast-cpu' || tier === 'fast-gpu') {
                // Route to fast coder model (auto-picks best available: GPU1→GPU0→CPU)
                code = await this.ai.reasonFast(prompt, { maxTokens: 2048, role: 'codeGeneration' });
                console.log(`[fileGenerator] Generated "${nodeLabel}" using fast coder (${tier === 'fast-cpu' ? 'CPU fallback' : 'GPU dedicated'})`);
            }
            else {
                // Route to primary 7B model (delegator — reserved for complex tasks).
                // Fix rounds use a LOW temperature so the model performs the repair
                // instead of reimagining the file (high temp makes it swap one invented
                // member for another each round instead of converging).
                const isFixRound = !!(fixErrors && fixErrors.length > 0);
                // 0.2: deterministic repair. Measured across 5 builds: 0.2 fix rounds
                // produced the best build (4 real errors) and beat 0.3 (which caused
                // fix-round drift: a 1-file-failing round-1 regressed to 6 files).
                code = await this.ai.reason(prompt, undefined, { maxTokens: 4096, temperature: isFixRound ? 0.2 : undefined, role: 'codeGeneration' });
                console.log(`[fileGenerator] Generated "${nodeLabel}" using 7B delegator (complex logic${isFixRound ? ', fix round @temp 0.2' : ''})`);
            }
            // Clean up any markdown fences the AI might add
            let cleaned = code.trim();
            const langPattern = (language || 'typescript').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            cleaned = cleaned.replace(new RegExp(`^\`\`\`(?:${langPattern}|typescript|javascript|python|go|rust)?\\s*\\n?`, 'i'), '');
            cleaned = cleaned.replace(/\n?```\s*$/i, '');
            cleaned = cleaned.trim();
            // ── Language-specific post-processing ──
            if (language?.toLowerCase() === 'go') {
                // Fix: Go doesn't allow "./" in the middle of import paths
                // e.g., "app-to-list-all-app/./src/config" → "app-to-list-all-app/src/config"
                // The AI sometimes generates "./" paths despite being told not to.
                //
                // This regex only matches inside "..." quotes where there's a leading /
                // before the ./. This is SAFE because:
                //   ✅ "module/./path" → matches (has /./)
                //   ❌ "./path" → no match (no / before ./)
                //   ❌ "../path" → no match (no / before ./)
                //   ❌ fmt.Println("./path") → no match (string not in quotes at regex level...
                //       actually it IS in quotes, but no leading / before ./)
                cleaned = cleaned.replace(/"([^"]+?)\/\.\/([^"]+)"/g, '"$1/$2"');
            }
            return cleaned || `// TODO: Implement ${nodeLabel}\nexport function ${labelToExportName(nodeLabel)}() {\n  // Auto-generated placeholder\n  throw new Error('Not implemented');\n}`;
        }
        catch (error) {
            console.error(`[fileGenerator] Failed to generate code for node ${nodeLabel}:`, error);
            return `// TODO: Implement ${nodeLabel}\nexport function ${labelToExportName(nodeLabel)}() {\n  // Code generation failed — implement manually\n  throw new Error('Not implemented');\n}`;
        }
    }
    /**
     * Extract exported symbols from generated code.
     */
    extractExports(code, language) {
        const names = [];
        let defaultName;
        switch (language?.toLowerCase()) {
            case 'typescript':
            case 'javascript': {
                // NOTE: all export regexes are anchored to a line start (allowing
                // leading whitespace) so comments/strings mentioning "export" can
                // never register a false export contract.
                // Named exports: `export function name`, `export const name`, etc.
                const exportRegex = /^\s*export\s+(?!default\b)(?:function|const|let|var|class|interface|type|enum)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)/gm;
                let match;
                while ((match = exportRegex.exec(code)) !== null) {
                    names.push(match[1]);
                }
                // `export { name1, name2 }` — ALL such blocks, not just the first.
                const namedRegex = /^\s*export\s*\{\s*([^}]+)\s*\}/gm;
                let namedMatch;
                while ((namedMatch = namedRegex.exec(code)) !== null) {
                    namedMatch[1].split(',').forEach(e => {
                        const n = e.trim().split(/\s+as\s+/)[0].trim();
                        if (n && n !== 'default')
                            names.push(n);
                    });
                }
                // `export default Name` — captured so dependents can `import Name from`.
                // Handles BOTH `export default Foo` AND `export default class Foo` (the
                // latter must not capture the "class" keyword as the name).
                const defMatch = code.match(/^\s*export\s+default\s+(?:(?:abstract\s+)?(?:class|interface|enum|function)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)|([a-zA-Z_$][a-zA-Z0-9_$]*))/m);
                if (defMatch)
                    defaultName = defMatch[1] || defMatch[2];
                // `export { X as default }` — also a default export.
                const asDefault = code.match(/^\s*export\s*\{\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s+as\s+default\s*\}/m);
                if (asDefault && !defaultName)
                    defaultName = asDefault[1];
                // ── Member whitelist extraction (typescript/javascript) ──
                // For every exported class/interface, capture the member names inside its
                // body so dependents are told which members they may call. A member is any
                // `name`, `name(...)`, `name: ...`, `name = ...`, `readonly name`, or
                // optional `name?` at brace depth 1 of that declaration.
                const memberWhitelist = {};
                // ANY top-level class/interface declaration (optional export/default/abstract
                // modifiers). Members are only KEPT when the type is actually exported, so
                // `export class X`, `class X { ... } export { X }`, and `export default X`
                // styles all get whitelists (the model invented members on those too).
                const classDeclRe = /^\s*(?:export\s+(?:default\s+)?|declare\s+)?(?:abstract\s+)?class\s+([a-zA-Z_$][a-zA-Z0-9_$]*)[^{]*\{/gm;
                // export interface Name { ... }
                const ifaceDeclRe = /^\s*(?:export\s+(?:default\s+)?|declare\s+)?interface\s+([a-zA-Z_$][a-zA-Z0-9_$]*)[^{]*\{/gm;
                const collectMembers = (typeName, body) => {
                    // Skip the opening brace itself; capture depth-1 member declarations.
                    // Matches: foo, foo(), foo(..): T, foo: T, foo = ..., readonly foo, foo?
                    const memberRe = /(?:^|;|\n)\s*(?:readonly\s+|static\s+|private\s+|protected\s+|public\s+)*(?!if\b|for\b|while\b|return\b|throw\b|switch\b|const\b|let\b|var\b|new\b|else\b)([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?:\(|\?\s*[:;(]|\s*[:;=(]|\s*$)/g;
                    const members = new Set();
                    let m;
                    while ((m = memberRe.exec(body)) !== null) {
                        if (m[1] && !/^(?:if|for|while|return|throw|switch|const|let|var|new|else|get|set)$/.test(m[1])) {
                            members.add(m[1]);
                        }
                    }
                    // Also catch getters/setters and plain methods without type annotations.
                    const methodRe = /(?:^|;|\n)\s*(?:get\s+|set\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(/g;
                    while ((m = methodRe.exec(body)) !== null) {
                        if (m[1] && !/^(?:if|for|while|return|throw|switch|new|else)$/.test(m[1])) {
                            members.add(m[1]);
                        }
                    }
                    if (members.size > 0) {
                        memberWhitelist[typeName] = [...members];
                    }
                };
                const exportedNames = new Set([...(names || []), ...(defaultName ? [defaultName] : [])]);
                const classMatches = [...code.matchAll(classDeclRe)];
                for (const cm of classMatches) {
                    if (!exportedNames.has(cm[1]))
                        continue;
                    const start = (cm.index || 0) + cm[0].length;
                    const body = extractBraceBody(code, start);
                    if (body)
                        collectMembers(cm[1], body);
                }
                const ifaceMatches = [...code.matchAll(ifaceDeclRe)];
                for (const im of ifaceMatches) {
                    if (!exportedNames.has(im[1]))
                        continue;
                    const start = (im.index || 0) + im[0].length;
                    const body = extractBraceBody(code, start);
                    if (body)
                        collectMembers(im[1], body);
                }
                return {
                    names: [...new Set(names)],
                    defaultName,
                    ...(Object.keys(memberWhitelist).length > 0 ? { members: memberWhitelist } : {}),
                };
            }
            case 'python': {
                // Match top-level def and class (not indented)
                const pyRegex = /^(?:async\s+)?(?:def|class)\s+([a-zA-Z_][a-zA-Z0-9_]*)/gm;
                let match;
                while ((match = pyRegex.exec(code)) !== null) {
                    if (!match[1].startsWith('_'))
                        names.push(match[1]);
                }
                break;
            }
            case 'go': {
                // Match exported functions/types (capitalized)
                const goRegex = /^func\s+([A-Z][a-zA-Z0-9_]*)|^type\s+([A-Z][a-zA-Z0-9_]*)/gm;
                let match;
                while ((match = goRegex.exec(code)) !== null) {
                    names.push(match[1] || match[2]);
                }
                break;
            }
            case 'rust': {
                // Match `pub fn`, `pub struct`, `pub enum`, `pub trait`, `pub type`, `pub const`, `pub unsafe fn`
                const rustRegex = /^pub\s+(?:unsafe\s+)?(?:fn|struct|enum|trait|type|const|static|mod|use|macro|union)\s+([a-zA-Z_][a-zA-Z0-9_]*)/gm;
                let match;
                while ((match = rustRegex.exec(code)) !== null) {
                    names.push(match[1]);
                }
                break;
            }
        }
        return { names: [...new Set(names)], defaultName };
    }
    /**
     * Topological sort of nodes based on dependency graph.
     * Ensures dependencies are generated before dependents.
     */
    topologicalSort(nodes, depGraph) {
        const visited = new Set();
        const sorted = [];
        const labelToNode = new Map();
        for (const node of nodes) {
            labelToNode.set(node.data.label || node.id, node);
        }
        function visit(label) {
            if (visited.has(label))
                return;
            visited.add(label);
            const deps = depGraph.get(label) || [];
            for (const dep of deps) {
                visit(dep);
            }
            const node = labelToNode.get(label);
            if (node)
                sorted.push(node);
        }
        for (const node of nodes) {
            visit(node.data.label || node.id);
        }
        return sorted;
    }
    /**
     * Group nodes into batches by topological depth using Kahn's algorithm.
     * Nodes in the same batch have NO dependencies on each other and can be
     * generated in parallel. Each batch waits for all previous batches to complete
     * so that import/export data is available when generating dependent nodes.
     *
     * Returns an array of batches, where each batch is an array of nodes.
     */
    topologicalBatches(nodes, depGraph) {
        // Build label → node map
        const labelToNode = new Map();
        const allLabels = new Set();
        for (const node of nodes) {
            const label = node.data.label || node.id;
            labelToNode.set(label, node);
            allLabels.add(label);
        }
        // Calculate in-degree (number of unprocessed deps) for each node
        const inDegree = new Map();
        for (const label of allLabels) {
            const deps = (depGraph.get(label) || []).filter(d => allLabels.has(d));
            inDegree.set(label, deps.length);
        }
        const batches = [];
        const remaining = new Set(allLabels);
        while (remaining.size > 0) {
            // Find all nodes with in-degree 0 (no remaining dependencies)
            const batchLabels = [];
            for (const label of remaining) {
                if ((inDegree.get(label) || 0) === 0) {
                    batchLabels.push(label);
                }
            }
            // Guard against circular dependencies
            if (batchLabels.length === 0) {
                console.warn('[fileGenerator] Circular dependency detected — breaking by adding remaining nodes as a single batch');
                const emergencyBatch = Array.from(remaining).map(l => labelToNode.get(l)).filter(Boolean);
                if (emergencyBatch.length > 0)
                    batches.push(emergencyBatch);
                break;
            }
            // Map labels to nodes
            const batch = batchLabels.map(l => labelToNode.get(l)).filter(Boolean);
            batches.push(batch);
            // Remove batch nodes from remaining
            for (const label of batchLabels) {
                remaining.delete(label);
            }
            // Decrease in-degree for nodes that depend on this batch
            for (const label of remaining) {
                const deps = (depGraph.get(label) || []).filter(d => allLabels.has(d));
                const depInBatch = deps.filter(d => batchLabels.includes(d)).length;
                if (depInBatch > 0) {
                    inDegree.set(label, (inDegree.get(label) || 0) - depInBatch);
                }
            }
        }
        return batches;
    }
    /**
     * Generate a preview HTML wrapper that assembles all generated files into a standalone,
     * runnable GUI page — designed to work in an iframe via srcdoc (no external file imports).
     *
     * This creates an index.html that:
     *   - Inlines ALL CSS and JS/TS code directly (no module imports — those fail in srcdoc)
     *   - Detects entry-point exports (init, main, run, render, start, etc.) and calls them
     *   - Provides a dark-themed UI wrapper with loading spinner and error toast
     *   - Includes error boundaries so the app doesn't crash silently
     *   - Adds a <base> tag for relative image path resolution
     */
    generatePreviewHtml(project, generatedFiles, fileExports, backendUrl) {
        const jsFiles = generatedFiles.filter(f => f.language === 'javascript' || f.language === 'typescript');
        const cssFiles = generatedFiles.filter(f => f.language === 'css');
        const hasHtml = generatedFiles.some(f => f.language === 'html');
        // Skip if there's already an HTML file — we don't want to override it
        if (hasHtml)
            return null;
        // GUI-entry enforcement (mirrors the chat/CLI path): a GUI canvas project
        // MUST get a viewable index.html even when no web-language UI files were
        // produced yet (Python/Go UI nodes, failed generation, etc.). Headless
        // projects only get a wrapper when there's JS/CSS to assemble.
        const isGui = isGuiCanvasProject(project);
        if (jsFiles.length === 0 && !isGui)
            return null;
        const projectName = project.name || 'Untitled App';
        const masterNode = project.nodes.find((n) => n.type === 'master');
        const appGoal = masterNode?.data?.appGoal || '';
        // ── Build the CSS section (inline) ──
        const cssSection = cssFiles.length > 0
            ? cssFiles.map(f => `/* ${f.fileName} */\n${f.code}`).join('\n\n')
            : '';
        // ── Build the JS section ──
        // BUNDLE the TS/JS files with esbuild so cross-module imports actually
        // resolve inside the srcdoc iframe. The historical per-file IIFE wrapper
        // elided `import` statements, so any file importing a sibling crashed with
        // a ReferenceError (e.g. ui_screens importing ChessEngine from core-engine
        // on the chess build). Falls back to the legacy IIFE assembly when bundling
        // fails (bare package imports, unparseable code) so previews still render.
        let previewBundleError = '';
        const bundledJs = bundlePreviewJs(jsFiles, { onError: (msg) => { previewBundleError = msg; } });
        let jsScriptBlocks = [];
        let legacyNamespaces = '';
        let legacyInitCalls = '';
        // Module inventory for the "nothing rendered" panel. Built from the files
        // regardless of which path runs: the legacy branch supplies its own list,
        // but the BUNDLED path is the common case and used to leave this empty,
        // which made the HTML-level fallback panel a no-op exactly when it was
        // needed.
        let previewModules = jsFiles.map(f => ({ label: f.nodeLabel, file: f.fileName, exports: f.exports || [] }));
        if (bundledJs) {
            jsScriptBlocks.push(`<script>\n${bundledJs}\n</script>`);
        }
        else if (jsFiles.length > 0) {
            const legacy = assembleLegacyPreviewJs(jsFiles);
            legacyNamespaces = legacy.namespaceDeclarations;
            legacyInitCalls = legacy.initSetupCalls.join('\n');
            previewModules = legacy.modules;
            // ONE <script> per generated file. jsSectionLines used to be joined into a
            // single block, and a syntax error in one generated file made that whole
            // block unparseable — so every other file's IIFE silently never ran and
            // the preview went blank. As separate blocks a broken file only costs
            // itself.
            jsScriptBlocks.push(...legacy.perFileScripts.map(s => `<script>\n${s}\n</script>`));
        }
        // Diagnostic payload for the "nothing rendered" panel below: what was built,
        // and the esbuild error when the generated code could not be parsed.
        const previewDiag = JSON.stringify({
            modules: previewModules,
            bundleFailed: previewBundleError ? previewBundleError.split('\n')[0].slice(0, 300) : '',
        }).replace(/<\//g, '<\\/');
        // ── Build the full HTML ──
        const safeGoal = (appGoal || projectName).replace(/[<>&"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' })[c] || c);
        const baseUrl = (backendUrl || 'http://localhost:3001').replace(/\/+$/, '');
        const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <base href="${baseUrl}/">
  <title>${safeGoal}</title>
  <meta name="description" content="${safeGoal} — generated by VACA">
  <style>
    /* ── Base Reset ── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; font-family: system-ui, -apple-system, sans-serif; }
    body { background: #0f0f1a; color: #e0e0e0; display: flex; flex-direction: column; }

    /* ── Error Toast ── */
    #error-toast { display: none; position: fixed; top: 12px; right: 12px; z-index: 9999;
      background: #ef4444; color: white; padding: 10px 16px; border-radius: 8px;
      font-size: 13px; max-width: 400px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      animation: slideIn 0.2s ease-out; }
    @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }

    /* ── Loading ── */
    #loading { display: flex; align-items: center; justify-content: center; height: 100vh;
      flex-direction: column; gap: 16px; color: #64748b; }
    #loading .spinner { width: 32px; height: 32px; border: 3px solid rgba(74,158,255,0.2);
      border-top-color: #4a9eff; border-radius: 50%; animation: spin 0.6s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    #loading-bar { width: 200px; height: 3px; background: rgba(74,158,255,0.15); border-radius: 4px; overflow: hidden; margin-top: 4px; }
    #loading-bar-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #4a9eff, #60a5fa); border-radius: 4px; animation: progress 1.5s ease-in-out infinite; }
    @keyframes progress { 0% { width: 0%; } 50% { width: 70%; } 100% { width: 100%; } }

    /* ── App Container ── */
    #app-container { flex: 1; display: flex; flex-direction: column; min-height: 0; }

    /* ── App-generated CSS ── */
${cssSection ? cssSection.split('\n').map(l => `    ${l}`).join('\n') : ''}
  </style>
</head>
<body>
  <div id="error-toast"></div>
  <div id="loading">
    <div class="spinner"></div>
    <span>Loading ${safeGoal}...</span>
    <div id="loading-bar"><div id="loading-bar-fill"></div></div>
  </div>
  <div id="app-container"></div>

  <script>
    // ── Global error boundary ──
    function addError(msg) {
      var toast = document.getElementById('error-toast');
      if (!toast) return;
      toast.textContent = '⚠️ ' + msg;
      toast.style.display = 'block';
      setTimeout(function() { toast.style.display = 'none'; }, 5000);
    }
    window.addEventListener('error', function(ev) { addError(ev.message || 'Unknown error'); });
    window.addEventListener('unhandledrejection', function(ev) { addError((ev.reason && ev.reason.message) || 'Unhandled rejection'); });${legacyNamespaces ? `
      // ── Declare module namespaces (used by the legacy IIFEs below) ──
      ${legacyNamespaces}` : ''}
  </script>

  <!-- ── Inline Generated JS (esbuild-bundled so cross-module imports resolve) ── -->
${jsScriptBlocks.join('\n\n')}

  <script>
    // ── Initialize app ──
    try {
      var loadingEl = document.getElementById('loading');
      var containerEl = document.getElementById('app-container');
      if (loadingEl) loadingEl.style.display = 'none';
      if (containerEl) containerEl.style.display = 'flex';
${legacyInitCalls}
      // GUI entry placeholder — only when there was NOTHING to assemble (no
      // web-language files). Apps that DO have JS render asynchronously may
      // legitimately mount nothing at init, so don't clobber them.
      // jsFiles is interpolated at build time (${jsFiles.length}) — a bare
      // reference would leak an undeclared identifier into the page and throw
      // a ReferenceError that blanks every GUI preview.
      // ── Never leave a SILENT blank preview ──
      // Modules were generated but nothing rendered (the bundler could not parse
      // the code, or no module exports a callable entry point). A blank box next
      // to a "build succeeded" message is the worst outcome, so say what was
      // built and why nothing ran.
      if (containerEl && ${jsFiles.length} > 0 && !containerEl.children.length && !containerEl.textContent.trim()) {
        var __diag = ${previewDiag};
        var __esc = function(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
        if (__diag.modules && __diag.modules.length) {
          var __rows = '';
          for (var __i = 0; __i < __diag.modules.length; __i++) {
            var __m = __diag.modules[__i];
            __rows += '<tr><td style="padding:4px 10px;color:#8fd6ff;font:12px ui-monospace,monospace;vertical-align:top">' + __esc(__m.label)
              + '</td><td style="padding:4px 10px;color:#cfd8dc;font:12px ui-monospace,monospace">' + __esc((__m.exports || []).join(', ') || '(no exports)') + '</td></tr>';
          }
          var __why = __diag.bundleFailed
            ? 'The generated code could not be bundled, so the preview could not execute it: ' + __esc(__diag.bundleFailed)
            : 'No module exports an entry point the preview can call (render / init / main / mount).';
          containerEl.innerHTML = '<div style="padding:18px;font:13px system-ui;color:#eceff1;background:#11151c;border:1px solid #263238;border-radius:8px;max-width:860px">'
            + '<div style="font-weight:700;margin-bottom:6px">📦 Built ' + __diag.modules.length + ' module(s) — nothing to auto-run</div>'
            + '<div style="color:#90a4ae;margin-bottom:10px;line-height:1.5">' + __why
            + ' The code is on the canvas and exportable — open a node to read it.</div>'
            + '<table style="border-collapse:collapse"><tbody>' + __rows + '</tbody></table></div>';
        }
      }
      if (containerEl && ${jsFiles.length} === 0 && !containerEl.children.length && !containerEl.textContent.trim()) {
        containerEl.innerHTML = '<div style="padding:48px 24px;text-align:center;color:#94a3b8;font-family:system-ui,sans-serif"><h2 style="color:#e2e8f0;margin:0 0 8px">${safeGoal}</h2><p style="margin:0 0 16px">This app\\'s interface is ready — generated code is below.</p><div style="font-size:12px;opacity:.7">Preview shell · VACA</div></div>';
      }
      console.log('✅ ${safeGoal} initialized successfully');
    } catch(e) {
      var loadingEl2 = document.getElementById('loading');
      if (loadingEl2) loadingEl2.innerHTML = '<div style="color:#ef4444;text-align:center">❌ Failed to initialize:<br><pre style="margin-top:8px;font-size:12px;color:#aaa">' + e.message + '</pre></div>';
      addError(e.message);
    }
  </script>
</body>
</html>`;
        return {
            fileName: 'index.html',
            language: 'html',
            code: html,
            nodeId: 'preview_gui_wrapper',
            nodeLabel: 'App Preview (Auto-generated)',
            dependencies: jsFiles.map(f => f.nodeLabel),
            exports: [],
            errors: [],
            validated: true,
        };
    }
    /**
     * Get the availability of sandbox tools for code validation.
     */
    getAvailability() {
        return this.sandbox.getAvailability();
    }
}
// ─── Preview JS assembly helpers ────────────────────────────────────────────
const PREFERRED_ENTRY_POINTS = ['init', 'main', 'run', 'render', 'start', 'createApp', 'setup', 'createUI'];
/**
 * Max simultaneous model calls for INDEPENDENT work (module generation and
 * per-file repair). DSpark serves concurrent completions in parallel rather
 * than queuing them (measured: 8.4s for one 220-token completion vs 9.4s for
 * two at once), so overlapping independent calls is close to free wall-clock.
 * Bounded so a wide graph can't open dozens of requests at once.
 */
const MAX_PARALLEL_MODEL_CALLS = Math.max(1, Number(process.env.VACA_MAX_PARALLEL_GENERATIONS || 4));
/**
 * Run `fn` over `items` with at most `limit` calls in flight, preserving input
 * order in the result array. Used to parallelise work that was serial only by
 * accident — repairing every failing file one after another — without opening
 * an unbounded number of simultaneous model requests.
 */
async function mapWithConcurrency(items, limit, fn) {
    const results = new Array(items.length);
    let cursor = 0;
    const worker = async () => {
        while (true) {
            const i = cursor++;
            if (i >= items.length)
                return;
            try {
                results[i] = { ok: true, value: await fn(items[i]) };
            }
            catch (reason) {
                results[i] = { ok: false, reason };
            }
        }
    };
    await Promise.all(Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, () => worker()));
    return results;
}
/**
 * Relaxed entry-point match: real generated modules are named `renderView`,
 * `initGame`, `startGame`, `setupBoard`, `mainLoop` — not the bare
 * `render`/`init`/`main` the exact list looks for. Requiring an EXACT name is
 * why a whole generated app could preview as a BLANK iframe while the build
 * reported success (every module was skipped: "no entry export (gameState)").
 *
 * A camelCase name that STARTS WITH a preferred root counts as an entry point.
 * Deliberately prefix-only, never "contains", so a data helper like
 * `searchAndFilter` can never be mistaken for an entry point and invoked with
 * the container (the crash the exact-match rule was originally added for).
 */
function looksLikeEntryName(name) {
    const lower = name.toLowerCase();
    return PREFERRED_ENTRY_POINTS.some(root => lower.startsWith(root.toLowerCase()));
}
/**
 * Candidate entry points for a module, in the order the preview should try
 * them: exact names, then relaxed camelCase matches, then PascalCase classes
 * (instantiated and called via render/mount/init). Names that no plausible
 * entry could use are omitted so the runtime driver never calls a data helper.
 */
function previewCandidateOrder(exportsList) {
    const list = Array.isArray(exportsList) ? exportsList : [];
    const exact = PREFERRED_ENTRY_POINTS.filter(n => list.includes(n));
    const relaxed = list.filter(n => !exact.includes(n) && looksLikeEntryName(n));
    const classes = list.filter(n => !exact.includes(n) && !relaxed.includes(n) && /^[A-Z][A-Za-z0-9_$]*$/.test(n));
    return [...exact, ...relaxed, ...classes];
}
function previewNamespace(label) {
    return label.replace(/[^a-zA-Z0-9_]/g, '_').replace(/^([0-9])/, '_$1');
}
/**
 * Bundle the project's TS/JS files with esbuild into a single browser-safe
 * IIFE so cross-module imports actually resolve inside the srcdoc preview
 * iframe. Each file is written to a temp dir mirroring its label-based path
 * (`<label-dir>/<fileName>` — the same shape the generated import statements
 * reference, e.g. `../core-engine/core-engine.ts`), a virtual entry imports
 * every file as a module namespace and calls the preferred entry exports
 * (render/init/main/…) with #app-container, and esbuild resolves and inlines
 * everything.
 *
 * Returns the bundled code, or null when bundling fails (caller falls back to
 * the legacy IIFE assembly). Exported for tests.
 */
export function bundlePreviewJs(jsFiles, opts) {
    if (jsFiles.length === 0)
        return null;
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-preview-'));
    try {
        // Mirror the on-disk layout the generated import statements assume.
        for (const f of jsFiles) {
            const dir = path.join(tmp, labelToFileName(f.nodeLabel));
            fs.mkdirSync(dir, { recursive: true });
            fs.writeFileSync(path.join(dir, f.fileName), f.code);
        }
        const entryPath = path.join(tmp, '_preview_entry.ts');
        const lines = [];
        for (const f of jsFiles) {
            lines.push(`import * as ${previewNamespace(f.nodeLabel)} from './${labelToFileName(f.nodeLabel)}/${f.fileName}';`);
        }
        // Module manifest: every generated module with its exports and the ordered
        // entry-point candidates the runtime driver below should try.
        lines.push('const __vacaModules = [');
        for (const f of jsFiles) {
            lines.push(`  { label: ${JSON.stringify(f.nodeLabel)}, file: ${JSON.stringify(f.fileName)}, ns: ${previewNamespace(f.nodeLabel)}, exports: ${JSON.stringify(f.exports || [])}, candidates: ${JSON.stringify(previewCandidateOrder(f.exports))} },`);
        }
        lines.push('];');
        // ── Runtime driver ──
        // Tries each module's candidates in order. A class is instantiated and its
        // render/mount/init called; a plain function is called with the container.
        // Every attempt is individually guarded, so one bad module can never blank
        // the whole preview. Purely runtime JS (no codegen interpolation).
        lines.push(`
const __vacaEl = document.getElementById('app-container');
const __vacaRan = [];
const __vacaIsClass = (fn) => { try { return /^class\\s/.test(Function.prototype.toString.call(fn)); } catch (e) { return false; } };
const __vacaMethods = ['render', 'mount', 'init', 'start', 'draw', 'setup'];
for (const mod of __vacaModules) {
  let done = false;
  for (const name of mod.candidates) {
    const fn = mod.ns ? mod.ns[name] : undefined;
    if (typeof fn !== 'function') continue;
    try {
      if (__vacaIsClass(fn)) {
        const inst = new fn();
        const m = __vacaMethods.find((k) => typeof inst[k] === 'function');
        if (!m) continue;
        inst[m](__vacaEl);
      } else {
        fn(__vacaEl);
      }
      __vacaRan.push(mod.label + '.' + name + '()');
      done = true;
      break;
    } catch (e) {
      console.error('[preview] ' + mod.label + '.' + name + '() failed:', e);
    }
  }
  if (!done) console.log('[preview] ' + mod.file + ': nothing auto-invoked');
}
console.log('[preview] entry calls: ' + (__vacaRan.length ? __vacaRan.join(', ') : '(none)'));

// ── Guaranteed fallback ──
// A blank iframe next to a "build succeeded" message is the worst outcome, so
// if nothing rendered, show WHAT was built (module -> exports) instead of a
// silent white box, and say plainly that no UI entry point was generated.
if (!__vacaEl) {
  console.error('[preview] #app-container missing');
} else if (__vacaEl.childNodes.length === 0 && !__vacaEl.textContent.trim()) {
  const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  let rows = '';
  for (const mod of __vacaModules) {
    rows += '<tr><td style="padding:4px 10px;color:#8fd6ff;font:12px ui-monospace,monospace;vertical-align:top">' + esc(mod.label) + '</td>'
         + '<td style="padding:4px 10px;color:#cfd8dc;font:12px ui-monospace,monospace">' + esc((mod.exports || []).join(', ') || '(no exports)') + '</td></tr>';
  }
  __vacaEl.innerHTML = '<div style="padding:18px;font:13px system-ui;color:#eceff1;background:#11151c;border:1px solid #263238;border-radius:8px">'
    + '<div style="font-weight:700;margin-bottom:6px">📦 Built ' + __vacaModules.length + ' module(s) — no UI entry point generated</div>'
    + '<div style="color:#90a4ae;margin-bottom:10px;line-height:1.5">These modules expose data and logic APIs, but none exports something the preview can auto-run (render / init / main / mount). The code itself is complete and exportable — open a node on the canvas to read it.</div>'
    + '<table style="border-collapse:collapse"><tbody>' + rows + '</tbody></table></div>';
}
`);
        fs.writeFileSync(entryPath, lines.join('\n'));
        const result = esbuildBuildSync({
            entryPoints: [entryPath],
            bundle: true,
            format: 'iife',
            target: 'es2017',
            write: false,
            logLevel: 'silent',
            loader: { '.ts': 'ts' },
        });
        return result.outputFiles[0].text;
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.warn('[preview] esbuild bundling failed, falling back to legacy IIFE assembly:', msg);
        // Hand the reason to the caller so the preview can SAY why it is empty
        // instead of rendering a silent blank box next to a "build succeeded".
        opts?.onError?.(msg);
        return null;
    }
    finally {
        fs.rmSync(tmp, { recursive: true, force: true });
    }
}
/**
 * Legacy preview JS assembly: wraps each file in an IIFE that attaches its
 * exports to a per-file namespace object. Import statements are elided by
 * `stripTypeScriptKeepExports`, so cross-module calls do NOT work here — this
 * is only the fallback when esbuild bundling fails. Exported for tests.
 */
export function assembleLegacyPreviewJs(jsFiles) {
    const jsSectionLines = [];
    const perFileScripts = [];
    const initSetupCalls = [];
    const namespaceDeclarations = [];
    const modules = [];
    for (const file of jsFiles) {
        const ns = previewNamespace(file.nodeLabel);
        // Use `var` not `const` — const declarations in one <script> block are NOT visible in other <script> blocks
        namespaceDeclarations.push(`var ${ns} = {};`);
        // Wrap code in an IIFE that assigns exports to the namespace
        // Escape backticks and `${` patterns in generated code so they don't break the outer template literal
        // Transpile TS to browser-safe JS first (keeps exports.* for the
        // IIFE namespace) — raw TS in the iframe throws SyntaxError.
        const rawCode = (file.language === 'typescript' || file.language === 'tsx')
            ? stripTypeScriptKeepExports(file.code)
            : file.code;
        const safeCode = rawCode.replace(/`/g, '\\`').replace(/\$\{/g, '\\${');
        const iife = `(function(exports) {\n${safeCode}\n})(typeof ${ns} !== 'undefined' ? ${ns} : {});`;
        jsSectionLines.push(`// ── ${file.fileName} ──`);
        jsSectionLines.push(iife);
        // One entry per FILE (not one giant blob): jsSectionLines is joined into a
        // single <script>, and a syntax error in ONE generated file makes the whole
        // block unparseable, so every other file's IIFE silently never runs. As
        // separate <script> blocks a broken file only costs itself.
        perFileScripts.push(`// ── ${file.fileName} ──\n${iife}`);
        modules.push({ label: file.nodeLabel, file: file.fileName, exports: file.exports || [] });
        // Detect entry point exports and call them. Uses the SAME relaxed matching
        // as the bundled path (renderView ~ render) so a real UI module is actually
        // driven; only candidates can ever be called, so a data helper like
        // searchAndFilter is still never invoked with the container (seq-12).
        const foundEntry = previewCandidateOrder(file.exports)[0];
        if (foundEntry) {
            initSetupCalls.push(`  try { ${ns}.${foundEntry}(document.getElementById('app-container')); } catch(e) { console.error('Error calling ${ns}.${foundEntry}:', e); }`);
        }
        else {
            // No plausible entry export — skip the call instead of invoking a data
            // function like searchAndFilter(container).
            console.log(`[preview-legacy] ${file.fileName}: no entry export (${(file.exports || []).slice(0, 4).join(', ')}) — skipped`);
        }
    }
    return {
        namespaceDeclarations: namespaceDeclarations.join(' '),
        jsSectionLines,
        perFileScripts,
        initSetupCalls,
        modules,
    };
}
