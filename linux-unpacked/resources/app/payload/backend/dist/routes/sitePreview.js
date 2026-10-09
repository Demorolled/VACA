/**
 * Dropped-Site Preview Routes
 * ===========================
 * Serve a dropped folder (from the browser FileSystem API) as a real static
 * website so the user can play it in the Live Preview floating window.
 *
 *   POST /api/preview/site       — Save dropped files ({ files: [{path, content}] })
 *                                  to a per-id temp dir; returns { url, id }
 *   GET  /api/preview/site/:id   — Serve index.html (or redirect to it)
 *   GET  /api/preview/site/:id/* — Serve any file from that site
 *
 * Path traversal is blocked: every saved and served path is normalized and
 * validated to stay inside the site's root directory.
 */
import { Router } from 'express';
import path from 'path';
import fs from 'fs';
import { randomUUID } from 'crypto';
import { tmpdir } from 'os';
import { sanitizeSiteRelPath, mimeForPath, resolveSitePreviewPath } from '../utils/sitePreviewPaths.js';
const PREVIEW_ROOT = path.join(tmpdir(), 'vaca-site-previews');
try {
    fs.mkdirSync(PREVIEW_ROOT, { recursive: true });
}
catch { /* exists */ }
// TTL sweep: drop preview dirs older than 24h on startup (tmpdir usually clears
// on reboot anyway, this keeps long-running servers tidy).
try {
    const DAY_MS = 24 * 60 * 60 * 1000;
    const now = Date.now();
    for (const entry of fs.readdirSync(PREVIEW_ROOT)) {
        const dir = path.join(PREVIEW_ROOT, entry);
        try {
            const stat = fs.statSync(dir);
            if (stat.isDirectory() && now - stat.mtimeMs > DAY_MS) {
                fs.rmSync(dir, { recursive: true, force: true });
            }
        }
        catch { /* ignore */ }
    }
}
catch { /* ignore */ }
export const sitePreviewRoutes = Router();
// ═══════════════════════════════════════════════════════════════════════════
// POST /api/preview/site — save dropped files
// ═══════════════════════════════════════════════════════════════════════════
sitePreviewRoutes.post('/site', (req, res) => {
    try {
        const { files } = req.body;
        if (!Array.isArray(files) || files.length === 0) {
            return void res.status(400).json({ success: false, error: 'files array is required' });
        }
        const MAX_FILES = 300;
        const MAX_TOTAL_BYTES = 8 * 1024 * 1024; // ~8mb of text content (json limit is 10mb)
        const id = randomUUID().slice(0, 8);
        const siteDir = path.join(PREVIEW_ROOT, id);
        fs.mkdirSync(siteDir, { recursive: true });
        let written = 0;
        let skipped = 0;
        let totalBytes = 0;
        for (const f of files.slice(0, MAX_FILES)) {
            const rel = sanitizeSiteRelPath(f?.path);
            if (!rel) {
                skipped++;
                continue;
            }
            const content = String(f?.content ?? '');
            // Cumulative size guard: skip files once we've stored ~8mb total.
            if (totalBytes + content.length > MAX_TOTAL_BYTES) {
                skipped++;
                continue;
            }
            const dest = path.join(siteDir, rel);
            // Belt-and-braces: ensure the resolved dest stays inside siteDir.
            if (!dest.startsWith(siteDir + path.sep)) {
                skipped++;
                continue;
            }
            fs.mkdirSync(path.dirname(dest), { recursive: true });
            fs.writeFileSync(dest, content, 'utf-8');
            totalBytes += content.length;
            written++;
        }
        const hasIndex = fs.existsSync(path.join(siteDir, 'index.html')) || fs.existsSync(path.join(siteDir, 'index.htm'));
        if (written === 0 || !hasIndex) {
            fs.rmSync(siteDir, { recursive: true, force: true });
            return void res.status(400).json({
                success: false,
                error: 'No index.html found in the dropped files — nothing to preview as a web app.',
                written,
                skipped,
            });
        }
        console.log(`[preview-site] Saved ${written} file(s) as site ${id} (skipped ${skipped})`);
        res.json({ success: true, id, url: `/api/preview/site/${id}/`, written, skipped });
    }
    catch (err) {
        console.error('[preview-site] Save failed:', err);
        res.status(500).json({ success: false, error: err?.message || 'Failed to save preview site' });
    }
});
// ═══════════════════════════════════════════════════════════════════════════
// GET /api/preview/site/:id[/path] — serve static files
// ═══════════════════════════════════════════════════════════════════════════
function serveFileFromSite(res, siteDir, relPath) {
    const filePath = resolveSitePreviewPath(siteDir, relPath);
    if (!filePath || !fs.existsSync(filePath)) {
        res.status(404).json({ error: 'Not found in preview site' });
        return;
    }
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
        // Directory URL (e.g. /site/:id/tools/ or a bare dir link) → serve its index.
        const index = fs.existsSync(path.join(filePath, 'index.html')) ? 'index.html' : 'index.htm';
        if (!index) {
            res.status(404).json({ error: 'Directory has no index.html' });
            return;
        }
        return void serveFileFromSite(res, siteDir, path.join(relPath, index));
    }
    if (!stat.isFile()) {
        res.status(404).json({ error: 'Not found in preview site' });
        return;
    }
    const csp = [
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:",
        "img-src 'self' data: blob:",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' data: https://fonts.gstatic.com",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
        "connect-src 'self'",
    ].join('; ');
    res.setHeader('Content-Security-Policy', csp);
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Content-Type', mimeForPath(filePath));
    res.sendFile(filePath);
}
/** GET /api/preview/site/:id — bare id: serve index.html (fall back to index.htm) */
sitePreviewRoutes.get('/site/:id', (req, res) => {
    const { id } = req.params;
    if (!/^[a-f0-9]{8}$/i.test(id || ''))
        return void res.status(400).json({ error: 'Bad preview id' });
    const siteDir = path.join(PREVIEW_ROOT, id);
    if (!fs.existsSync(siteDir))
        return void res.status(404).json({ error: 'Preview not found or expired' });
    const index = fs.existsSync(path.join(siteDir, 'index.html')) ? 'index.html' : 'index.htm';
    serveFileFromSite(res, siteDir, index);
});
/** GET /api/preview/site/:id/* — any file path under the site */
sitePreviewRoutes.get('/site/:id/*', (req, res) => {
    const { id } = req.params;
    const wildcard = req.params['0'] || '';
    if (!/^[a-f0-9]{8}$/i.test(id || ''))
        return void res.status(400).json({ error: 'Bad preview id' });
    const siteDir = path.join(PREVIEW_ROOT, id);
    if (!fs.existsSync(siteDir))
        return void res.status(404).json({ error: 'Preview not found or expired' });
    if (!wildcard)
        return void serveFileFromSite(res, siteDir, 'index.html');
    serveFileFromSite(res, siteDir, wildcard);
});
