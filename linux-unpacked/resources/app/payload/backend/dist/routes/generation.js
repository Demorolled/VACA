import { Router } from 'express';
import { FileGenerator, labelToFileName, getFileExtension, stripLabelExtension, projectGraphSignature } from '../layers/fileGenerator.js';
import { projects } from '../db/projects.js';
import { SandboxRunner } from '../sandbox/runner.js';
import { codeScanner } from '../scanner/CodeScanner.js';
import { broadcastGenerationProgress } from '../socket/socketManager.js';
import { runRuntimeSmokeTest, isRuntimeSmokeEnabled } from '../sandbox/runtimeSmokeTest.js';
export const generationRoutes = Router();
const fileGenerator = new FileGenerator();
const sandbox = new SandboxRunner();
// ═══════════════════════════════════════════════════════════════════════════
// Per-File Generation (Node-per-File Architecture)
// ═══════════════════════════════════════════════════════════════════════════
/**
 * POST /api/generate/:projectId/files
 * Generate individual files for each node in the project (node-per-file architecture).
 * Each node becomes its own standalone source file with proper imports/exports.
 * Automatically runs AI-powered code review after generation.
 */
generationRoutes.post('/:projectId/files', async (req, res) => {
    try {
        const { projectId } = req.params;
        const project = projects.getById(projectId);
        if (!project) {
            return res.status(404).json({ error: 'Project not found' });
        }
        const startTime = Date.now();
        const skipValidation = req.body.skipValidation === true;
        const skipSecurityScan = req.body.skipSecurityScan === true;
        // Wire up progress streaming via Socket.IO for real-time frontend updates
        const onProgress = (progress) => {
            broadcastGenerationProgress({
                batch: progress.batch,
                totalBatches: progress.totalBatches,
                batchSize: progress.batchSize,
                generatingNodes: progress.generatingNodes,
                percent: progress.percent,
                phase: progress.phase,
            });
        };
        const result = await fileGenerator.generateFiles(project, skipValidation, onProgress);
        const generationTime = Date.now() - startTime;
        // Cache the generation keyed by project id (mirrored to a sidecar file) so
        // a later export — even after a backend restart — reuses the exact code the
        // user saw instead of regenerating non-deterministically (the root cause of
        // entry-point imports not matching exported files).
        projects.setGenerationCache(project.id, {
            sig: projectGraphSignature(project),
            result,
            at: Date.now(),
        });
        // ── Step 1: Security scan on all generated files (skippable for preview builds) ──
        const securityScans = skipSecurityScan ? [] : result.files.map(f => ({
            fileName: f.fileName,
            nodeLabel: f.nodeLabel,
            codeLength: f.code.length,
            validated: f.validated,
            errors: f.errors,
            securityScan: codeScanner.securityScan(f.fileName, f.code),
            complexity: codeScanner.analyzeComplexity(f.code),
        }));
        // ── Step 2: (DISABLED) AI code review overlaps with CodeScanner which runs in Step 1
        // CodeScanner catches security issues, hardcoded secrets, console.log, etc. instantly.
        // The AI reviewer was redundant and slow with the local 7B model.
        // The standalone POST /api/review endpoint remains available for manual use.
        const codeReview = null;
        // ── Step 3: Automated RUNTIME smoke test (real builds only) ──
        // Boots the generated app in headless Chromium and clicks through it —
        // every button, every input — asserting it loads error-free and the UI
        // responds. This is the "does the assembled app actually work" check that
        // tsc (type-level) and the sandbox (single-file syntax) cannot provide.
        // Skipped for fast preview builds (skipValidation=true) and can be disabled
        // per-request with { runtimeSmoke: false }. Non-fatal: a smoke failure is
        // reported in the response but never fails generation itself.
        //
        // Browser-only: a Go/CLI/Python project is NOT a browser app — the
        // auto-generated preview wrapper exists for every project, so previously
        // the smoke booted a Go CLI in Chromium, "passed" with zero clickables,
        // and reported a false green. The smoke only runs when the project
        // actually contains web-language files.
        let runtimeSmoke = null;
        const hasWebLanguageFiles = result.files.some((f) => ['typescript', 'javascript', 'html'].includes((f.language || '').toLowerCase()));
        if (!skipValidation && req.body.runtimeSmoke !== false) {
            const smokeStart = Date.now();
            try {
                if (!hasWebLanguageFiles) {
                    runtimeSmoke = {
                        available: false,
                        reason: 'No web-language files (TypeScript/JavaScript/HTML) — this is a CLI/native project; browser smoke skipped',
                        success: false,
                        durationMs: 0,
                        entryFile: null,
                        checks: [],
                        consoleErrors: [],
                        interactions: { clickableFound: 0, clicked: 0, inputsFound: 0, typed: 0, domChangedAfterClick: 0 },
                    };
                }
                else {
                    runtimeSmoke = await runRuntimeSmokeTest(result.files.map((f) => ({ fileName: f.fileName, code: f.code })), { timeoutMs: 45000 });
                    if (runtimeSmoke.available) {
                        console.log(`[generation] runtime smoke ${runtimeSmoke.success ? 'PASS' : 'FAIL'} (${Date.now() - smokeStart}ms) for project ${projectId}${runtimeSmoke.checks.length ? ' — ' + runtimeSmoke.checks.map(c => `${c.name}=${c.status}`).join(', ') : ''}`);
                    }
                }
            }
            catch (err) {
                runtimeSmoke = { available: false, reason: `smoke test threw: ${err instanceof Error ? err.message : String(err)}` };
            }
        }
        res.json({
            success: true,
            projectId,
            ...result,
            securityScans,
            codeReview,
            runtimeSmoke,
            timingMs: {
                generation: generationTime,
                codeReview: 0,
                runtimeSmoke: runtimeSmoke && runtimeSmoke.available ? runtimeSmoke.durationMs : 0,
                total: Date.now() - startTime,
            },
            summary: {
                totalFiles: result.files.length,
                totalChars: result.totalChars,
                totalErrors: result.totalErrors,
                validated: result.validatedCount,
                failed: result.failedCount,
                // Honest verdict: every file must have zero errors AND the whole
                // project must pass the live tsc compile gate. Previously this only
                // checked failedCount, which reported isAllValidated:true while
                // tsCompileClean:false (the countdown-timer evaluation caught this).
                isAllValidated: result.failedCount === 0 && result.totalErrors === 0 && result.tsCompileClean === true,
                tsCompileClean: result.tsCompileClean,
                contractViolations: result.contractViolations ?? 0,
                reviewIssues: 0,
                reviewCritical: 0,
                reviewHigh: 0,
            },
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'File generation failed',
        });
    }
});
/**
 * POST /api/generate/runtime-smoke
 * Run automated click-through smoke tests on an arbitrary generated file set
 * (the same kind of files `/files` returns). Launches the app in headless
 * Chromium, clicks every visible button, types into every input, and reports
 * whether the app boots error-free and responds.
 *
 * Body: { files: [{ fileName, code }] }
 * Returns: RuntimeSmokeResult (available/success/checks/consoleErrors/...)
 */
