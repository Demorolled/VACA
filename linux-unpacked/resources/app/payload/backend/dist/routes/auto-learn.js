/**
 * Auto-Learning API Routes
 * =======================
 *
 * Endpoints for the frontend (and other components) to:
 *   - Push interactions to be captured as training data
 *   - Query learning status and statistics
 *   - View captured training data files
 *   - Force-flush or reset the learning buffer
 */
import { Router } from 'express';
import { autoLearnService } from '../services/autoLearnService.js';
const router = Router();
/**
 * POST /api/auto-learn/record
 * Record a single interaction for training.
 * Body: { type, content, user?, metadata? }
 */
router.post('/record', (req, res) => {
    try {
        const { type, content, user, metadata = {} } = req.body;
        if (!type || !content) {
            return res.status(400).json({ error: 'type and content are required' });
        }
        const record = autoLearnService.record({
            type,
            content,
            user: user || 'anonymous',
            metadata,
            source: req.headers['x-source'] || 'api',
        });
        res.json({ success: true, id: record.id });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * POST /api/auto-learn/conversation
 * Record a conversation interaction (prompt + response).
 * Body: { prompt, response, user?, metadata? }
 */
router.post('/conversation', (req, res) => {
    try {
        const { prompt, response, user, metadata = {} } = req.body;
        if (!prompt || !response) {
            return res.status(400).json({ error: 'prompt and response are required' });
        }
        const record = autoLearnService.recordConversation(prompt, response, user, metadata);
        res.json({ success: true, id: record.id });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * POST /api/auto-learn/code-generation
 * Record generated code.
 * Body: { nodeLabel, language, code, user?, metadata? }
 */
router.post('/code-generation', (req, res) => {
    try {
        const { nodeLabel, language, code, user, metadata = {} } = req.body;
        if (!code) {
            return res.status(400).json({ error: 'code is required' });
        }
        const record = autoLearnService.recordCodeGeneration(nodeLabel || 'unknown', language || 'typescript', code, user, metadata);
        res.json({ success: true, id: record.id });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * POST /api/auto-learn/design-save
 * Record a design save.
 * Body: { projectName, nodeCount, code, user? }
 */
router.post('/design-save', (req, res) => {
    try {
        const { projectName, nodeCount, code, user } = req.body;
        const record = autoLearnService.recordDesignSave(projectName || 'unnamed', nodeCount || 0, code || '', user);
        res.json({ success: true, id: record.id });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * POST /api/auto-learn/terminal
 * Record a terminal message.
 * Body: { message, role, user? }
 */
router.post('/terminal', (req, res) => {
    try {
        const { message, role, user } = req.body;
        if (!message) {
            return res.status(400).json({ error: 'message is required' });
        }
        const record = autoLearnService.recordTerminalMessage(message, role || 'user', user);
        res.json({ success: true, id: record.id });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * GET /api/auto-learn/status
 * Get learning service status and statistics.
 */
router.get('/status', (_req, res) => {
    try {
        const status = autoLearnService.getStatus();
        res.json({ success: true, ...status });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * GET /api/auto-learn/data-files
 * Get list of captured training data files.
 */
router.get('/data-files', (_req, res) => {
    try {
        const files = autoLearnService.getTrainingDataFiles();
        res.json({ success: true, files, count: files.length });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * POST /api/auto-learn/flush
 * Force-flush the interaction buffer to disk.
 */
router.post('/flush', (_req, res) => {
    try {
        const count = autoLearnService.forceFlush();
        res.json({ success: true, flushed: count });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * POST /api/auto-learn/reset
 * Reset all captured learning data (caution: destructive).
 */
router.post('/reset', (_req, res) => {
    try {
        autoLearnService.reset();
        res.json({ success: true, message: 'Auto-learning data reset' });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * POST /api/auto-learn/import
 * Import all existing training data from the training studio uploads,
 * MindSpace trainer datasheets, growth datasheets, and knowledge store
 * into the auto-learning pipeline so past interactions count too.
 * Returns { totalImported, sourceCounts }.
 */
router.post('/import', (_req, res) => {
    try {
        const result = autoLearnService.importExistingData();
        const { totalImported, sourceCounts } = result;
        res.json({
            success: true,
            totalImported,
            sourceCounts,
            message: totalImported > 0
                ? `Imported ${totalImported} existing records from ${Object.keys(sourceCounts).length} sources`
                : 'No existing data found to import',
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
export { router as autoLearnRoutes };
// ─── Reminder for the author: register new routes in backend/src/index.ts ─
// App name: autoLearnRoutes  |  Prefix: /api/auto-learn  |  Already wired
