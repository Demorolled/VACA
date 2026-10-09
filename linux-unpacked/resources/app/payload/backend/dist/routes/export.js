import { Router } from 'express';
import { projects } from '../db/projects.js';
import { FileGenerator, projectGraphSignature } from '../layers/fileGenerator.js';
import { PerFileScaffolder } from '../export/perFileScaffolder.js';
import { codeScanner } from '../scanner/CodeScanner.js';
import { spawn } from 'child_process';
import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';
export const exportRoutes = Router();
const perFileScaffolder = new PerFileScaffolder();
const fileGenerator = new FileGenerator();
/**
 * Decide whether an export may reuse the cached generation result instead of
 * re-running the LLM. Reuse iff the caller did NOT force regeneration AND a
 * cache exists whose signature still matches the current project graph AND it
 * produced at least one file.
 *
 * The signature is the key that ties the cache to the exact canvas that
 * produced it: any node/edge/targetOS change yields a new signature, so the
 * cache is discarded and the export regenerates — exported code always matches
 * what the user reviewed, never a stale graph.
 *
 * `getCache` is injectable for tests; by default it reads the ProjectStore's
 * sidecar-persisted cache (which survives backend restarts).
 */
export function resolveCachedGeneration(project, opts, getCache = (id) => projects.getGenerationCache(id)) {
    if (opts?.regenerate)
        return undefined;
    const sig = projectGraphSignature(project);
    const cached = getCache(project.id);
    if (!cached || cached.sig !== sig)
        return undefined;
    if (!Array.isArray(cached.result?.files) || cached.result.files.length === 0)
        return undefined;
    return cached;
}
// ═══════════════════════════════════════════════════════════════════════════
// Per-File Scaffold (Node-per-File Architecture)
// ═══════════════════════════════════════════════════════════════════════════
/**
 * POST /api/export/:projectId/per-file-scaffold
 *
 * Generate per-node files using the FileGenerator, then scaffold a complete
 * project directory where each node is its own standalone source file.
 *
 * This is the new per-file architecture — replaces the old 3-layer approach.
 */
exportRoutes.post('/:projectId/per-file-scaffold', async (req, res) => {
    try {
        const { projectId } = req.params;
        const project = projects.getById(projectId);
        if (!project) {
            return res.status(404).json({ error: 'Project not found' });
        }
        // Step 1: Generate per-node files
        // Reuse the cached generation from the last /api/generate/:id/files call
        // when the canvas hasn't changed — regenerating here produced a DIFFERENT
        // codebase than the one the user reviewed, and the scaffold's entry point
        // then imported symbols that never appeared in the exported files. Pass
        // { regenerate: true } to force a fresh run.
        const skipValidation = req.body.skipValidation === true;
        const skipSecurityScan = req.body.skipSecurityScan === true;
        const cached = resolveCachedGeneration(project, { regenerate: req.body.regenerate === true });
        let generationResult;
        if (cached) {
            generationResult = cached.result;
            console.log(`[export] Reusing cached generation for ${projectId} (${generationResult.files.length} files, sig unchanged)`);
        }
        else {
            const sig = projectGraphSignature(project);
            generationResult = await fileGenerator.generateFiles(project, skipValidation);
            projects.setGenerationCache(project.id, { sig, result: generationResult, at: Date.now() });
        }
        if (generationResult.files.length === 0) {
            return res.status(400).json({
                error: 'No files generated. Ensure the project has non-master nodes with code generation.',
            });
        }
        // Find goal/purpose from the master node
        const masterNode = project.nodes.find((n) => n.type === 'master');
        const appGoal = masterNode?.data?.appGoal || '';
        const appPurpose = masterNode?.data?.appPurpose || '';
        const linuxDistro = req.body.linuxDistro || masterNode?.data?.selectedDistro || undefined;
        // Step 2: Scaffold using per-file architecture
        const scaffoldResult = await perFileScaffolder.scaffold({
            projectName: req.body.projectName || project.name,
            targetOS: req.body.targetOS || project.targetOS,
            linuxDistro,
            outputDir: req.body.outputDir || undefined,
            files: generationResult.files,
            nodes: project.nodes,
            edges: project.edges,
            // Tree Mode: more than one app tree exports as separate apps (`apps/<app>/`)
            // plus a shared `bridge/` for the cross-app handoffs.
            trees: project.trees ?? [],
            appGoal,
            appPurpose,
        });
        // Run security scan on each generated file (skippable for preview builds)
        let securityScanResults = [];
        let securitySummary = { totalVulnerabilities: 0, critical: 0, high: 0, medium: 0, low: 0, isSecure: true };
        if (!skipSecurityScan) {
            try {
                securityScanResults = generationResult.files.map((f) => {
                    const scan = codeScanner.securityScan(f.fileName, f.code);
                    return {
                        fileName: f.fileName,
                        nodeLabel: f.nodeLabel,
                        codeLength: f.code.length,
                        validated: f.validated,
                        vulnerabilities: scan.vulnerabilities,
                        summary: scan.summary,
                    };
                });
                const allVulns = securityScanResults.flatMap(sr => sr.vulnerabilities);
                securitySummary = {
                    totalVulnerabilities: allVulns.length,
                    critical: allVulns.filter((v) => v.severity === 'critical').length,
                    high: allVulns.filter((v) => v.severity === 'high').length,
                    medium: allVulns.filter((v) => v.severity === 'medium').length,
                    low: allVulns.filter((v) => v.severity === 'low').length,
                    isSecure: !allVulns.some((v) => v.severity === 'critical' || v.severity === 'high'),
                };
            }
            catch (scanErr) {
                console.warn('[export] Security scan failed (non-blocking):', scanErr);
            }
        }
        res.json({
            success: scaffoldResult.success,
            outputPath: scaffoldResult.outputPath,
            files: scaffoldResult.files,
            perNodeFiles: scaffoldResult.perNodeFiles,
            ...(scaffoldResult.warning ? { warning: scaffoldResult.warning } : {}),
            generationSummary: {
                totalFiles: generationResult.files.length,
                totalChars: generationResult.totalChars,
                validatedCount: generationResult.validatedCount,
                failedCount: generationResult.failedCount,
            },
            securityScan: {
                files: securityScanResults,
                summary: securitySummary,
            },
            message: scaffoldResult.message,
        });
    }
    catch (error) {
        console.error('[export] Per-file scaffold failed:', error);
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Per-file scaffold failed',
        });
    }
});
/**
 * POST /api/export/validate-path
 *
 * Check whether a custom output path can actually be created before the build
 * runs — catches the EACCES failure (e.g. /home/desktop on a root-owned /home)
 * up front so the user can pick a better location instead of a 500 mid-build.
 * Walks up to the nearest existing ancestor and tests write permission.
 */
