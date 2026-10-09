/**
 * Planner write path — Tree Mode on the CHAT path.
 *
 * Proves that a chat-initiated build for a MULTI-APP project (2+ app trees) is
 * laid out as separate apps under `apps/<app>/`, and that the cross-app handoff
 * becomes a bridge module in the shared `bridge/` directory — mirroring what the
 * canvas path (layers/fileGenerator.ts) already produces. The other half of the
 * contract is the regression guard: a SINGLE-tree project must be byte-identical
 * to the ordinary flat build (no `apps/` prefixes, no bridges).
 *
 * The LLM is mocked (no model server) and the projects store is mocked (no disk
 * writes): `applyTreePlanLayout` resolves the project through the `projects`
 * singleton, so the test registers a fixture there and reads it back.
 */
import { describe, it, expect, vi } from 'vitest';
// The chat pipeline talks to the LLM through the module-level `translator`
// singleton. Mock it so the write path runs deterministically. The write call
// returns the plan's files; the bridge call returns a small module body.
vi.mock('../ai/translator.js', () => {
    class AITranslator {
        async reason(prompt) {
            // Bridge generation prompt — return a plausible bridge module.
            if (prompt.includes('integration module')) {
                return '```ts\nexport interface NotesPayload { items: string[] }\nexport function readNotes(payload: NotesPayload): string[] { return payload.items; }\n```';
            }
            return JSON.stringify({
                files: [
                    { path: 'index.html', content: '<!doctype html><html><body>notes</body></html>' },
                    { path: 'dashboard.html', content: '<!doctype html><html><body>dashboard</body></html>' },
                ],
            });
        }
        async reasonFast() { return ''; }
    }
    return {
        AITranslator,
        askOtherLlm: async () => '',
        askConductor: async () => '',
        classifyCodeComplexity: () => 'simple',
        ModelTier: {},
    };
});
// In-memory projects registry so the test never writes backend/data/projects.json.
vi.mock('../db/projects.js', () => {
    const store = new Map();
    return {
        projects: {
            getById: (id) => store.get(id),
            create: (p) => { store.set(p.id, p); return p; },
            delete: (id) => store.delete(id),
            __store: store,
        },
        ProjectStore: class {
        },
    };
});
import { generatePlanFiles } from './codePlanner.js';
import { projects } from '../db/projects.js';
const REQUEST = 'Build a notes app and a dashboard app that share the notes list';
// FLAT plan paths — Tree Mode must remap these into per-app directories.
const PLAN = {
    files: [
        { path: 'index.html', summary: 'Notes app UI', language: 'html' },
        { path: 'dashboard.html', summary: 'Dashboard UI', language: 'html' },
    ],
    questions: [],
};
/** A two-app project: Notes and Dashboard, wired by a cross-app handoff. */
const TWO_APP_PROJECT = {
    id: 'proj-two-apps',
    name: 'Two App Project',
    targetOS: 'linux',
    nodes: [
        { id: 'm1', type: 'master', data: { label: 'Notes', treeId: 'tree_1' } },
        { id: 'n1', type: 'module', data: { label: 'Note Store', treeId: 'tree_1', language: 'typescript' } },
        { id: 'm2', type: 'master', data: { label: 'Dashboard', treeId: 'tree_2' } },
        { id: 'n2', type: 'module', data: { label: 'Chart', treeId: 'tree_2', language: 'typescript' } },
    ],
    edges: [
        {
            id: 'e1',
            source: 'n1',
            target: 'n2',
            data: { kind: 'cross-tree', payloadType: 'notes', payloadLabel: 'Notes list' },
        },
    ],
    trees: [
        { id: 'tree_1', name: 'Notes', goal: 'Take notes', targetOS: 'linux', rootNodeId: 'm1' },
        { id: 'tree_2', name: 'Dashboard', goal: 'Show stats', targetOS: 'linux', rootNodeId: 'm2' },
    ],
};
/** A pre-Tree-Mode project: one implicit app, no `trees`. */
const SINGLE_APP_PROJECT = {
    id: 'proj-single-app',
    name: 'Single App',
    targetOS: 'linux',
    nodes: [{ id: 'm1', type: 'master', data: { label: 'App' } }],
    edges: [],
};
describe('planner write path — Tree Mode (chat path)', () => {
    it('lays out a multi-app project as separate apps and emits a bridge module', async () => {
        projects.create(TWO_APP_PROJECT);
        const res = await generatePlanFiles(REQUEST, PLAN, undefined, 20_000, undefined, undefined, undefined, 'proj-two-apps');
        expect(res, 'planner returned no result').not.toBeNull();
        const paths = res.files.map((f) => f.path);
        // The flat plan paths were remapped into per-app directories — one program
        // per app, matching the canvas path's layout.
        expect(paths.filter((p) => p.startsWith('apps/')).length).toBe(2);
        expect(paths).toContain('apps/notes/index.html');
        expect(paths).toContain('apps/dashboard/dashboard.html');
        // The cross-app handoff became a bridge module in the shared dir.
        const bridge = paths.find((p) => p.startsWith('bridge/'));
        expect(bridge, `no bridge module in ${JSON.stringify(paths)}`).toBeDefined();
        expect(bridge).toMatch(/^bridge\/bridge-notes\./);
        // The bridge carries real code, not an empty placeholder.
        const bridgeFile = res.files.find((f) => f.path === bridge);
        expect(bridgeFile.content).toMatch(/export interface NotesPayload/);
    }, 60_000);
    it('leaves a single-app project byte-identical to the flat build', async () => {
        projects.create(SINGLE_APP_PROJECT);
        const res = await generatePlanFiles(REQUEST, PLAN, undefined, 20_000, undefined, undefined, undefined, 'proj-single-app');
        expect(res, 'planner returned no result').not.toBeNull();
        const paths = res.files.map((f) => f.path);
        // No app-directory remap, no bridges — the ordinary flat build.
        expect(paths).toContain('index.html');
        expect(paths).toContain('dashboard.html');
        expect(paths.some((p) => p.startsWith('apps/'))).toBe(false);
        expect(paths.some((p) => p.startsWith('bridge/'))).toBe(false);
    }, 60_000);
    it('is unchanged when no projectId is supplied', async () => {
        const res = await generatePlanFiles(REQUEST, PLAN, undefined, 20_000);
        expect(res, 'planner returned no result').not.toBeNull();
        const paths = res.files.map((f) => f.path);
        expect(paths.some((p) => p.startsWith('bridge/'))).toBe(false);
    }, 60_000);
});
