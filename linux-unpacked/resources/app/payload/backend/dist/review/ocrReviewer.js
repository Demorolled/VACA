/**
 * ocrReviewer — adapter that runs the real OpenCodeReview CLI (`ocr`)
 * against locally/remotely configured LLMs and normalizes its JSON report
 * into VACA's internal CodeReviewResult shape.
 *
 * The `ocr` binary is the Alibaba OpenCodeReview tool (see
 * /home/final-flash1/Desktop/open-code-review-main). It is agentic: each file
 * gets a PLAN_TASK pre-pass, an agentic MAIN_TASK loop (code_comment /
 * task_done tools), batch DEDUP_TASK, and a PROJECT_SUMMARY_TASK. Because the
 * agent loop requires an LLM that supports function calling, the default local
 * model is an Ollama qwen2.5-coder build (plain instruct GGUFs without tool
 * templates are rejected with "does not support tools").
 *
 * Configuration (env vars, all optional):
 *   OCR_MODEL            model to scan with (default: gpt-oss:20b)
 *   OCR_BASE_URL         OpenAI-compatible endpoint (default: ollama /v1)
 *   OCR_PROVIDER         custom provider name in ocr's config (default: vaca-local)
 *   OCR_API_KEY          api key sent to the provider (default: "local")
 *   OCR_TIMEOUT_MIN      per-file agent timeout in minutes (default: 10)
 *   OCR_TOTAL_TIMEOUT_MS overall scan timeout (default: 5 min)
 */
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, writeFile, rm, mkdir, readFile, copyFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { homedir } from 'node:os';
const execFileAsync = promisify(execFile);
// gpt-oss:20b is the first locally-hosted model verified to emit structured
// tool calls (the agentic ocr loop requires them). The qwen2.5-coder builds
// only emit tool-shaped text, so they cannot complete a scan.
const DEFAULT_MODEL = 'gpt-oss:20b';
const DEFAULT_BASE_URL = process.env.OLLAMA_BASE_URL || 'http://192.168.1.234:11434/v1';
const DEFAULT_PROVIDER = 'vaca-local';
const DEFAULT_TIMEOUT_MIN = 10;
// Keep the overall cap modest so a misconfigured model fails fast and the
// route can fall back to the in-house reviewer instead of blocking for minutes.
const DEFAULT_TOTAL_TIMEOUT_MS = 5 * 60 * 1000;
// Overridable so tests (or containers) never touch the real user config.
const OCR_CONFIG_PATH = process.env.OCR_CONFIG_PATH || join(homedir(), '.opencodereview', 'config.json');
// ─── Mapping (pure, unit-testable) ─────────────────────────────────────────
const SEVERITY_MAP = {
    critical: 'critical',
    blocker: 'critical',
    high: 'high',
    medium: 'medium',
    moderate: 'medium',
    low: 'low',
    minor: 'low',
    info: 'info',
    nit: 'info',
};
const CATEGORY_MAP = {
    bug: 'bug',
    correctness: 'bug',
    security: 'security',
    performance: 'performance',
    maintainability: 'maintainability',
    test: 'best-practice',
    style: 'style',
    documentation: 'documentation',
};
/** Normalize an ocr severity string into the internal enum. */
export function mapOcrSeverity(severity) {
    if (!severity)
        return 'medium';
    const key = severity.trim().toLowerCase();
    return SEVERITY_MAP[key] ?? 'medium';
}
/** Normalize an ocr category string into the internal enum. */
export function mapOcrCategory(category) {
    if (!category)
        return 'best-practice';
    const key = category.trim().toLowerCase();
    return CATEGORY_MAP[key] ?? 'best-practice';
}
/** Convert a raw ocr comment into the internal ReviewComment shape. */
export function toReviewComment(raw) {
    return {
        path: raw.path ?? '',
        content: raw.content ?? '',
        severity: mapOcrSeverity(raw.severity),
        category: mapOcrCategory(raw.category),
        startLine: raw.start_line ?? 0,
        endLine: raw.end_line ?? 0,
        suggestionCode: raw.suggestion_code || undefined,
        existingCode: raw.existing_code || undefined,
    };
}
/**
 * True when an ocr payload reports that nothing was scanned (the CLI's
 * "skipped" status), which callers must treat as a failure, not success.
 */
