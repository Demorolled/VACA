import { Router } from 'express';
import { v4 as uuidv4 } from 'uuid';
import { projects } from '../db/projects.js';
// Factory so tests can inject an isolated store (temp file) — the live app
// uses the shared singleton that persists to backend/data/projects.json.
export function createProjectRoutes(store = projects) {
    const r = Router();
    r.get('/', (_req, res) => {
        res.json(store.getAll());
    });
    r.get('/:id', (req, res) => {
        const project = store.getById(req.params.id);
        if (!project) {
            return res.status(404).json({ error: 'Project not found' });
        }
        res.json(project);
    });
    r.post('/', (req, res) => {
        const { name, targetOS } = req.body;
        const project = store.create({
            id: uuidv4(),
            name: name || 'Untitled Project',
            targetOS: targetOS || 'linux',
            nodes: [],
            edges: [],
        });
        res.status(201).json(project);
    });
    r.put('/:id', (req, res) => {
        const project = store.update(req.params.id, req.body);
        if (!project) {
            return res.status(404).json({ error: 'Project not found' });
        }
        res.json(project);
    });
    r.delete('/:id', (req, res) => {
        const success = store.delete(req.params.id);
        if (!success) {
            return res.status(404).json({ error: 'Project not found' });
        }
        res.json({ success: true });
    });
    // ── Export ──────────────────────────────────────────────────────────────
    // Serialize one project as a downloadable JSON file (the server-side half of
    // the "export projects" claim — mirrors the frontend's localStorage export).
    r.get('/:id/export', (req, res) => {
        const project = store.getById(req.params.id);
        if (!project) {
            return res.status(404).json({ error: 'Project not found' });
        }
        const safeName = (project.name || 'project').replace(/[^a-z0-9-_]+/gi, '_');
        res.setHeader('Content-Type', 'application/json');
        res.setHeader('Content-Disposition', `attachment; filename="${safeName}.project.json"`);
        res.json(project);
    });
    // ── Import ──────────────────────────────────────────────────────────────
    // Accept an exported project JSON (or a minimal {name, nodes, edges}) and
    // create a fresh project with a new id — the server-side half of the
    // "import projects" claim.
    r.post('/import', (req, res) => {
        const body = req.body || {};
        if (typeof body !== 'object' || body === null) {
            return res.status(400).json({ error: 'Invalid project JSON' });
        }
        // Match the frontend importProject contract: nodes must be an array if
        // present (absent defaults to [] so minimal {name} imports still work).
        if (body.nodes !== undefined && !Array.isArray(body.nodes)) {
            return res.status(400).json({ error: 'nodes must be an array' });
        }
        if (body.edges !== undefined && !Array.isArray(body.edges)) {
            return res.status(400).json({ error: 'edges must be an array' });
        }
        const name = typeof body.name === 'string' && body.name.trim() ? body.name.trim() : 'Imported Project';
        const project = store.create({
            id: uuidv4(),
            name,
            targetOS: body.targetOS || 'linux',
            nodes: Array.isArray(body.nodes) ? body.nodes : [],
            edges: Array.isArray(body.edges) ? body.edges : [],
        });
        res.status(201).json(project);
    });
    return r;
}
export const projectRoutes = createProjectRoutes();
// Get all projects
projectRoutes.get('/', (_req, res) => {
    res.json(projects.getAll());
});
// Get single project
projectRoutes.get('/:id', (req, res) => {
    const project = projects.getById(req.params.id);
    if (!project) {
        return res.status(404).json({ error: 'Project not found' });
    }
    res.json(project);
});
// Create new project
projectRoutes.post('/', (req, res) => {
    const { name, targetOS } = req.body;
    const project = projects.create({
        id: uuidv4(),
        name: name || 'Untitled Project',
        targetOS: targetOS || 'linux',
        nodes: [],
        edges: [],
    });
    res.status(201).json(project);
});
// Update project
projectRoutes.put('/:id', (req, res) => {
    const project = projects.update(req.params.id, req.body);
    if (!project) {
        return res.status(404).json({ error: 'Project not found' });
    }
    res.json(project);
});
// Delete project
projectRoutes.delete('/:id', (req, res) => {
    const success = projects.delete(req.params.id);
    if (!success) {
        return res.status(404).json({ error: 'Project not found' });
    }
    res.json({ success: true });
});
