import { Router } from 'express';
import { nodeStore } from '../database/nodeStore.js';
const router = Router();
// GET /api/nodes — list all node designs
router.get('/', (_req, res) => {
    res.json({ success: true, nodes: nodeStore.getAll(), count: nodeStore.count() });
});
// GET /api/nodes/search?q=... — search node designs
router.get('/search', (req, res) => {
    const q = (req.query.q || '').trim();
    if (!q) {
        res.json({ success: true, nodes: nodeStore.getAll() });
        return;
    }
    res.json({ success: true, nodes: nodeStore.search(q) });
});
// GET /api/nodes/type/:type — get nodes by type
router.get('/type/:type', (req, res) => {
    const nodes = nodeStore.searchByType(req.params.type);
    res.json({ success: true, nodes });
});
// POST /api/nodes — add a new node design
router.post('/', (req, res) => {
    try {
        const { type, label, description, language, category, tags, code } = req.body;
        if (!type || !label) {
            res.status(400).json({ error: 'Type and label are required' });
            return;
        }
        const node = nodeStore.add({
            id: `node_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
            type, label, description: description || '',
            language: language || 'typescript',
            category: category || type,
            tags: tags || [],
            code: code || '',
            source: 'learned',
            usageCount: 0,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
        });
        res.json({ success: true, node });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// POST /api/nodes/learn — learn from a node after generation
router.post('/learn', (req, res) => {
    try {
        const { type, label, description, language, generatedCode } = req.body;
        if (!type || !label) {
            res.status(400).json({ error: 'Type and label are required' });
            return;
        }
        const learned = nodeStore.learnFromNode({ type, label, description, language, generatedCode });
        res.json({ success: true, node: learned });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// DELETE /api/nodes/:id
router.delete('/:id', (req, res) => {
    const ok = nodeStore.delete(req.params.id);
    res.json({ success: ok });
});
export { router as nodeStoreRoutes };