export function isOcrSkipped(raw) {
    const out = (raw ?? {});
    return out.status === 'skipped';
}
/**
 * Validate a repo-relative file path before writing it to the temp dir.
 * Returns the normalized path, or null when it would escape the temp dir
 * (absolute paths, drive letters, or `..` segments).
 */
export function sanitizeRelPath(fileName) {
    const norm = fileName.replace(/\\/g, '/').replace(/^\.\//, '');
    if (norm.startsWith('/') || /^[a-zA-Z]:\//.test(norm))
        return null;
    if (norm.split('/').some((p) => p === '..'))
        return null;
    if (norm.length === 0 || norm === '.')
        return null;
    return norm;
}
/** Normalize a full `ocr scan --format json` stdout payload. */
export function normalizeOcrOutput(raw) {
    const out = (raw ?? {});
    const comments = Array.isArray(out.comments) ? out.comments.map(toReviewComment) : [];
    // Group by normalized file path for perFile reporting. Normalization
    // (via sanitizeRelPath) strips './' prefixes and backslashes so the
    // resulting fileName matches the original file names, which downstream
    // logic (e.g. fixFromReview) relies on.
    const byPath = new Map();
    for (const c of comments) {
        const key = (c.path && sanitizeRelPath(c.path)) || c.path || 'unknown';
        const arr = byPath.get(key) ?? [];
        arr.push(c);
        byPath.set(key, arr);
    }
    const perFile = [...byPath.entries()].map(([path, cs]) => ({
        fileName: path,
        nodeLabel: path,
        nodeId: `ocr_${path}`,
        comments: cs,
        score: cs.some((c) => c.severity === 'critical' || c.severity === 'high')
            ? 'fail'
            : cs.length > 0
                ? 'warning'
                : 'pass',
        summary: `${cs.length} finding(s)`,
    }));
    const counts = {
        critical: 0,
        high: 0,
        medium: 0,
        low: 0,
        info: 0,
    };
    for (const c of comments) {
        if (counts[c.severity] !== undefined)
            counts[c.severity]++;
    }
    const summary = {
        filesReviewed: out.summary?.files_reviewed ?? perFile.length,
        totalComments: comments.length,
        criticalCount: counts.critical,
        highCount: counts.high,
        mediumCount: counts.medium,
        lowCount: counts.low,
        infoCount: counts.info,
    };
    return {
        comments,
        summary,
        perFile,
        projectSummary: out.project_summary,
        sessionId: out.session_id,
    };
}
// ─── Availability probe ────────────────────────────────────────────────────
/**
 * Return the path to the `ocr` binary, or null when it is not installed.
 * Uses `which ocr` (cheap, ~ms) rather than caching, so a later install is
 * picked up without a backend restart.
 */
export async function findOcrBinary() {
    try {
        const { stdout } = await execFileAsync('which', ['ocr'], { timeout: 5_000 });
        const bin = stdout.trim();
        return bin.length > 0 ? bin : null;
    }
    catch {
        return null;
    }
}
export async function isOcrAvailable() {
    return (await findOcrBinary()) !== null;
}
// ─── Runner ────────────────────────────────────────────────────────────────
function resolveConfig(opts) {
    return {
        model: opts.model ?? process.env.OCR_MODEL ?? DEFAULT_MODEL,
        baseUrl: opts.baseUrl ?? process.env.OCR_BASE_URL ?? DEFAULT_BASE_URL,
        provider: process.env.OCR_PROVIDER ?? DEFAULT_PROVIDER,
        timeoutMin: opts.timeoutMinutes ?? DEFAULT_TIMEOUT_MIN,
        totalTimeoutMs: opts.totalTimeoutMs ?? DEFAULT_TOTAL_TIMEOUT_MS,
    };
}
/**
 * Back up the user's ocr config file (if any) so the scan's provider
 * override can be restored afterwards. Returns the backup bytes.
 */
async function backupOcrConfig() {
    try {
        return await readFile(OCR_CONFIG_PATH, 'utf8');
    }
    catch {
        return null;
    }
}
/** Point ocr's custom provider at the configured endpoint + model. */
async function configureProvider(bin, cfg) {
    const set = (key, value) => execFileAsync(bin, ['config', 'set', key, value], { timeout: 15_000 });
    await set(`custom_providers.${cfg.provider}.url`, cfg.baseUrl);
    await set(`custom_providers.${cfg.provider}.protocol`, 'openai');
    await set(`custom_providers.${cfg.provider}.api_key`, process.env.OCR_API_KEY ?? 'local');
    await set('provider', cfg.provider);
}
/** Restore the user's ocr config to its pre-scan state. */
async function restoreOcrConfig(backup) {
    try {
        if (backup === null) {
            await rm(OCR_CONFIG_PATH, { force: true });
        }
        else {
            await copyFile(OCR_CONFIG_PATH, `${OCR_CONFIG_PATH}.bak`).catch(() => { });
            await writeFile(OCR_CONFIG_PATH, backup, 'utf8');
        }
    }
    catch {
        // Best-effort: the scan already produced its report; a failed restore
        // must not turn a successful review into an error.
    }
}
/**
 * Run a real OpenCodeReview scan over the given files and return the
 * normalized internal result. Throws when `ocr` is unavailable, a file path
 * would escape the temp dir, or the scan fails — callers (the route) should
 * fall back to the in-house CodeReviewer.
 */
export async function runOcrReview(files, opts = {}) {
    const bin = await findOcrBinary();
    if (!bin) {
        throw new Error('ocr CLI is not installed (expected: open-code-review binary on PATH)');
    }
    if (!files.length) {
        throw new Error('No files provided to ocr review');
    }
    const cfg = resolveConfig(opts);
    const configBackup = await backupOcrConfig();
    await configureProvider(bin, cfg);
    // Write files to an isolated temp dir, preserving relative paths.
    const dir = await mkdtemp(join(tmpdir(), 'vaca-ocr-review-'));
    try {
        const written = [];
        for (const f of files) {
            const rel = sanitizeRelPath(f.fileName);
            if (!rel) {
                throw new Error(`Refusing to write file outside temp dir: ${f.fileName}`);
            }
            const target = join(dir, rel);
            await mkdir(dirname(target), { recursive: true });
            await writeFile(target, f.code, 'utf8');
            written.push(rel);
        }
        // `--path` takes repo-relative paths. `--path .` makes ocr report
        // "No supported files changed", so pass the concrete file paths.
        const relPaths = written.join(',');
        const args = [
            'scan',
            '--path', relPaths,
            '--repo', dir,
            '--format', 'json',
            '--audience', 'agent',
            '--model', cfg.model,
            '--timeout', String(cfg.timeoutMin),
        ];
        const { stdout } = await execFileAsync(bin, args, {
            cwd: dir,
            timeout: cfg.totalTimeoutMs,
            maxBuffer: 32 * 1024 * 1024,
        });
        let parsed;
        try {
            parsed = JSON.parse(stdout);
        }
        catch {
            throw new Error(`ocr scan returned non-JSON output. Is the configured model tool-capable? ` +
                `(model: ${cfg.model}, url: ${cfg.baseUrl})`);
        }
        // A "skipped" scan means ocr found nothing to review — treat as failure
        // so callers fall back to the in-house reviewer instead of reporting an
        // empty-but-successful review.
        if (isOcrSkipped(parsed)) {
            const raw = parsed;
            throw new Error(`ocr scan skipped all files: ${raw.message ?? 'no supported files'}`);
        }
        const normalized = normalizeOcrOutput(parsed);
        return {
            success: true,
            comments: normalized.comments,
            summary: normalized.summary,
            perFile: normalized.perFile,
        };
    }
    finally {
        await rm(dir, { recursive: true, force: true });
        await restoreOcrConfig(configBackup);
    }
}
