/**
 * Plan Mode routes.
 *
 * Plan Mode captures the user's app ideas and saves them to a text file
 * (data/plans/<project-name>.txt) for later creation. The user defines the
 * project name; when one is not provided the API answers with `needName` so
 * the UI can ask the user for it before saving.
 */
import { Router } from 'express';
import { savePlanFile, listPlanFiles, readPlanFile, savePlanGraph, readPlanGraph, listPlanGraphs, } from '../utils/planFile.js';
import { writePlanMap, planMapExists } from '../utils/planMap.js';
import { AITranslator } from '../ai/translator.js';
const router = Router();
// ---------------------------------------------------------------------------
// The Big Plan Mode co-worker
// ---------------------------------------------------------------------------
//
// While the user designs a node graph, this asks the questions a second person
// on the team would ask — nothing more. It NEVER generates code, files, or a
// build: Big Plan Mode is design-only by design, and the whole point of the
// question form is to leave every decision with the user.
//
// Structured questions were chosen over free-text advice because VACA's own
// intent-upgrade work measured the difference: free-text guidance gets a "yes"
// back and the model guesses anyway, while a real question forces the user to
// state the decision (see INTENT_UPGRADE_PLAN.md §1.2). So the contract here is
// one question per line, no preamble, no advice paragraphs.
const COWORK_SYSTEM_PROMPT = `You are a co-worker helping someone think through an app design.
The user is describing their architecture as nodes in a graph. You are NOT building anything and you must NOT write code, files, or a plan yourself.

Your only job: ask the few questions a good teammate would ask at this exact moment.

Rules:
- Ask 1 to 3 questions, each on its own line.
- EVERY line must use exactly this format: <node label> :: <question ending in "?>
- Use the node's label EXACTLY as written in the list you are given, so the answer can be filed against that node. If a question is about the design as a whole, write OVERALL :: <question>.
- Each question is under 140 characters and refers to the user's actual nodes, not generic advice.
- Ask about what is MISSING or AMBIGUOUS — a node whose job is unclear, a node with no wiring, two nodes that seem to overlap, a decision nobody has made, an answer they gave that is still vague.
- No greetings, no preamble, no numbering, no bullet points, no advice.
- Never ask something the user has already answered (their answers are listed per node).
- Never suggest a whole new app or restate their idea back to them.
- If the design already answers everything you would ask, return exactly: NONE

Example of a good line:
Encrypted Store :: Should this write to disk itself, or only hand ciphered bytes to the Notes Core?`;
let _translator = null;
function getTranslator() {
    if (!_translator)
        _translator = new AITranslator();
    return _translator;
}
/**
 * Normalise a question for comparison: lowercase, strip punctuation, drop the
 * filler words that vary between paraphrases of the same question.
 */
const STOP_WORDS = new Set([
    'a', 'an', 'and', 'are', 'be', 'do', 'does', 'for', 'from', 'how', 'in',
    'is', 'it', 'its', 'of', 'on', 'or', 'that', 'the', 'their', 'them', 'this',
    'to', 'was', 'will', 'with', 'you', 'your',
]);
function keywords(q) {
    return new Set(q
        .toLowerCase()
        .replace(/[^a-z0-9 ]+/g, ' ')
        .split(/\s+/)
        .filter((w) => w.length > 1 && !STOP_WORDS.has(w)));
}
/**
 * How much two questions overlap, as a share of the smaller one's keywords.
 *
 * Exact string matching was not enough: asked "What is the purpose of the
 * Encrypted Store? Is it meant to save notes to disk…", the model came back
 * with "What is the purpose of the Encrypted Store node? How does it interact
 * with the Notes Core?" — the same question, reworded, so the user would have
 * been asked it twice. Measured against that pair: 0.75 overlap, hence a 0.6
 * threshold.
 */
function similarity(a, b) {
    if (a.size === 0 || b.size === 0)
        return 0;
    let shared = 0;
    for (const w of a)
        if (b.has(w))
            shared += 1;
    return shared / Math.min(a.size, b.size);
}
function labelKey(s) {
    return s.toLowerCase().replace(/[^a-z0-9]/g, '');
}
/**
 * Turn the model's lines into questions tagged with the node they are about.
 *
 * The tag is what lets the UI attach an answer to a specific node, so a line
 * the model wrote without a usable tag is kept but left untagged (nodeId null)
 * rather than thrown away: the question is still worth asking, it just lands
 * under "the design as a whole".
 */
