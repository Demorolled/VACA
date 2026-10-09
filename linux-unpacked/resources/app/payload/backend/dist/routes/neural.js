import { Router } from 'express';
import { rnnEngine } from '../neural/trainer.js';
import { getSyncStatus, checkAndSync, forceSync } from '../neural/syncManager.js';
import { knowledgeStore } from '../knowledge/knowledgeStore.js';
const router = Router();
// Get model status
router.get('/', (_req, res) => {
    const status = rnnEngine.getStatus();
    res.json(status);
});
// Initialize a fresh model
router.post('/init', (_req, res) => {
    try {
        rnnEngine.initModel();
        res.json({ success: true, status: rnnEngine.getStatus() });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// Train the model on knowledge patterns
router.post('/train', async (req, res) => {
    try {
        const iterations = req.body.iterations || 500;
        if (rnnEngine.isTraining) {
            return res.status(409).json({ error: 'Model is already training' });
        }
        const result = await rnnEngine.train(iterations);
        res.json({
            success: true,
            loss: result.loss,
            charsTrained: result.chars,
            status: rnnEngine.getStatus(),
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// Learn from current knowledge patterns
router.post('/learn', async (req, res) => {
    try {
        const iterations = req.body.iterations || 200;
        if (rnnEngine.isTraining) {
            return res.status(409).json({ error: 'Model is already training' });
        }
        const result = await rnnEngine.learnFromKnowledge(iterations);
        res.json({
            success: true,
            loss: result.loss,
            charsTrained: result.chars,
            status: rnnEngine.getStatus(),
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// Generate code from the model
router.post('/generate', (req, res) => {
    try {
        const seedText = req.body.seed || 'function';
        const length = req.body.length || 200;
        const temperature = req.body.temperature ?? 0.8;
        const generated = rnnEngine.generate(seedText, length, temperature);
        res.json({ success: true, generated, seedText, length, temperature });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// Test the model's understanding - compute perplexity on validation data
router.post('/test', (req, res) => {
    try {
        const status = rnnEngine.getStatus();
        if (!status.initialized || !status.loss) {
            return res.json({ trained: false, message: 'Model not trained yet' });
        }
        const loss = status.loss;
        const vocabSize = status.vocabSize || 1;
        const perplexity = Math.exp(loss / status.seqLength || 64);
        const randomPerplexity = Math.exp(Math.log(vocabSize));
        const understandingPct = Math.max(0, Math.min(100, ((randomPerplexity - perplexity) / randomPerplexity) * 100));
        res.json({
            success: true,
            trained: true,
            loss,
            perplexity: parseFloat(perplexity.toFixed(4)),
            randomPerplexity: parseFloat(randomPerplexity.toFixed(4)),
            understandingScore: parseFloat(understandingPct.toFixed(2)),
            charsTrained: status.trainedChars,
            iterations: status.iterations,
            patternsLearned: status.patternCount,
            status: understandingPct > 10 ? 'learning' : (status.iterations > 0 ? 'starting' : 'untrained'),
            message: understandingPct > 10
                ? 'Model is learning code patterns'
                : 'Model needs more training data and iterations',
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// Save model
router.post('/save', (_req, res) => {
    try {
        rnnEngine.saveModel();
        res.json({ success: true, message: 'Model saved' });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/** GET /sheet - Get current training sheet info */
router.get('/sheet', (_req, res) => {
    const patterns = knowledgeStore.getAll();
    const count = knowledgeStore.count();
    const sheetNum = knowledgeStore.getCurrentSheet();
    const cap = 100;
    const pct = ((count / cap) * 100).toFixed(1);
    res.json({
        currentSheet: sheetNum,
        patternCount: count,
        sheetCap: cap,
        fillPercent: pct,
        remaining: cap - count,
        archiveDue: count >= cap,
        message: count >= cap
            ? `Sheet #${sheetNum} is full! Archiving...`
            : `Sheet #${sheetNum}: ${count}/${cap} patterns (${pct}%)`,
    });
});
/** POST /sheet/archive - Manually trigger sheet archive now */
router.post('/sheet/archive', (_req, res) => {
    try {
        const result = knowledgeStore.archiveCurrentSheet();
        if (result) {
            res.json({
                success: true,
                sheetNumber: result.sheetNumber,
                patternCount: result.patternCount,
                exportPath: result.exportPath,
                newSheet: knowledgeStore.getCurrentSheet(),
                message: `Archived ${result.patternCount} patterns from sheet #${result.sheetNumber} to Training Studio`,
            });
        }
        else {
            res.json({ success: false, message: 'No patterns to archive' });
        }
    }
    catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});
/** GET /sync - Get sync status and current training data size */
router.get('/sync', (_req, res) => {
    res.json(getSyncStatus());
});
/** POST /sync - Check threshold and sync to Training Studio if needed */
router.post('/sync', (_req, res) => {
    const result = checkAndSync();
    if (result.thresholdReached && result.lastSyncResult === 'synced') {
        res.json({ ...result, message: 'Auto-synced ' + result.totalSize + ' of training data to LLM Training Studio' });
    }
    else if (result.thresholdReached) {
        res.json({ ...result, message: 'Data is ' + result.totalSize + ' - threshold reached but sync pending' });
    }
    else {
        res.json({ ...result, message: 'Training data is ' + result.totalSize + ' (' + result.thresholdPercent + '% of 50 MB threshold). Keep building!' });
    }
});
/** POST /sync/force - Force immediate export to Training Studio regardless of size */
router.post('/sync/force', (_req, res) => {
    const result = forceSync();
    if (result.success) {
        res.json({ success: true, path: result.path, message: result.message, totalSize: getSyncStatus().totalSize });
    }
    else {
        res.status(500).json({ success: false, message: result.message });
    }
});
export default router;
