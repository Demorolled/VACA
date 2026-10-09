/**
 * Build-Ladder API — surfaces the training/operator build-ladder campaign in
 * the app so the 55 builds are visible and re-testable from the browser:
 *   GET  /api/build-ladder/state    → summary + all build results
 *   GET  /api/build-ladder/files/:id → kept failed-export file listing
 *   POST /api/build-ladder/retest/:id → re-run the acceptance test live
 *   GET  /api/build-ladder/dataset  → the round9 training dataset (jsonl)
 */
import { Router } from 'express';
import { execFile } from 'child_process';
import fs from 'fs';
import path from 'path';
const ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const OP_DIR = path.join(ROOT, 'training', 'operator');
function readJson(p) {
    try {
        return JSON.parse(fs.readFileSync(p, 'utf-8'));
    }
    catch {
        return null;
    }
}
export const buildLadderRoutes = Router();
buildLadderRoutes.get('/state', (_req, res) => {
    const state = readJson(path.join(OP_DIR, 'state.json'));
    const summary = readJson(path.join(OP_DIR, 'summary.json'));
    const fixesPath = path.join(OP_DIR, 'datasheet-fixes.jsonl');
    let fixes = [];
    if (fs.existsSync(fixesPath)) {
        fixes = fs.readFileSync(fixesPath, 'utf-8').split('\n').filter(Boolean).map(l => {
            try {
                return JSON.parse(l);
            }
            catch {
                return null;
            }
        }).filter(Boolean);
    }
    if (!state || !summary) {
        return res.status(404).json({ error: 'build-ladder state not found — run training/operator/run_operator.py first' });
    }
    const builds = Object.values(state.done ?? {}).sort((a, b) => String(a.id).localeCompare(String(b.id)));
    res.json({ summary, builds, fixes, updated: new Date().toISOString() });
});
const BUILD_ID_RE = /^[seh]\d{2}$/;
buildLadderRoutes.get('/files/:id', (req, res) => {
    const id = String(req.params.id);
    if (!BUILD_ID_RE.test(id)) {
        return res.status(400).json({ error: 'invalid build id' });
    }
    const dir = path.join(OP_DIR, 'dataset', 'failed', id);
    if (!fs.existsSync(dir)) {
        return res.status(404).json({ error: `no kept export for ${id}` });
    }
    const files = [];
    for (const f of fs.readdirSync(dir)) {
        const fp = path.join(dir, f);
        if (!fs.statSync(fp).isFile())
            continue;
        let content = '';
        try {
            content = fs.readFileSync(fp, 'utf-8').slice(0, 8000);
        }
        catch {
            content = '(binary/read error)';
        }
        files.push({ path: f, content, size: fs.statSync(fp).size });
    }
    res.json({ id: req.params.id, files });
});
buildLadderRoutes.post('/retest/:id', (req, res) => {
    const id = String(req.params.id);
    if (!BUILD_ID_RE.test(id)) {
        return res.status(400).json({ error: 'invalid build id' });
    }
    const script = path.join(OP_DIR, 'retest_one.py');
    if (!fs.existsSync(script)) {
        return res.status(500).json({ error: 'retest_one.py missing' });
    }
    execFile('python3', [script, id], { timeout: 180_000, maxBuffer: 4 * 1024 * 1024 }, (err, stdout) => {
        if (err) {
            return res.status(500).json({ error: String(err.message || err).slice(0, 500) });
        }
        try {
            res.json(JSON.parse(stdout));
        }
        catch {
            res.status(500).json({ error: 'retest script returned invalid JSON', raw: stdout.slice(0, 500) });
        }
    });
});
buildLadderRoutes.get('/dataset', (_req, res) => {
    const p = path.join(OP_DIR, 'dataset', 'round9-buildladder.jsonl');
    if (!fs.existsSync(p)) {
        return res.status(404).json({ error: 'dataset not found' });
    }
    res.type('text/plain').send(fs.readFileSync(p, 'utf-8'));
});
