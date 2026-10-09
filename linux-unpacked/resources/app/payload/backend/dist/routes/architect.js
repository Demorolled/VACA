import { Router } from 'express';
import { AITranslator } from '../ai/translator.js';
import { getArchitectPrompt, ARCHITECT_SYSTEM_PROMPT, normalizeScale } from '../ai/prompts.js';
import { inferLanguageForGoal, normalizeNodeLanguage, normalizeClientSideLanguages, } from '../ai/languageInference.js';
import { loadPreference } from './uiPreference.js';
import { knowledgeStore } from '../knowledge/knowledgeStore.js';
import { getPlaceholderFileNames } from '../export/placeholderFiles.js';
import { broadcastArchitectProgress } from '../socket/socketManager.js';
import { PLAN_NODE_TYPES } from '../types.js';
import { researchDesign } from '../search/designResearch.js';
import { getSearchService } from '../search/webSearch.js';
import { getManifestoContext } from '../ai/manifesto.js';
import { getLibraryContextDense } from '../ai/libraryContext.js';
import { deriveNodeId, flattenSuggestedWidgets } from '../shared/designContract.js';
const router = Router();
class RequestQueue {
    queue = [];
    activeCount = 0;
    concurrency;
    timeoutMs;
    constructor(concurrency = 1, timeoutMs = 180000) {
        this.concurrency = concurrency;
        this.timeoutMs = timeoutMs;
    }
    async enqueue(execute) {
        return new Promise((resolve, reject) => {
            this.queue.push({
                execute: execute,
                resolve: resolve,
                reject,
            });
            this.processNext();
        });
    }
    processNext() {
        if (this.activeCount >= this.concurrency)
            return;
        if (this.queue.length === 0)
            return;
        const item = this.queue.shift();
        this.activeCount++;
        const timeout = setTimeout(() => {
            this.activeCount--;
            item.reject(new Error(`Architect request timed out after ${this.timeoutMs}ms`));
            this.processNext();
        }, this.timeoutMs);
        Promise.resolve()
            .then(() => item.execute())
            .then((result) => {
            clearTimeout(timeout);
            this.activeCount--;
            item.resolve(result);
            this.processNext();
        })
            .catch((err) => {
            clearTimeout(timeout);
            this.activeCount--;
            item.reject(err);
            this.processNext();
        });
    }
    get pending() {
        return this.queue.length;
    }
    get active() {
        return this.activeCount;
    }
}
const architectQueue = new RequestQueue(1, 600000);
// ─── Testable constants ────────────────────────────────────────────────────
// Canonical file-node types — single source of truth in types.ts. Re-exported
// so existing importers/tests keep working; the plan prompt below interpolates
// THIS list so the vocabulary can never drift from the validator again.
export const NODE_TYPES = [...PLAN_NODE_TYPES];
// ─── Testable helper functions ─────────────────────────────────────────────
/**
 * Attempt to clean and parse malformed JSON from the LLM.
 * Handles common issues: markdown fences, trailing commas, single quotes,
 * unquoted keys, comments, truncated output, and more.
 */