function parseQuestions(raw, alreadyAsked, nodes) {
    const asked = alreadyAsked.map(keywords);
    const labelled = nodes.map((n) => ({ node: n, key: labelKey(n.label || '') }));
    const lines = raw
        .split('\n')
        .map((l) => l.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, '').trim())
        .filter((l) => l.length > 8 && l.length <= 260)
        .map((l) => {
        // "Node Label :: question" (also tolerate a single colon or an em dash).
        const m = l.match(/^(.{1,60}?)\s*(?:::→|::|—|-|:)\s*(.+)$/);
        if (!m)
            return { text: l, node: null };
        const [, labelPart, questionPart] = m;
        if (!questionPart.includes('?'))
            return { text: l, node: null };
        const key = labelKey(labelPart);
        const hit = labelled.find((x) => x.key && x.key === key);
        return { text: questionPart.trim(), node: hit?.node || null };
    })
        .filter((x) => x.text.includes('?'));
    const out = [];
    const seen = [];
    for (const line of lines) {
        const key = keywords(line.text);
        if (asked.some((prev) => similarity(prev, key) >= 0.6))
            continue;
        if (seen.some((prev) => similarity(prev, key) >= 0.6))
            continue;
        seen.push(key);
        out.push({
            id: `q_${out.length}_${Date.now().toString(36)}`,
            text: line.text,
            nodeId: line.node?.id || null,
            nodeLabel: line.node?.label || null,
        });
        if (out.length === 3)
            break;
    }
    return out;
}
// POST /api/plans/cowork — monitor the design and return questions to ask.
// Body: { projectName, goal, nodes, edges, alreadyAsked?: string[] }
router.post('/cowork', async (req, res) => {
    try {
        const { projectName, goal, nodes, edges, alreadyAsked } = req.body || {};
        if (!Array.isArray(nodes) || nodes.length === 0) {
            res.json({ success: true, questions: [] });
            return;
        }
        const designNodes = nodes.filter((n) => n && n.type !== 'master');
        const master = designNodes.find((n) => n.isMaster);
        const edgeCount = Array.isArray(edges) ? edges.length : 0;
        // Nothing to ask before the user has said what they are building.
        if (!master && !goal) {
            res.json({ success: true, questions: [] });
            return;
        }
        const nodeLines = designNodes
            .map((n, i) => {
            const bits = [
                `- ${n.label || `node ${i + 1}`}${n.isMaster ? ' (MASTER — this is the app itself)' : ''}`,
                n.type ? `type=${n.type}` : '',
                n.language ? `lang=${n.language}` : '',
                n.description ? `purpose="${n.description}"` : '(no purpose written yet)',
            ].filter(Boolean);
            return bits.join(' · ');
        })
            .join('\n');
        // Edges carry node IDS (the canvas snapshot), so label them by id first.
        const labelOf = (id) => designNodes.find((n) => n.id === id)?.label || id;
        const edgeList = Array.isArray(edges) ? edges : [];
        const wiringLines = edgeList.length
            ? edgeList
                .map((e) => `- ${labelOf(e.source)} → ${labelOf(e.target)}${e.label ? ` (${e.label})` : ''}`)
                .join('\n')
            : '(none wired yet)';
        const unwired = designNodes.filter((n) => !edgeList.some((e) => e.source === n.id || e.target === n.id));
        // Answers the user has already given, per node. Included so the co-worker
        // builds on them instead of re-asking — the whole reason answers are
        // attached to nodes rather than dropped into a transcript.
        const answeredLines = designNodes
            .flatMap((n) => (Array.isArray(n.qa) ? n.qa : []).map((qa) => `- ${n.label}: Q: ${qa.q || ''} | A: ${qa.a || ''}`))
            .join('\n');
        const prompt = `The user is designing: "${goal || master?.description || projectName || 'an app'}"

Nodes in their design so far (${designNodes.length}):
${nodeLines}

Wiring they have drawn (${edgeCount} edge${edgeCount === 1 ? '' : 's'}):
${wiringLines}

Nodes with no wiring yet: ${unwired.map((n) => n.label || 'unnamed').join(', ') || 'none'}

Answers they have already given (do NOT ask these again):
${answeredLines || '(none yet)'}

Ask the questions that move this design forward right now. Tag each one with its node label.`;
        let questions = [];
        try {
            const raw = await getTranslator().reason(prompt, COWORK_SYSTEM_PROMPT, {
                maxTokens: 300,
                temperature: 0.4,
                role: 'reasoning',
            });
            if (!/^\s*NONE\s*$/i.test(raw)) {
                questions = parseQuestions(raw, Array.isArray(alreadyAsked) ? alreadyAsked : [], designNodes);
            }
        }
        catch (err) {
            // The co-worker is advisory: if the LLM is down the design is unaffected,
            // so answer 200 with no questions rather than surfacing an error.
            console.warn('[plans] cowork questions unavailable:', err instanceof Error ? err.message : err);
        }
        res.json({ success: true, questions });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// POST /api/plans — save (create or update) a plan file
router.post('/', (req, res) => {
    try {
        const { projectName, ideas, guidance, questions } = req.body || {};
        if (!projectName || typeof projectName !== 'string' || !projectName.trim()) {
            res.status(400).json({
                error: 'A project name is required to save a plan.',
                needName: true,
                hint: 'Give this plan a project name so it can be saved for later creation.',
            });
            return;
        }
        if (!ideas || typeof ideas !== 'string' || !ideas.trim()) {
            res.status(400).json({ error: 'Plan ideas/notes are required.' });
            return;
        }
        const record = savePlanFile({
            projectName,
            ideas,
            guidance: guidance || '',
            questions: questions || '',
        });
        res.json({ success: true, ...record });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// POST /api/plans/graph — autosave a Big Plan Mode design.
//
// Writes data/plans/<name>/ {plan.md, graph.json}, creating the directory on the
// first call. The canvas calls this when the master node is placed and then
// every 5 minutes, so the design on screen always has a copy on disk. No app
// code is generated here — this only records the design.
router.post('/graph', (req, res) => {
    try {
        const { projectName, goal, nodes, edges } = req.body || {};
        if (!Array.isArray(nodes) || nodes.length === 0) {
            res.status(400).json({ error: 'A plan graph needs at least the master node.' });
            return;
        }
        const name = typeof projectName === 'string' ? projectName : '';
        const record = savePlanGraph({
            projectName: name,
            goal: typeof goal === 'string' ? goal : '',
            nodes,
            edges: Array.isArray(edges) ? edges : [],
        });
        // Once a design has been mapped, every autosave refreshes the map.
        //
        // The user's ask was to "finish the design in my head as I make changes",
        // and a map that only updates when a button is pressed goes stale the
        // moment the design moves — which is exactly when it stops being a map of
        // their design. Refreshing only when a map ALREADY exists keeps the build
        // deliberate (mapping is still an explicit first action) while making the
        // result self-maintaining. Failure here never fails the save: the design
        // itself is the thing that must not be lost.
        let mapRefreshed = false;
        if (planMapExists(name)) {
            try {
                writePlanMap({
                    projectName: name,
                    goal: typeof goal === 'string' ? goal : '',
                    nodes,
                    edges: Array.isArray(edges) ? edges : [],
                });
                mapRefreshed = true;
            }
            catch (err) {
                console.warn('[plans] map refresh failed (non-fatal):', err instanceof Error ? err.message : err);
            }
        }
        res.json({ success: true, ...record, mapRefreshed });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// POST /api/plans/map — "build" the design into a node map: real files and
// folders, one per node, named and wired as a later build would name them, with
// NO code generated.
//
// This is deliberately not a code-generation endpoint. Nothing here calls a
// model: the map is derived from the graph with pure functions, so it costs no
// GPU, cannot fail on a dead LLM, and cannot enter the training set (verified
// capture is keyed to FileGenerator runs, and this never runs FileGenerator).
//
// Body: { projectName, goal, nodes, edges }
router.post('/map', (req, res) => {
    try {
        const { projectName, goal, nodes, edges } = req.body || {};
        if (!Array.isArray(nodes) || nodes.length === 0) {
            res.status(400).json({ error: 'The design needs at least one node to map.' });
            return;
        }
        const record = writePlanMap({
            projectName: typeof projectName === 'string' ? projectName : '',
            goal: typeof goal === 'string' ? goal : '',
            nodes,
            edges: Array.isArray(edges) ? edges : [],
        });
        res.json({ success: true, ...record });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// GET /api/plans/graphs — list saved Big Plan Mode designs to reopen.
//
// MUST stay registered before GET /:name below: Express matches in order and
// '/graphs' is a single path segment, so /:name would otherwise swallow it and
// try to read a plan file literally called "graphs".
router.get('/graphs', (_req, res) => {
    try {
        res.json({ success: true, graphs: listPlanGraphs() });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// GET /api/plans/graph/:name — read a saved design back
router.get('/graph/:name', (req, res) => {
    try {
        const graph = readPlanGraph(req.params.name);
        if (!graph) {
            res.status(404).json({ error: 'Plan graph not found' });
            return;
        }
        res.json({ success: true, ...graph });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// GET /api/plans — list saved plans
router.get('/', (_req, res) => {
    try {
        res.json({ success: true, plans: listPlanFiles() });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
// GET /api/plans/:name — read a plan's text content
router.get('/:name', (req, res) => {
    try {
        const plan = readPlanFile(req.params.name);
        if (!plan) {
            res.status(404).json({ error: 'Plan not found' });
            return;
        }
        res.json({ success: true, ...plan });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
export { router as planRoutes };
