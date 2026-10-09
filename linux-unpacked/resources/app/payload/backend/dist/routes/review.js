/**
 * Standalone code review endpoints — review arbitrary code without needing
 * a project in VACA. Accepts one or more code files and returns AI-powered
 * review results with severity-graded comments, categorization, and summary.
 *
 * POST /api/review          — review files (engine: 'internal' | 'ocr')
 * POST /api/review/and-fix  — review AND auto-fix critical/high issues
 * POST /api/review/batch    — review with explicit batch configuration
 *
 * Body (all three): {
 *   files: Array<{
 *     fileName: string;
 *     code: string;
 *     language?: string;
 *     nodeLabel?: string;
 *   }>,
 *   projectName?: string,
 *   appGoal?: string,
 *   targetOS?: string,
 *   engine?: 'internal' | 'ocr',   // default 'internal'
 *   model?: string,                // ocr: LLM model override
 *   baseUrl?: string,              // ocr: OpenAI-compatible endpoint override
 *   timeoutMinutes?: number,       // ocr: per-file agent timeout
 *   totalTimeoutMs?: number,       // ocr: overall scan timeout
 * }
 *
 * Engine semantics: 'ocr' runs the real OpenCodeReview CLI. If the ocr
 * binary is missing or the scan fails, the request falls back to the
 * in-house reviewer and the response reports engine:'internal' with
 * requestedEngine:'ocr' and fallbackReason.
 */
import { Router } from 'express';
import { codeReviewer, toReviewableFiles, DEFAULT_BATCH_CONFIG, } from '../review/CodeReviewer.js';
import { runOcrReview, isOcrAvailable } from '../review/ocrReviewer.js';
function parseEngine(value) {
    return String(value ?? '').toLowerCase() === 'ocr' ? 'ocr' : 'internal';
}
/** Ocr-specific overrides passed through from the request body. */
function extractOcrOptions(body) {
    return {
        model: body?.model,
        baseUrl: body?.baseUrl,
        timeoutMinutes: body?.timeoutMinutes,
        totalTimeoutMs: body?.totalTimeoutMs,
    };
}
/**
 * Run a review with the requested engine. For 'ocr', the real OpenCodeReview
 * CLI is tried first and any failure (missing binary, scan error, skipped
 * scan, timeout) falls back to the in-house reviewer, reporting the reason.
 */
async function reviewWithEngine(reviewable, context, engine, ocrOptions, batchConfig) {
    if (engine !== 'ocr') {
        const result = await codeReviewer.reviewAll(reviewable, context, batchConfig);
        return { result, engine };
    }
    if (!(await isOcrAvailable())) {
        const result = await codeReviewer.reviewAll(reviewable, context, batchConfig);
        return {
            result,
            engine: 'internal',
            requestedEngine: 'ocr',
            fallbackReason: 'ocr binary not found on PATH',
        };
    }
    try {
        const result = await runOcrReview(reviewable, ocrOptions);
        return { result, engine: 'ocr' };
    }
    catch (error) {
        const result = await codeReviewer.reviewAll(reviewable, context, batchConfig);
        return {
            result,
            engine: 'internal',
            requestedEngine: 'ocr',
            fallbackReason: error instanceof Error ? error.message : 'ocr scan failed',
        };
    }
}
/** Shared input validation for review endpoints */
function validateFiles(files) {
    if (!files || !Array.isArray(files) || files.length === 0) {
        return 'Request must include a "files" array with at least one entry.';
    }
    for (let i = 0; i < files.length; i++) {
        const f = files[i];
        if (!f.fileName || typeof f.fileName !== 'string') {
            return `files[${i}].fileName is required and must be a string.`;
        }
        if (!f.code || typeof f.code !== 'string') {
            return `files[${i}].code is required and must be a string.`;
        }
    }
    return null;
}
function toReviewable(files, projectName, appGoal, targetOS) {
    const reviewable = toReviewableFiles(files.map((f) => ({
        fileName: f.fileName,
        code: f.code,
        nodeId: f.nodeId || `external_${f.fileName}`,
        nodeLabel: f.nodeLabel || f.fileName,
        language: f.language || 'typescript',
    })));
    return {
        files: reviewable,
        context: {
            projectName: projectName || 'Standalone Review',
            appGoal: appGoal || undefined,
            targetOS: targetOS || undefined,
        },
    };
}
export const reviewRoutes = Router();
/**
 * POST /api/review
 * Standard code review. Engine-aware: 'internal' (default) uses the in-house
 * 4-phase pipeline (batch strategy, concurrency, PLAN_TASK, token budgeting);
 * 'ocr' uses the real OpenCodeReview CLI with graceful fallback.
 */