export function repairAndParseJSON(raw) {
    let cleaned = raw.trim();
    // 1. Strip markdown code fences (```json ... ```, ``` ... ```)
    cleaned = cleaned.replace(/^```(?:json)?\s*\n?/i, '').replace(/\n?```\s*$/i, '').trim();
    // 2. Try to extract the outermost { ... } block (handles extra text before/after)
    const braceStart = cleaned.indexOf('{');
    const braceEnd = cleaned.lastIndexOf('}');
    if (braceStart !== -1 && braceEnd > braceStart) {
        cleaned = cleaned.slice(braceStart, braceEnd + 1);
    }
    // 3. Pre-process common LLM JSON mistakes before attempting parse
    //    Replace ? placeholders with 0 (common when LLM doesn't know a value)
    cleaned = cleaned.replace(/:[\s]*\?[\s]*([,}\]])/g, ': 0$1');
    //    Replace bare identifiers used as values (e.g., "x": someVar) with 0
    cleaned = cleaned.replace(/:[\s]*[a-zA-Z_][a-zA-Z0-9_]*[\s]*([,}\]])/g, ': 0$1');
    //    Fix "x": ,  (empty value after colon) -> "x": 0
    cleaned = cleaned.replace(/:[\s]*,[\s]*/g, ': 0,');
    try {
        return JSON.parse(cleaned);
    }
    catch { }
    // 4. Try direct parse
    try {
        return JSON.parse(cleaned);
    }
    catch { }
    // 5. Remove single-line // comments (only at line boundaries, not inside strings)
    //    This regex only matches // when preceded by whitespace or line start, avoiding URLs in strings
    cleaned = cleaned.replace(/^[\s]*\/\/.*$/gm, '');
    cleaned = cleaned.replace(/\n\s*\/\/.*$/gm, '');
    // Remove /* */ block comments
    cleaned = cleaned.replace(/\/\*[\s\S]*?\*\//g, '');
    try {
        return JSON.parse(cleaned);
    }
    catch { }
    // 5. Replace single quotes around property values with double quotes (targeted: `'value'` -> `"value"`)
    //    Only replaces single quotes that look like string delimiters, not apostrophes inside words
    cleaned = cleaned.replace(/'([^']*?)'(\s*[},:\]])/g, '"$1"$2');
    cleaned = cleaned.replace(/([{,]\s*)'([^']*?)'(\s*:)/g, '$1"$2"$3');
    try {
        return JSON.parse(cleaned);
    }
    catch { }
    // 6. Unquote property names (keys without quotes, like {name: "foo"})
    cleaned = cleaned.replace(/([{,])[\s]*([a-zA-Z_][a-zA-Z0-9_]*)[\s]*:/g, '$1"$2":');
    try {
        return JSON.parse(cleaned);
    }
    catch { }
    // 7. Remove ALL trailing commas (also before closing braces we'll add later)
    cleaned = cleaned.replace(/,([\s]*[}\]])/g, '$1');
    // Also remove trailing comma at the very end of the string (fixes truncation before brace closure)
    cleaned = cleaned.replace(/,\s*$/, '');
    try {
        return JSON.parse(cleaned);
    }
    catch { }
    // 8. Close unclosed structures in LIFO order using a stack (handles nested truncation correctly)
    //     Simple counting (closing all braces before brackets) produces invalid JSON like `}}]`
    //     Stack-based closing produces correct `}]}` by tracking nesting depth.
    {
        let repairStack = [];
        let inString = false;
        let escape = false;
        for (let i = 0; i < cleaned.length; i++) {
            const ch = cleaned[i];
            if (escape) {
                escape = false;
                continue;
            }
            if (ch === '\\') {
                escape = true;
                continue;
            }
            if (ch === '"') {
                inString = !inString;
                continue;
            }
            if (inString)
                continue;
            if (ch === '{')
                repairStack.push('}');
            else if (ch === '[')
                repairStack.push(']');
        }
        while (repairStack.length > 0) {
            cleaned += repairStack.pop();
        }
        try {
            return JSON.parse(cleaned);
        }
        catch { }
    }
    // 9. Fix truncated last value + mid-key truncation using stack-based closer
    //     Handle both cases: trailing incomplete token (e.g., `, "labe`) and trailing complete value with missing closers
    {
        // Helper: close unclosed JSON structures in LIFO order with matching
        const closeUnclosed = (target) => {
            const stack = [];
            let inStr = false;
            let esc = false;
            for (let i = 0; i < target.length; i++) {
                const c = target[i];
                if (esc) {
                    esc = false;
                    continue;
                }
                if (c === '\\') {
                    esc = true;
                    continue;
                }
                if (c === '"') {
                    inStr = !inStr;
                    continue;
                }
                if (inStr)
                    continue;
                if (c === '{')
                    stack.push('}');
                else if (c === '[')
                    stack.push(']');
                else if ((c === '}' || c === ']') && stack.length > 0 && stack[stack.length - 1] === c)
                    stack.pop();
            }
            let result = target;
            while (stack.length > 0)
                result += stack.pop();
            return result;
        };
        // Try truncating incomplete last value
        const lastComma = cleaned.lastIndexOf(',');
        if (lastComma > 0) {
            const afterComma = cleaned.slice(lastComma);
            if (afterComma.match(/,\s*["']?[a-zA-Z0-9_]+\s*$/)) {
                let attempt = cleaned.slice(0, lastComma);
                attempt = closeUnclosed(attempt);
                try {
                    return JSON.parse(attempt);
                }
                catch { }
            }
        }
        // Try removing incomplete key-value pair at the end
        const incompletePattern = /[,\s]*\"[a-zA-Z0-9_]*\s*$/;
        if (incompletePattern.test(cleaned)) {
            let attempt = cleaned.replace(/,[^,]*$/, '');
            attempt = closeUnclosed(attempt);
            try {
                return JSON.parse(attempt);
            }
            catch { }
        }
    }
    // 11. Last resort: try to find a valid "nodes" array even from deeply broken JSON
    try {
        const nodesMatch = cleaned.match(/"nodes"\s*:\s*\[[\s\S]*?\](?:\s*,\s*"edges"\s*:\s*\[[\s\S]*?\])?/);
        if (nodesMatch) {
            const partial = JSON.parse(`{${nodesMatch[0]}}`);
            if (Array.isArray(partial.nodes) && partial.nodes.length > 0) {
                return partial;
            }
        }
    }
    catch { }
    return null;
}
/**
 * Parse the LLM response JSON with multiple fallback strategies.
 * Returns null on failure.
 */
export function parseArchitectResponse(response) {
    const parsed = repairAndParseJSON(response);
    if (!parsed)
        return null;
    if (typeof parsed === 'object' && parsed !== null) {
        const obj = parsed;
        if (Array.isArray(obj.nodes) && obj.nodes.length > 0) {
            // A node carrying a recognisable filename in ANY accepted key is usable
            // (see nodeLabelOf). When not a single node has one, the model answered in
            // the wrong shape entirely (e.g. an array of bare strings, or objects with
            // only `type`): accepting that would make sanitizeNodes fabricate
            // "Node 1..N" for the whole graph — reject so the retry prompt asks for
            // valid JSON instead of silently shipping a canvas of blank nodes.
            if (!obj.nodes.some((n) => nodeLabelOf(n)))
                return null;
            return { nodes: obj.nodes, edges: (obj.edges || []) };
        }
    }
    return null;
}
/**
 * Resolve a node's filename from the raw LLM JSON.
 *
 * The architect prompt documents a `label` field, but models routinely put the
 * filename under another key: the qwen-coder family answers that prompt with
 * `{ "name": "src/index.ts", "type": "entry" }` — no `label`, no
 * `description`. Reading only `n.label` handed every one of those nodes to the
 * `Node ${i + 1}` placeholder, so a real build request rendered as a canvas of
 * blank nodes labeled "Node 1".."Node N". Accept the common aliases so a node
 * that DOES carry a filename keeps it.
 */
export function nodeLabelOf(n) {
    if (!n || typeof n !== 'object')
        return '';
    const o = n;
    // First key that yields a NON-EMPTY STRING wins. A present-but-unusable
    // `label` (empty string, number, null) must fall through to `name` — an
    // empty label is exactly the blank-node case this exists to catch.
    for (const key of ['label', 'name', 'file', 'filename', 'path']) {
        const raw = o[key];
        if (typeof raw === 'string' && raw.trim())
            return raw.trim();
    }
    return '';
}
/**
 * Sanitize and validate raw node data from the LLM.
 */
export function sanitizeNodes(nodes) {
    const validTypes = new Set(NODE_TYPES);
    return nodes.map((n, i) => ({
        label: (nodeLabelOf(n) || `Node ${i + 1}`).slice(0, 60),
        description: (n.description || '').trim().slice(0, 1000),
        type: validTypes.has(n.type) ? n.type : 'logic',
        language: n.language || 'typescript',
        position: {
            x: typeof n.position?.x === 'number' ? n.position.x : 250 + (i % 3) * 200,
            y: typeof n.position?.y === 'number' ? n.position.y : 300 + Math.floor(i / 3) * 170,
        },
        // Pass through uiPorts and suggestedWidgets from the LLM output
        uiPorts: n.uiPorts || undefined,
        suggestedWidgets: (n.suggestedWidgets && Array.isArray(n.suggestedWidgets) && n.suggestedWidgets.length > 0)
            ? n.suggestedWidgets.filter((sw) => sw.label && sw.type)
            : undefined,
    }));
}
/**
 * Heuristic: is this request for a CLIENT-SIDE (presentation) app rather than
 * a server/backend system? Used to stop the type-distribution enforcer from
 * bolting a database + REST-handler layer onto apps that should be pure UI
 * (the countdown-timer→SQLite/CRUD-server failure the live eval caught).
 * True when: targetOS is web, the goal/purpose is strongly client-side, or
 * every existing node is a UI-layer node (nothing for a DB/API to serve).
 */
export function isClientSideRequest(goal, purpose, targetOS, nodes) {
    if (targetOS && targetOS.toLowerCase() === 'web')
        return true;
    const text = `${goal || ''} ${purpose || ''}`.toLowerCase();
    // Substring keywords (no regex escapes — keeps the source free of the
    // backslash-escaping pitfalls that silently corrupt regex literals).
    const CLIENT_SIDE_KEYWORDS = [
        'web page', 'website', 'landing page', 'frontend', 'front end', 'spa',
        'single page', 'single-page', 'client-side', 'browser', 'gui app',
        'dashboard', 'widget', 'countdown', 'timer', 'calculator', 'todo',
        'note pad', 'notepad', 'game', 'quiz', 'landing',
    ];
    if (CLIENT_SIDE_KEYWORDS.some(k => text.includes(k)))
        return true;
    if (nodes.length > 0 && nodes.every(n => ['ui', 'gui-layout', 'input', 'output', 'ui-functions'].includes(n.type)))
        return true;
    return false;
}
/**
 * ENFORCE required node type distribution.
 * If the LLM omitted critical types (ui, database, api) for apps with >3 nodes,
 * auto-insert placeholder nodes to ensure the architecture is complete.
 *
 * `clientSide` skips database/API injection entirely — a browser app has no
 * server to expose handlers for and no schema to persist.
 */
export function enforceRequiredTypes(nodes, _goal, lang, clientSide = false) {
    if (nodes.length <= 3)
        return nodes; // small apps don't need all layers
    const hasType = (type) => nodes.some(n => n.type === type);
    // Full language→extension map (getExtensionForLanguage), not a 4-case
    // ternary: the old chain only special-cased go/csharp/swift/kotlin and fell
    // through to '.ts' for everything else, so a C++ plan got an inserted node
    // literally named "ui.ts" (same for java/php/ruby/rust/python).
    const ext = getExtensionForLanguage(lang);
    const missing = [];
    // Calculate a reasonable position for inserted nodes
    const maxY = Math.max(...nodes.map(n => n.position?.y || 0), 300);
    const maxX = Math.max(...nodes.map(n => n.position?.x || 0), 500);
    if (!hasType('ui')) {
        missing.push({
            label: `ui${ext}`,
            description: `User interface layer. Renders output and handles user input. For CLI: prints formatted output, reads stdin. For web: HTML templates or JSON API responses. Imports: types, handlers.`,
            type: 'ui',
            language: lang,
            position: { x: maxX + 100, y: maxY + 100 },
        });
    }
    // Client-side apps: no database and no API-handler layer. Injecting them
    // forced SQLite repositories and REST handlers into browser apps that never
    // needed persistence or a server.
    if (!clientSide && !hasType('database')) {
        missing.push({
            label: `repository${ext}`,
            description: `Data persistence layer. Manages application data in ${lang === 'go' ? 'SQLite' : 'a database or file store'}. Handles CRUD operations, connection pooling, and data validation. Exports: Create, Read, Update, Delete, List methods.`,
            type: 'database',
            language: lang,
            position: { x: maxX + 100, y: maxY + 250 },
        });
    }
    if (!clientSide && !hasType('api')) {
        missing.push({
            label: `handlers${ext}`,
            description: `API request handlers. Routes incoming requests to business logic, validates input, formats JSON responses. Handles HTTP methods (GET, POST, PUT, DELETE). Imports: service, types.`,
            type: 'api',
            language: lang,
            position: { x: maxX + 100, y: maxY + 400 },
        });
    }
    if (missing.length > 0) {
        console.log(`[architect] Enforcing type distribution: inserted ${missing.length} missing node(s) (${missing.map(n => n.type).join(', ')})`);
        return [...nodes, ...missing];
    }
    return nodes;
}
/**
 * Build React Flow-compatible node objects with generated IDs.
 */
export function buildFlowNodes(sanitizedNodes) {
    const idMap = {};
    const nodes = sanitizedNodes.map((n) => {
        const nodeId = `node_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        idMap[n.label] = nodeId;
        return {
            id: nodeId,
            type: n.type,
            position: n.position,
            data: {
                label: n.label,
                description: n.description,
                type: n.type,
                status: 'pending',
                language: n.language,
                resourceFiles: getPlaceholderFileNames(n.type, n.language),
            },
        };
    });
    return { nodes, idMap };
}
/**
 * Build and validate edges, filtering out any that reference unknown node labels.
 */
export function buildFlowEdges(edges, sanitizedNodes, idMap) {
    const nodeLabels = new Set(sanitizedNodes.map((n) => n.label));
    return edges
        .filter((e) => e.source && e.target && nodeLabels.has(e.source) && nodeLabels.has(e.target))
        .map((e) => ({
        id: `edge_${idMap[e.source]}_${idMap[e.target]}`,
        source: idMap[e.source],
        target: idMap[e.target],
        type: 'default',
    }));
}
/**
 * ENFORCE minimum edge density (the build-eval P1 gap: 0.35 edges/node vs a
 * 0.7+ target). Edges model file dependencies — an app with >3 nodes but
 * almost no edges is an island graph whose imports were never modeled, which
 * is the ROOT CAUSE of the cross-file compile failures (files that import from
 * siblings the graph never connected).
 *
 * When a graph with >3 nodes has fewer than 0.3 edges/node, auto-generate the
 * standard dependency chain (the same edges the rule-based fallback emits:
 * repository → service → handlers → main, plus types/config/middleware fan-in),
 * filtered to nodes that actually exist. Idempotent — never duplicates an
 * existing edge.
 */
// Standard server-side dependency chain (repository → service → handlers →
// main, plus types/config/middleware fan-in) — the rule-based fallback's graph.
const SERVER_EDGE_CANDIDATES = [
    { source: 'repository', target: 'service' },
    { source: 'service', target: 'handlers' },
    { source: 'handlers', target: 'main' },
    { source: 'config', target: 'main' },
    { source: 'types', target: 'handlers' },
    { source: 'types', target: 'service' },
    { source: 'types', target: 'repository' },
    { source: 'middleware', target: 'main' },
    { source: 'auth', target: 'handlers' },
    { source: 'auth', target: 'main' },
    { source: 'cache', target: 'repository' },
    { source: 'events', target: 'service' },
    { source: 'websocket', target: 'handlers' },
    { source: 'websocket', target: 'main' },
    { source: 'validators', target: 'handlers' },
    { source: 'migrations', target: 'repository' },
];
// CLIENT-SIDE dependency chain for browser/GUI apps (ui + logic only, no
// api/database layers). The server chain found nothing to wire on a pure-UI
// graph, so browser apps kept shipping with 0 edges — and 0 edges means the
// FileGenerator never wires the imports (the measured pomodoro-timer build:
// TS2304 'CoreEngine' not imported, ui.ts with no connection to main). An
// edge "X → Y" means Y imports from X: main imports the app logic + the UI;
// the UI imports the app logic + shared types; logic imports types/utils.
const CLIENT_SIDE_EDGE_CANDIDATES = [
    { source: 'types', target: 'main' },
    { source: 'types', target: 'app' },
    { source: 'types', target: 'ui' },
    { source: 'app', target: 'main' },
    { source: 'ui', target: 'main' },
    { source: 'app', target: 'ui' },
    { source: 'utils', target: 'app' },
    { source: 'utils', target: 'ui' },
    { source: 'state', target: 'app' },
    { source: 'state', target: 'ui' },
    { source: 'renderer', target: 'main' },
];
const SERVER_TYPE_FOR_ROLE = {
    repository: 'database',
    handlers: 'api',
    service: 'logic',
    main: 'logic',
    config: 'logic',
    types: 'logic',
    middleware: 'logic',
    auth: 'api',
    cache: 'database',
    events: 'logic',
    websocket: 'api',
    validators: 'logic',
    migrations: 'database',
};
const CLIENT_SIDE_TYPE_FOR_ROLE = {
    types: 'logic',
    app: 'logic',
    main: 'logic',
    utils: 'logic',
    state: 'logic',
};
/** Entry-point-ish labels (main/index/entry/app) — the client-side 'main' role's natural home. */
const ENTRY_LIKE_LABEL = /^(main|index|entry|start|run|app)[.\-_]/;
/**
 * ENFORCE minimum edge density (the build-eval P1 gap: 0.35 edges/node vs a
 * 0.7+ target). Edges model file dependencies — an app with >3 nodes but
 * almost no edges is an island graph whose imports were never modeled, which
 * is the ROOT CAUSE of the cross-file compile failures (files that import from
 * siblings the graph never connected).
 *
 * When a graph with >3 nodes has fewer than 0.3 edges/node, auto-generate the
 * standard dependency chain — the SERVER chain (repository → service →
 * handlers → main, plus types/config/middleware fan-in) for apps with
 * api/database layers, or the CLIENT-SIDE chain (main ← ui/app ← types/utils)
 * for browser/GUI graphs (ui/gui-layout nodes and no api/database nodes) —
 * filtered to nodes that actually exist. Idempotent — never duplicates an
 * existing edge.
 */
export function enforceEdgeDensity(nodes, edges) {
    if (nodes.length <= 3)
        return edges; // small apps legitimately have few edges
    const density = edges.length / nodes.length;
    if (density >= 0.3)
        return edges;
    // Client-side detection mirrors isClientSideRequest's structural test: UI
    // nodes present, no server layers. Browser apps have no repository/handlers
    // for the server chain to find, so they need their own wiring.
    const clientSide = nodes.some(n => n.type === 'ui' || n.type === 'gui-layout')
        && !nodes.some(n => n.type === 'api' || n.type === 'database');
    const edgeCandidates = clientSide ? CLIENT_SIDE_EDGE_CANDIDATES : SERVER_EDGE_CANDIDATES;
    const existing = new Set(edges.map(e => `${e.source}->${e.target}`));
    const added = [];
    // Type fallbacks for candidates whose label doesn't start with the
    // conventional name (e.g. "data-store.ts" is still the database layer):
    const TYPE_FOR_ROLE = clientSide ? CLIENT_SIDE_TYPE_FOR_ROLE : SERVER_TYPE_FOR_ROLE;
    const findNode = (role, excludeLabel) => {
        const byLabel = nodes.find(n => n.label.startsWith(role) && n.label !== excludeLabel);
        if (byLabel)
            return byLabel;
        if (clientSide && role === 'main') {
            // Client-side: the entry point IS entry-point-ish (main.ts/index.ts/
            // app.ts) — the type fallback must PREFER it, unlike other roles.
            return nodes.find(n => n.label !== excludeLabel && ENTRY_LIKE_LABEL.test(n.label));
        }
        if (clientSide && role === 'ui') {
            return nodes.find(n => (n.type === 'ui' || n.type === 'gui-layout') && n.label !== excludeLabel);
        }
        const byType = TYPE_FOR_ROLE[role];
        if (!byType)
            return undefined;
        // Type-based fallback: prefer labels that are NOT entry-point-ish
        // (main/index/entry/app) so the 'service'/'app' role lands on the
        // business layer, not the entry point.
        return nodes.find(n => n.type === byType && n.label !== excludeLabel && !ENTRY_LIKE_LABEL.test(n.label));
    };
    for (const cand of edgeCandidates) {
        const sourceNode = findNode(cand.source, '');
        const targetNode = findNode(cand.target, sourceNode?.label || '');
        if (!sourceNode || !targetNode || sourceNode.label === targetNode.label)
            continue;
        const key = `${sourceNode.label}->${targetNode.label}`;
        if (existing.has(key))
            continue;
        existing.add(key);
        added.push({ source: sourceNode.label, target: targetNode.label });
    }
    if (added.length > 0) {
        console.log(`[architect] Edge density ${density.toFixed(2)} below 0.3 — auto-generated ${added.length} ${clientSide ? 'client-side' : 'standard'} dependency edge(s)`);
        return [...edges, ...added];
    }
    return edges;
}
/**
 * Validate the request payload. Returns an error message or null.
 */
export function validateArchitectRequest(goal) {
    if (!goal || typeof goal !== 'string' || goal.trim().length === 0) {
        return 'A non-empty goal string is required.';
    }
    return null;
}
// ─── Rule-based fallback architecture generator ─────────────────────────
// Generates sensible default nodes when the LLM fails to return valid JSON.
// Uses the goal text to infer complexity and creates appropriate file structure.
// Language comes from the app's DOMAIN (inferLanguageForGoal), never from the
// OS alone — a web goal must not become a Go server stack.
const OS_FRAMEWORK_MAP = {
    linux: 'Go standard library / gin',
    windows: '.NET / ASP.NET',
    mac: 'SwiftUI / Vapor',
    ios: 'SwiftUI / UIKit',
    android: 'Jetpack Compose / Ktor',
};
/**
 * Infer complexity level from the goal description.
 * Simple: <40 chars, few keywords
 * Medium: 40-100 chars, moderate detail
 * Complex: 100-200 chars, detailed requirements
 * Enterprise: >200 chars or mentions specific enterprise features
 */
function inferComplexity(goal) {
    const lower = goal.toLowerCase();
    const enterpriseKeywords = ['enterprise', 'multi-user', 'scalable', 'microservice', 'distributed',
        'kubernetes', 'docker', 'ci/cd', 'monitoring', 'analytics', 'realtime'];
    const complexKeywords = ['auth', 'database', 'api', 'websocket', 'payment', 'chat',
        'streaming', 'video', 'editor', 'pipeline'];
    const enterpriseCount = enterpriseKeywords.filter(k => lower.includes(k)).length;
    const complexCount = complexKeywords.filter(k => lower.includes(k)).length;
    const length = goal.length;
    if (enterpriseCount >= 1 || length > 200)
        return 'enterprise';
    if (complexCount >= 2 || length > 100)
        return 'complex';
    if (complexCount >= 1 || length > 40)
        return 'medium';
    return 'simple';
}
function getExtensionForLanguage(lang) {
    const extMap = {
        go: '.go',
        csharp: '.cs',
        swift: '.swift',
        kotlin: '.kt',
        javascript: '.js',
        typescript: '.ts',
        python: '.py',
        rust: '.rs',
        java: '.java',
        php: '.php',
        ruby: '.rb',
        cpp: '.cpp',
        c: '.c',
    };
    return extMap[lang] || '.ts';
}
/**
 * Web fallback architecture — the DOMAIN-correct fallback for browser/GUI
 * goals (timers, calculators, games, widgets, dashboards). Pure TypeScript +
 * HTML/CSS with a real dependency chain, so the tsc gate and the preview
 * wrapper can actually validate and run what was planned.
 */
export function generateWebFallbackArchitecture(goal) {
    const nodes = [
        {
            label: 'main.ts',
            description: `Entry point for ${goal}: parses the page's initial state, wires the UI to the logic layer, and starts rendering. Imports: app, ui. Exports: start().`,
            type: 'logic',
            language: 'typescript',
            position: { x: 500, y: 50 },
        },
        {
            label: 'app.ts',
            description: `Core application logic for ${goal}: state management, input validation, and the business rules the UI calls. No DOM access. Imports: types. Exports: createState(), updateState(), getState().`,
            type: 'logic',
            language: 'typescript',
            position: { x: 300, y: 220 },
        },
        {
            label: 'types.ts',
            description: 'Shared type definitions: state shapes, input payloads, and result types used by the app and UI layers.',
            type: 'logic',
            language: 'typescript',
            position: { x: 100, y: 220 },
        },
        {
            label: 'ui.ts',
            description: 'User interface layer: builds the DOM with createElement (NO JSX), renders state to #app-container, attaches event handlers that call the app logic. Imports: app, types. Exports: render(state, container), bindEvents(handlers).',
            type: 'ui',
            language: 'typescript',
            position: { x: 500, y: 400 },
        },
        {
            label: 'index.html',
            description: 'HTML shell: loads main.ts as a module, contains the #app-container mount point and the page title.',
            type: 'ui',
            language: 'html',
            position: { x: 700, y: 400 },
        },
        {
            label: 'styles.css',
            description: 'Stylesheet: layout, colors, and responsive sizing for the app interface.',
            type: 'ui',
            language: 'css',
            position: { x: 700, y: 560 },
        },
    ];
    const edges = [
        { source: 'main.ts', target: 'app.ts' },
        { source: 'main.ts', target: 'ui.ts' },
        { source: 'ui.ts', target: 'app.ts' },
        { source: 'app.ts', target: 'types.ts' },
        { source: 'ui.ts', target: 'types.ts' },
    ];
    console.log(`[architect] Generated web fallback architecture: ${nodes.length} nodes, ${edges.length} edges (typescript)`);
    return { nodes, edges };
}
/**
 * Generate a complete fallback architecture when the LLM fails.
 * Uses rule-based templates keyed by OS/language to create sensible defaults.
 * The language is inferred from the app's DOMAIN — web/CLI goals never
 * fall back to a Go server stack (the countdown-timer→main.go failure class).
 */
export function generateFallbackArchitecture(goal, purpose, targetOS, uiPreference) {
    const lang = inferLanguageForGoal(goal, purpose, targetOS, uiPreference);
    const clientSide = isClientSideRequest(goal, purpose, targetOS, []);
    if (clientSide) {
        return generateWebFallbackArchitecture(goal);
    }
    const ext = getExtensionForLanguage(lang);
    const complexity = inferComplexity(goal);
    const framework = OS_FRAMEWORK_MAP[targetOS] || 'standard libraries';
    // Build platform-specific template nodes
    const baseNodes = [
        {
            filename: `main${ext}`,
            type: 'logic',
            description: `Application entry point. Initializes config, sets up routes, starts the HTTP server on the configured port. Handles graceful shutdown (SIGTERM/SIGINT). Imports: config, routes, middleware. Framework: ${framework}.`,
        },
        {
            filename: `config${ext}`,
            type: 'logic',
            description: `Configuration loader. Reads environment variables, CLI flags, and optional config file. Provides typed config struct with defaults. Exports: Config struct, LoadConfig() function, Validate() method.`,
        },
        {
            filename: `types${ext}`,
            type: 'logic',
            description: `Shared type definitions and data models. Defines request/response structs, enums, constants, and error types used across the application.`,
        },
        {
            filename: `repository${ext}`,
            type: 'database',
            description: `Data access layer. Implements CRUD operations using ${lang === 'go' ? 'database/sql with SQLite' : 'appropriate ORM or database driver'}. Thread-safe connection pooling. Exports: Repository struct with Create, Read, Update, Delete, List methods.`,
        },
        {
            filename: `service${ext}`,
            type: 'logic',
            description: `Business logic layer. Validates inputs, enforces business rules, orchestrates data between repository and handlers. Exports: Service struct with business methods. Handles errors with typed error returns.`,
        },
        {
            filename: `handlers${ext}`,
            type: 'api',
            description: `HTTP request handlers. Routes incoming requests to appropriate service methods. Parses request bodies, validates input, formats responses as JSON. Imports: service, types. Exports: Handler struct with route handler methods.`,
        },
        {
            filename: `ui${ext}`,
            type: 'ui',
            description: `User interface layer. Renders the application UI using platform-appropriate components. For CLI apps: terminal output formatting. For web apps: HTML templates or JSON API responses for a frontend.`,
        },
        {
            filename: `middleware${ext}`,
            type: 'logic',
            description: `HTTP middleware. Implements logging, CORS headers, request ID injection, panic recovery, and request timing. Wraps handlers with common cross-cutting concerns.`,
        },
    ];
    // Additional nodes based on complexity
    const additionalNodes = {
        medium: [
            { filename: `migrations${ext === '.go' ? '.sql' : ext}`, type: 'database', description: `Database schema migrations. Defines table creation, indexes, seed data, and migration version tracking. Applied in order on startup to ensure schema is up to date.` },
            { filename: `validators${ext}`, type: 'logic', description: `Input validation utilities. Provides reusable validation functions for common patterns (email, URL, phone, required fields, length constraints). Returns structured validation errors.` },
            { filename: `errors${ext}`, type: 'logic', description: `Application-specific error types and error handling utilities. Defines typed errors for common failure modes (not found, conflict, validation, unauthorized). Implements error wrapping and stack tracing.` },
            { filename: `tests${ext}`, type: 'logic', description: `Unit and integration tests. Covers service layer business logic, repository CRUD operations, and handler request/response cycles. Uses table-driven test patterns.` },
        ],
        complex: [
            { filename: `migrations${ext === '.go' ? '.sql' : ext}`, type: 'database', description: `Database schema migrations. Defines table creation, indexes, seed data, and migration version tracking. Applied in order on startup to ensure schema is up to date.` },
            { filename: `validators${ext}`, type: 'logic', description: `Input validation utilities. Provides reusable validation functions for common patterns (email, URL, phone, required fields, length constraints). Returns structured validation errors.` },
            { filename: `errors${ext}`, type: 'logic', description: `Application-specific error types and error handling utilities. Defines typed errors for common failure modes.` },
            { filename: `events${ext}`, type: 'logic', description: `Event bus for internal pub/sub communication. Components publish events (e.g., UserCreated, ItemUpdated) and subscribe to relevant events. Decouples components for testability.` },
            { filename: `cache${ext}`, type: 'database', description: `Caching layer. In-memory cache with TTL support. Reduces database load for frequently accessed data. Exports: Cache struct with Get, Set, Delete, Clear methods. Thread-safe with mutex.` },
            { filename: `auth${ext}`, type: 'api', description: `Authentication and authorization middleware. Handles JWT token generation/validation, password hashing (bcrypt), session management, and role-based access control.` },
            { filename: `websocket${ext}`, type: 'api', description: `WebSocket connection manager. Handles client connections, message broadcasting, room management, and heartbeat/ping-pong for connection health. Implements reconnection logic.` },
            { filename: `tests${ext}`, type: 'logic', description: `Comprehensive test suite. Unit tests for all service methods, integration tests for repository, and HTTP handler tests with request/response validation.` },
            { filename: `.env.example`, type: 'logic', description: `Example environment configuration file. Lists all required environment variables with placeholder values and documentation for each setting.` },
        ],
        enterprise: [
            { filename: `migrations${ext === '.go' ? '.sql' : ext}`, type: 'database', description: `Database schema migrations. Defines table creation, indexes, seed data, and migration version tracking. Applied in order on startup to ensure schema is up to date.` },
            { filename: `validators${ext}`, type: 'logic', description: `Input validation utilities. Provides reusable validation functions for common patterns. Returns structured validation errors.` },
            { filename: `errors${ext}`, type: 'logic', description: `Application-specific error types. Defines typed errors for common failure modes.` },
            { filename: `events${ext}`, type: 'logic', description: `Event bus for internal pub/sub communication. Decouples components for testability.` },
            { filename: `cache${ext}`, type: 'database', description: `Caching layer. In-memory cache with TTL. Thread-safe with mutex.` },
            { filename: `auth${ext}`, type: 'api', description: `Authentication middleware. JWT token generation/validation, password hashing, RBAC.` },
            { filename: `websocket${ext}`, type: 'api', description: `WebSocket connection manager. Handles connections, broadcasting, room management.` },
            { filename: `metrics${ext}`, type: 'api', description: `Application metrics and health endpoints. Exposes Prometheus metrics, health check, readiness probe, and debug endpoints. Tracks request duration, error rates, and active connections.` },
            { filename: `hot_reload${ext}`, type: 'logic', description: `Hot-reload configuration watcher. Monitors config file changes and applies updates without restarting the server. Uses file system watcher (inotify on Linux, FSEvents on macOS). Emits change events to subscribers.` },
            { filename: `queue${ext}`, type: 'logic', description: `Background job queue. Processes asynchronous tasks like email sending, report generation, and data exports. Supports retry with backoff, dead letter queue, and job scheduling.` },
            { filename: `tests${ext}`, type: 'logic', description: `Comprehensive test suite. Unit, integration, and e2e tests.` },
            { filename: `Dockerfile`, type: 'logic', description: `Multi-stage Docker build. Stage 1: build the application binary. Stage 2: minimal runtime image with CA certificates and timezone data. Exposes app port, uses non-root user.` },
            { filename: `docker-compose.yml`, type: 'logic', description: `Docker Compose configuration. Defines app service, database (PostgreSQL), cache (Redis), and queue worker. Health checks, volume mounts, and network configuration included.` },
        ],
    };
    // Build the final node list
    const allTemplates = [
        ...baseNodes,
        ...(additionalNodes[complexity] || []),
    ];
    const nodes = allTemplates.map((t, i) => ({
        label: t.filename,
        description: t.description,
        type: t.type,
        language: lang,
        position: {
            x: 250 + (i % 4) * 200,
            y: 100 + Math.floor(i / 4) * 180,
        },
    }));
    // Build edges: data flows from repository → service → handlers → main
    const edgeCandidates = [
        { source: 'repository', target: 'service' },
        { source: 'service', target: 'handlers' },
        { source: 'handlers', target: 'main' },
        { source: 'config', target: 'main' },
        { source: 'types', target: 'handlers' },
        { source: 'types', target: 'service' },
        { source: 'types', target: 'repository' },
        { source: 'middleware', target: 'main' },
        { source: 'auth', target: 'handlers' },
        { source: 'auth', target: 'main' },
        { source: 'cache', target: 'repository' },
        { source: 'events', target: 'service' },
        { source: 'websocket', target: 'handlers' },
        { source: 'websocket', target: 'main' },
        { source: 'validators', target: 'handlers' },
        { source: 'migrations', target: 'repository' },
    ];
    // Filter edges to only include nodes that exist in the generated set
    const nodeLabels = new Set(nodes.map(n => n.label.replace(ext, '').split('.')[0]));
    const edges = edgeCandidates
        .filter(e => {
        const sourceMatch = nodes.some(n => n.label.startsWith(e.source));
        const targetMatch = nodes.some(n => n.label.startsWith(e.target));
        return sourceMatch && targetMatch;
    })
        .map(e => ({
        source: nodes.find(n => n.label.startsWith(e.source)).label,
        target: nodes.find(n => n.label.startsWith(e.target)).label,
    }));
    console.log(`[architect] Generated fallback architecture: ${nodes.length} nodes, ${edges.length} edges (${complexity} complexity)`);
    return { nodes, edges };
}
let currentProjectState = null;
/**
 * Update the current project state cache (called by other routes when designs change).
 */
export function updateCurrentProjectState(state) {
    currentProjectState = state;
}
/**
 * Get the current project state cache.
 * Returns null if no state has been set yet.
 */
export function getCurrentProjectState() {
    return currentProjectState;
}
router.get('/current', (_req, res) => {
    if (!currentProjectState) {
        res.status(404).json({
            success: false,
            error: 'No current project state available. Create a design first.',
        });
        return;
    }
    res.json({
        success: true,
        ...currentProjectState,
    });
});
/**
 * POST /api/architect/current
 * Update the cached project state from the frontend.
 * This lets the frontend sync its latest canvas state (nodes, edges, etc.)
 * to the backend before pushing, ensuring the
 * auto-place LLM has the most up-to-date architecture to work with.
 */
router.post('/current', (req, res) => {
    const { name, goal, purpose, targetOS, nodes, edges, uiFunctions, placedWidgets } = req.body;
    if (!nodes && !edges) {
        res.status(400).json({ error: 'At least nodes or edges is required' });
        return;
    }
    currentProjectState = {
        name: name || currentProjectState?.name || 'Untitled',
        goal: goal || currentProjectState?.goal || '',
        purpose: purpose || currentProjectState?.purpose || '',
        targetOS: targetOS || currentProjectState?.targetOS || 'linux',
        nodes: nodes || currentProjectState?.nodes || [],
        edges: edges || currentProjectState?.edges || [],
        uiFunctions: uiFunctions || currentProjectState?.uiFunctions || [],
        placedWidgets: placedWidgets || currentProjectState?.placedWidgets || [],
    };
    console.log('[architect] Project state updated via POST /current:', currentProjectState.nodes.length, 'nodes,', currentProjectState.edges.length, 'edges,', 'purpose:', currentProjectState.purpose || '(none)');
    res.json({
        success: true,
        ...currentProjectState,
    });
});
// ─── Architect prompt endpoint ──────────────────────────────────────────────
// GET /api/architect/prompt
// Returns the architect system prompt used for node architecture generation.
// The frontend fetches this to keep the fallback prompt in sync.
router.get('/prompt', (_req, res) => {
    res.json({
        success: true,
        prompt: ARCHITECT_SYSTEM_PROMPT,
    });
});
// ─── Architect plan endpoint ───────────────────────────────────────────────
// POST /api/architect/plan
// Takes { goal, purpose, targetOS } and returns { nodes, edges }
// The LLM plans the complete node architecture for the app.
router.post('/plan', async (req, res) => {
    try {
        const { goal, purpose, targetOS, scale } = req.body;
        const validationError = validateArchitectRequest(goal);
        if (validationError) {
            res.status(400).json({ error: validationError });
            return;
        }
        // Broadcast progress: starting
        broadcastArchitectProgress({ phase: 'researching', message: '🔍 Researching similar app architectures...', percent: 5 });
        // Gather relevant knowledge from past architectures
        let knowledgeContext = '';
        try {
            const patterns = knowledgeStore.query({
                nodeType: 'master',
                language: targetOS === 'python' ? 'python' : 'typescript',
                targetOS: targetOS || 'linux',
                searchText: goal,
                limit: 3,
            });
            if (patterns.length > 0) {
                knowledgeContext = patterns
                    .map((p) => `- Pattern: ${p.title}\n  Description: ${p.description}\n  Code: ${p.code.slice(0, 300)}`)
                    .join('\n');
            }
        }
        catch {
            // Knowledge enrichment is optional
        }
        // ── Research similar designs on the internet, GitHub, and OpenSourceAlternative.to ──
        let referenceContext = '';
        broadcastArchitectProgress({ phase: 'researching', message: '🔍 Searching web, GitHub, and open source for reference designs...', percent: 10 });
        try {
            const searchText = purpose ? `${goal} ${purpose}` : goal;
            const searchService = getSearchService();
            // Limit maxResults to 2 per source to keep the prompt size manageable
            // (Ollama local models are slower with very large prompts)
            // Race research against a 15s timeout so a hanging external search doesn't block the whole request
            const research = await Promise.race([
                researchDesign(searchText.trim(), searchService, 2),
                new Promise((_, reject) => setTimeout(() => reject(new Error('Research timed out after 15s')), 15000)),
            ]);
            if (research && research.totalReferences > 0) {
                // Build a compact reference context — just the essentials
                const lines = [];
                lines.push(`📋 Reference designs found from the web, GitHub, and open source alternatives:`);
                for (const w of research.webResults.slice(0, 2)) {
                    lines.push(`  • ${w.title}`);
                    lines.push(`    ${w.content.substring(0, 200)}`);
                }
                for (const g of research.githubResults.slice(0, 2)) {
                    lines.push(`  • ⭐${g.stars} ${g.full_name}: ${g.description.substring(0, 150)}`);
                }
                for (const a of research.altResults.projects.slice(0, 2)) {
                    lines.push(`  • ${a.name} (${a.category}): ${a.description.substring(0, 150)}`);
                }
                lines.push(`\nUse these as inspiration for designing the app architecture.`);
                referenceContext = lines.join('\n');
                console.log(`[architect] Found ${research.totalReferences} reference designs for "${goal.substring(0, 50)}..."`);
                console.log(`  🌐 Web: ${research.webResults.length} results`);
                console.log(`  🐙 GitHub: ${research.githubResults.length} repos`);
                console.log(`  📦 OpenSourceAlt: ${research.altResults.totalFound} projects`);
            }
        }
        catch (err) {
            console.warn('[architect] Design research failed (non-fatal):', err.message);
        }
        // ── Inject library reference context ──
        let libraryContext;
        try {
            const searchText = purpose ? `${goal} ${purpose}` : goal;
            libraryContext = await getLibraryContextDense(searchText);
            if (libraryContext) {
                console.log(`[architect] Injected library context for "${searchText.substring(0, 50)}..."`);
            }
        }
        catch (err) {
            console.warn('[architect] Library context injection failed (non-fatal):', err.message);
        }
        const uiPreference = loadPreference().preference;
        const scaleN = normalizeScale(scale);
        if (scaleN)
            console.log(`[architect] Scale override requested: ${scaleN}`);
        const prompt = getArchitectPrompt(goal.trim(), (purpose || '').trim(), (targetOS || 'linux').trim(), knowledgeContext, referenceContext || undefined, undefined, libraryContext, uiPreference, scaleN);
        broadcastArchitectProgress({ phase: 'designing', message: '🧠 Designing application architecture with AI...', percent: 30 });
        const translator = new AITranslator();
        // ── Attempt to get a parseable response, with retry ──
        let response = '';
        let parsed = null;
        const MAX_ATTEMPTS = 3;
        for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            // Attempt 1 caps the response budget at 8192 tokens: with the doctrine +
            // knowledge/library/reference context the input is several thousand tokens,
            // and llama-server rejects input + max_tokens beyond the 16384 context
            // window ("Context size has been exceeded"). Plans are 1-3k tokens in
            // practice; retries stay at 6144.
            const maxTokens = attempt === 1 ? 8192 : 6144;
            const attemptPrompt = attempt === 1
                ? prompt
                : `${prompt}\n\nIMPORTANT: Your previous response had malformed JSON. Return ONLY valid JSON. No markdown, no extra text, no comments — just the JSON object with "nodes" and "edges" arrays.`;
            // Queue the LLM call — only 1 architect request processes at a time
            response = await architectQueue.enqueue(() => translator.reason(attemptPrompt, undefined, { maxTokens, timeoutMs: 600000 }));
            parsed = parseArchitectResponse(response);
            if (parsed) {
                broadcastArchitectProgress({ phase: 'validating', message: `✅ Architecture designed (${parsed.nodes.length} nodes, ${parsed.edges.length} connections)`, percent: 70 });
                break;
            }
            console.warn(`[architect] JSON parse failed (attempt ${attempt}/${MAX_ATTEMPTS}), retrying...`);
            broadcastArchitectProgress({ phase: 'designing', message: `⚠️ Retrying architecture design (attempt ${attempt}/${MAX_ATTEMPTS})...`, percent: 30 });
        }
        if (!parsed) {
            console.warn('[architect] All LLM attempts failed. Using rule-based fallback for:', goal.slice(0, 60));
            broadcastArchitectProgress({ phase: 'building', message: '⚠️ Using rule-based fallback architecture', percent: 75 });
            const fallback = generateFallbackArchitecture(goal, purpose || '', targetOS || 'linux');
            parsed = fallback;
        }
        broadcastArchitectProgress({ phase: 'validating', message: '🔧 Validating and sanitizing architecture nodes...', percent: 80 });
        // Validate structure
        if (!Array.isArray(parsed.nodes) || parsed.nodes.length === 0) {
            res.status(500).json({ error: 'LLM returned invalid architecture structure', raw: response });
            return;
        }
        // Validate and sanitize nodes
        let sanitizedNodes = sanitizeNodes(parsed.nodes);
        // Language comes from the app's DOMAIN (web/CLI → TypeScript; explicit
        // OS targets keep their native language), never from the OS default
        // alone — the countdown-timer→main.go failure class.
        const inferredLang = inferLanguageForGoal(goal.trim(), (purpose || '').trim(), (targetOS || 'linux').trim(), uiPreference);
        // Client-side requests (web pages, timers, widgets, …): the LLM still often
        // emits server layers (repository/handlers) because its architecture prompt
        // biases toward full-stack. Drop api/database nodes outright so a browser
        // app never ships with a SQLite repo and REST handlers bolted on, and skip
        // the type-enforcer's database/API injection.
        const clientSide = isClientSideRequest(goal, purpose || '', targetOS || '', sanitizedNodes);
        if (clientSide) {
            const before = sanitizedNodes.length;
            sanitizedNodes = sanitizedNodes.filter(n => n.type !== 'api' && n.type !== 'database');
            if (sanitizedNodes.length !== before) {
                console.log(`[architect] Client-side request — dropped ${before - sanitizedNodes.length} server-layer node(s) (api/database) from the plan`);
            }
        }
        // Coerce every node to the inferred language: browser apps are ALL
        // TypeScript (a single Go node in a web plan is a guaranteed build
        // failure), and unknown/typo'd languages collapse to the plan's language.
        if (clientSide) {
            const langs = sanitizedNodes.map(n => n.language);
            const normalized = normalizeClientSideLanguages(langs);
            sanitizedNodes.forEach((n, i) => { n.language = normalized[i]; });
        }
        else {
            sanitizedNodes.forEach((n) => { n.language = normalizeNodeLanguage(n.language, inferredLang); });
        }
        sanitizedNodes = enforceRequiredTypes(sanitizedNodes, goal, inferredLang, clientSide);
        // Build flow nodes with ID map
        const { nodes: flowNodes, idMap } = buildFlowNodes(sanitizedNodes);
        // Validate and create edges — enforcing minimum edge density so the graph
        // models cross-file imports (the build-eval P1 gap).
        const enforcedEdges = enforceEdgeDensity(sanitizedNodes, parsed.edges || []);
        const flowEdges = buildFlowEdges(enforcedEdges, sanitizedNodes, idMap);
        // ── Build Design Contract ──
        // Data comes from LLM JSON output — cast through any since strict port types
        // are validated at the shared contract layer, not at the JSON parsing layer
        const contractNodes = sanitizedNodes.map((n) => ({
            label: n.label,
            description: n.description,
            type: n.type,
            language: n.language,
            position: n.position,
            uiPorts: n.uiPorts,
            suggestedWidgets: n.suggestedWidgets,
        }));
        // Build the design contract
        const placedWidgets = flattenSuggestedWidgets(contractNodes);
        const hasContractWidgets = placedWidgets.length > 0;
        // Update current project state cache (include contract info)
        currentProjectState = {
            name: goal || 'Untitled',
            goal: goal || '',
            purpose: purpose || '',
            targetOS: targetOS || 'linux',
            nodes: flowNodes,
            edges: flowEdges,
            uiFunctions: contractNodes.map(n => ({
                id: deriveNodeId(n.label),
                label: n.label,
                type: 'button',
                description: n.description,
                defaultAction: '',
                category: 'utility',
                linkedNodeLabel: n.label,
                reasoning: n.uiPorts ? `Ports: ${(n.uiPorts.outputs || []).map(o => o.name).join(', ')}` : '',
            })),
            placedWidgets,
        };
        broadcastArchitectProgress({ phase: 'done', message: `✅ Architecture complete: ${flowNodes.length} nodes, ${flowEdges.length} edges`, percent: 100 });
        res.json({
            success: true,
            nodes: flowNodes,
            edges: flowEdges,
            architecture: {
                totalNodes: flowNodes.length,
                totalEdges: flowEdges.length,
                nodeTypes: [...new Set(flowNodes.map((n) => n.type))],
                languages: [...new Set(flowNodes.map((n) => n.data.language))],
            },
        });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error('[architect] Plan error:', message);
        broadcastArchitectProgress({ phase: 'error', message: `❌ Architecture planning failed: ${message}`, percent: 0 });
        res.status(500).json({ error: 'Failed to generate architecture plan.', details: message });
    }
});
// ─── Architect rework endpoint ────────────────────────────────────────────
// POST /api/architect/rework
// Takes { goal, purpose, targetOS, existingNodes, existingEdges } and returns { nodes, edges }
// The LLM inserts new nodes into the existing graph and rewires connections.
router.post('/rework', async (req, res) => {
    try {
        const { goal, purpose, targetOS, existingNodes, existingEdges } = req.body;
        if (!goal || typeof goal !== 'string') {
            res.status(400).json({ error: 'A goal string is required.' });
            return;
        }
        // Build a description of the existing graph
        const existingGraph = existingNodes?.length
            ? `EXISTING NODES:\n${existingNodes.map((n) => `  - ${n.label} (${n.type}): ${n.description || 'No description'}`).join('\n')}\n\nEXISTING EDGES:\n${(existingEdges || []).map((e) => `  ${e.source} → ${e.target}`).join('\n')}`
            : 'No existing nodes yet — create a fresh architecture.';
        const manifestoContext = getManifestoContext();
        const manifestoSection = manifestoContext ? `\n\nUser's Design Preferences:\n${manifestoContext}` : '';
        const reworkPrompt = `You are an expert software architect performing a **rework** on an existing architecture. A user has added a new component to their app, and you need to rewire the connections to integrate it.

USER'S APP:\nGoal: ${goal.trim()}\nPurpose: ${(purpose || '').trim()}\nTarget OS: ${(targetOS || 'linux').trim()}\n\n${existingGraph}${manifestoSection}\n\nTASK:\n1. Review the existing nodes and edges\n2. Determine which new nodes need to be added (if the existing nodes list doesn't include all files) — the user may have added 1-3 new nodes manually\n3. **Rewrite ALL edges** to properly connect every file (existing + new) in a directed dependency graph\n4. Update node positions to accommodate the new nodes in a logical layout\n5. **Return ALL nodes** (existing + new) with their updated descriptions and positions\n\nAvailable node types: ${NODE_TYPES.join(', ')}\nAvailable languages: javascript, typescript, python, rust, go, java, csharp, cpp, swift, kotlin, php, ruby\n\nReturn ONLY valid JSON with this structure:\n{\n  "nodes": [\n    {\n      "label": "filename (e.g. main.go, auth.ts)",\n      "description": "description of what this file does",\n      "type": "one of the node types",\n      "language": "programming language",\n      "position": { "x": number, "y": number }\n    }\n  ],\n  "edges": [\n    { "source": "filename of source", "target": "filename of target" }\n  ]\n}\n\nIMPORTANT: Include ALL nodes (existing and any new ones the user added). The edges must form a complete dependency graph. No markdown, no explanations — just the JSON.`;
        const translator = new AITranslator();
        const response = await architectQueue.enqueue(() => translator.reason(reworkPrompt, undefined, { maxTokens: 8192 }));
        let parsed = parseArchitectResponse(response);
        if (!parsed) {
            console.warn('[architect] Rework LLM failed. Using fallback with existing nodes.');
            if (existingNodes?.length) {
                parsed = {
                    nodes: existingNodes.map((n, i) => ({
                        label: n.data?.label || n.label || `Node ${i + 1}`,
                        description: n.data?.description || n.description || '',
                        type: n.data?.type || n.type || 'logic',
                        language: n.data?.language || n.language || 'typescript',
                        position: n.position || { x: 250 + (i % 3) * 200, y: 200 + Math.floor(i / 3) * 170 },
                    })),
                    edges: (existingEdges || []).map((e) => ({ source: e.source, target: e.target })),
                };
            }
            else {
                parsed = generateFallbackArchitecture(goal, purpose || '', targetOS || 'linux');
            }
        }
        if (!Array.isArray(parsed.nodes) || parsed.nodes.length === 0) {
            res.status(500).json({ error: 'LLM returned invalid rework structure', raw: response });
            return;
        }
        let sanitizedNodes = sanitizeNodes(parsed.nodes);
        // Rework is client-side aware too: strip server layers for presentation apps,
        // and coerce languages to the domain-inferred one (web/CLI → TypeScript).
        const inferredLang = inferLanguageForGoal(goal.trim(), (purpose || '').trim(), (targetOS || 'linux').trim());
        const reworkClientSide = isClientSideRequest(goal, purpose || '', targetOS || '', sanitizedNodes);
        if (reworkClientSide) {
            const before = sanitizedNodes.length;
            sanitizedNodes = sanitizedNodes.filter(n => n.type !== 'api' && n.type !== 'database');
            if (sanitizedNodes.length !== before) {
                console.log(`[architect] Rework client-side request — dropped ${before - sanitizedNodes.length} server-layer node(s) (api/database)`);
            }
        }
        if (reworkClientSide) {
            const langs = sanitizedNodes.map(n => n.language);
            const normalized = normalizeClientSideLanguages(langs);
            sanitizedNodes.forEach((n, i) => { n.language = normalized[i]; });
        }
        else {
            sanitizedNodes.forEach((n) => { n.language = normalizeNodeLanguage(n.language, inferredLang); });
        }
        sanitizedNodes = enforceRequiredTypes(sanitizedNodes, goal, inferredLang, reworkClientSide);
        const { nodes: flowNodes, idMap } = buildFlowNodes(sanitizedNodes);
        // Enforce minimum edge density for rework too (same P1 gap as the main path).
        const enforcedEdges = enforceEdgeDensity(sanitizedNodes, parsed.edges || []);
        const flowEdges = buildFlowEdges(enforcedEdges, sanitizedNodes, idMap);
        res.json({
            success: true,
            nodes: flowNodes,
            edges: flowEdges,
            architecture: {
                totalNodes: flowNodes.length,
                totalEdges: flowEdges.length,
                nodeTypes: [...new Set(flowNodes.map((n) => n.type))],
                languages: [...new Set(flowNodes.map((n) => n.data.language))],
            },
        });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error('[architect] Rework error:', message);
        res.status(500).json({ error: 'Failed to rework architecture.', details: message });
    }
});
export default router;
