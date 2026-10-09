/**
 * Experiments Routes — the idle micro-app experimenter's HTTP surface.
 * Exposes the self-improvement loop and its ideas database so it can be
 * inspected and triggered without digging into the log.
 */
import { Router } from 'express';
import { execFileSync } from 'child_process';
import path from 'path';
import { microExperimenter } from '../services/microExperimenterService.js';
import { idleMonitor } from '../services/idleMonitor.js';
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
export const experimentRoutes = Router();
// GET /api/experiments/status — loop config + live state (also powers a simple
// watchdog: idle, running, ideas count, last run outcome).
experimentRoutes.get('/status', (_req, res) => {
    res.json(microExperimenter.getStatus());
});
// GET /api/experiments — list every stored "new idea" (purpose, design, code,
// metrics). Envelope includes count. `?limit=` trims for big DBs.
experimentRoutes.get('/', (req, res) => {
    const limit = Number(req.query.limit) > 0 ? Number(req.query.limit) : Infinity;
    const ideas = microExperimenter.getIdeas();
    const shown = limit === Infinity ? ideas : ideas.slice(-limit);
    res.json({ count: ideas.length, ideas: shown });
});
// POST /api/experiments/run — run one experiment cycle now.
//   { force?: boolean, purpose?: string }  force=true (default) runs even
//   while not idle — used for manual/CI triggers. force=false mirrors the idle
//   gate. purpose selects one catalog entry (password checker, mini server, …)
//   instead of rotating to the next.
experimentRoutes.post('/run', async (req, res) => {
    const force = req.body?.force !== false;
    const purpose = typeof req.body?.purpose === 'string' && req.body.purpose.trim() ? req.body.purpose.trim() : undefined;
    try {
        const result = await microExperimenter.runExperiment(force, purpose);
        const status = result.ok ? 200 : 400;
        res.status(status).json(result);
    }
    catch (err) {
        res.status(500).json({ ok: false, error: err?.message || String(err) });
    }
});
// POST /api/experiments/build-catalog — build every micro-app in the catalog
// (the ten mock-up projects) in one go, checking each iteration and reporting
// a thumbs-up/thumbs-down per change.
//   { force?: boolean }  force=true builds even while not idle.
experimentRoutes.post('/build-catalog', async (req, res) => {
    const force = req.body?.force !== false;
    try {
        const results = await microExperimenter.runCatalog(force);
        res.json({ ok: true, count: results.length, results });
    }
    catch (err) {
        res.status(500).json({ ok: false, error: err?.message || String(err) });
    }
});
// POST /api/experiments/export-training — convert the ideas DB to training
// JSONL (training/dataset + Training Studio uploads dir), the SFT/corpus form.
experimentRoutes.post('/export-training', (_req, res) => {
    const out = microExperimenter.exportTrainingData();
    if ('error' in out) {
        res.status(400).json({ ok: false, error: out.error });
        return;
    }
    res.json({ ok: true, ...out });
});
// POST /api/experiments/export-orpo — turn stored (baseline → improved) ideas
// into ORPO preference pairs {instruction, chosen, rejected} so the loop feeds
// direct preference-tuning fuel. Pairs are also emitted live during every run.
experimentRoutes.post('/export-orpo', (_req, res) => {
    const out = microExperimenter.exportOrpoPairs();
    if ('error' in out) {
        res.status(400).json({ ok: false, error: out.error });
        return;
    }
    res.json({ ok: true, ...out });
});
// POST /api/experiments/index-rag — convert the verified winners into RAG
// training material: embed them into the FAISS vector store and emit a
// RAG-augmented training sheet (scripts/index-micro-ideas-to-rag.py).
// Soft no-op (ok:false) when sentence-transformers/faiss aren't installed.
experimentRoutes.post('/index-rag', (_req, res) => {
    const rag = runRagIndex();
    res.json(rag.ok ? { ok: true, ...rag } : { ok: false, ...rag });
});
// POST /api/experiments/compile — consolidate the current winners into the
// training inputs a SMALL incremental run needs, in one call:
//   - SFT/corpus sheet (export-training)
//   - ORPO preference pairs (export-orpo)
//   - RAG index + RAG-augmented sheet (index-rag)
// Compiling is safe and cheap; training itself stays on the project's existing
// small-quantity paths (MindSpace/engine incremental RNN or the LoRA/ORPO
// pipeline), which pick the emitted sheets up from the uploads dir.
experimentRoutes.post('/compile', (_req, res) => {
    const training = microExperimenter.exportTrainingData();
    const orpo = microExperimenter.exportOrpoPairs();
    res.json({
        ok: true,
        training: 'error' in training ? training : { file: training.file, count: training.count },
        orpo: 'error' in orpo ? orpo : { file: orpo.file, count: orpo.count },
        rag: runRagIndex(),
    });
});
/** Run the RAG-ingest python script and return its parsed JSON (safe). */
function runRagIndex() {
    try {
        const raw = execFileSync('python3', ['scripts/index-micro-ideas-to-rag.py'], { cwd: PROJECT_ROOT, encoding: 'utf-8', timeout: 300_000, stdio: 'pipe' });
        const last = raw.trim().split('\n').pop() || '{}';
        try {
            return JSON.parse(last);
        }
        catch {
            return { ok: false, error: raw.slice(0, 300) };
        }
    }
    catch (err) {
        return { ok: false, error: err?.message || String(err) };
    }
}
// GET /api/experiments/scaffold-variants — winning SCAFFOLD variants discovered
// by the self-improvement loop (mutated blueprints VACA may adopt).
experimentRoutes.get('/scaffold-variants', (_req, res) => {
    const ideas = microExperimenter.getScaffoldIdeas();
    res.json({ count: ideas.length, variants: ideas });
});
// POST /api/experiments/run-scaffold — run ONE scaffold experiment: build the
// incumbent blueprint and its mutated variants, and keep the best if it beats
// the incumbent on the adherence/smoke gates. Body: { force?, appType? }.
experimentRoutes.post('/run-scaffold', async (req, res) => {
    const force = req.body?.force !== false;
    const appType = typeof req.body?.appType === 'string' && req.body.appType.trim() ? req.body.appType.trim() : undefined;
    try {
        const result = await microExperimenter.runScaffoldExperiment(force, appType);
        res.status(result.error && !result.ok ? 400 : 200).json(result);
    }
    catch (err) {
        res.status(500).json({ ok: false, error: err?.message || String(err) });
    }
});
// POST /api/experiments/promote-scaffold — explicitly promote a REVIEWED
// scaffold variant into the live blueprints (overwrites the source blueprint,
// backing it up first). Body: { id }.
experimentRoutes.post('/promote-scaffold', (req, res) => {
    const id = typeof req.body?.id === 'string' ? req.body.id.trim() : '';
    if (!id) {
        res.status(400).json({ ok: false, error: 'Body requires { id }' });
        return;
    }
    const out = microExperimenter.promoteScaffoldIdea(id);
    res.status(out.ok ? 200 : 400).json(out);
});
// GET /api/experiments/activity — the idle monitor's raw signal (handy to
// confirm the detector is being fed by the middleware/socket hooks).
experimentRoutes.get('/activity', (_req, res) => {
    res.json({
        lastActivityAt: idleMonitor.lastActivityAt,
        lastSignal: idleMonitor.lastSignal,
        idle: idleMonitor.isIdle(),
        uptimeMs: idleMonitor.uptimeMs,
    });
});