reviewRoutes.post('/', async (req, res) => {
    try {
        const { files, projectName, appGoal, targetOS, batchConfig, engine: engineRaw } = req.body;
        const engine = parseEngine(engineRaw);
        const ocrOptions = extractOcrOptions(req.body);
        const validationError = validateFiles(files);
        if (validationError) {
            return res.status(400).json({ success: false, error: validationError });
        }
        const { files: reviewable, context } = toReviewable(files, projectName, appGoal, targetOS);
        if (reviewable.length === 0) {
            return res.status(400).json({
                success: false,
                error: 'No reviewable files after filtering — all files appear to have empty code.',
            });
        }
        const startTime = Date.now();
        const dispatch = await reviewWithEngine(reviewable, context, engine, ocrOptions, batchConfig);
        const timingMs = Date.now() - startTime;
        res.json({
            success: dispatch.result.success,
            engine: dispatch.engine,
            requestedEngine: dispatch.requestedEngine,
            fallbackReason: dispatch.fallbackReason,
            comments: dispatch.result.comments,
            summary: dispatch.result.summary,
            perFile: dispatch.result.perFile,
            tokenBudget: dispatch.result.tokenBudget,
            timingMs,
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Code review failed',
        });
    }
});
/**
 * POST /api/review/and-fix
 * Review code AND auto-fix critical/high issues found. Works with either
 * engine: the review is produced by the selected engine and its findings are
 * fed through the same error-correction fix loop.
 *
 * Body: {
 *   files: Array<{ fileName, code, language?, nodeLabel? }>,
 *   projectName?: string,
 *   appGoal?: string,
 *   targetOS?: string,
 *   engine?: 'internal' | 'ocr',
 *   batchConfig?: BatchConfig,     // optional review config (internal engine)
 *   fixConfig?: {                   // optional fix config
 *     maxFixAttempts?: number,      // default 3
 *     minSeverity?: 'critical' | 'high'  // default 'critical'
 *   }
 * }
 *
 * Returns: {
 *   success: boolean,
 *   engine: 'internal' | 'ocr',
 *   review: CodeReviewResult,
 *   fixes: Array<{ fileName, originalCode, fixedCode, fixAttempts, success }>,
 *   timingMs: number,
 * }
 */
reviewRoutes.post('/and-fix', async (req, res) => {
    try {
        const { files, projectName, appGoal, targetOS, batchConfig, fixConfig, engine: engineRaw } = req.body;
        const engine = parseEngine(engineRaw);
        const ocrOptions = extractOcrOptions(req.body);
        const validationError = validateFiles(files);
        if (validationError) {
            return res.status(400).json({ success: false, error: validationError });
        }
        const { files: reviewable, context } = toReviewable(files, projectName, appGoal, targetOS);
        if (reviewable.length === 0) {
            return res.status(400).json({
                success: false,
                error: 'No reviewable files after filtering — all files appear to have empty code.',
            });
        }
        const startTime = Date.now();
        const dispatch = await reviewWithEngine(reviewable, context, engine, ocrOptions, batchConfig);
        // Auto-fix critical/high findings from whichever engine produced the review.
        const fixes = await codeReviewer.fixFromReview(reviewable, dispatch.result, context, fixConfig);
        const timingMs = Date.now() - startTime;
        res.json({
            success: dispatch.result.success,
            engine: dispatch.engine,
            requestedEngine: dispatch.requestedEngine,
            fallbackReason: dispatch.fallbackReason,
            review: dispatch.result,
            fixes,
            timingMs,
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Review and fix failed',
        });
    }
});
/**
 * POST /api/review/batch
 * Batch review with explicit batch configuration. Engine-aware like
 * POST /api/review; the `config` block configures the internal reviewer's
 * batching (strategy/concurrency/token budget), while engine:'ocr' runs the
 * OpenCodeReview CLI (which batches internally).
 */
reviewRoutes.post('/batch', async (req, res) => {
    try {
        const { files, projectName, appGoal, targetOS, engine: engineRaw } = req.body;
        const config = req.body.config || {};
        const engine = parseEngine(engineRaw);
        const ocrOptions = extractOcrOptions(req.body);
        const validationError = validateFiles(files);
        if (validationError) {
            return res.status(400).json({ success: false, error: validationError });
        }
        const { files: reviewable, context } = toReviewable(files, projectName, appGoal, targetOS);
        if (reviewable.length === 0) {
            return res.status(400).json({
                success: false,
                error: 'No reviewable files after filtering.',
            });
        }
        const batchConfig = {
            strategy: config.strategy || DEFAULT_BATCH_CONFIG.strategy,
            concurrency: config.concurrency || DEFAULT_BATCH_CONFIG.concurrency,
            maxTokensBudget: config.maxTokensBudget || DEFAULT_BATCH_CONFIG.maxTokensBudget,
            enablePlan: config.enablePlan !== false,
            enableLlmDedup: config.enableLlmDedup !== false,
        };
        const startTime = Date.now();
        const dispatch = await reviewWithEngine(reviewable, context, engine, ocrOptions, batchConfig);
        const timingMs = Date.now() - startTime;
        res.json({
            success: dispatch.result.success,
            engine: dispatch.engine,
            requestedEngine: dispatch.requestedEngine,
            fallbackReason: dispatch.fallbackReason,
            comments: dispatch.result.comments,
            summary: dispatch.result.summary,
            perFile: dispatch.result.perFile,
            tokenBudget: dispatch.result.tokenBudget,
            config: batchConfig,
            timingMs,
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Batch review failed',
        });
    }
});
