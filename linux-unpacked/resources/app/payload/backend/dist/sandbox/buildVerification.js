/**
 * buildVerification — the ONE verification path shared by both generation
 * pipelines.
 *
 * VACA has two independent generation pipelines:
 *   - canvas: layers/fileGenerator.ts   (POST /api/generate/:id/files)
 *   - chat:   routes/codePlanner.ts     (POST /api/reason/write-code|interactive)
 *
 * Historically each carried its own copy of the verification gates, so their
 * standards could drift — the chat path once shipped Go builds with
 * `tsCompileClean:true` while 8/9 files failed, because tsc is blind to Go and
 * the chat path never ran the canvas's non-TS gate. Everything in this module
 * is the single implementation both pipelines now delegate to:
 *
 *   - runTscGate      — the TypeScript compiler gate (the compiler is the
 *                       authority). Temp-scaffolds every file, writes a
 *                       tsconfig + ambient globals, runs `tsc -p`, parses
 *                       per-file diagnostics.
 *   - runStubGate     — the deterministic stub/placeholder/prompt-artifact gate
 *                       (a body that compiles but never implements its contract
 *                       must not ship, and must not teach the pattern store).
 *   - deriveBuildVerdict — the single "is this build verified, and may it
 *                       teach the pattern store / be captured as training
 *                       data?" decision. Both pipelines read it, so neither
 *                       can claim a green build the other would reject.
 *
 * Non-TS languages (Go/Python/Rust/...) live in ./nonTsCompileGate.ts, which
 * this module re-exports for callers that want one import site.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import { TEST_GLOBALS_DTS } from './testGlobals.js';
import { isStubBody } from '../knowledge/qualityGate.js';
export { runNonTsProjectGates, sanitizeGoModuleName, resolveGateLanguage, GATE_LANGUAGES } from './nonTsCompileGate.js';
const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const TSC_BIN = path.join(PROJECT_ROOT, 'node_modules', 'typescript', 'bin', 'tsc');
/**
 * Run the TypeScript compiler gate over a set of in-memory files.
 *
 * Both pipelines call THIS function:
 *   - canvas maps GeneratedFile → {label: nodeLabel, relPath: scaffoldRelPath}
 *   - chat reads each written file from disk → {label: path, relPath: path}
 *
 * The scaffold lives in a temp dir and uses an explicit `files` list (not a
 * glob include), so ANY project layout compiles — including the flat single-app
 * chat layout, the `src/<label>/` canvas layout, and the `apps/**` + `bridge/**`
 * Tree Mode layout. `@types/react` (and friends) are mapped by absolute path so
 * JSX compiles cleanly no matter where the scaffold lives; node + test-runner
 * globals are declared ambiently, matching what the 7B model legitimately emits
 * (the gate reports STRUCTURAL errors, not missing-type-install noise).
 *
 * Status is honest about verification:
 *   - 'skipped'     : no .ts/.tsx files — nothing to compile
 *   - 'unavailable' : tsc could not run (missing binary / spawn error / killed)
 *   - 'clean' | 'errors': the compiler's verdict
 */
