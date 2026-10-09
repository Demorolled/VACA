import { Router } from 'express';
import { exec, execSync } from 'child_process';
import { readFileSync, existsSync, writeFileSync, readdirSync, statSync } from 'fs';
import path from 'path';
import http from 'http';
const router = Router();
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const PROJECT_ROOT = path.resolve(BACKEND_DIR, '..');
const TRAINING_APP_DIR = path.join(PROJECT_ROOT, 'llm-training-app');
const WEB_LAUNCH_SCRIPT = path.join(TRAINING_APP_DIR, 'launch-web.sh');
const TRAINING_PORT = 8001;
// Track the web server process
let webServerProcess = null;
// Clean up the child process when the Express server shuts down
function cleanupWebServer() {
    if (webServerProcess && !webServerProcess.killed) {
        try {
            webServerProcess.kill('SIGTERM');
        }
        catch { }
        webServerProcess = null;
    }
}
process.on('exit', cleanupWebServer);
process.on('SIGTERM', cleanupWebServer);
process.on('SIGINT', cleanupWebServer);
function probeTrainingServer() {
    return new Promise((resolve) => {
        const req = http.get(`http://localhost:${TRAINING_PORT}/api/status`, (res) => {
            let body = '';
            res.on('data', (chunk) => { body += chunk; });
            res.on('end', () => {
                try {
                    const data = JSON.parse(body);
                    resolve(!!data.status);
                }
                catch {
                    resolve(false);
                }
            });
        });
        req.on('error', () => resolve(false));
        req.setTimeout(2000, () => { req.destroy(); resolve(false); });
    });
}
router.post('/open', async (_req, res) => {
    try {
        // Step 1: Probe port 8000 to see if Training Studio is already running
        const alreadyRunning = await probeTrainingServer();
        if (alreadyRunning) {
            try {
                execSync(`xdg-open http://localhost:${TRAINING_PORT}`, { timeout: 3000 });
            }
            catch { /* xdg-open may not be available */ }
            res.json({ status: 'launched', mode: 'web', port: TRAINING_PORT, message: `Training Studio is running at http://localhost:${TRAINING_PORT}` });
            return;
        }
        // Step 2: Ensure launch script is executable
        try {
            execSync(`chmod +x "${WEB_LAUNCH_SCRIPT}"`, { timeout: 2000 });
        }
        catch { /* ignore */ }
        // Step 3: Launch the web-based training studio (FastAPI + uvicorn)
        const proc = exec(`"${WEB_LAUNCH_SCRIPT}"`, {
            cwd: TRAINING_APP_DIR,
            env: { ...process.env },
        });
        webServerProcess = proc;
        let started = false;
        proc.stdout?.on('data', (data) => {
            console.log('[training-web]', data.toString().trim());
            if (!started && data.toString().includes('Uvicorn running')) {
                started = true;
                try {
                    execSync(`xdg-open http://localhost:${TRAINING_PORT}`, { timeout: 3000 });
                }
                catch { }
                res.json({ status: 'launched', mode: 'web', port: TRAINING_PORT, message: `LLM Training Studio launched at http://localhost:${TRAINING_PORT}` });
            }
        });
        proc.stderr?.on('data', (data) => {
            const msg = data.toString();
            console.error('[training-web]', msg);
            if (!started && (msg.includes('Uvicorn running') || msg.includes('Started server') || msg.includes('listen'))) {
                started = true;
                try {
                    execSync(`xdg-open http://localhost:${TRAINING_PORT}`, { timeout: 3000 });
                }
                catch { }
                res.json({ status: 'launched', mode: 'web', port: TRAINING_PORT, message: `LLM Training Studio launched at http://localhost:${TRAINING_PORT}` });
            }
        });
        proc.on('error', (err) => {
            console.error('[training-web] Process error:', err.message);
            if (!started) {
                started = true;
                openFolderFallback(res);
            }
        });
        proc.on('exit', (code) => {
            if (!started) {
                started = true;
                console.warn(`[training-web] launch-web.sh exited with code ${code}`);
                openFolderFallback(res);
            }
        });
        // Safety timeout - reduced to 5 seconds for faster feedback
        setTimeout(() => {
            if (!started) {
                started = true;
                console.warn('[training-web] Launch timeout - opening folder instead');
                try {
                    execSync(`xdg-open "${TRAINING_APP_DIR}"`, { timeout: 3000 });
                }
                catch { }
                res.json({ status: 'folder-opened', mode: 'folder', path: TRAINING_APP_DIR, message: `Training Studio web server could not start. Opened folder at ${TRAINING_APP_DIR}` });
            }
        }, 5000);
    }
    catch (err) {
        console.error('[training-web] Route error:', err.message);
        openFolderFallback(res);
    }
});
function openFolderFallback(res) {
    try {
        // Try to open the directory in file manager
        try {
            execSync(`xdg-open "${TRAINING_APP_DIR}"`, { timeout: 3000 });
            res.json({
                status: 'folder-opened',
                path: TRAINING_APP_DIR,
                mode: 'folder',
                message: 'Desktop app could not launch (Python compatibility issue). Opened the training folder instead.'
            });
        }
        catch {
            // xdg-open may not be available
            res.json({
                status: 'path-returned',
                path: TRAINING_APP_DIR,
                mode: 'path',
                message: 'Training studio folder: ' + TRAINING_APP_DIR
            });
        }
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
}
// Generate a training datasheet from knowledge patterns
router.post('/generate-datasheet', (_req, res) => {
    try {
        const knowledgePatternsPath = path.join(BACKEND_DIR, 'knowledge', 'patterns.json');
        const uploadsDir = path.join(TRAINING_APP_DIR, 'data', 'uploads');
        // Ensure uploads directory exists
        execSync(`mkdir -p "${uploadsDir}"`, { timeout: 2000 });
        let patterns = [];
        try {
            if (existsSync(knowledgePatternsPath)) {
                patterns = JSON.parse(readFileSync(knowledgePatternsPath, 'utf-8'));
            }
        }
        catch { /* no patterns file */ }
        if (patterns.length === 0) {
            res.json({ status: 'no-data', message: 'No knowledge patterns found to generate datasheet.' });
            return;
        }
        // Generate a consolidated training JSONL file
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `training-datasheet-${timestamp}.jsonl`;
        const filepath = path.join(uploadsDir, filename);
        const lines = patterns.map(p => JSON.stringify({
            text: p.code || '',
            title: p.title || 'Untitled Pattern',
            language: p.language || 'unknown',
            nodeType: p.nodeType || 'generic',
            tags: p.tags || [],
            source: 'knowledge-base',
            timestamp: p.createdAt || new Date().toISOString(),
            category: p.category || 'code_pattern',
            qualityScore: p.qualityScore || 5,
        })).join('\n');
        writeFileSync(filepath, lines, 'utf-8');
        // Also update metadata.json to pre-import these files
        const metadataPath = path.join(TRAINING_APP_DIR, 'data', 'metadata.json');
        let metadata = { files: {}, training_queue: [], epochs: 3, model_metrics: {}, training_history: [], experiments: {} };
        try {
            if (existsSync(metadataPath)) {
                metadata = JSON.parse(readFileSync(metadataPath, 'utf-8'));
            }
        }
        catch { }
        // Rebuild metadata files from all uploads
        try {
            const uploadFiles = readdirSync(uploadsDir);
            metadata.files = {};
            metadata.training_queue = [];
            for (const fname of uploadFiles) {
                if (fname.endsWith('.jsonl')) {
                    const fileId = `file_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
                    const fpath = path.join(uploadsDir, fname);
                    const stats = statSync(fpath);
                    metadata.files[fileId] = {
                        id: fileId,
                        name: fname,
                        saved_name: fname,
                        category: 'Ready for Training',
                        themes: ['training-data', 'code-patterns'],
                        size: stats.size,
                        content_preview: `Training dataset: ${fname} (${(stats.size / 1024).toFixed(1)} KB)`,
                        uploaded_at: new Date().toISOString(),
                        in_queue: true,
                    };
                    metadata.training_queue.push(fileId);
                }
            }
        }
        catch { }
        writeFileSync(metadataPath, JSON.stringify(metadata, null, 2), 'utf-8');
        console.log(`[training] Generated training datasheet: ${filename} (${patterns.length} patterns, ${Object.keys(metadata.files).length} total files queued)`);
        res.json({
            status: 'datasheet-generated',
            filename,
            patterns_count: patterns.length,
            total_files: Object.keys(metadata.files).length,
            filepath,
            message: `Training datasheet created with ${patterns.length} patterns and ${Object.keys(metadata.files).length} files pre-loaded into the studio queue.`
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// POST /api/training/generate-datasheet-from-design — generate training data from a completed design
router.post('/generate-datasheet-from-design', async (req, res) => {
    try {
        const { design } = req.body;
        if (!design || !design.nodes) {
            res.status(400).json({ error: 'Design with nodes required' });
            return;
        }
        const uploadsDir = path.join(TRAINING_APP_DIR, 'data', 'uploads');
        execSync(`mkdir -p "${uploadsDir}"`, { timeout: 2000 });
        const lines = design.nodes.map((n) => JSON.stringify({
            text: n.generatedCode || n.description || '',
            title: n.label || 'Untitled Node',
            language: n.language || 'typescript',
            nodeType: n.type || 'generic',
            tags: [n.type, n.label?.toLowerCase().replace(/\s+/g, '-')].filter(Boolean),
            source: 'design-export',
            timestamp: new Date().toISOString(),
            category: 'node_design',
            qualityScore: 5,
        })).join('\n');
        if (!lines.trim()) {
            res.json({ status: 'no-data', message: 'No code in design nodes to generate datasheet.' });
            return;
        }
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const designName = (design.name || 'design').replace(/[^a-zA-Z0-9_-]/g, '_');
        const filename = `design-${designName}-${timestamp}.jsonl`;
        writeFileSync(path.join(uploadsDir, filename), lines, 'utf-8');
        const metadataPath = path.join(TRAINING_APP_DIR, 'data', 'metadata.json');
        let metadata = { files: {}, training_queue: [], epochs: 3, model_metrics: {}, training_history: [], experiments: {} };
        try {
            if (existsSync(metadataPath)) {
                metadata = JSON.parse(readFileSync(metadataPath, 'utf-8'));
            }
        }
        catch { }
        const fileId = `file_${Date.now()}`;
        metadata.files[fileId] = {
            id: fileId, name: filename, saved_name: filename,
            category: 'Design Export',
            themes: ['design', designName],
            size: Buffer.byteLength(lines),
            content_preview: `Design: ${designName} (${design.nodes.length} nodes)`,
            uploaded_at: new Date().toISOString(),
            in_queue: true,
        };
        metadata.training_queue.push(fileId);
        writeFileSync(metadataPath, JSON.stringify(metadata, null, 2), 'utf-8');
        res.json({
            status: 'datasheet-generated',
            filename,
            nodes_count: design.nodes.length,
            message: `Training datasheet created for design "${design.name}" with ${design.nodes.length} node patterns.`,
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// GET /api/training/growth-datasheets — load learning-is-growth datasheets into the training queue
router.get('/growth-datasheets', (_req, res) => {
    try {
        const datasheetsDir = path.join(PROJECT_ROOT, 'datasheets growth');
        const uploadsDir = path.join(TRAINING_APP_DIR, 'data', 'uploads');
        execSync(`mkdir -p "${uploadsDir}"`, { timeout: 2000 });
        if (!existsSync(datasheetsDir)) {
            res.json({ status: 'no-datasheets', message: 'datasheets growth folder not found.' });
            return;
        }
        const files = readdirSync(datasheetsDir).filter(f => f.endsWith('.jsonl'));
        if (files.length === 0) {
            res.json({ status: 'no-datasheets', message: 'No datasheet files found in datasheets growth/.' });
            return;
        }
        // Copy each datasheet to the training uploads and build metadata
        const metadataPath = path.join(TRAINING_APP_DIR, 'data', 'metadata.json');
        let metadata = { files: {}, training_queue: [], epochs: 3, model_metrics: {}, training_history: [], experiments: {} };
        try {
            if (existsSync(metadataPath)) {
                metadata = JSON.parse(readFileSync(metadataPath, 'utf-8'));
            }
        }
        catch { }
        const imported = [];
        for (const fname of files) {
            const src = path.join(datasheetsDir, fname);
            const dst = path.join(uploadsDir, fname);
            const content = readFileSync(src, 'utf-8');
            const lineCount = content.trim().split('\n').filter(Boolean).length;
            writeFileSync(dst, content, 'utf-8');
            if (!Object.values(metadata.files).some((f) => f.name === fname)) {
                const fileId = `growth_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
                metadata.files[fileId] = {
                    id: fileId,
                    name: fname,
                    saved_name: fname,
                    category: 'Growth Mindset',
                    themes: ['learning-is-growth', 'growth-mindset', 'training'],
                    size: content.length,
                    content_preview: `Growth mindset training: ${fname.replace('.jsonl', '')} (${lineCount} examples)`,
                    uploaded_at: new Date().toISOString(),
                    in_queue: true,
                };
                metadata.training_queue.push(fileId);
            }
            imported.push(fname);
        }
        writeFileSync(metadataPath, JSON.stringify(metadata, null, 2), 'utf-8');
        res.json({
            status: 'imported',
            files: imported,
            total_examples: files.length,
            queue_size: metadata.training_queue.length,
            message: `Loaded ${imported.length} growth mindset datasheets (${files.length} total) into the training queue. Learning is growth!`,
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
router.get('/status', (_req, res) => {
    res.json({ status: 'standalone', path: TRAINING_APP_DIR });
});
export { router as trainingRoutes };
