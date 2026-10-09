/**
 * behavioralSmoke — the ONE behavioral smoke gate shared by both generation
 * pipelines (the last piece the chat/canvas unification left behind).
 *
 * tsc can only see types. The "compiles but doesn't work" class — an HTML app
 * that throws on click, a static board whose pieces never move, a CLI that
 * prints nothing, a file cut off mid-generation — is invisible to it. This
 * module runs the real behavioral probes and feeds a FAILED verdict into a
 * bounded LLM repair loop, so broken output is repaired instead of shipped.
 *
 * Historically this lived entirely in `routes/codePlanner.ts` (the CHAT path),
 * so the canvas path (`layers/fileGenerator.ts`) could only run the one-shot,
 * non-repairing TS browser engine and never repaired a behavioral failure. The
 * gates are pure (fs + spawn + injected LLM callback), so they belong in
 * `sandbox/` beside `buildVerification.ts` — the module BOTH pipelines already
 * delegate to. `codePlanner` now re-exports these for compatibility.
 *
 * Everything LLM-shaped is INJECTED (`repairCall`), never imported: the sandbox
 * layer must not depend on a routes module (that would be a cycle) and must
 * stay unit-testable without a model server.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { inlineExternalScriptRefs } from '../ai/guiShared.js';
import { runRuntimeSmokeTest } from './runtimeSmokeTest.js';
const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
/** Resolve a LLM-supplied relative path safely INSIDE the export dir. */
function safeJoin(exportDir, relPath) {
    const rel = path.normalize(relPath || 'file.txt').replace(/^(\.\.(\/|\\|$))+/, '');
    const full = path.resolve(exportDir, rel);
    return full.startsWith(exportDir + path.sep) ? full : path.join(exportDir, 'file.txt');
}
/** Normalize a file path for contract matching (strip ./, trailing /, ext). */
function normalizeContractPath(p) {
    return (p || '')
        .replace(/^\.\//, '')
        .replace(/\/+$/, '')
        .replace(/\.(ts|tsx|js|jsx|go|rs|py|java|rb|php|c|cpp|cs)$/i, '');
}
// ─── Render probe (HTML entries) ─────────────────────────────────────────
/**
 * Render smoke-test for generated HTML/GUI entries (behavioral + 3D gate).
 *
 * tsc can only see TypeScript — a single-file HTML app (vanilla JS + Three.js
 * via CDN) is invisible to it, so wrong CDN paths, undefined THREE, a broken
 * render loop, OR a page that crashes when the user actually clicks it all
 * pass the type gate. This spawns scripts/smoke-test-html.py (Playwright +
 * system Chrome, headless) to actually OPEN the file and report console/page
 * errors, WebGL canvas presence, the 3D-fallback banner, AND (behavioral mode)
 * new errors triggered by primary interactions (fill first input + Enter,
 * click primary control, click secondary control) plus blank-page detection.
 *
 * Best-effort by design: never blocks or fails generation — the verdict is
 * reported and logged. Status:
 *   'passed' | 'failed' | 'skipped' (no HTML) | 'unavailable' (no playwright/chrome)
 */
export function runRenderSmoke(exportDir, files, timeoutMs = 35_000) {
    const html = files.find(f => /\.html?$/i.test(f.path) && (f.content || '').trim().length > 0);
    if (!html)
        return Promise.resolve({ status: 'skipped', errors: [], detail: 'no HTML entry file' });
    const content = html.content || '';
    // Cost + relevance guard: headless Chrome costs ~8-10s, so only fire for
    // entries with something to BEHAVE — 3D/graphics markers (three.js/WebGL)
    // or interactive markers (inline script, event handlers, form controls).
    // A static info page with zero JS and zero controls is skipped.
    const is3D = /new\s+THREE\.|THREE\.[A-Z]|three(?:\.min)?\.js|from\s+['"]three['"]|webgl|getContext\s*\(\s*['"]webgl/i.test(content);
    const isInteractive = /<script|on(?:click|keydown|keyup|change|input|submit)\s*=|addEventListener|\b<(?:button|input|form|select|textarea)\b/i.test(content);
    if (!is3D && !isInteractive) {
        return Promise.resolve({ status: 'skipped', errors: [], detail: 'no interactive or 3D markers in HTML' });
    }
    const absPath = safeJoin(exportDir, html.path);
    if (!fs.existsSync(absPath))
        return Promise.resolve({ status: 'skipped', errors: [], detail: 'HTML file not on disk' });
    const script = path.join(PROJECT_ROOT, 'scripts', 'smoke-test-html.py');
    // Fallback behavioral gate: when the Python/Playwright script is unavailable
    // (missing, no playwright, crashed), run the SAME check through the TS browser
    // engine (sandbox/runtimeSmokeTest.ts — Playwright/system Chrome). Without
    // this, a build path cannot detect "compiles but crashes on click" at all in
    // an environment without the Python Playwright package.
    const tsFallback = async (reason) => {
        try {
            const res = await runRuntimeSmokeTest(files.map((f) => ({ fileName: f.path, code: f.content || '' })), { timeoutMs: Math.min(timeoutMs, 45_000) });
            if (!res.available) {
                return { status: 'unavailable', errors: [], detail: `${reason}; ts-engine: ${res.reason || 'unavailable'}` };
            }
            const failedChecks = res.checks.filter((c) => c.status === 'fail').map((c) => c.name);
            return {
                status: res.success ? 'passed' : 'failed',
                errors: res.consoleErrors.slice(0, 8),
                detail: `[fallback: ts-engine] ${failedChecks.length ? failedChecks.join(', ') : 'ok'}`,
            };
        }
        catch (err) {
            return { status: 'unavailable', errors: [], detail: `${reason}; ts-engine threw: ${err?.message || err}` };
        }
    };
    if (!fs.existsSync(script))
        return tsFallback('smoke-test-html.py missing');
    return new Promise((resolve) => {
        const proc = spawn('python3', [script, absPath, '--behavioral', '--wait', '4000', '--out', `${absPath}.smoke.png`], { stdio: ['ignore', 'pipe', 'pipe'] });
        let out = '';
        let timedOut = false;
        const killTimer = setTimeout(() => { timedOut = true; proc.kill('SIGKILL'); }, timeoutMs);
        proc.stdout.on('data', (d) => { out += String(d); });
        proc.stderr.on('data', (d) => { out += String(d); });
        proc.on('error', (err) => {
            clearTimeout(killTimer);
            console.warn('[behavioralSmoke] render smoke unavailable:', err?.message || err);
            void tsFallback(err?.message || 'spawn failed').then(resolve);
        });
        proc.on('close', () => {
            clearTimeout(killTimer);
            if (timedOut) {
                console.warn('[behavioralSmoke] render smoke timed out — HTML render NOT verified');
                void tsFallback('timeout').then(resolve);
                return;
            }
            try {
                const parsed = JSON.parse(out);
                // Infra failure (chrome/playwright missing, launch crash) is NOT a
                // model verdict — report 'unavailable' so the model isn't blamed.
                if (parsed.error) {
                    void tsFallback(String(parsed.error).slice(0, 160)).then(resolve);
                    return;
                }
                const behavioral = parsed.behavioral;
                const interactionErrors = Array.isArray(behavioral?.interactionErrors)
                    ? behavioral.interactionErrors
                    : [];
                // Playability probe verdict: a board-like page (>=8 clickable cells)
                // whose pieces can never move — no legal-move targets ever appear and
                // no destination click relocates anything. The "static board" class.
                const playability = behavioral?.playability;
                const boardDead = !!playability?.detected && playability.playable !== true;
                // Truncation verdict: the smoke script flags a file cut off mid-
                // generation (missing </html>/</body> or an unclosed <script>/<style>).
                // This is the gate's worst blind spot — Chrome silently swallows an
                // unclosed <script>, the app never runs, and the playability probe then
                // reports "no board" → the truncated file PASSES. Surface it as a hard
                // error so the repair loop fires with the real cause.
                const truncation = parsed.truncation;
                const truncatedHtml = !!truncation?.truncated;
                const truncationError = truncatedHtml
                    ? `TRUNCATION: ${truncation?.detail || 'file is INCOMPLETE — cut off mid-generation (missing closing tags). RE-GENERATE the COMPLETE file: every function, statement, and closing tag must be present.'}`
                    : '';
                const errors = [
                    ...(truncationError ? [truncationError] : []),
                    ...(parsed.pageErrors || []),
                    ...(parsed.consoleErrors || []),
                    ...interactionErrors,
                    ...(boardDead
                        ? [`static board: ${playability?.occupiedCells ?? '?'} piece(s) probed across the board, but pieces never move (no legal-move targets, no relocation)`]
                        : []),
                ];
                const passed = parsed.pass === true;
                let detail;
                if (truncatedHtml) {
                    detail = `truncated: ${truncation?.detail || 'file cut off mid-generation (missing closing tags)'}`;
                }
                else if (boardDead) {
                    detail = `static board (${playability?.occupiedCells ?? '?'} occupied cells, ${playability?.piecesTried ?? '?'} tried — pieces never move)`;
                }
                else if (behavioral && Array.isArray(behavioral.interactions)) {
                    const n = behavioral.interactions.length;
                    detail = interactionErrors.length
                        ? `${interactionErrors.length} interaction-triggered error(s): ${interactionErrors[0].slice(0, 120)}`
                        : `interactions=${n}, bodyText=${behavioral.bodyTextLength ?? '?'}`;
                }
                else if (parsed.fallbackVisible) {
                    detail = '3D fallback banner visible (CDN blocked?)';
                }
                else {
                    detail = `canvas=${parsed.canvas?.found}`;
                }
                resolve({ status: passed ? 'passed' : 'failed', errors: errors.slice(0, 8), detail });
            }
            catch {
                void tsFallback(`unparsable smoke output: ${String(out).slice(0, 160)}`).then(resolve);
            }
        });
    });
}
// ─── CLI probe (non-HTML entries) ────────────────────────────────────────
/**
 * Pick the runnable entry file of a generated non-HTML project (the file the
 * user would launch): prefers main/index/cli/app/server/start.* then falls
 * back to the first TS/JS file. Pure function — unit-testable.
 */
export function pickCliEntryFile(files) {
    const runnable = files.filter(f => /\.(?:ts|tsx|js|mjs|cjs)$/i.test(f.path));
    if (!runnable.length)
        return null;
    const order = ['main', 'index', 'cli', 'app', 'server', 'start'];
    for (const name of order) {
        const hit = runnable.find(f => {
            const base = f.path.split('/').pop() || '';
            return new RegExp(`^${name}\\.(?:ts|tsx|js|mjs|cjs)$`, 'i').test(base);
        });
        if (hit)
            return hit.path;
    }
    return runnable[0].path;
}
/**
 * Deterministic zero-LLM fix for the recurring "defines but never invokes"
 * CLI failure class: generated entries that define a module-scope `main`
 * (function or const) but never call it. tsc passes (the code compiles), the
 * CLI smoke gate flags a blank/stub CLI (every invocation prints nothing), and
 * LLM repair rounds repeatedly fail to add the missing call. Detects the
 * pattern and appends an invocation. Handles sync and async definitions.
 * Returns the fixed content, or null when there is nothing to fix.
 */
export function fixUninvokedEntryMain(content) {
    const src = content || '';
    if (!src.trim())
        return null;
    const funcDefRe = /(?:^|\n)\s*(?:export\s+)?(?:async\s+)?function\s+main\s*\(/;
    const constDefRe = /(?:^|\n)\s*(?:export\s+)?(?:const|let|var)\s+main\s*(?::[^=\n]*)?=\s*(?:async\s*)?(?:\(|function\s*\()/;
    const isFuncDef = funcDefRe.test(src);
    const isConstDef = constDefRe.test(src);
    if (!isFuncDef && !isConstDef)
        return null;
    // Count `main(` call sites, ignoring line comments. The `function main(`
    // declaration itself contributes exactly one match.
    let callCount = 0;
    for (const line of src.split('\n')) {
        const ci = line.indexOf('//');
        callCount += ((ci >= 0 ? line.slice(0, ci) : line).match(/\bmain\s*\(/g) || []).length;
    }
    const invoked = isFuncDef ? callCount > 1 : callCount > 0;
    if (invoked)
        return null;
    const isAsync = /(?:^|\n)\s*(?:export\s+)?async\s+function\s+main\s*\(/.test(src)
        || /(?:^|\n)\s*(?:export\s+)?(?:const|let|var)\s+main\s*(?::[^=\n]*)?=\s*async\s*\(/.test(src);
    const call = isAsync ? 'void main();' : 'main();';
    return `${src.replace(/\s+$/, '')}\n\n// Deterministic fix: the entry defines main() but never invokes it.\n${call}\n`;
}
/**
 * Deterministic zero-LLM fix for the second recurring CLI failure class: the
 * entry has a command dispatch (switch/if on the first arg) but no --help / -h
 * handling — every probe (--help, -h, bare run) hits the "unknown command"
 * path and exits non-zero with nothing on stdout, so the smoke gate reports a
 * blank/stub CLI even though main() IS invoked. Detects the pattern and
 * injects a help handler at the top of the entry function that prints usage
 * (with the commands extracted from the dispatch) to stdout and returns —
 * making all three probes exit 0 with output. Idempotent. Returns the fixed
 * content, or null when nothing to fix.
 */
export function addDeterministicHelpHandler(content) {
    const src = content || '';
    if (!src.trim())
        return null;
    if (src.includes('__vacaHelp'))
        return null; // already injected
    // Entry function: strictly prefer main (the true entry point — it parses
    // process.argv and delegates), fall back to run.
    const mainRe = /(?:^|\n)\s*(?:export\s+)?(?:async\s+)?function\s+main\s*\(/;
    const runRe = /(?:^|\n)\s*(?:export\s+)?(?:async\s+)?function\s+run\s*\(/;
    const m = mainRe.exec(src) ?? runRe.exec(src);
    if (!m)
        return null;
    const fnStart = m.index;
    // Must have a command dispatch somewhere.
    const caseCmds = [...src.matchAll(/\bcase\s+['"]([^'"]+)['"]\s*:/g)].map(x => x[1]);
    const ifDispatch = /\b(?:cmd|command|action|op)\s*(?:===|==)\s*['"]/.test(src)
        || /\bargs\[0\]\s*(?:===|==)\s*['"]/.test(src);
    if (!caseCmds.length && !ifDispatch)
        return null;
    // Must NOT already handle help in any form.
    if (/['"]--?help['"]|['"]-h['"]|['"]help['"]/i.test(src))
        return null;
    // Build the help block from the extracted commands.
    const cmds = caseCmds
        .filter(c => c && c !== 'default' && /^[\w.-]{1,24}$/.test(c))
        .slice(0, 12);
    const usageMatch = /\bUsage:\s*([^\n'"]{2,90})/.exec(src);
    const usage = usageMatch ? usageMatch[1].trim() : '<tool> <command> [args]';
    const blockLines = [
        `const __vacaHelp = process.argv.slice(2);`,
        `if (__vacaHelp.length === 0 || __vacaHelp[0] === '--help' || __vacaHelp[0] === '-h' || __vacaHelp[0] === 'help') {`,
        `  console.log('Usage: ${usage}');`,
    ];
    if (cmds.length) {
        blockLines.push(`  console.log('');`);
        blockLines.push(`  console.log('Commands:');`);
        for (const c of cmds)
            blockLines.push(`  console.log('  ${c}');`);
    }
    blockLines.push(`  return;`);
    blockLines.push(`}`);
    // Find the body-open brace after the entry function signature.
    const closeParen = src.indexOf(')', fnStart);
    const braceIdx = closeParen >= 0 ? src.indexOf('{', closeParen) : -1;
    if (braceIdx < 0)
        return null;
    const lineStart = src.lastIndexOf('\n', fnStart) + 1;
    const fnLine = src.slice(lineStart, src.indexOf('\n', fnStart) < 0 ? src.length : src.indexOf('\n', fnStart));
    const indent = (fnLine.match(/^\s*/) || [''])[0];
    const bodyIndent = indent + '  ';
    const block = blockLines.map(l => bodyIndent + l).join('\n');
    return `${src.slice(0, braceIdx + 1)}\n${block}\n${src.slice(braceIdx + 1)}`;
}
/**
 * Run every deterministic zero-LLM CLI fix in order (main invocation, then
 * help handler). Returns the possibly-changed content plus which fixes fired.
 */
export function applyDeterministicCliFixes(content) {
    const applied = [];
    let c = content || '';
    const main = fixUninvokedEntryMain(c);
    if (main !== null) {
        c = main;
        applied.push('main-invocation');
    }
    const help = addDeterministicHelpHandler(c);
    if (help !== null) {
        c = help;
        applied.push('help-handler');
    }
    return { content: c, applied };
}
/**
 * CLI behavioral gate for non-HTML (terminal/script) apps. tsc can only see
 * types — a CLI that imports a type-only member as a value (erased at runtime),
 * references an undefined symbol at module scope, or is a stub body
 * (loadHabits = () => []) passes the type gate but crashes or prints NOTHING
 * when executed. This spawns scripts/smoke-test-cli.py which runs the entry
 * under tsx with --help / -h and reports the verdict + captured errors.
 *
 * Status: 'passed' | 'failed' | 'skipped' (no runnable entry) | 'unavailable'
 * (tsx/python missing — infra, never the model's fault).
 */
export function runCliSmoke(exportDir, files, timeoutMs = 45_000) {
    const entry = pickCliEntryFile(files);
    if (!entry)
        return Promise.resolve({ status: 'skipped', errors: [], detail: 'no runnable entry file' });
    const absPath = safeJoin(exportDir, entry);
    if (!fs.existsSync(absPath))
        return Promise.resolve({ status: 'skipped', errors: [], detail: `entry not on disk: ${entry}` });
    const script = path.join(PROJECT_ROOT, 'scripts', 'smoke-test-cli.py');
    if (!fs.existsSync(script))
        return Promise.resolve({ status: 'unavailable', errors: [], detail: 'smoke-test-cli.py missing' });
    return new Promise((resolve) => {
        const proc = spawn('python3', [script, exportDir, '--entry', entry], { stdio: ['ignore', 'pipe', 'pipe'] });
        let out = '';
        let timedOut = false;
        const killTimer = setTimeout(() => { timedOut = true; proc.kill('SIGKILL'); }, timeoutMs);
        proc.stdout.on('data', (d) => { out += String(d); });
        proc.stderr.on('data', (d) => { out += String(d); });
        proc.on('error', (err) => {
            clearTimeout(killTimer);
            console.warn('[behavioralSmoke] cli smoke unavailable:', err?.message || err);
            resolve({ status: 'unavailable', errors: [], detail: err?.message || 'spawn failed' });
        });
        proc.on('close', () => {
            clearTimeout(killTimer);
            if (timedOut) {
                console.warn('[behavioralSmoke] cli smoke timed out — CLI run NOT verified');
                resolve({ status: 'unavailable', errors: [], detail: 'timeout' });
                return;
            }
            try {
                const parsed = JSON.parse(out);
                if (parsed.error) {
                    resolve({ status: 'unavailable', errors: [], detail: String(parsed.error).slice(0, 160) });
                    return;
                }
                const status = parsed.status === 'passed' ? 'passed' : parsed.status === 'failed' ? 'failed' : 'skipped';
                const errors = Array.isArray(parsed.errors) ? parsed.errors.slice(0, 8) : [];
                resolve({ status, errors, detail: String(parsed.detail || '').slice(0, 240) });
            }
            catch {
                resolve({ status: 'unavailable', errors: [], detail: `unparsable cli smoke output: ${String(out).slice(0, 160)}` });
            }
        });
    });
}
// ─── Deterministic HTML runtime fixer ────────────────────────────────────
/**
 * Deterministic zero-LLM fixes for the three mechanical JS runtime bug classes
 * observed in generated board games. Runs BEFORE the LLM repair call; the smoke
 * re-run is the arbiter, so a fix that doesn't help is simply not kept.
 */
export function applyDeterministicHtmlRuntimeFixes(html) {
    if (!html)
        return html;
    let out = html;
    // A) dataset-string vs number comparison — the FIRST-CLICK crash class.
    // Generated boards store coordinates as `dataset.row = row` (string) and
    // later look them up with `el.dataset.row === row` against a NUMBER. Strict
    // equality between "0" and 0 is false → find() returns undefined → the next
    // `.querySelector` crashes on the very first user click (observed live in
    // the checkers build: `Cannot read properties of undefined`). Fix: coerce
    // the compared VALUE to a string with String(...) — true for both String(0)
    // and String("0"), and it needs no element capture (so `e.target.dataset.row`
    // stays intact). Only comparisons against a coordinate name fire.
    const coordNames = ['row', 'col', 'i', 'j', 'r', 'c', 'idx', 'index', 'x', 'y'];
    for (const n of coordNames) {
        const re = new RegExp(`(\\.dataset\\.)([A-Za-z_$][\\w$]*)(\\s*[!=]==?\\s*)((?:[A-Za-z_$][\\w$]*\\.)*)(${n})(\\b)`, 'g');
        out = out.replace(re, (_m, dot, prop, op, prefix, ident, boundary) => `${dot}${prop}${op}String(${prefix}${ident})${boundary}`);
    }
    // B) use-after-null timing — `X = null;` then a LATER line reads `X.`/`X[`.
    // The read is guaranteed to crash; the null assignment is re-ordered to
    // AFTER the read. Conservative: only when the read is within the next 3
    // lines, nothing reassigns X in between, and the null is a bare `= null`.
    const lines = out.split('\n');
    for (let i = 0; i < lines.length; i++) {
        const m = lines[i].match(/^(\s*)([A-Za-z_$][\w$]*)\s*=\s*null;\s*$/);
        if (!m)
            continue;
        const name = m[2];
        for (let j = i + 1; j <= Math.min(i + 3, lines.length - 1); j++) {
            if (new RegExp(`\\b${name}\\s*=`).test(lines[j]))
                break; // reassigned → unsafe
            if (new RegExp(`\\b${name}(?:\\.|\\[)`).test(lines[j])) {
                lines.splice(i, 1);
                i--;
                break;
            }
        }
    }
    out = lines.join('\n');
    // C) unguarded computed lookup — `arr.find(EXPR).prop` where EXPR looks up
    // a grid coordinate (dataset.row/col, or a capture midpoint like
    // `(a + b) / 2`) that may not exist → find() returns undefined → `.prop`
    // throws. Two guards, by usage:
    //  - METHOD CALL: optional chaining (returns undefined, which callers test).
    //  - PROPERTY ACCESS: `|| {}` (optional chaining on the left of an
    //    assignment is a SyntaxError).
    const isCoordLookup = (findArg) => /\.dataset\.(?:row|col|i|j|x|y|r|c)/.test(findArg)
        || /\/\s*2|\+|\-|Math\./.test(findArg);
    out = out.replace(/([A-Za-z_$][\w$]*)\.find\((.*?)\)\.([A-Za-z_$][\w$]*)(?=\()/g, (_m, arr, findArg, prop) => isCoordLookup(findArg)
        ? `${arr}.find(${findArg})?.${prop}`
        : _m);
    out = out.replace(/([A-Za-z_$][\w$]*)\.find\((.*?)\)\.([A-Za-z_$][\w$]*)(?!\()/g, (_m, arr, findArg, prop) => isCoordLookup(findArg)
        ? `(${arr}.find(${findArg}) || {}).${prop}`
        : _m);
    return out === html ? html : out;
}
/**
 * Structural HTML truncation check: flags a document cut off mid-generation
 * (missing </html>/</body> or an unclosed <script>/<style>). Mirrors the source
 * check in scripts/smoke-test-html.py so the repair loop can ALSO detect it
 * without Chrome (e.g. when the smoke gate is skipped or unavailable). Returns
 * a human-readable note, or '' when the document looks structurally complete.
 * A bare fragment with no `<html>` at all is legit — only an OPENED-but-never-
 * closed document is flagged.
 */
export function detectHtmlTruncation(content) {
    if (!content)
        return '';
    const lower = content.toLowerCase();
    const htmlOpen = /<html\b/.test(lower);
    const htmlClosed = /<\/html\s*>/.test(lower);
    const bodyOpen = /<body\b/.test(lower);
    const bodyClosed = /<\/body\s*>/.test(lower);
    const scriptOpen = (lower.match(/<script\b/g) || []).length;
    const scriptClosed = (lower.match(/<\/script\s*>/g) || []).length;
    const styleOpen = (lower.match(/<style\b/g) || []).length;
    const styleClosed = (lower.match(/<\/style\s*>/g) || []).length;
    const problems = [];
    if (htmlOpen && !htmlClosed)
        problems.push('missing closing </html>');
    if (bodyOpen && !bodyClosed)
        problems.push('missing closing </body>');
    if (scriptOpen > scriptClosed)
        problems.push(`${scriptOpen - scriptClosed} unclosed <script> block(s)`);
    if (styleOpen > styleClosed)
        problems.push(`${styleOpen - styleClosed} unclosed <style> block(s)`);
    return problems.length
        ? `file is INCOMPLETE — ${problems.join('; ')} (the generation hit the output token limit and was cut off before its natural end; the app never ran)`
        : '';
}
// ─── Repair prompts ──────────────────────────────────────────────────────
/**
 * Line-numbered, error-focused view of a file for a repair prompt: the header
 * plus a window around each error line, with omitted regions marked. Bounded
 * so a large file can't blow the prompt budget.
 */
export function buildErrorFocusedNumberedSource(content, errors, opts) {
    const maxChars = opts?.maxChars ?? 8000;
    const window = opts?.window ?? 12;
    const headerLines = opts?.headerLines ?? 30;
    const numberize = (lines) => lines.map((l, i) => `${String(i + 1).padStart(4)} | ${l}`).join('\n');
    if (content.length <= maxChars)
        return { source: numberize(content.split('\n')), truncated: false };
    const lines = content.split('\n');
    const keep = new Set();
    // Always keep the header (imports/exports region) — drift lives there.
    for (let i = 0; i < Math.min(headerLines, lines.length); i++)
        keep.add(i);
    // Keep a window around every error line. Two locator formats are parsed:
    // tsc's `file(line,col)` and Chrome console's `file:///...html:line:col`.
    for (const e of errors) {
        const tscLoc = e.match(/\((\d+),(\d+)\)/);
        const chromeLoc = !tscLoc ? e.match(/:\s*(\d+):(\d+)\b/) : null;
        const lineNo = tscLoc ? Number(tscLoc[1]) : chromeLoc ? Number(chromeLoc[1]) : null;
        if (!lineNo)
            continue;
        for (let i = Math.max(0, lineNo - 1 - window); i < Math.min(lines.length, lineNo + window); i++)
            keep.add(i);
    }
    const kept = [...keep].sort((a, b) => a - b);
    const out = [];
    let prev = -1;
    for (const idx of kept) {
        if (prev >= 0 && idx > prev + 1)
            out.push(`… (${idx - prev - 1} line(s) omitted) …`);
        out.push(`${String(idx + 1).padStart(4)} | ${lines[idx]}`);
        prev = idx;
    }
    if (prev >= 0 && prev < lines.length - 1) {
        out.push(`… (${lines.length - 1 - prev} line(s) omitted) …`);
    }
    return { source: out.join('\n'), truncated: true };
}
export function buildRenderSmokeRepairPrompt(request, file, currentContent, smokeErrors, detail) {
    const { source: numbered, truncated: contentTruncated } = buildErrorFocusedNumberedSource(currentContent, smokeErrors);
    const truncated = contentTruncated
        ? `\n\nNOTE: the file is large — the numbered view shows the header plus a window around each error line (omitted regions are marked with ellipses). Every error below points at a visible line — fix it exactly there.`
        : '';
    const truncationNote = smokeErrors.some(e => /^TRUNCATION:/i.test(e))
        ? `\n⚠️ TRUNCATION: this file was cut off MID-GENERATION — it is INCOMPLETE and does not end at its natural end (missing closing tags / an unclosed <script> block). The page never ran because the browser swallowed the incomplete script. RE-GENERATE the COMPLETE file: every function, every statement, and every closing tag (</script>, </body>, </html>) must be present. Do NOT leave the code mid-expression — finish the file to its natural end.`
        : '';
    return `User request: ${request}\n\nThe generated HTML app ${file.path} LOADS but FAILS behavioral checks in headless Chrome — it is the "compiles but doesn't work" class: an error, a crash on interaction, or a blank page. Rewrite the ENTIRE file so it both renders AND behaves.${truncationNote}\n\n━━━ SMOKE-GATE FAILURE (what Chrome saw) ━━━\n${detail || '(no detail)'}${smokeErrors.length ? `\n${smokeErrors.join('\n')}` : ''}\n\n━━━ CURRENT CONTENT (LINE-NUMBERED) ━━━\n${numbered}${truncated}\n\n━━━ TASK ━━━\nProduce a COMPLETE rewritten ${file.path} that: (1) loads with ZERO console/page errors, (2) actually WORKS when used — the primary action (form submit, button click, search, add, send) must do something visible with no thrown exception, and (3) is not a blank page (real rendered content). Common root causes to check: a function referenced by an inline onclick/onkeydown that is never defined, calling a DOM method on null (element missing because the JS runs before the DOM or the id is wrong), an unguarded undefined variable, a missing closing tag that breaks the whole script section, or an event listener attached to an element that doesn't exist. If the failure says \"static board\" — the page renders a board of clickable pieces but pieces can NEVER move — the fix is to implement the real interaction: clicking a piece must reveal legal-move targets (or otherwise indicate possible moves) and clicking a destination must actually relocate the piece / change the game state.\n\n  Return ONLY the file's raw HTML — no markdown fences, no JSON wrapper, no commentary.`;
}
/**
 * Completion repair prompt for a TRUNCATED HTML file. Unlike the full-file
 * regeneration prompt, this asks the model to CONTINUE from the exact cut
 * point and return ONLY the missing tail. Why: the observed failure mode is a
 * generation that stops early at ~1.5-2.5k tokens, so a "re-generate the
 * COMPLETE file" repair hits the SAME early stop and re-emits a truncated
 * file. A tail completion only needs a few hundred tokens.
 */
export function buildTruncationCompletionPrompt(request, file, currentContent, detail) {
    const tail = currentContent.slice(-1200);
    return `User request: ${request}\n\nYour generated HTML app ${file.path} was CUT OFF mid-generation — the file is INCOMPLETE (${detail}). The page never ran because the browser swallowed the incomplete script.

━━━ WHERE THE FILE STOPS (the last part of the current content) ━━━
\`\`\`
${tail}
\`\`\`

━━━ TASK ━━━
CONTINUE from EXACTLY where the file above stops — do NOT repeat or rewrite any of the code above. Write ONLY the missing continuation that:
(1) finishes the interrupted expression/statement/function exactly where it was cut (the file may end mid-expression like \`cell.classList.\` or mid-line),
(2) closes every open construct — braces, brackets, quotes, template literals — for the code that was cut,
(3) completes any functions that were cut off and any remaining logic the app still needs to work,
(4) ends the file at its natural end with the closing tags: </script></body></html> (plus </style> if a style block is still open).

Return ONLY the continuation text — start exactly where the file stopped, no markdown fences, no JSON wrapper, no commentary. Do NOT regenerate the whole file — just the missing tail.`;
}
/**
 * Repair prompt for the CLI behavioral gate (non-HTML apps). The generated
 * program passed tsc but crashed or produced no output when actually executed.
 */
export function buildCliSmokeRepairPrompt(request, file, currentContent, smokeErrors, detail) {
    const { source: numbered, truncated: contentTruncated } = buildErrorFocusedNumberedSource(currentContent, smokeErrors);
    const truncated = contentTruncated
        ? `\n\nNOTE: the file is large — the numbered view shows the header plus a window around each error line (omitted regions are marked with ellipses). Every error below points at a visible line — fix it exactly there.`
        : '';
    return `User request: ${request}\n\nThe generated CLI app ${file.path} COMPILES but FAILS when actually executed — it is the "compiles but doesn't work" class for terminal apps: it crashes at startup, or runs and prints NOTHING (a stub). Rewrite the ENTIRE file so the program actually runs and does the job the request describes.\n\n━━━ CLI SMOKE-GATE FAILURE (what happened when it was executed) ━━━\n${detail || '(no detail)'}${smokeErrors.length ? `\n${smokeErrors.join('\n')}` : ''}\n\n━━━ CURRENT CONTENT (LINE-NUMBERED) ━━━\n${numbered}${truncated}\n\n━━━ TASK ━━━\nProduce a COMPLETE rewritten ${file.path} that when executed: (1) starts with ZERO thrown errors, (2) handles its CLI arguments / reads its input, (3) produces REAL output — it must print the results of the user's request, never exit silently. Common root causes to check: importing a TYPE-ONLY member (interface/type/class as a value) from a sibling file — types are erased at runtime, so import only real values or use \"import type\"; referencing an undefined symbol; a stub body that returns an empty array / does nothing; unguarded null/undefined dereference. If another generated file must export a runtime value this file imports, keep the import AND make sure the symbol is actually exported there, or adjust the import to what the other file really exports.\n\n  Return ONLY the file's raw code — no markdown fences, no JSON wrapper, no commentary.`;
}
// ─── Scripted CLI game probe (tic-tac-toe) ───────────────────────────────
/**
 * A tic-tac-toe CLI we can drive deterministically. Detected from the request
 * or the generated source (the game name, or a 3×3 board with a win-check +
 * the X/O marks + an input call). Pure — unit-testable.
 */
export function looksLikeTicTacToe(request, files) {
    const blob = `${request || ''}\n${files.map((f) => f.content || '').join('\n')}`;
    if (/tic[\s-]?tac[\s-]?toe/i.test(blob))
        return true;
    return /checkWin|isWinner|hasWon|winner|isDraw|isFull/i.test(blob)
        && /['"][XO]['"]/.test(blob)
        && /nextInt|readLine|Scanner|input\s*\(|prompt/i.test(blob)
        && /\bboard\b/i.test(blob);
}
/** stdin that makes the FIRST mover take the top row (0,0)(0,1)(0,2). */
export function ticTacToeWinningInput(oneBased, rowCol) {
    if (rowCol)
        return ['0 0', '1 0', '0 1', '1 1', '0 2'].join('\n') + '\n';
    const seq = oneBased ? [1, 4, 2, 5, 3] : [0, 3, 1, 4, 2];
    return seq.join('\n') + '\n';
}
/** Parse the mark the program names as the winner, or null when it names none. */
export function parseAnnouncedWinner(out) {
    const m = out.match(/(?:player\s*)?([XO])\s*(?:wins|won|is the winner|win[s]?\b)/i)
        || out.match(/winner[:\s]*([XO])\b/i);
    return m ? m[1].toUpperCase() : null;
}
/** Parse the FIRST player named in a prompt (the first mover), or null. */
export function parseFirstPlayer(out) {
    const m = out.match(/player\s*([XO])\b/i) || out.match(/['"]([XO])['"]\s*,?\s*(?:enter|move|turn)/i);
    return m ? m[1].toUpperCase() : null;
}
/** Spawn a process with a fixed stdin and bounded timeout. */
function spawnWithInput(cmd, args, opts, input, timeoutMs) {
    return new Promise((resolve) => {
        let proc;
        try {
            // detached makes the child a process-group leader so a runaway game can
            // be killed as a GROUP. Runners like `tsx` spawn a grandchild (the real
            // node process) that inherits the stdout pipe — killing only the wrapper
            // leaves the grandchild alive holding the pipe, so the parent's 'close'
            // event NEVER fires and the probe hangs forever (observed live: the
            // backend health went dark during a tic-tac-toe smoke run).
            proc = spawn(cmd, args, { cwd: opts.cwd, stdio: ['pipe', 'pipe', 'pipe'], detached: true });
        }
        catch (err) {
            resolve({ exit: null, out: '', err: String(err?.message || err), timedOut: false });
            return;
        }
        let out = '';
        let err = '';
        let timedOut = false;
        let settled = false;
        const finish = (exit) => {
            if (settled)
                return;
            settled = true;
            clearTimeout(killTimer);
            resolve({ exit, out, err, timedOut });
        };
        // Bound the captured output: a generated game can loop forever printing the
        // board (e.g. it never consumes our scripted input), and unbounded string
        // accumulation threw V8's "Invalid string length" and crashed the backend.
        const MAX_OUT = 256 * 1024;
        const killGroup = () => {
            try {
                if (proc.pid)
                    process.kill(-proc.pid, 'SIGKILL');
            }
            catch { /* group may be gone */ }
            try {
                proc.kill('SIGKILL');
            }
            catch { /* noop */ }
        };
        const killTimer = setTimeout(() => { timedOut = true; killGroup(); finish(null); }, timeoutMs);
        const onChunk = (chunk, buf) => {
            const s = String(chunk);
            if (buf === 'out') {
                if (out.length < MAX_OUT)
                    out += s.slice(0, MAX_OUT - out.length);
            }
            else if (err.length < MAX_OUT) {
                err += s.slice(0, MAX_OUT - err.length);
            }
            if (!settled && out.length + err.length >= MAX_OUT) {
                // Runaway output — stop it rather than let it grow without bound.
                killGroup();
                finish(null);
            }
        };
        try {
            proc.stdout?.on('data', (d) => onChunk(d, 'out'));
            proc.stderr?.on('data', (d) => onChunk(d, 'err'));
        }
        catch { /* listener attach best-effort */ }
        proc.on('error', (e) => { err += String(e?.message || e); finish(null); });
        proc.on('close', (code) => finish(code));
        // 'exit' fires even when a grandchild keeps the stdio pipe open (so 'close'
        // never does). A short grace lets any final buffered stdout arrive first.
        proc.on('exit', (code) => { setTimeout(() => finish(code), 150); });
        try {
            proc.stdin?.write(input);
            proc.stdin?.end();
        }
        catch { /* stdin may be closed */ }
    });
}
/**
 * Scripted behavioral smoke for a tic-tac-toe CLI: compile/run the program,
 * feed a deterministic winning sequence, and assert the ANNOUNCED winner matches
 * the player who actually won. This is the one CLI failure class a generic
 * "does it run" probe cannot see — a game that runs perfectly but announces the
 * wrong result (observed live: an X win printed "Player O wins!" because
 * `currentPlayer` was toggled before the win message).
 *
 * Runner: TS/JS via tsx, or Java via `javac` + `java`. Other languages skip.
 */
export async function runScriptedTicTacToe(exportDir, files, opts = {}) {
    const timeoutMs = opts.timeoutMs ?? 25_000;
    const skip = (detail) => ({ verdict: { status: 'skipped', errors: [], detail }, entryPath: null });
    if (!looksLikeTicTacToe(opts.request || '', files))
        return skip('not a tic-tac-toe app');
    const oneBased = /\b1\s*(?:-|to)\s*9\b|\[1-9\]/.test(files.map((f) => f.content || '').join('\n'));
    const rowCol = /\bnextInt\s*\(\s*\)[\s\S]{0,240}?\bnextInt\s*\(\s*\)/.test(files.map((f) => f.content || '').join('\n'))
        && /row/i.test(files.map((f) => f.content || '').join('\n'))
        && /col/i.test(files.map((f) => f.content || '').join('\n'));
    const input = ticTacToeWinningInput(oneBased, rowCol);
    // ── Java runner ──
    const javaFiles = files.filter((f) => /\.java$/i.test(f.path));
    if (javaFiles.length) {
        const mainFile = javaFiles.find((f) => /static\s+void\s+main\s*\(/.test(f.content || ''));
        if (!mainFile) {
            // A Java tic-tac-toe with NO `main` cannot be launched at all — that is a
            // failure, not something to skip: the generic CLI probe only understands
            // TS/JS, so skipping here would let an unrunnable Java CLI ship un-verified
            // (observed live: the plan exported `playGame` but the model never wrote a
            // `main`, and the whole behavioral gate reported `skipped`). Target the
            // likeliest entry file so the repair loop can ADD the entry point.
            const entryGuess = javaFiles.find(f => /main|game|app|cli/i.test((f.path.split('/').pop() || '').replace(/\.java$/i, '')))
                || javaFiles.find(f => /playGame|startGame|gameLoop|static\s+void\s+main/i.test(f.content || ''))
                || javaFiles[0];
            return {
                verdict: {
                    status: 'failed',
                    errors: ['java tic-tac-toe has NO `public static void main(String[] args)` entry point — the program cannot be launched'],
                    detail: 'tic-tac-toe: no main class',
                },
                entryPath: entryGuess.path,
            };
        }
        const mainClass = (mainFile.path.split('/').pop() || '').replace(/\.java$/i, '');
        const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-ttt-java-'));
        try {
            for (const f of javaFiles) {
                const target = safeJoin(tmp, f.path);
                fs.mkdirSync(path.dirname(target), { recursive: true });
                fs.writeFileSync(target, f.content || '', 'utf-8');
            }
            const classes = path.join(tmp, '__classes__');
            fs.mkdirSync(classes, { recursive: true });
            const compile = await spawnWithInput('javac', ['-d', classes, ...javaFiles.map((f) => safeJoin(tmp, f.path))], { cwd: tmp }, '', 60_000);
            if (compile.exit !== 0) {
                return { verdict: { status: 'failed', errors: [`javac failed: ${(compile.err || compile.out).slice(0, 300)}`], detail: 'scripted tic-tac-toe: compile failed' }, entryPath: mainFile.path };
            }
            const run = await spawnWithInput('java', ['-cp', classes, mainClass], { cwd: tmp }, input, timeoutMs);
            return { verdict: judgeTicTacToe(run), entryPath: mainFile.path };
        }
        catch (err) {
            return { verdict: { status: 'unavailable', errors: [], detail: String(err?.message || err) }, entryPath: null };
        }
        finally {
            try {
                fs.rmSync(tmp, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    // ── TS/JS runner (tsx) ──
    const entry = pickCliEntryFile(files);
    if (!entry)
        return skip('tic-tac-toe: no runnable entry');
    const tsx = path.join(PROJECT_ROOT, 'node_modules', '.bin', 'tsx');
    if (!fs.existsSync(tsx))
        return { verdict: { status: 'unavailable', errors: [], detail: 'tsx binary missing' }, entryPath: entry };
    try {
        const run = await spawnWithInput(tsx, [safeJoin(exportDir, entry)], { cwd: exportDir }, input, timeoutMs);
        return { verdict: judgeTicTacToe(run), entryPath: entry };
    }
    catch (err) {
        return { verdict: { status: 'unavailable', errors: [], detail: String(err?.message || err) }, entryPath: entry };
    }
}
/** Turn a scripted run into a verdict: the announced winner must be the mover. */
function judgeTicTacToe(run) {
    const blob = `${run.out}\n${run.err}`;
    if (run.timedOut)
        return { status: 'failed', errors: ['scripted game hung (did not terminate on the winning sequence)'], detail: 'tic-tac-toe: timed out' };
    // Runaway output is a failure in its own right (a game that never consumes
    // input and loops forever printing the board).
    if (run.out.length >= 256 * 1024 || run.err.length >= 256 * 1024) {
        return { status: 'failed', errors: ['scripted game produced runaway output (never terminated on the winning input)'], detail: 'tic-tac-toe: runaway output' };
    }
    if (/Exception in thread|Error:|SyntaxError/.test(blob)) {
        return { status: 'failed', errors: [blob.split('\n').find((l) => /Exception|Error/.test(l))?.slice(0, 200) || 'runtime error'], detail: 'tic-tac-toe: crashed while playing' };
    }
    const expected = parseFirstPlayer(run.out) || 'X';
    const announced = parseAnnouncedWinner(run.out);
    if (!announced) {
        return { status: 'failed', errors: ['scripted winning game ended WITHOUT announcing a winner'], detail: 'tic-tac-toe: no winner announced' };
    }
    if (announced !== expected) {
        return { status: 'failed', errors: [`scripted game: ${expected} completed the top row, but the program announced "Player ${announced} wins!" (wrong winner)`], detail: `tic-tac-toe: announced ${announced}, expected ${expected}` };
    }
    return { status: 'passed', errors: [], detail: `tic-tac-toe: ${announced} won as scripted` };
}
/**
 * Run the render gate (HTML entries) and, when no HTML entry exists, the CLI
 * gate — each with a bounded repair loop (up to 2 rounds per gate). `canRepair`
 * / `consumeRepair` hook into the caller's shared LLM-repair budget so the
 * smoke phase can never starve (or be starved by) other phases; `tag` prefixes
 * logs so callers are distinguishable. Mutates `files` in place when a repair
 * rewrites the failing entry, and writes the repair to disk so the next probe
 * sees it.
 */
export async function runBehavioralSmokeGates(opts) {
    const { request, files, contractFiles, exportDir, timeoutMs, tag } = opts;
    const canRepair = opts.canRepair;
    const consumeRepair = opts.consumeRepair;
    const renderProbe = opts.renderProbe ?? runRenderSmoke;
    const cliProbe = opts.cliProbe ?? runCliSmoke;
    const repairCall = opts.repairCall;
    const emit = opts.onProgress ?? (() => { });
    // Truncation blind-spot guard: a file cut off mid-generation (output token
    // cap) can PASS the smoke gate — Chrome silently swallows an unclosed
    // <script>, the app never runs, and the playability probe then reports "no
    // board" → pass. A structurally truncated file is a hard failure regardless
    // of what Chrome happened to report, so the guard wraps EVERY probe result.
    const applyTruncationGuard = async (verdict) => {
        if (verdict.status !== 'passed')
            return verdict;
        const html = files.find(f => /\.html?$/i.test(f.path) && (f.content || '').trim().length > 0);
        if (!html)
            return verdict;
        const truncNote = detectHtmlTruncation(html.content);
        if (!truncNote)
            return verdict;
        console.warn(`[behavioralSmoke] ${tag} render smoke: PASSED but source is TRUNCATED (${truncNote}) — forcing repair`);
        return {
            status: 'failed',
            errors: [`TRUNCATION: ${truncNote}`],
            detail: `truncated: ${truncNote}`,
        };
    };
    let renderSmoke = await applyTruncationGuard(await renderProbe(exportDir, files));
    const MAX_SMOKE_REPAIR_ROUNDS = 2;
    let smokeRounds = 0;
    while (renderSmoke.status === 'failed' && smokeRounds < MAX_SMOKE_REPAIR_ROUNDS && canRepair()) {
        smokeRounds += 1;
        const htmlEntry = files.find(f => /\.html?$/i.test(f.path) && (f.content || '').trim().length > 0);
        if (!htmlEntry)
            break;
        const planned = contractFiles.find(t => normalizeContractPath(t.path) === normalizeContractPath(htmlEntry.path))
            || { path: htmlEntry.path, summary: 'HTML app', language: 'html' };
        consumeRepair();
        console.warn(`[behavioralSmoke] ${tag} render smoke: FAILED (${renderSmoke.detail}) — behavioral repair round ${smokeRounds}`);
        emit({ phase: 'validating', percent: 90 + smokeRounds * 3, message: `Fixing ${renderSmoke.errors.length} runtime error(s) in ${htmlEntry.path}…` });
        // Deterministic runtime fixes first (zero LLM, idempotent — the smoke re-run
        // below is the arbiter).
        const detFixed = applyDeterministicHtmlRuntimeFixes(htmlEntry.content);
        if (detFixed !== htmlEntry.content) {
            htmlEntry.content = detFixed;
            inlineExternalScriptRefs(files);
            fs.writeFileSync(safeJoin(exportDir, htmlEntry.path), htmlEntry.content, 'utf-8');
            console.log(`[behavioralSmoke] ${tag} render smoke: applied deterministic HTML runtime fixes`);
            const reSmoke = await applyTruncationGuard(await renderProbe(exportDir, files));
            if (reSmoke.status !== 'failed') {
                renderSmoke = reSmoke;
                continue;
            }
        }
        // Truncation → COMPLETION repair (not regeneration): the model stopped
        // early, so asking it to re-generate the whole file hits the SAME early
        // stop. Ask for ONLY the missing tail and append it.
        const isTruncation = renderSmoke.errors.some(e => /^TRUNCATION:/i.test(e))
            || renderSmoke.detail.startsWith('truncated:');
        const prompt = isTruncation
            ? buildTruncationCompletionPrompt(request, planned, htmlEntry.content, renderSmoke.detail)
            : buildRenderSmokeRepairPrompt(request, planned, htmlEntry.content, renderSmoke.errors, renderSmoke.detail);
        const content = await repairCall(prompt);
        let candidate = '';
        if (content) {
            const looksLikeFullDoc = /^\s*(<!doctype|<html)/i.test(content);
            candidate = isTruncation && !looksLikeFullDoc
                ? htmlEntry.content + content
                : content;
        }
        if (!candidate || candidate === htmlEntry.content) {
            console.warn(`[behavioralSmoke] ${tag} render smoke: repair round ${smokeRounds} produced no usable rewrite — stopping`);
            break;
        }
        htmlEntry.content = candidate;
        // Re-apply the self-containment pass: a repair that introduces external
        // <script src> refs must still yield a single-file preview-ready entry.
        inlineExternalScriptRefs(files);
        fs.writeFileSync(safeJoin(exportDir, htmlEntry.path), htmlEntry.content, 'utf-8');
        renderSmoke = await applyTruncationGuard(await renderProbe(exportDir, files));
    }
    if (renderSmoke.status !== 'skipped') {
        console.log(`[behavioralSmoke] ${tag} render smoke: ${renderSmoke.status} (${renderSmoke.detail})${smokeRounds ? ` after ${smokeRounds} repair round(s)` : ''}`);
    }
    // CLI gate: for non-HTML projects, execute the entry under tsx and feed a
    // FAILED verdict into the same bounded repair loop — the "compiles but
    // doesn't work" class for CLIs. Deterministic zero-LLM pre-fix first.
    if (renderSmoke.status === 'skipped') {
        const entryPath = pickCliEntryFile(files);
        const entry = entryPath ? files.find(f => f.path === entryPath) : undefined;
        if (entry) {
            const r = applyDeterministicCliFixes(entry.content || '');
            if (r.content !== entry.content) {
                entry.content = r.content;
                fs.writeFileSync(safeJoin(exportDir, entry.path), r.content, 'utf-8');
                console.log(`[behavioralSmoke] ${tag} cli smoke: deterministic fix(es) applied to ${entry.path}: ${r.applied.join(', ')}`);
            }
        }
    }
    // For a tic-tac-toe CLI, prefer the SCRIPTED game probe (plays a deterministic
    // win and asserts the announced winner) over the generic "does it run" probe.
    // Falls back to the generic probe when the app isn't a scriptable game.
    let cliEntryOverride = null;
    let cliSmoke;
    // `scriptedActive` records that the SCRIPTED probe produced this verdict, so
    // the repair loop below re-runs the SAME probe. Falling back to the generic
    // cliProbe after a scripted FAIL is a FALSE PASS: the generic probe only
    // understands TS/JS, so for a Java game it returns `skipped` and silently
    // clears a real behavioral failure (observed live: a Java crash was repaired
    // then reported "✅ Wrote 1 file successfully").
    let scriptedActive = false;
    if (renderSmoke.status !== 'skipped') {
        cliSmoke = { status: 'skipped', errors: [], detail: 'HTML entry present — render gate used' };
    }
    else {
        let scripted;
        try {
            scripted = await (opts.gameProbe ?? runScriptedTicTacToe)(exportDir, files, { request, timeoutMs });
        }
        catch (err) {
            // A probe failure must never break the gate — treat it as not-run.
            console.warn('[behavioralSmoke] scripted game probe threw (non-fatal):', err?.message || err);
            scripted = { verdict: { status: 'skipped', errors: [], detail: 'game probe threw' }, entryPath: null };
        }
        if (scripted.verdict.status === 'skipped') {
            cliSmoke = await cliProbe(exportDir, files);
        }
        else {
            cliSmoke = scripted.verdict;
            cliEntryOverride = scripted.entryPath;
            scriptedActive = true;
        }
    }
    const MAX_CLI_SMOKE_REPAIR_ROUNDS = 2;
    let cliSmokeRounds = 0;
    while (cliSmoke.status === 'failed' && cliSmokeRounds < MAX_CLI_SMOKE_REPAIR_ROUNDS && canRepair()) {
        cliSmokeRounds += 1;
        const entryPath = cliEntryOverride || pickCliEntryFile(files);
        const entry = entryPath ? files.find(f => f.path === entryPath) : undefined;
        if (!entry)
            break;
        const planned = contractFiles.find(t => normalizeContractPath(t.path) === normalizeContractPath(entry.path))
            || { path: entry.path, summary: 'CLI app', language: 'typescript' };
        consumeRepair();
        console.warn(`[behavioralSmoke] ${tag} cli smoke: FAILED (${cliSmoke.detail}) — behavioral repair round ${cliSmokeRounds}`);
        emit({ phase: 'validating', percent: 90 + cliSmokeRounds * 3, message: `Fixing ${cliSmoke.errors.length} runtime error(s) in ${entry.path}…` });
        // The Java "no main entry point" case needs its own instruction: the model
        // must ADD the launcher, not rewrite the game logic.
        const prompt = /no main class/i.test(cliSmoke.detail)
            ? `User request: ${request}\n\nThe generated Java app ${entry.path} has NO entry point — there is no \`public static void main(String[] args)\` anywhere in the project, so the program cannot be launched at all.\n\n━━━ CURRENT CONTENT OF ${entry.path} (LINE-NUMBERED) ━━━\n${entry.content || ''}\n\n━━━ TASK ━━━\nAdd a \`public static void main(String[] args)\` entry point to ${entry.path} that STARTS the game and plays a full game to completion using standard input (so it can be run non-interactively). Keep the existing game logic intact; only add the missing launcher (and fix any compile error the launcher reveals).\n\n  Return ONLY the file's raw Java code — no markdown fences, no JSON wrapper, no commentary.`
            : buildCliSmokeRepairPrompt(request, planned, entry.content || '', cliSmoke.errors, cliSmoke.detail);
        const content = await repairCall(prompt);
        if (!content || content === entry.content) {
            console.warn(`[behavioralSmoke] ${tag} cli smoke: repair round ${cliSmokeRounds} produced no usable rewrite — stopping`);
            break;
        }
        entry.content = content;
        fs.writeFileSync(safeJoin(exportDir, entry.path), content, 'utf-8');
        // Re-apply the deterministic CLI fixes in case the LLM rewrite dropped them.
        const refixed = applyDeterministicCliFixes(entry.content || '');
        if (refixed.content !== entry.content) {
            entry.content = refixed.content;
            fs.writeFileSync(safeJoin(exportDir, entry.path), refixed.content, 'utf-8');
        }
        // Re-run the SAME probe that produced the failure — NOT a cheaper fallback.
        if (scriptedActive) {
            try {
                const re = await (opts.gameProbe ?? runScriptedTicTacToe)(exportDir, files, { request, timeoutMs });
                cliSmoke = re.verdict;
                cliEntryOverride = re.entryPath ?? cliEntryOverride;
                if (re.verdict.status === 'skipped') {
                    // A scripted probe that can no longer recognize the app is a signal,
                    // not a pass — keep the previous failure so the build stays flagged.
                    console.warn(`[behavioralSmoke] ${tag} cliProbeNeverReplacesScripted: scripted re-probe skipped (${re.verdict.detail})`);
                    cliSmoke = { status: 'failed', errors: cliSmoke.errors, detail: cliSmoke.detail };
                    break;
                }
            }
            catch (err) {
                console.warn('[behavioralSmoke] scripted re-probe threw (non-fatal):', err?.message || err);
                cliSmoke = { status: 'failed', errors: cliSmoke.errors, detail: cliSmoke.detail };
                break;
            }
        }
        else {
            cliSmoke = await cliProbe(exportDir, files);
        }
    }
    if (cliSmoke.status !== 'skipped') {
        console.log(`[behavioralSmoke] ${tag} cli smoke: ${cliSmoke.status} (${cliSmoke.detail})${cliSmokeRounds ? ` after ${cliSmokeRounds} repair round(s)` : ''}`);
    }
    return { renderSmoke, cliSmoke };
}
/**
 * Stage a file set into a throwaway temp dir and run the shared behavioral
 * smoke gate against it — the CANVAS path's entry point (the chat path already
 * has its own export dir on disk). `writeBack` maps a repaired file path back
 * onto the caller's file objects; the callback runs for every file whose
 * content the gate changed.
 *
 * Returns the two verdicts (both `skipped`/`unavailable` when nothing ran) and
 * the paths that were rewritten. The temp dir is always removed.
 */
export async function runStagedBehavioralSmoke(opts) {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-smoke-'));
    try {
        for (const f of opts.files) {
            const target = safeJoin(tmpDir, f.path);
            fs.mkdirSync(path.dirname(target), { recursive: true });
            fs.writeFileSync(target, f.content, 'utf-8');
        }
        const before = new Map(opts.files.map((f) => [f.path, f.content]));
        const budget = opts.maxRepairRounds ?? 2;
        let used = 0;
        const { renderSmoke, cliSmoke } = await runBehavioralSmokeGates({
            request: opts.request,
            files: opts.files,
            contractFiles: opts.contractFiles,
            exportDir: tmpDir,
            timeoutMs: opts.timeoutMs,
            tag: opts.tag,
            canRepair: () => used < budget,
            consumeRepair: () => { used += 1; },
            repairCall: opts.repairCall,
            onProgress: opts.onProgress,
        });
        const repairedPaths = opts.files.filter((f) => before.get(f.path) !== f.content).map((f) => f.path);
        return { renderSmoke, cliSmoke, repairedPaths, exportDir: tmpDir };
    }
    finally {
        try {
            fs.rmSync(tmpDir, { recursive: true, force: true });
        }
        catch { /* best-effort */ }
    }
}