export async function runTscGate(entries, opts = {}) {
    // Compile checkable sources. Callers choose what to pass (chat passes
    // .ts/.tsx; canvas also passes .js), but the gate itself handles any of them.
    const tsEntries = entries.filter((e) => /\.(?:ts|tsx|js|jsx|mjs|cjs)$/i.test(e.relPath));
    if (!tsEntries.length) {
        return { status: 'skipped', errorsByLabel: new Map(), errors: [] };
    }
    const timeoutMs = opts.timeoutMs ?? 180_000;
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-tsgate-'));
    const cleanup = () => {
        try {
            fs.rmSync(tmpDir, { recursive: true, force: true });
        }
        catch { /* best-effort */ }
    };
    try {
        const relByLabel = new Map();
        const relPaths = [];
        for (const e of tsEntries) {
            // Path-traversal guard: a malicious relPath must never escape the scaffold.
            const rel = path.normalize(e.relPath).replace(/^([/\\])+/, '');
            if (rel.startsWith('..'))
                continue;
            const target = path.join(tmpDir, ...rel.split('/'));
            fs.mkdirSync(path.dirname(target), { recursive: true });
            fs.writeFileSync(target, e.code, 'utf-8');
            relByLabel.set(e.label, rel);
            relPaths.push(rel);
        }
        if (!relPaths.length) {
            return { status: 'skipped', errorsByLabel: new Map(), errors: [] };
        }
        const tsconfig = {
            compilerOptions: {
                target: 'ES2022',
                module: 'ESNext',
                moduleResolution: 'bundler',
                strict: false,
                esModuleInterop: true,
                skipLibCheck: true,
                noEmit: true,
                allowImportingTsExtensions: true,
                rootDir: '.',
                jsx: 'react-jsx',
                baseUrl: '.',
                paths: {
                    react: [path.join(PROJECT_ROOT, 'node_modules', '@types', 'react', 'index.d.ts')],
                    'react/jsx-runtime': [path.join(PROJECT_ROOT, 'node_modules', '@types', 'react', 'jsx-runtime.d.ts')],
                    'react/jsx-dev-runtime': [path.join(PROJECT_ROOT, 'node_modules', '@types', 'react', 'jsx-dev-runtime.d.ts')],
                    'react-dom': [path.join(PROJECT_ROOT, 'node_modules', '@types', 'react-dom', 'index.d.ts')],
                    'react-dom/client': [path.join(PROJECT_ROOT, 'node_modules', '@types', 'react-dom', 'client.d.ts')],
                },
            },
            files: [...relPaths, 'globals.d.ts'],
        };
        fs.writeFileSync(path.join(tmpDir, 'tsconfig.json'), JSON.stringify(tsconfig, null, 2));
        fs.writeFileSync(path.join(tmpDir, 'globals.d.ts'), GLOBALS_DTS, 'utf-8');
        const out = await new Promise((resolve) => {
            const proc = spawn('node', [TSC_BIN, '--noEmit', '--allowImportingTsExtensions', '-p', tmpDir], {
                cwd: tmpDir,
            });
            let text = '';
            let timedOut = false;
            const killTimer = setTimeout(() => { timedOut = true; proc.kill('SIGKILL'); }, timeoutMs);
            proc.stdout.on('data', (d) => { text += String(d); });
            proc.stderr.on('data', (d) => { text += String(d); });
            proc.on('error', (err) => {
                clearTimeout(killTimer);
                console.warn('[buildVerification] tsc gate unavailable:', err?.message || err);
                resolve({ text: '', unavailable: true });
            });
            proc.on('close', () => {
                clearTimeout(killTimer);
                if (timedOut) {
                    console.warn(`[buildVerification] tsc gate timed out after ${timeoutMs}ms — compile NOT verified`);
                    resolve({ text: '', unavailable: true });
                }
                else if (proc.signalCode !== null) {
                    console.warn(`[buildVerification] tsc gate killed by signal ${proc.signalCode} — compile NOT verified`);
                    resolve({ text: '', unavailable: true });
                }
                else {
                    resolve({ text, unavailable: false });
                }
            });
        });
        if (out.unavailable) {
            return { status: 'unavailable', errorsByLabel: new Map(), errors: [] };
        }
        const errorsByLabel = new Map();
        const errors = [];
        for (const line of out.text.split('\n')) {
            const m = line.match(/^(.+?)\((\d+),(\d+)\):\s+error\s+(TS\d+):\s+(.+)$/);
            if (!m)
                continue;
            // TS5112 (config-present-with-explicit-files) is a harness artifact, never a code error.
            if (m[4] === 'TS5112')
                continue;
            const filePath = m[1].replace(/\\/g, '/');
            let label;
            for (const [lbl, rel] of relByLabel) {
                if (filePath.endsWith(rel)) {
                    label = lbl;
                    break;
                }
            }
            errors.push(line);
            if (label) {
                const list = errorsByLabel.get(label) || [];
                list.push(`${m[4]}: ${m[5]} (line ${m[2]})`);
                errorsByLabel.set(label, list);
            }
        }
        return { status: errors.length ? 'errors' : 'clean', errorsByLabel, errors };
    }
    finally {
        cleanup();
    }
}
/**
 * Ambient declarations for the node + test-runner globals the model legitimately
 * emits. Shared by both pipelines (previously duplicated in fileGenerator's
 * scaffold and codePlanner's temp d.ts). The temp scaffold lives far from the
 * backend's node_modules, so without these tsc false-positives on TS2580
 * ('Cannot find name process') and TS2304/TS2593 on bare test/it/expect.
 */
