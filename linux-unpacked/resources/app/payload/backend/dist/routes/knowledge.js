import { Router } from 'express';
import { knowledgeStore } from '../knowledge/knowledgeStore.js';
import { learningEngine } from '../knowledge/learningEngine.js';
import * as path from 'path';
import * as fs from 'fs';
import { gunzipSync } from 'zlib';
const router = Router();
// Get dashboard stats (aggregated from knowledge + neural systems)
router.get('/stats', (req, res) => {
    try {
        // knowledgeStore already imported at top
        const patterns = knowledgeStore.getAll();
        // Count by language
        const byLanguage = {};
        // Count by node type
        const byNodeType = {};
        // Count by tag
        const byTag = {};
        for (const p of patterns) {
            byLanguage[p.language] = (byLanguage[p.language] || 0) + 1;
            byNodeType[p.nodeType] = (byNodeType[p.nodeType] || 0) + 1;
            for (const tag of p.tags) {
                byTag[tag] = (byTag[tag] || 0) + 1;
            }
        }
        // Try to get neural status
        let neuralStatus = null;
        try {
            // path already imported at top
            const modelPath = path.join(process.cwd(), 'knowledge', 'rnn-model.json');
            // fs already imported at top
            if (fs.existsSync(modelPath)) {
                const raw = fs.readFileSync(modelPath);
                let parsed;
                try {
                    parsed = JSON.parse(gunzipSync(raw).toString('utf-8'));
                }
                catch {
                    parsed = JSON.parse(raw.toString('utf-8'));
                }
                const modelData = parsed;
                neuralStatus = {
                    loss: modelData.model?.smoothLoss || null,
                    iterations: modelData.model?.iter || 0,
                    trainedChars: modelData.trainedChars || 0,
                };
            }
        }
        catch { }
        res.json({
            patterns: {
                total: patterns.length,
                byLanguage,
                byNodeType,
                byTag,
                averageQuality: patterns.length > 0
                    ? (patterns.reduce((s, p) => s + (p.qualityScore || 0), 0) / patterns.length).toFixed(1)
                    : 0,
            },
            neural: neuralStatus
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// Get all patterns
router.get('/', (_req, res) => {
    const patterns = knowledgeStore.getAll();
    res.json({ count: patterns.length, patterns });
});
// Query patterns with filters
router.post('/query', (req, res) => {
    const query = req.body;
    const results = knowledgeStore.query(query);
    res.json({ count: results.length, patterns: results });
});
// Get a specific pattern by ID
router.get('/:id', (req, res) => {
    const pattern = knowledgeStore.getById(req.params.id);
    if (!pattern) {
        return res.status(404).json({ error: 'Pattern not found' });
    }
    res.json(pattern);
});
// Add a new pattern manually
router.post('/', (req, res) => {
    const { category, title, code, description, tags, projectId, targetOS, nodeType, language } = req.body;
    if (!title || !code) {
        return res.status(400).json({ error: 'Title and code are required' });
    }
    const pattern = knowledgeStore.addPattern({
        category: category || 'code_pattern',
        title,
        code,
        description: description || '',
        tags: tags || [],
        projectId: projectId || '',
        targetOS: targetOS || 'linux',
        nodeType: nodeType || 'logic',
        language: language || 'javascript',
        success: true,
        qualityScore: 5.0,
    });
    if (!pattern) {
        return res.status(422).json({ error: 'Pattern rejected (capture disabled or content failed the quality gate)' });
    }
    res.status(201).json(pattern);
});
// Record usage of a pattern (increment counter)
router.post('/:id/use', (req, res) => {
    const pattern = knowledgeStore.getById(req.params.id);
    if (!pattern) {
        return res.status(404).json({ error: 'Pattern not found' });
    }
    knowledgeStore.usePattern(req.params.id);
    res.json({ success: true, usageCount: pattern.usageCount + 1 });
});
// Rate/update quality of a pattern
router.put('/:id/rate', (req, res) => {
    const { score } = req.body;
    if (typeof score !== 'number' || score < 0 || score > 10) {
        return res.status(400).json({ error: 'Score must be a number between 0 and 10' });
    }
    const pattern = knowledgeStore.getById(req.params.id);
    if (!pattern) {
        return res.status(404).json({ error: 'Pattern not found' });
    }
    knowledgeStore.updateQuality(req.params.id, score);
    res.json({ success: true, newScore: score });
});
// Get context for generation (useful for frontend to pre-fetch relevant patterns)
router.post('/context', (req, res) => {
    const { nodeType, language, targetOS, searchText } = req.body;
    const context = learningEngine.getGenerationContext(nodeType || 'logic', language || 'javascript', targetOS || 'linux', 
    // The build goal: when given, patterns matching it outrank merely
    // higher-scored ones. Optional — without it the ordering is unchanged.
    searchText || undefined);
    res.json({ context, patternCount: knowledgeStore.count() });
});
// Learn from a project (called after successful generation)
router.post('/learn', (req, res) => {
    const { project, generatedCode, success } = req.body;
    if (!project) {
        return res.status(400).json({ error: 'Project data is required' });
    }
    const entries = learningEngine.learnFromProject(project, generatedCode || '', success !== false);
    res.status(201).json({
        success: true,
        patternsStored: entries.length,
        totalPatterns: knowledgeStore.count(),
    });
});
// Export knowledge patterns to the Training Studio
router.post('/export-to-studio', (req, res) => {
    // path already imported at top
    try {
        const patterns = knowledgeStore.getAll();
        if (patterns.length === 0) {
            return res.status(400).json({ error: 'No patterns to export' });
        }
        // Write patterns to a JSON file the Training Studio can read
        const studioDataDir = path.join(process.cwd(), '..', 'llm-training-app', 'data', 'uploads');
        if (!fs.existsSync(studioDataDir)) {
            fs.mkdirSync(studioDataDir, { recursive: true });
        }
        // Export as a JSONL file (one pattern per line, easiest cross-format)
        const exportPath = path.join(studioDataDir, 'architect_patterns.jsonl');
        const lines = patterns.map(p => JSON.stringify({
            id: p.id,
            title: p.title,
            code: p.code,
            description: p.description,
            tags: p.tags,
            nodeType: p.nodeType,
            language: p.language,
            targetOS: p.targetOS,
            category: 'code_pattern',
            source: 'visual-ai-architect'
        }));
        fs.writeFileSync(exportPath, lines.join('\n'), 'utf-8');
        // Also create a metadata file the Studio can use
        const metaPath = path.join(studioDataDir, 'architect_patterns_meta.json');
        fs.writeFileSync(metaPath, JSON.stringify({
            source: 'visual-ai-architect',
            exportedAt: new Date().toISOString(),
            patternCount: patterns.length,
            languages: [...new Set(patterns.map(p => p.language))],
            nodeTypes: [...new Set(patterns.map(p => p.nodeType))]
        }, null, 2), 'utf-8');
        // ── Signal the Training Studio by updating data/metadata.json (its file
        //    discovery mechanism). The studio reads { files, training_queue } from
        //    llm-training-app/data/metadata.json — the same convention the
        //    generate-datasheet routes in routes/training.ts use. Unlike them, this
        //    endpoint previously only updated the file when it ALREADY existed (and
        //    even then set in_queue: false), so on a fresh studio the export was
        //    silently invisible. Now: create the file if missing, and queue every
        //    .jsonl in the uploads dir (mirroring the datasheet routes) so the
        //    export is immediately visible as 'Ready for Training'. ──
        try {
            const studioDataDir = path.join(process.cwd(), '..', 'llm-training-app', 'data');
            const studioMetaPath = path.join(studioDataDir, 'metadata.json');
            let studioMeta = { files: {}, training_queue: [], epochs: 3, model_metrics: {}, training_history: [], experiments: {} };
            try {
                if (fs.existsSync(studioMetaPath)) {
                    studioMeta = JSON.parse(fs.readFileSync(studioMetaPath, 'utf-8'));
                }
            }
            catch { /* fall back to a fresh metadata shape */ }
            if (!studioMeta.files)
                studioMeta.files = {};
            if (!Array.isArray(studioMeta.training_queue))
                studioMeta.training_queue = [];
            // Rebuild the file list from ALL uploads (same as routes/training.ts) so
            // pre-existing uploads stay queued and the new export is added exactly once.
            try {
                const uploadFiles = fs.readdirSync(studioDataDir + '/uploads');
                studioMeta.files = {};
                studioMeta.training_queue = [];
                for (const fname of uploadFiles) {
                    if (!fname.endsWith('.jsonl'))
                        continue;
                    const fileId = `file_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
                    const fpath = path.join(studioDataDir, 'uploads', fname);
                    const stats = fs.statSync(fpath);
                    studioMeta.files[fileId] = {
                        id: fileId,
                        name: fname,
                        saved_name: fname,
                        category: 'Ready for Training',
                        themes: fname === 'architect_patterns.jsonl' ? ['code-patterns', 'architect'] : ['training-data'],
                        size: stats.size,
                        content_preview: `Training dataset: ${fname} (${(stats.size / 1024).toFixed(1)} KB)`,
                        uploaded_at: new Date().toISOString(),
                        in_queue: true,
                    };
                    studioMeta.training_queue.push(fileId);
                }
            }
            catch { /* uploads dir not readable — keep existing files map */ }
            fs.writeFileSync(studioMetaPath, JSON.stringify(studioMeta, null, 2), 'utf-8');
            console.log(`[bridge] Training Studio metadata updated: ${studioMeta.training_queue.length} file(s) queued`);
        }
        catch (err) {
            console.warn('[bridge] Could not update Studio metadata:', err);
        }
        res.json({
            success: true,
            exportedTo: exportPath,
            patternCount: patterns.length,
            message: `Exported ${patterns.length} patterns to Training Studio and updated its metadata`
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// Delete a pattern
router.delete('/:id', (req, res) => {
    const deleted = knowledgeStore.deletePattern(req.params.id);
    if (!deleted) {
        return res.status(404).json({ error: 'Pattern not found' });
    }
    res.json({ success: true });
});
export default router;