generationRoutes.post('/runtime-smoke', async (req, res) => {
    try {
        const { files } = req.body || {};
        if (!Array.isArray(files) || files.length === 0 || !files.every((f) => f && typeof f.fileName === 'string' && typeof f.code === 'string')) {
            return res.status(400).json({ success: false, error: 'Body must be { files: [{ fileName, code }] }' });
        }
        if (!isRuntimeSmokeEnabled()) {
            return res.json({ success: true, smoke: { available: false, reason: 'disabled via VACA_SKIP_RUNTIME_SMOKE' } });
        }
        const smoke = await runRuntimeSmokeTest(files);
        console.log(`[runtime-smoke] ${smoke.available ? (smoke.success ? 'PASS' : 'FAIL') : 'UNAVAILABLE'} — ${smoke.interactions.clicked} clicks, ${smoke.interactions.typed} typed, ${smoke.checks.length} checks`);
        res.json({ success: true, smoke });
    }
    catch (error) {
        res.status(500).json({ success: false, error: error instanceof Error ? error.message : 'Runtime smoke test failed' });
    }
});
/**
 * POST /api/generate/:projectId/file/:nodeId
 * Generate or regenerate code for a single node file (hot-swap editing).
 */
generationRoutes.post('/:projectId/file/:nodeId', async (req, res) => {
    try {
        const { projectId, nodeId } = req.params;
        const project = projects.getById(projectId);
        if (!project) {
            return res.status(404).json({ error: 'Project not found' });
        }
        const node = project.nodes.find((n) => n.id === nodeId);
        if (!node) {
            return res.status(404).json({ error: 'Node not found' });
        }
        // Build dependency context from edges
        const incomingEdges = project.edges.filter((e) => e.target === nodeId);
        const depLabels = incomingEdges.map((e) => {
            const sourceNode = project.nodes.find((n) => n.id === e.source);
            return sourceNode?.data?.label || '';
        }).filter(Boolean);
        // Generate just this one file using the public single-file API
        const code = await fileGenerator.generateSingleFile(node, project, depLabels);
        // Use shared utilities from fileGenerator to handle embedded extensions (avoids "main.go" → "main-go.go")
        const rawLabel = node.data.label || '';
        const fileName = labelToFileName(rawLabel);
        // Use label's embedded extension if present, otherwise derive from language
        const { extOverride } = stripLabelExtension(rawLabel);
        const ext = extOverride || getFileExtension(node.data.language || 'typescript');
        // Run sandbox validation on this single file
        let errors = [];
        let validated = false;
        try {
            const validation = await sandbox.run(code, node.data.language || 'typescript');
            errors = validation.errors || [];
            validated = validation.success;
        }
        catch {
            errors = ['Sandbox validation unavailable'];
        }
        res.json({
            success: true,
            file: {
                fileName: `${fileName}.${ext}`,
                language: node.data.language || 'typescript',
                code,
                nodeId,
                nodeLabel: node.data.label,
                errors,
                validated,
            },
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Single file generation failed',
        });
    }
});
/**
 * GET /api/generate/file-generator-status
 * Check what tools are available for file generation.
 */