export const GLOBALS_DTS = [
    'declare const process: {',
    '  env: Record<string, string | undefined>;',
    '  argv: string[];',
    '  cwd(): string;',
    '  exit(code?: number): never;',
    '  stdout: { write(s: string): void };',
    '  stderr: { write(s: string): void };',
    '  on(event: string, cb: (...args: any[]) => void): void;',
    '};',
    'interface ImportMeta {',
    '  env: { [key: string]: string | undefined; MODE: string; DEV: boolean; PROD: boolean } & Record<string, string | undefined>;',
    '  dirname: string;',
    '  filename: string;',
    '  url: string;',
    '}',
    'declare const require: any;',
    'declare const module: { exports: any };',
    'declare const __dirname: string;',
    'declare const __filename: string;',
    'declare function setTimeout(cb: () => void, ms: number): any;',
    'declare function setInterval(cb: () => void, ms: number): any;',
    'declare function clearTimeout(t: any): void;',
    'declare function clearInterval(t: any): void;',
    'declare const console: any;',
    'declare namespace NodeJS { export interface ProcessEnv { [key: string]: string | undefined } }',
    '',
    TEST_GLOBALS_DTS,
].join('\n');
// ─── Stub gate ───────────────────────────────────────────────────────────
// Stub detection only makes sense for SOURCE bodies. A README (markdown
// fences/`---`), a data JSON, or a plain-text file would false-positive the
// shared gate, so restrict it to code/HTML extensions.
export const STUB_CHECK_EXTS = /\.(?:ts|tsx|js|jsx|mjs|cjs|go|py|rs|java|cs|cpp|cc|c|h|hpp|swift|kt|php|rb|html?)$/i;
/**
 * The shared deterministic stub/placeholder gate: returns the paths whose body
 * compiles but never implements its contract (`// TODO: Implement`, echoed
 * `REAL FILE CONTENT`, comment-only files). Both pipelines call this.
 */
export function runStubGate(files) {
    return files
        .filter((f) => STUB_CHECK_EXTS.test(f.path) && isStubBody(f.content))
        .map((f) => f.path);
}
/**
 * The single build verdict both pipelines read. Priority of failures matches
 * the summary the user sees: compile errors > unverified compile > failed
 * language gate > stub body > failed behavioral smoke > no gate applied.
 */
export function deriveBuildVerdict(input) {
    const legacy = input.tscStatus === undefined;
    const tscErrors = input.tscErrors ?? 0;
    const renderFailed = input.renderSmoke?.status === 'failed';
    const cliFailed = input.cliSmoke?.status === 'failed';
    const failedGate = input.languageGates?.find((g) => !g.clean);
    let failure = null;
    if (tscErrors > 0 || input.tscStatus === 'errors') {
        failure = { kind: 'tsc', detail: `${tscErrors} compile error(s) remain` };
    }
    else if (failedGate) {
        const detail = (failedGate.errors?.[0] || '').replace(/\s+/g, ' ').slice(0, 140);
        failure = { kind: 'language', detail: `${failedGate.language} compile gate FAILED (${detail})` };
    }
    else if (input.stubFailures && input.stubFailures.length) {
        failure = { kind: 'stub', detail: `${input.stubFailures.length} stub/placeholder file(s) (${input.stubFailures[0]}) not implemented` };
    }
    else if (renderFailed || cliFailed) {
        const which = renderFailed ? 'render' : 'cli';
        const detail = (renderFailed ? input.renderSmoke?.detail : input.cliSmoke?.detail) || '';
        failure = { kind: 'smoke', detail: `${which} smoke check FAILED (${detail.slice(0, 140)})` };
    }
    const smokePassed = input.renderSmoke?.status === 'passed' || input.cliSmoke?.status === 'passed';
    const langPassed = !!(input.languageGates && input.languageGates.some((g) => g.clean));
    const tscClean = input.tscStatus === 'clean';
    const tscUnverified = input.tscStatus === 'unavailable';
    const compileVerified = tscClean || langPassed || smokePassed;
    if (!failure && tscUnverified) {
        failure = { kind: 'noGate', detail: 'compile NOT verified (tsc unavailable)' };
    }
    if (!failure && !legacy && (input.tscStatus === 'skipped') && !compileVerified) {
        failure = { kind: 'noGate', detail: 'compile NOT verified (no gate applied)' };
    }
    const anyFailed = !!failure;
    // Empty languageGates + skipped tsc + no smoke = nothing vouched. A verified
    // build must have at least one gate that actually PASSED (legacy callers keep
    // their pre-gate behavior and are exempt).
    const clean = !legacy && !anyFailed && compileVerified;
    const learnEligible = !anyFailed && compileVerified;
    return { compileVerified, clean, learnEligible, failure, legacy };
}
