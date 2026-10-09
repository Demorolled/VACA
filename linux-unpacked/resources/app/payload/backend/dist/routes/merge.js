/**
 * Merge routes — POST /api/merge
 *
 * Merges two VACA architecture graphs (from the current canvas and a saved
 * project) into one: resolves node-id collisions, renames label conflicts,
 * remaps edges, drops dangling edges / B's master node, and reports a full
 * summary so the UI can show exactly what changed.
 */
import { Router } from 'express';
import { mergeGraphs } from '../utils/graphMerge.js';
import { AITranslator } from '../ai/translator.js';
import { buildConnectPrompt, parseConnectResponse } from '../utils/semanticConnect.js';
const router = Router();
// ── Semantic Connect: POST /api/merge/connect ──
// After a structural merge the user picks a SOURCE node (from the dropped app)
// and a TARGET node (from the existing app), then describes how they should
// connect in plain language. The LLM interprets that description into a
// semantic edge { label, relation, codeHint } stored on edge.data (semantic:
// true), so codegen both imports the dependency AND implements the wiring.
router.post('/connect', async (req, res) => {
    try {
        const { nodes, edges, sourceNodeId, targetNodeId, description } = req.body || {};
        if (!Array.isArray(nodes) || nodes.length === 0) {
            res.status(400).json({ error: 'nodes array is required.' });
            return;
        }
        if (!sourceNodeId || !targetNodeId) {
            res.status(400).json({ error: 'Both sourceNodeId and targetNodeId are required.' });
            return;
        }
        if (sourceNodeId === targetNodeId) {
            res.status(400).json({ error: 'Source and target must be different nodes.' });
            return;
        }
        const source = nodes.find((n) => n.id === sourceNodeId);
        const target = nodes.find((n) => n.id === targetNodeId);
        if (!source || !target) {
            res.status(400).json({ error: 'sourceNodeId and targetNodeId must reference existing nodes.' });
            return;
        }
        // Duplicate-edge guard (server-side): a direct API call or a stale frontend
        // must never create a second source→target edge, which would double the
        // import dependency in codegen.
        if (Array.isArray(edges) && edges.some((e) => e?.source === sourceNodeId && e?.target === targetNodeId)) {
            res.status(409).json({ error: 'These two nodes are already connected.' });
            return;
        }
        const prompt = buildConnectPrompt({
            nodes,
            sourceNodeId,
            targetNodeId,
            description: (description || '').trim(),
            projectName: req.body?.projectName,
            targetOS: req.body?.targetOS,
        });
        const ai = new AITranslator();
        const raw = await ai.reason(prompt, 'You are an expert software architect who turns plain-language descriptions of how two modules should connect into precise, machine-readable wiring specs. Always reply with ONLY the requested JSON object — no markdown fences, no prose.', { maxTokens: 320, timeoutMs: 45000, temperature: 0.2 });
        const conn = parseConnectResponse(raw);
        const edge = {
            id: `edge_sem_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
            source: sourceNodeId,
            target: targetNodeId,
            label: conn.label,
            data: {
                label: conn.label,
                relation: conn.relation,
                codeHint: conn.codeHint,
                sourceHint: conn.sourceHint,
                targetHint: conn.targetHint,
                description: (description || '').trim(),
                semantic: true,
            },
        };
        res.json({ success: true, edge });
    }
    catch (err) {
        res.status(500).json({ error: err?.message || 'Failed to interpret connection.' });
    }
});
// POST /api/merge
router.post('/', (req, res) => {
    try {
        const { projectA, projectB, offsetB, offsetGap } = req.body || {};
        if (!projectA || !projectB) {
            res.status(400).json({ error: 'Both projectA and projectB are required.' });
            return;
        }
        if (!Array.isArray(projectA.nodes) || !Array.isArray(projectB.nodes)) {
            res.status(400).json({ error: 'Both projects must include a nodes array.' });
            return;
        }
        const result = mergeGraphs({
            name: projectA.name || 'Project A',
            nodes: projectA.nodes,
            edges: (projectA.edges || []),
        }, {
            name: projectB.name || 'Project B',
            nodes: projectB.nodes,
            edges: (projectB.edges || []),
        }, { offsetB: offsetB !== false, offsetGap: typeof offsetGap === 'number' ? offsetGap : 250 });
        res.json({ success: true, ...result });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
export { router as mergeRoutes };
