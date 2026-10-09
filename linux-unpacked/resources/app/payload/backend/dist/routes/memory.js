import { Router } from 'express';
import { sessionMemory } from '../database/sessionMemory.js';
const router = Router();
// GET /api/memory — get session memory
router.get('/', (_req, res) => {
    res.json({ success: true, memory: sessionMemory.getMemory(), context: sessionMemory.getMemoryContext() });
});
// POST /api/memory/build — record a build
router.post('/build', (req, res) => {
    try {
        const { projectName, targetOS, nodeCount, edgeCount, filesCreated } = req.body;
        if (!projectName) {
            res.status(400).json({ error: 'projectName required' });
            return;
        }
        sessionMemory.recordBuild(projectName, targetOS || 'linux', nodeCount || 0, edgeCount || 0, filesCreated || []);
        res.json({ success: true });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// POST /api/memory/file-access — record a file access
router.post('/file-access', (req, res) => {
    try {
        const { filePath, type, projectName } = req.body;
        if (!filePath) {
            res.status(400).json({ error: 'filePath required' });
            return;
        }
        sessionMemory.recordFileAccess(filePath, type || 'read', projectName || 'unknown');
        res.json({ success: true });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// GET /api/memory/context — get memory context string for prompts
router.get('/context', (_req, res) => {
    res.json({ success: true, context: sessionMemory.getMemoryContext() });
});
// GET /api/memory/notes — list saved memory notes
router.get('/notes', (_req, res) => {
    res.json({ success: true, notes: sessionMemory.getNotes(50), total: sessionMemory.getNotes(100).length });
});
// DELETE /api/memory/notes/:id — remove a single saved note (audit/tester
// probes delete exactly the note they created; users can delete a stale note).
router.delete('/notes/:id', (req, res) => {
    const id = (req.params.id || '').trim();
    if (!id) {
        res.status(400).json({ error: 'note id required' });
        return;
    }
    const removed = sessionMemory.deleteNote(id);
    if (!removed) {
        res.status(404).json({ error: 'note not found' });
        return;
    }
    res.json({ success: true, total: sessionMemory.getNotes(100).length });
});
// POST /api/memory/notes/restore — replace ALL notes with a snapshot array.
// Used by audit/tester probes (save notes -> write probe fact -> verify ->\
// restore) so probe runs never leave junk in session-memory.json.
router.post('/notes/restore', (req, res) => {
    const { notes } = req.body || {};
    if (!Array.isArray(notes)) {
        res.status(400).json({ error: 'notes array required' });
        return;
    }
    // Wipe-guard: an empty snapshot must never erase a non-empty store (a
    // failed snapshot fetch upstream must not silently become []). Callers with
    // a genuinely empty store can pass an explicit `force: true`.
    if (notes.length === 0 && sessionMemory.getNotes(100).length > 0 && !req.body?.force) {
        res.status(400).json({ error: 'refusing to restore an empty snapshot over a non-empty store (pass force:true to override)' });
        return;
    }
    const clean = notes
        .filter((n) => !!n && typeof n === 'object')
        .map(n => ({
        id: typeof n.id === 'string' ? n.id : `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        topic: typeof n.topic === 'string' ? n.topic : 'Untitled note',
        content: typeof n.content === 'string' ? n.content : '',
        source: typeof n.source === 'string' ? n.source : 'restored',
        timestamp: typeof n.timestamp === 'string' ? n.timestamp : new Date().toISOString(),
    }));
    sessionMemory.restoreNotes(clean);
    res.json({ success: true, total: clean.length });
});
// POST /api/memory/write — write a note to persistent memory
router.post('/write', (req, res) => {
    try {
        const { topic, content, source } = req.body || {};
        if (!content || typeof content !== 'string' || !content.trim()) {
            res.status(400).json({ error: 'content required' });
            return;
        }
        const note = sessionMemory.recordNote(topic || 'Untitled note', content, source || 'api');
        res.json({ success: true, note, total: sessionMemory.getNotes(100).length });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// POST /api/memory/clear — clear all session memory
router.post('/clear', (_req, res) => {
    sessionMemory.clear();
    console.log('[Memory] Session memory cleared by user');
    res.json({ success: true });
});
export { router as memoryRoutes };