exportRoutes.post('/validate-path', async (req, res) => {
    try {
        const rawPath = typeof req.body?.path === 'string' ? req.body.path.trim() : '';
        if (!rawPath) {
            return res.json({ success: true, writable: true, message: '' });
        }
        // Expand "~" / "~/..." to the user's home directory (same as the scaffolder).
        const expanded = rawPath === '~'
            ? os.homedir()
            : rawPath.startsWith('~/')
                ? path.join(os.homedir(), rawPath.slice(2))
                : rawPath;
        const resolved = path.resolve(expanded);
        // Walk up to the nearest existing ancestor.
        let ancestor = resolved;
        const missing = [];
        while (true) {
            try {
                await fs.access(ancestor);
                break;
            }
            catch {
                const parent = path.dirname(ancestor);
                if (parent === ancestor)
                    break;
                missing.unshift(path.basename(ancestor));
                ancestor = parent;
            }
        }
        // Test write permission on the existing ancestor.
        try {
            await fs.access(ancestor, fs.constants.W_OK);
            return res.json({
                success: true,
                writable: true,
                resolvedPath: resolved,
                missingDirs: missing,
            });
        }
        catch {
            return res.json({
                success: false,
                writable: false,
                resolvedPath: resolved,
                missingDirs: missing,
                message: `"${ancestor}" is not writable — use a path under your home directory (e.g. ~/Desktop/myapp) instead.`,
            });
        }
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Path validation failed',
        });
    }
});
/**
 * POST /api/export/open-folder
 *
 * Open an exported project folder in the system file manager
 * (xdg-open on Linux, `open` on macOS). Detached so the server never blocks.
 */
exportRoutes.post('/open-folder', async (req, res) => {
    try {
        const rawPath = typeof req.body?.path === 'string' ? req.body.path.trim() : '';
        if (!rawPath) {
            return res.status(400).json({ error: 'No path provided' });
        }
        const resolved = path.resolve(rawPath);
        try {
            await fs.access(resolved);
        }
        catch {
            return res.status(404).json({ error: `Path does not exist: ${resolved}` });
        }
        const opener = process.platform === 'darwin' ? 'open' : 'xdg-open';
        const child = spawn(opener, [resolved], { detached: true, stdio: 'ignore' });
        child.unref();
        res.json({ success: true, opened: resolved });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Open folder failed',
        });
    }
});
