/**
 * verifiedGenerationCapture — closes the learning loop for BOTH pipelines.
 *
 * CANVAS path: FileGenerator.generateFiles (validated builds were thrown away
 * instead of becoming training data). This module appends per-file training
 * rows (same {instruction, input, output, source} JSONL format as
 * captured-verified.jsonl) for files that PASSED the full verification
 * pipeline: per-file sandbox validation AND/OR the live compile-check-retry
 * loop (tsc --noEmit, zero remaining failures).
 *
 * CHAT path: codePlanner.ts drops `_training.json` sidecars next to its
 * exports. captureVerifiedSidecar() folds those SIDECARS into the SAME
 * verified-generations.jsonl — it mirrors the tsc gate + quality filters of
 * scripts/capture-verified-pairs.py (so both capture routes share ONE loop),
 * and marks the sidecar `capturedAt` so the Python gate skips it (no
 * duplicate rows across captured-verified.jsonl and verified-generations.jsonl).
 *
 * Only verified code is learned from — the dataset never sees broken output.
 * Capture file is env-overridable (VACA_VERIFIED_CAPTURE_FILE) so tests can
 * use a temp file instead of the real dataset.
 */
import { readFileSync, appendFileSync, existsSync, mkdirSync, writeFileSync } from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
/** backend/src/training → project root. */
const PROJECT_ROOT = path.resolve(__dirname, '..', '..', '..');
export const VERIFIED_CAPTURE_FILE = process.env.VACA_VERIFIED_CAPTURE_FILE ||
    path.join(PROJECT_ROOT, 'training', 'dataset', 'verified-generations.jsonl');
