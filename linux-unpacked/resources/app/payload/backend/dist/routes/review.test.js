/**
 * Integration tests for the /api/review engine dispatch contract.
 *
 * These mount the real reviewRoutes router on an ephemeral express server and
 * drive it with real HTTP requests. The real ocr binary is stubbed by placing
 * a fake executable `ocr` script on PATH; the internal CodeReviewer is mocked
 * so the fallback path does not hit the real local LLM.
 *
 * Contract under test (all three endpoints):
 *   engine: 'ocr'  →  ocr missing  → { engine: 'internal', requestedEngine: 'ocr', fallbackReason: 'ocr binary not found on PATH' }
 *   engine: 'ocr'  →  scan ok      → { engine: 'ocr', comments: <from ocr>, no fallback fields }
 *   engine: 'ocr'  →  scan skipped → fallback with reason mentioning 'skipped'
 *   engine: 'ocr'  →  scan failed  → fallback with reason mentioning 'Command failed'
 *   engine: (default / 'internal')  → { engine: 'internal', no fallback fields }
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import { mkdtemp, writeFile, rm, chmod } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import express from 'express';
// Point the ocrReviewer at a throwaway config path BEFORE the module graph is
// imported, so backup/restore never touches the real ~/.opencodereview config.
// (vi.hoisted runs before module imports, so no imported bindings here.)
vi.hoisted(() => {
    const base = process.env.TMPDIR || process.env.TMP || '/tmp';
    process.env.OCR_CONFIG_PATH = `${base}/vaca-ocr-test-config.json`;
});
// Mock only the internal reviewer: the fallback path calls reviewAll /
// fixFromReview, which would otherwise invoke the real local LLM. The rest of
// the module (toReviewableFiles, DEFAULT_BATCH_CONFIG, types) stays real.
// Note: the mock surface is intentionally partial — the route only calls
// reviewAll and fixFromReview; adding a route that calls other CodeReviewer
// methods would need this mock extended.
vi.mock('../review/CodeReviewer.js', async (importOriginal) => {
    const actual = await importOriginal();
    return {
        ...actual,
        codeReviewer: {
            reviewAll: vi.fn(),
            fixFromReview: vi.fn(),
        },
    };
});
import { reviewRoutes } from './review.js';
import { codeReviewer } from '../review/CodeReviewer.js';
// ─── Fake ocr binary ───────────────────────────────────────────────────────
/** Behavior selectable per test via env vars read by the fake script. */
const FAKE_OCR_SCRIPT = `#!/usr/bin/env bash
# Fake ocr binary for integration tests. Handles the subcommands the
# ocrReviewer adapter invokes: 'config set ...' and 'scan ...'.
if [[ "$1" == "config" ]]; then
  exit 0
fi
if [[ "$1" == "scan" ]]; then
  if [[ -n "$FAKE_OCR_FAIL" ]]; then
    echo "Error: scan failed: all file scan(s) failed" >&2
    exit 1
  fi
  if [[ -n "$FAKE_OCR_SKIPPED" ]]; then
    cat <<'JSON'
{"status":"skipped","message":"No supported files changed.","comments":[]}
JSON
    exit 0
  fi
  cat <<'JSON'
{"status":"success","comments":[{"path":"src/core.ts","content":"Missing null check on fetch result","severity":"high","category":"bug","start_line":3,"end_line":4,"suggestion_code":"if (!data) return [];"}],"summary":{"files_reviewed":1,"comments":1,"total_tokens":120},"session_id":"fake-123"}
JSON
  exit 0
fi
exit 0
`;
const FILES = [{ fileName: 'src/core.ts', code: 'export const x = 1;' }];
const INTERNAL_REVIEW = {
    success: true,
    comments: [
        {
            path: 'src/core.ts',
            content: 'Internal reviewer finding',
            severity: 'medium',
            category: 'bug',
            startLine: 1,
            endLine: 1,
        },
    ],
    summary: {
        filesReviewed: 1,
        totalComments: 1,
        criticalCount: 0,
        highCount: 0,
        mediumCount: 1,
        lowCount: 0,
        infoCount: 0,
    },
    perFile: [
        {
            fileName: 'src/core.ts',
            nodeLabel: 'src/core.ts',
            nodeId: 'n1',
            score: 'warning',
            summary: '1 finding(s)',
            comments: [],
        },
    ],
};
let fakeDir;
let server;
let baseUrl;
async function startServer() {
    const app = express();
    app.use(express.json());
    app.use('/api/review', reviewRoutes);
    const srv = app.listen(0);
    await new Promise((resolve) => srv.once('listening', resolve));
    const port = srv.address().port;
    return { server: srv, baseUrl: `http://127.0.0.1:${port}` };
}
async function postReview(path, body) {
    const res = await fetch(`${baseUrl}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    return { status: res.status, body: (await res.json()) };
}
beforeAll(async () => {
    fakeDir = await mkdtemp(join(tmpdir(), 'vaca-ocr-fake-'));
    const ocrBin = join(fakeDir, 'ocr');
    await writeFile(ocrBin, FAKE_OCR_SCRIPT, 'utf8');
    await chmod(ocrBin, 0o755);
    const started = await startServer();
    server = started.server;
    baseUrl = started.baseUrl;
});
afterAll(async () => {
    if (server) {
        await new Promise((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())));
    }
    await rm(fakeDir, { recursive: true, force: true });
});
beforeEach(() => {
    // Default: fake ocr found on PATH, succeeds. Individual tests override.
    vi.stubEnv('PATH', `${fakeDir}:/usr/local/bin:/usr/bin:/bin`);
    codeReviewer.reviewAll.mockResolvedValue(INTERNAL_REVIEW);
    codeReviewer.fixFromReview.mockResolvedValue([]);
});
afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
});
// ─── Validation ────────────────────────────────────────────────────────────
describe('POST /api/review — validation', () => {
    it('returns 400 when files is missing', async () => {
        const { status, body } = await postReview('/api/review', {});
        expect(status).toBe(400);
        expect(body.success).toBe(false);
        expect(body.error).toContain('files');
    });
    it('returns 400 when a file has no code', async () => {
        const { status, body } = await postReview('/api/review', {
            files: [{ fileName: 'a.ts' }],
        });
        expect(status).toBe(400);
        expect(body.success).toBe(false);
        expect(body.error).toContain('code');
    });
});
// ─── POST /api/review ──────────────────────────────────────────────────────
describe('POST /api/review — engine fallback contract', () => {
    it('runs ocr and returns its comments when the scan succeeds', async () => {
        const { status, body } = await postReview('/api/review', {
            files: FILES,
            engine: 'ocr',
            model: 'fake-model',
        });
        expect(status).toBe(200);
        expect(body.engine).toBe('ocr');
        expect(body.requestedEngine).toBeUndefined();
        expect(body.fallbackReason).toBeUndefined();
        expect(body.comments).toHaveLength(1);
        expect(body.comments[0].content).toContain('Missing null check');
        expect(body.comments[0].severity).toBe('high');
        // The internal reviewer must not have been consulted on the success path.
        expect(codeReviewer.reviewAll).not.toHaveBeenCalled();
    });
    it('falls back to internal when the ocr binary is missing', async () => {
        // PATH without the fake dir and without the real ocr install location.
        vi.stubEnv('PATH', '/usr/local/bin:/usr/bin:/bin');
        const { status, body } = await postReview('/api/review', { files: FILES, engine: 'ocr' });
        expect(status).toBe(200);
        expect(body.engine).toBe('internal');
        expect(body.requestedEngine).toBe('ocr');
        expect(body.fallbackReason).toBe('ocr binary not found on PATH');
        expect(body.comments).toHaveLength(1);
        expect(body.comments[0].content).toContain('Internal reviewer finding');
    });
    it('falls back to internal when ocr reports a skipped scan', async () => {
        vi.stubEnv('FAKE_OCR_SKIPPED', '1');
        const { status, body } = await postReview('/api/review', { files: FILES, engine: 'ocr' });
        expect(status).toBe(200);
        expect(body.engine).toBe('internal');
        expect(body.requestedEngine).toBe('ocr');
        expect(body.fallbackReason).toContain('skipped');
        expect(body.comments[0].content).toContain('Internal reviewer finding');
    });
    it('falls back to internal when the ocr scan fails', async () => {
        vi.stubEnv('FAKE_OCR_FAIL', '1');
        const { status, body } = await postReview('/api/review', { files: FILES, engine: 'ocr' });
        expect(status).toBe(200);
        expect(body.engine).toBe('internal');
        expect(body.requestedEngine).toBe('ocr');
        expect(body.fallbackReason).toContain('Command failed');
        expect(body.comments[0].content).toContain('Internal reviewer finding');
    });
    it('uses internal by default with no fallback fields', async () => {
        const { status, body } = await postReview('/api/review', { files: FILES });
        expect(status).toBe(200);
        expect(body.engine).toBe('internal');
        expect(body.requestedEngine).toBeUndefined();
        expect(body.fallbackReason).toBeUndefined();
        expect(body.comments[0].content).toContain('Internal reviewer finding');
        expect(codeReviewer.reviewAll).toHaveBeenCalledTimes(1);
    });
    it('uses internal when engine is explicitly "internal"', async () => {
        const { status, body } = await postReview('/api/review', {
            files: FILES,
            engine: 'internal',
        });
        expect(status).toBe(200);
        expect(body.engine).toBe('internal');
        expect(body.requestedEngine).toBeUndefined();
        expect(codeReviewer.reviewAll).toHaveBeenCalledTimes(1);
    });
    it('is case-insensitive when engine is "OCR"', async () => {
        const { status, body } = await postReview('/api/review', { files: FILES, engine: 'OCR' });
        expect(status).toBe(200);
        expect(body.engine).toBe('ocr');
        expect(body.comments[0].content).toContain('Missing null check');
    });
});
// ─── POST /api/review/and-fix ──────────────────────────────────────────────
describe('POST /api/review/and-fix — engine fallback contract', () => {
    it('returns review + fixes with engine=ocr when ocr succeeds', async () => {
        const { status, body } = await postReview('/api/review/and-fix', {
            files: FILES,
            engine: 'ocr',
            fixConfig: { maxFixAttempts: 2 },
        });
        expect(status).toBe(200);
        expect(body.engine).toBe('ocr');
        expect(body.review.comments[0].content).toContain('Missing null check');
        expect(body.fixes).toEqual([]);
        // The fix loop must have been invoked with the ocr review result.
        expect(codeReviewer.fixFromReview).toHaveBeenCalledTimes(1);
        const reviewArg = codeReviewer.fixFromReview.mock.calls[0][1];
        expect(reviewArg.comments[0].content).toContain('Missing null check');
    });
    it('falls back to internal review+fix when ocr is missing', async () => {
        vi.stubEnv('PATH', '/usr/local/bin:/usr/bin:/bin');
        const { status, body } = await postReview('/api/review/and-fix', {
            files: FILES,
            engine: 'ocr',
            fixConfig: { maxFixAttempts: 2 },
        });
        expect(status).toBe(200);
        expect(body.engine).toBe('internal');
        expect(body.requestedEngine).toBe('ocr');
        expect(body.fallbackReason).toBe('ocr binary not found on PATH');
        expect(body.review.comments[0].content).toContain('Internal reviewer finding');
        expect(body.fixes).toEqual([]);
    });
});
// ─── POST /api/review/batch ────────────────────────────────────────────────
describe('POST /api/review/batch — engine fallback contract', () => {
    it('runs ocr and echoes config when the scan succeeds', async () => {
        const { status, body } = await postReview('/api/review/batch', {
            files: FILES,
            engine: 'ocr',
            config: { strategy: 'all', concurrency: 2 },
        });
        expect(status).toBe(200);
        expect(body.engine).toBe('ocr');
        expect(body.config.strategy).toBe('all');
        expect(body.comments[0].content).toContain('Missing null check');
    });
    it('falls back to internal when the ocr scan fails', async () => {
        vi.stubEnv('FAKE_OCR_FAIL', '1');
        const { status, body } = await postReview('/api/review/batch', {
            files: FILES,
            engine: 'ocr',
            config: { strategy: 'all' },
        });
        expect(status).toBe(200);
        expect(body.engine).toBe('internal');
        expect(body.requestedEngine).toBe('ocr');
        expect(body.fallbackReason).toContain('Command failed');
        expect(body.config.strategy).toBe('all');
        expect(body.comments[0].content).toContain('Internal reviewer finding');
    });
});
