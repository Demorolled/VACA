import { Router } from 'express';
import { designStore } from '../database/designStore.js';
const router = Router();
// GET /api/designs/search?q=... — search local designs
router.get('/search', (req, res) => {
    try {
        const q = (req.query.q || '').trim();
        if (!q) {
            res.json({ success: true, designs: designStore.getAll() });
            return;
        }
        const results = designStore.search(q);
        res.json({ success: true, designs: results });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// GET /api/designs/search-open-source?q=... — search GitHub for matching projects
router.get('/search-open-source', async (req, res) => {
    try {
        const q = (req.query.q || '').trim();
        if (!q) {
            res.json({ success: false, error: 'Search query required' });
            return;
        }
        const query = encodeURIComponent(`${q} language:typescript OR language:python OR language:javascript`);
        const ghRes = await fetch(`https://api.github.com/search/repositories?q=${query}&sort=stars&per_page=10`, {
            headers: { 'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'VisualAIArchitect/1.0' },
            signal: AbortSignal.timeout(10000),
        });
        if (!ghRes.ok) {
            res.json({ success: false, error: `GitHub API returned ${ghRes.status}` });
            return;
        }
        const data = await ghRes.json();
        const repos = (data.items || []).slice(0, 8).map((repo) => ({
            id: `gh_${repo.id}`,
            name: repo.name,
            full_name: repo.full_name,
            description: repo.description || '',
            stars: repo.stargazers_count,
            url: repo.html_url,
            language: repo.language || 'unknown',
            topics: repo.topics || [],
            license: repo.license?.spdx_id || 'unknown',
        }));
        res.json({ success: true, repos });
    }
    catch (err) {
        res.json({ success: false, error: err.message });
    }
});
// POST /api/designs/search-open-source/details — get details of a repo
router.post('/search-open-source/details', async (req, res) => {
    try {
        const { repoUrl } = req.body;
        if (!repoUrl) {
            res.json({ success: false, error: 'repoUrl required' });
            return;
        }
        const match = repoUrl.match(/github\.com\/([^/]+\/[^/]+)/);
        if (!match) {
            res.json({ success: false, error: 'Invalid GitHub URL' });
            return;
        }
        const repoPath = match[1];
        const ghRes = await fetch(`https://api.github.com/repos/${repoPath}/readme`, {
            headers: { 'Accept': 'application/vnd.github.v3.raw', 'User-Agent': 'VisualAIArchitect/1.0' },
            signal: AbortSignal.timeout(10000),
        });
        if (!ghRes.ok) {
            res.json({ success: false, error: `Could not fetch README: ${ghRes.status}` });
            return;
        }
        const readme = await ghRes.text();
        const contentsRes = await fetch(`https://api.github.com/repos/${repoPath}/contents`, {
            headers: { 'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'VisualAIArchitect/1.0' },
            signal: AbortSignal.timeout(10000),
        });
        let structure = [];
        if (contentsRes.ok) {
            const items = await contentsRes.json();
            structure = (Array.isArray(items) ? items : []).map((i) => `${i.type === 'dir' ? '📁' : '📄'} ${i.name}`);
        }
        const langRes = await fetch(`https://api.github.com/repos/${repoPath}/languages`, {
            headers: { 'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'VisualAIArchitect/1.0' },
            signal: AbortSignal.timeout(5000),
        });
        let languages = {};
        if (langRes.ok)
            languages = await langRes.json();
        res.json({
            success: true,
            readme: readme.substring(0, 3000),
            structure: structure.slice(0, 30),
            languages,
        });
    }
    catch (err) {
        res.json({ success: false, error: err.message });
    }
});
// POST /api/designs/search-open-source/import — import a design from GitHub analysis
router.post('/search-open-source/import', async (req, res) => {
    try {
        const { repoUrl, name, description, goal } = req.body;
        if (!repoUrl) {
            res.json({ success: false, error: 'repoUrl required' });
            return;
        }
        const aiRes = await fetch('http://localhost:3001/api/reason', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt: `Analyze this GitHub repository and design a node-based architecture for it.

Repository: ${name || 'Unknown'}
Description: ${description || ''}
URL: ${repoUrl}
Goal: ${goal || name || 'Build an application'}

Design the architecture as JSON with this exact structure:
{
  "nodes": [{ "label": string, "description": string, "type": "input"|"output"|"logic"|"api"|"database"|"ui", "language": string }],
  "edges": [{ "source": string, "target": string }]
}

Think about what components, modules, and features this app needs and represent each as a node.
Connect nodes that depend on each other. Include at least 4 nodes.`,
                system: 'You are a software architect. Analyze repositories and extract their architectural design as node-based flow diagrams. Respond ONLY with valid JSON.',
                maxTokens: 2048,
            }),
            signal: AbortSignal.timeout(30000),
        });
        if (!aiRes.ok) {
            res.json({ success: false, error: 'AI analysis failed' });
            return;
        }
        const aiData = await aiRes.json();
        const text = aiData.response || '';
        let parsed;
        try {
            parsed = JSON.parse(text);
        }
        catch {
            const match = text.match(/\{[\s\S]*"nodes"[\s\S]*\}/);
            if (match) {
                try {
                    parsed = JSON.parse(match[0]);
                }
                catch {
                    parsed = null;
                }
            }
            else {
                parsed = null;
            }
        }
        if (!parsed || !parsed.nodes || !Array.isArray(parsed.nodes) || parsed.nodes.length === 0) {
            res.json({ success: false, error: 'Could not parse architecture from repository analysis' });
            return;
        }
        const nodes = parsed.nodes.map((n, i) => ({
            id: `imported_${i}`,
            type: n.type || 'logic',
            label: n.label || `Component ${i + 1}`,
            description: n.description || '',
            language: n.language || 'typescript',
            position: { x: 250, y: 200 + i * 170 },
        }));
        const edges = (parsed.edges || []).filter((e) => nodes.some((n) => n.label === e.source) &&
            nodes.some((n) => n.label === e.target)).map((e) => ({
            source: nodes.find((n) => n.label === e.source)?.id || '',
            target: nodes.find((n) => n.label === e.target)?.id || '',
        })).filter((e) => e.source && e.target);
        if (edges.length === 0 && nodes.length > 1) {
            for (let i = 0; i < nodes.length - 1; i++) {
                edges.push({ source: nodes[i].id, target: nodes[i + 1].id });
            }
        }
        const design = {
            id: `design_${Date.now()}`,
            name: name || 'Imported Design',
            goal: goal || description || name || 'Build from imported design',
            purpose: description || '',
            targetOS: 'linux',
            nodes,
            edges,
            roadmap: `Repository: ${repoUrl}\n\nArchitecture:\n${nodes.map((n) => `- ${n.label} (${n.type}): ${n.description}`).join('\n')}`,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            source: 'imported',
            sourceUrl: repoUrl,
            tags: (parsed.nodes || []).map((n) => n.type).filter(Boolean),
        };
        designStore.add(design);
        res.json({ success: true, design });
    }
    catch (err) {
        res.json({ success: false, error: err.message });
    }
});
// GET /api/designs — list all stored designs
router.get('/', (_req, res) => {
    res.json({ success: true, designs: designStore.getAll() });
});
// GET /api/designs/:id — get a specific design
router.get('/:id', (req, res) => {
    const design = designStore.getById(req.params.id);
    if (!design) {
        res.status(404).json({ error: 'Design not found' });
        return;
    }
    res.json({ success: true, design });
});
// POST /api/designs — save a new design (after build is complete)
router.post('/', (req, res) => {
    try {
        const { name, goal, purpose, targetOS, nodes, edges, roadmap, tags } = req.body;
        if (!name || !goal) {
            res.status(400).json({ error: 'Name and goal are required' });
            return;
        }
        const design = {
            id: `design_${Date.now()}`,
            name,
            goal,
            purpose: purpose || '',
            targetOS: targetOS || 'linux',
            nodes: (nodes || []).map((n, i) => ({
                id: `saved_${i}`,
                type: n.type || 'logic',
                label: n.label || `Node ${i + 1}`,
                description: n.description || '',
                language: n.language || 'typescript',
                position: n.position || { x: 250, y: 200 + i * 170 },
            })),
            edges: edges || [],
            roadmap: roadmap || '',
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            source: 'local',
            tags: tags || [],
        };
        designStore.add(design);
        res.json({ success: true, design });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// DELETE /api/designs/:id
router.delete('/:id', (req, res) => {
    const ok = designStore.delete(req.params.id);
    res.json({ success: ok });
});
export { router as designRoutes };