const MIN_CODE_CHARS = 80;
/** Stub markers — same gate as scripts/capture-verified-pairs.py. */
const STUB_PATTERNS = [
    /\bnot implemented\b/i,
    /placeholder\s+for\b/i,
    /\bcoming soon\b/i,
    /\blorem ipsum\b/i,
    /\bunimplemented\b/i,
    /throw new Error\(['"]not/i,
    /TODO:\s*Implement/i,
];
function isStub(code) {
    return STUB_PATTERNS.some((re) => re.test(code));
}
/**
 * Detect a "shell" placeholder — the class of stub the stub-pattern gate misses.
 *
 * Live failure: the "Game State" module of a memory-card build was captured as
 * `export class GameState { state_and_events: any[]; gameData: string; ...
 * update(result: any) { this.gameData = JSON.stringify(...) }
 * getData(): any[] { return JSON.parse(this.gameData) } }` — an untyped
 * blob-holder that only round-trips state through JSON, with zero imports and
 * zero typed domain model. It has no TODO/"not implemented" marker, so it
 * passed the stub gate. Two tell-tale signals identify it:
 *
 *  1. untyped (`any`) fields + a JSON stringify/parse round-trip + no imports
 *     (a real module in a multi-file app imports its siblings or at least
 *     declares a typed model; a pure any+JSON clone is a shell).
 *  2. echoed sibling-module filename headers — the model listed the OTHER
 *     planned files as `// X.ts` comments before emitting a stub.
 */
function isShell(code) {
    const commentStripped = code
        .replace(/^\s*\/\/.*$/gm, '')
        .replace(/\/\*[\s\S]*?\*\//g, '');
    const hasAny = /\bany\b/.test(commentStripped);
    const hasJsonRoundTrip = /JSON\.stringify\s*\(/.test(commentStripped) && /JSON\.parse\s*\(/.test(commentStripped);
    const hasImport = /^\s*import\b/m.test(commentStripped) || /\brequire\s*\(/.test(commentStripped);
    if (hasAny && hasJsonRoundTrip && !hasImport)
        return true;
    // Echoed sibling filename headers: 2+ distinct `// X.ts` comments naming
    // different files (the model listed the plan instead of implementing one).
    const headerFiles = new Set();
    for (const line of code.split('\n')) {
        const m = line.match(/^\s*\/\/\s*([\w][\w\s\-]*\.(?:ts|tsx|js))\s*$/i);
        if (m)
            headerFiles.add(m[1].toLowerCase());
    }
    return headerFiles.size >= 2;
}
function isTsJs(f) {
    return f.language === 'typescript' || f.language === 'javascript';
}
/** Skip reasons — the conservative quality gate for what may enter the dataset. */
function skipReason(f, opts) {
    if (!f.nodeId || f.fileName.toLowerCase().endsWith('.html'))
        return 'wrapper-or-html';
    // Verified means: sandbox-validated AND no errors, OR compile-check-clean TS/JS.
    const verified = isTsJs(f) && opts.tsCompileClean ? true : f.validated && f.errors.length === 0;
    if (!verified)
        return 'not-verified';
    if (f.code.length < MIN_CODE_CHARS)
        return 'too-small';
    if (isStub(f.code))
        return 'stub';
    if (isShell(f.code))
        return 'shell';
    return null;
}
/**
 * Build one training row per node file, mirroring the captured-verified format:
 * the instruction embeds the project goal + planned file list so the model
 * learns to generate code conditioned on the multi-file context.
 */
export function buildVerifiedRows(project, files, opts = {}) {
    const master = project.nodes.find((n) => n.type === 'master');
    const goal = master?.data?.appGoal || project.name || 'Untitled';
    const purpose = master?.data?.appPurpose || '';
    const targetOS = project.targetOS || 'linux';
    const planned = files
        .filter((x) => x.nodeId && !x.fileName.toLowerCase().endsWith('.html'))
        .map((x) => `  - ${x.fileName} (${x.language}) — ${x.nodeLabel}`)
        .join('\n');
    const rows = [];
    for (const f of files) {
        if (skipReason(f, opts))
            continue;
        const node = project.nodes.find((n) => n.id === f.nodeId);
        const nodeType = node?.type || '';
        const description = (node?.data?.description || '').trim();
        const instruction = [
            `Project goal: ${goal}`,
            purpose ? `Project purpose: ${purpose}` : '',
            `Target OS: ${targetOS}`,
            '',
            'PLANNED FILES:',
            planned,
            '',
            opts.blueprintContext
                ? `BLUEPRINT CONSTRAINTS (MANDATORY):\n${opts.blueprintContext}\nTHIS FILE'S MODULE: "${f.nodeLabel}"`
                : '',
            `Generate the COMPLETE file '${f.fileName}' for the multi-file app above.`,
            `Node: ${f.nodeLabel}`,
            nodeType ? `Node type: ${nodeType}` : '',
            description ? `Purpose: ${description}` : '',
            `Language: ${f.language}`,
            'Write production-quality, working code. Honor the plan: import only from the planned files above. NO placeholders, NO stubs, NO TODO comments. Return only the code.',
        ]
            .filter((line) => line !== '')
            .join('\n');
        rows.push({
            instruction,
            input: '',
            output: f.code,
            source: `${opts.sourceTag || 'verified-generation'}:${project.name || 'untitled'}`,
        });
    }
    return rows;
}
/**
 * Load the set of already-captured (instruction, output) keys from a JSONL
 * capture file. Shared by the canvas path and the chat-path sidecar capture so
 * BOTH write into one file with one idempotency contract.
 */
function loadExistingKeys(filePath) {
    const existing = new Set();
    if (!existsSync(filePath))
        return existing;
    for (const line of readFileSync(filePath, 'utf-8').split('\n')) {
        const trimmed = line.trim();
        if (!trimmed)
            continue;
        try {
            const rec = JSON.parse(trimmed);
            existing.add(`${rec.instruction ?? ''}\u0000${rec.output ?? ''}`);
        }
        catch {
            /* skip malformed line */
        }
    }
    return existing;
}
/**
 * Append new verified rows to the capture file. Idempotent: rows whose
 * (instruction, output) pair already exists are skipped, so re-runs never
 * duplicate training data.
 */
export function captureVerifiedGeneration(project, files, opts = {}) {
    const rows = buildVerifiedRows(project, files, opts);
    const reasons = {};
    for (const f of files) {
        const reason = skipReason(f, opts);
        if (reason)
            reasons[reason] = (reasons[reason] || 0) + 1;
    }
    const existing = loadExistingKeys(VERIFIED_CAPTURE_FILE);
    const fresh = rows.filter((r) => !existing.has(`${r.instruction}\u0000${r.output}`));
    if (fresh.length === 0) {
        return { captured: 0, skipped: rows.length, filePath: VERIFIED_CAPTURE_FILE, reasons };
    }
    mkdirSync(path.dirname(VERIFIED_CAPTURE_FILE), { recursive: true });
    const lines = fresh.map((r) => JSON.stringify(r)).join('\n') + '\n';
    appendFileSync(VERIFIED_CAPTURE_FILE, lines, 'utf-8');
    return { captured: fresh.length, skipped: rows.length - fresh.length, filePath: VERIFIED_CAPTURE_FILE, reasons };
}
const SIDECAR_FILENAME = '_training.json';
/** Non-source files the tsc gate can't vouch for — mirror of the Python SKIP_RE. */
const SIDECAR_SKIP_RE = /(README|\.gitignore|package\.json|tsconfig|\.md$|\.html$|__init__\.py$|_training\.json$)/i;
/** JSX tags in a .ts file (TS1005 failure mode) — mirror of the Python JSX_RE. */
const JSX_RE = /<\/?[a-z][a-z0-9]*\s[^>]*>|<\/[a-z][a-z0-9]*\s*>/;
/** Markdown leaks that break tsc (TS1443/TS1160) — ``` fences and batched `---`
 * separators written into a source file. Mirror of the learning-engine gate. */
const MARKDOWN_FENCE_RE = /^\s*```/m;
const BATCH_SEPARATOR_RE = /^\s*---\s*$/m;
/** Prompt scaffolding echoed into a source file (e.g. "REAL FILE CONTENT"). */
const PROMPT_ARTIFACT_RE = /REAL FILE CONTENT|injected by the platform|generated for the "[^"]+" node|entry point for the node/i;
/** Prose lines that break tsc (TS1434/TS1435) — mirror of the Python PROSE_RE. */
const PROSE_RE = /^\s*(?:\*\*[^*]+\*\*|[-*]\s+[A-Za-z]|Note:|NOTE:|> |Explanation:|Here's|Below is|In this (?:solution|implementation|file|module|example)|This (?:code|file|module|implementation|class|function) (?:defines|implements|handles|provides|is|shows)|For (?:a|an) .* (?:game|app|application)|The .* (?:function|class|module|implementation))/;
/** Reject absolute paths and anything escaping the export dir — mirror is_safe_rel(). */
function isSafeRel(f) {
    return !!f && !path.isAbsolute(f) && !f.split('/').some((seg) => seg === '..');
}
/** Strip string literals so JSX-in-ts detection doesn't match strings — mirror has_jsx_in_ts(). */
function stripStringLiterals(code) {
    return code.replace(/(['"`])(?:\\.|(?!\1)[^\\])*\1/g, '');
}
function hasJsxInTs(code) {
    return JSX_RE.test(stripStringLiterals(code));
}
function hasProse(code) {
    for (const line of code.split('\n')) {
        const t = line.trim();
        if (!t)
            continue;
        if (PROSE_RE.test(line) && !/[;{}()=<>]/.test(t))
            return true;
    }
    return false;
}
/** Markdown fence, batched `---` separator, or prompt artifact leaked into a
 * source file. */
function hasMarkdownLeak(code) {
    return MARKDOWN_FENCE_RE.test(code) || BATCH_SEPARATOR_RE.test(code) || PROMPT_ARTIFACT_RE.test(code);
}
/** Accept an array OR a comma string for coreFeatures (direct API callers may send the latter). */
function coreFeaturesList(v) {
    if (typeof v === 'string')
        return v.split(',').map((s) => s.trim()).filter(Boolean);
    return Array.isArray(v) ? v.filter((s) => typeof s === 'string' && s.trim().length > 0).map((s) => s.trim()) : [];
}
/**
 * Build the per-file instruction from the sidecar — mirrors the Python
 * build_instruction(): request + understood intent + user answers + planned
 * file list, then "Generate the COMPLETE file 'X'" so cross-file import
 * targets are known.
 */
export function buildSidecarInstruction(sidecar, filePath, summary, language) {
    const request = sidecar.request || '';
    const intent = sidecar.intent || {};
    const answers = sidecar.answers || {};
    const questions = sidecar.questions || [];
    const planFiles = sidecar.planFiles || [];
    const lines = [`User request: ${request}`];
    const iv = [];
    if (intent.goal)
        iv.push(`Goal: ${String(intent.goal)}`);
    if (intent.targetUser)
        iv.push(`Target user: ${String(intent.targetUser)}`);
    const cf = coreFeaturesList(intent.coreFeatures);
    if (cf.length)
        iv.push(`Core features: ${cf.join(', ')}`);
    if (intent.uiStyle)
        iv.push(`UI style: ${String(intent.uiStyle)}`);
    if (intent.language)
        iv.push(`Language: ${String(intent.language)}`);
    if (iv.length)
        lines.push('UNDERSTOOD INTENT: ' + iv.join(' | '));
    if (answers && typeof answers === 'object') {
        const qmap = new Map(questions.map((q) => [q.key, q.question]));
        const ans = Object.entries(answers)
            .map(([k, v]) => `${qmap.get(k) || k} → ${v}`)
            .join('; ');
        if (ans)
            lines.push('USER ANSWERS: ' + ans);
    }
    if (planFiles.length) {
        lines.push('PLANNED FILES:');
        for (const pf of planFiles) {
            lines.push(`  - ${pf.path} (${pf.language || '?'}) — ${pf.summary || ''}`);
        }
    }
    lines.push('');
    lines.push(`Generate the COMPLETE file '${filePath}' for the multi-file app above.`);
    if (summary)
        lines.push(`Purpose: ${summary}`);
    lines.push(`Language: ${language}`);
    lines.push('Write production-quality, working code. Honor the plan: you may ONLY import ' +
        'members the other planned files declare (the PLANNED FILES above are the import ' +
        'targets). NO JSX in .ts files. NO placeholders, NO stubs, NO TODO comments. ' +
        'Return only the code — no markdown, no explanations.');
    return lines.join('\n');
}
/**
 * Run the tsc gate over the export's .ts/.tsx files (the same command the
 * Python gate runs). Resolves the number of `error TS` lines; null when tsc is
 * unavailable (callers must SKIP — unverified code never enters the dataset).
 */
function runTscGate(exportDir, tsFiles) {
    if (!tsFiles.length)
        return Promise.resolve(0);
    const tscBin = path.join(PROJECT_ROOT, 'node_modules', '.bin', 'tsc');
    if (!existsSync(tscBin))
        return Promise.resolve(null);
    const absPaths = tsFiles.map((f) => path.join(exportDir, f));
    return new Promise((resolve) => {
        const proc = spawn(tscBin, ['--noEmit', '--target', 'ES2020', '--module', 'ESNext', '--moduleResolution', 'bundler', '--skipLibCheck', ...absPaths]);
        let out = '';
        const killTimer = setTimeout(() => proc.kill('SIGKILL'), 60_000);
        proc.stdout.on('data', (d) => { out += String(d); });
        proc.stderr.on('data', (d) => { out += String(d); });
        proc.on('error', () => {
            clearTimeout(killTimer);
            resolve(null);
        });
        proc.on('close', () => {
            clearTimeout(killTimer);
            // TS5112 (config-present-with-explicit-files) is a harness artifact, never a code error.
            resolve(out.split('\n').filter((l) => l.includes('error TS') && !l.includes('TS5112')).length);
        });
    });
}
/**
 * Fold a chat-path `_training.json` sidecar into the SHARED
 * verified-generations.jsonl (the same loop as the canvas path).
 *
 * Gate (mirrors scripts/capture-verified-pairs.py): only .ts/.tsx source files
 * that pass tsc --noEmit with zero errors are captured; stubs, JSX-in-ts,
 * prose and tiny files are skipped. Idempotent twice over: the sidecar's
 * `capturedAt` stamp prevents re-processing, and the shared (instruction,
 * output) dedupe prevents rows already in the capture file from re-appearing.
 *
 * `tsCompileClean` bypasses the tsc spawn (used by tests / callers that just
 * proved the export compiles) — the sidecar is never marked captured on a
 * failed gate, so the Python gate can still retry it later.
 */
export async function captureVerifiedSidecar(exportDir, opts = {}) {
    const sidecarPath = path.join(exportDir, SIDECAR_FILENAME);
    if (!existsSync(sidecarPath)) {
        return { captured: 0, skipped: 0, filePath: VERIFIED_CAPTURE_FILE, reasons: { 'no-sidecar': 1 } };
    }
    let sidecar;
    try {
        sidecar = JSON.parse(readFileSync(sidecarPath, 'utf-8'));
    }
    catch {
        return { captured: 0, skipped: 0, filePath: VERIFIED_CAPTURE_FILE, reasons: { 'unreadable-sidecar': 1 } };
    }
    if (sidecar.capturedAt) {
        return { captured: 0, skipped: 1, filePath: VERIFIED_CAPTURE_FILE, reasons: { 'already-captured': 1 } };
    }
    const reasons = {};
    const rawFiles = sidecar.files || [];
    const safeFiles = rawFiles.filter(isSafeRel);
    if (rawFiles.length !== safeFiles.length)
        reasons['unsafe-path'] = rawFiles.length - safeFiles.length;
    const tsFiles = safeFiles.filter((f) => f.endsWith('.ts') || f.endsWith('.tsx'));
    if (!tsFiles.length) {
        reasons['no-ts'] = 1;
        return { captured: 0, skipped: 1, filePath: VERIFIED_CAPTURE_FILE, reasons };
    }
    // Verification gate — the export must compile cleanly (or the caller must
    // have just proved it). A failed/unavailable gate leaves the sidecar UNMARKED
    // so a later run (or the Python gate) can retry.
    if (!opts.tsCompileClean) {
        const errors = await runTscGate(exportDir, tsFiles);
        if (errors === null) {
            reasons['tsc-unavailable'] = 1;
            return { captured: 0, skipped: tsFiles.length, filePath: VERIFIED_CAPTURE_FILE, reasons };
        }
        if (errors > 0) {
            reasons['tsc-failed'] = errors;
            return { captured: 0, skipped: tsFiles.length, filePath: VERIFIED_CAPTURE_FILE, reasons };
        }
    }
    const planByPath = new Map((sidecar.planFiles || []).map((pf) => [pf.path, pf]));
    const libCtx = typeof sidecar.libraryContext === 'string' && sidecar.libraryContext.trim() ? sidecar.libraryContext : '';
    const rows = [];
    for (const f of safeFiles) {
        if (!f.endsWith('.ts') && !f.endsWith('.tsx'))
            continue;
        if (SIDECAR_SKIP_RE.test(f)) {
            reasons['non-source'] = (reasons['non-source'] || 0) + 1;
            continue;
        }
        let code;
        try {
            code = readFileSync(path.join(exportDir, f), 'utf-8');
        }
        catch {
            reasons['unreadable'] = (reasons['unreadable'] || 0) + 1;
            continue;
        }
        if (code.trim().length < MIN_CODE_CHARS) {
            reasons['tiny'] = (reasons['tiny'] || 0) + 1;
            continue;
        }
        if (isStub(code)) {
            reasons['stub'] = (reasons['stub'] || 0) + 1;
            continue;
        }
        if (isShell(code)) {
            reasons['shell'] = (reasons['shell'] || 0) + 1;
            continue;
        }
        if (hasJsxInTs(code)) {
            reasons['jsx-in-ts'] = (reasons['jsx-in-ts'] || 0) + 1;
            continue;
        }
        if (hasMarkdownLeak(code)) {
            reasons['markdown-leak'] = (reasons['markdown-leak'] || 0) + 1;
            continue;
        }
        if (hasProse(code)) {
            reasons['prose'] = (reasons['prose'] || 0) + 1;
            continue;
        }
        const pf = planByPath.get(f);
        const language = pf?.language || (typeof sidecar.intent?.language === 'string' ? sidecar.intent.language : 'typescript');
        rows.push({
            instruction: buildSidecarInstruction(sidecar, f, pf?.summary || '', language),
            input: libCtx,
            output: code,
            source: 'captured-verified',
        });
    }
    if (!rows.length) {
        reasons['no-usable-files'] = 1;
        return { captured: 0, skipped: tsFiles.length, filePath: VERIFIED_CAPTURE_FILE, reasons };
    }
    // Shared-file dedupe (same key + file as the canvas path).
    const existing = loadExistingKeys(VERIFIED_CAPTURE_FILE);
    const fresh = rows.filter((r) => !existing.has(`${r.instruction}\u0000${r.output}`));
    if (!fresh.length) {
        reasons['duplicate'] = rows.length;
        return { captured: 0, skipped: rows.length, filePath: VERIFIED_CAPTURE_FILE, reasons };
    }
    mkdirSync(path.dirname(VERIFIED_CAPTURE_FILE), { recursive: true });
    appendFileSync(VERIFIED_CAPTURE_FILE, fresh.map((r) => JSON.stringify(r)).join('\n') + '\n', 'utf-8');
    // Stamp the sidecar so scripts/capture-verified-pairs.py skips it (one loop).
    sidecar.status = 'captured';
    sidecar.capturedAt = new Date().toISOString();
    sidecar.capturedRows = fresh.length;
    try {
        writeFileSync(sidecarPath, JSON.stringify(sidecar, null, 2), 'utf-8');
    }
    catch {
        /* non-fatal — the rows are already captured */
    }
    return { captured: fresh.length, skipped: rows.length - fresh.length, filePath: VERIFIED_CAPTURE_FILE, reasons };
}