generationRoutes.get('/file-generator-status', (_req, res) => {
    const availability = fileGenerator.getAvailability();
    res.json({
        success: true,
        ...availability,
        mode: 'per-file',
        description: 'Node-per-file architecture: each node generates an independent source file with proper imports/exports.',
    });
});
// ─── Sandbox Validation ──────────────────────────────────────────────────
/**
 * POST /api/generate/validate
 * Validate generated code in the sandbox (Docker or local).
 *
 * Body: { code: string, language?: string }
 * Returns: { success, output, errors, exitCode }
 */
generationRoutes.post('/validate', async (req, res) => {
    try {
        const { code, language } = req.body;
        if (!code || typeof code !== 'string') {
            return res.status(400).json({ error: 'Code string is required' });
        }
        const result = await sandbox.run(code, language);
        res.json({
            success: true,
            validation: result,
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Validation failed',
        });
    }
});
/**
 * POST /api/generate/validate-and-fix
 * Full error-correction loop: validate → detect errors → LLM fixes → retry.
 *
 * Body: { code, language?, projectName?, goal?, maxAttempts? }
 * Returns: { success, finalCode, fixAttempts, totalTimeMs, report, validation }
 */
generationRoutes.post('/validate-and-fix', async (req, res) => {
    try {
        const { code, language, projectName, goal, maxAttempts } = req.body;
        if (!code || typeof code !== 'string') {
            return res.status(400).json({ error: 'Code string is required' });
        }
        // First run initial validation
        const initialResult = await sandbox.run(code, language);
        // If already valid, return immediately
        if (initialResult.success) {
            return res.json({
                success: true,
                finalCode: code,
                language: language || 'typescript',
                fixAttempts: 0,
                totalTimeMs: 0,
                report: 'Code passed validation on first attempt — no fixes needed.',
                initialValidation: initialResult,
                fixed: false,
            });
        }
        // Run the error-correction loop
        const fixResult = await sandbox.runWithFix({
            code,
            language,
            projectName,
            goal,
            maxAttempts: maxAttempts || 3,
        });
        // Run final validation on fixed code
        const finalValidation = fixResult.success
            ? await sandbox.run(fixResult.finalCode, fixResult.language)
            : null;
        res.json({
            success: fixResult.success,
            finalCode: fixResult.finalCode,
            language: fixResult.language,
            fixAttempts: fixResult.fixAttempts,
            totalTimeMs: fixResult.totalTimeMs,
            report: fixResult.report,
            initialValidation: initialResult,
            finalValidation,
            fixed: fixResult.fixAttempts > 0,
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Validation and fix failed',
        });
    }
});
/**
 * POST /api/generate/:projectId/validate-single-file
 * Validate a single node's generated code in the sandbox (lightweight check).
 * Useful for live validation during node editing without full regeneration.
 */
generationRoutes.post('/:projectId/validate-single-file', async (req, res) => {
    try {
        const { projectId } = req.params;
        const { nodeId, code } = req.body;
        if (!code) {
            return res.status(400).json({ error: 'Code string is required' });
        }
        const project = projects.getById(projectId);
        const node = project?.nodes.find((n) => n.id === nodeId);
        const language = node?.data?.language || 'typescript';
        const validation = await sandbox.run(code, language);
        res.json({
            success: true,
            validated: validation.success,
            errors: validation.errors || [],
            output: validation.output || '',
            nodeId: nodeId || null,
            language,
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Validation failed',
        });
    }
});
/**
 * GET /api/generate/sandbox-status
 * Check what sandbox tools are available on this system.
 */
generationRoutes.get('/sandbox-status', (_req, res) => {
    const availability = sandbox.getAvailability();
    res.json({
        success: true,
        ...availability,
    });
});
/**
 * POST /api/generate/security-scan-code
 * Run a security scan on arbitrary code strings (no project needed).
 * Body: { code: string, filePath?: string }
 */
generationRoutes.post('/security-scan-code', async (req, res) => {
    try {
        const { code, filePath } = req.body;
        if (!code || typeof code !== 'string') {
            return res.status(400).json({ error: 'Code string is required' });
        }
        const path = filePath || 'submitted-code.ts';
        const securityScan = codeScanner.securityScan(path, code);
        const complexity = codeScanner.analyzeComplexity(code);
        const hasCritical = securityScan.vulnerabilities.some(v => v.severity === 'critical');
        const hasHigh = securityScan.vulnerabilities.some(v => v.severity === 'high');
        res.json({
            success: true,
            securityScan,
            complexity,
            summary: {
                totalVulnerabilities: securityScan.vulnerabilities.length,
                criticalCount: securityScan.summary.critical,
                highCount: securityScan.summary.high,
                mediumCount: securityScan.summary.medium,
                lowCount: securityScan.summary.low,
                isSecure: !hasCritical && !hasHigh,
            },
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Security scan failed',
        });
    }
});
