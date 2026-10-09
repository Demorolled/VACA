import { describe, it, expect } from 'vitest';
import { resolveTreeScopes, planBridges, buildCrossTreeBoundarySection, buildBridgePrompt, parseBridgeResponse, bridgeFileName, planExportLayout, exportDirFor, } from './treeScope.js';
// ─── Fixtures ──────────────────────────────────────────────────────
const node = (id, treeId, type = 'logic', label) => ({
    id,
    type,
    position: { x: 0, y: 0 },
    data: { label: label || id, description: '', status: 'pending', ...(treeId ? { treeId } : {}) },
});
const edge = (source, target, data) => ({
    id: `${source}->${target}`,
    source,
    target,
    ...(data ? { data } : {}),
});
/** A project with two app trees: Auth (node_a) → Shop (node_c). */
function twoAppProject() {
    return {
        name: 'Shop + Auth',
        nodes: [
            node('master-node', undefined, 'master', 'Auth'),
            node('master-tree_2', undefined, 'master', 'Shop'),
            node('node_a', 'tree_1', 'api', 'Login'),
            node('node_b', 'tree_1', 'database', 'Session Store'),
            node('node_c', 'tree_2', 'logic', 'Cart'),
            node('node_d', 'tree_2', 'ui', 'Checkout'),
        ],
        edges: [
            // inside app 1
            edge('node_a', 'node_b'),
            // inside app 2
            edge('node_c', 'node_d'),
            // ACROSS the boundary — the login session handoff
            edge('node_a', 'node_c', {
                kind: 'cross-tree',
                semantic: true,
                payloadType: 'auth-session',
                payloadLabel: 'Authentication / login session',
                payloadDetail: 'the bearer token',
                description: 'Login hands the session to the shop',
                relation: 'Shop checks out as the signed-in user',
            }),
        ],
        trees: [
            { id: 'tree_1', name: 'Auth', goal: 'Sign people in', targetOS: 'linux', rootNodeId: 'master-node' },
            { id: 'tree_2', name: 'Shop', goal: 'Sell things', targetOS: 'linux', rootNodeId: 'master-tree_2' },
        ],
    };
}
// ─── resolveTreeScopes ─────────────────────────────────────────────
describe('resolveTreeScopes', () => {
    it('splits an edge between two trees off the intra-tree edges', () => {
        const r = resolveTreeScopes(twoAppProject());
        // THE bug this module exists to prevent: if the cross-tree edge stayed in
        // the dependency graph, app 2's file would import app 1's source.
        expect(r.links).toHaveLength(1);
        expect(r.intraEdges.map((e) => e.id)).toEqual(['node_a->node_b', 'node_c->node_d']);
    });
    it('reports which tree each node is in', () => {
        const r = resolveTreeScopes(twoAppProject());
        expect(r.treeIdByNode.get('node_a')).toBe('tree_1');
        expect(r.treeIdByNode.get('node_c')).toBe('tree_2');
        expect(r.trees.find((t) => t.id === 'tree_1').nodeIds).toEqual(['node_a', 'node_b']);
        expect(r.trees.find((t) => t.id === 'tree_2').nodeIds).toEqual(['node_c', 'node_d']);
    });
    it('carries the payload the user chose', () => {
        const [link] = resolveTreeScopes(twoAppProject()).links;
        expect(link).toMatchObject({
            sourceNodeId: 'node_a',
            targetNodeId: 'node_c',
            sourceTreeId: 'tree_1',
            targetTreeId: 'tree_2',
            payloadType: 'auth-session',
            payloadLabel: 'Authentication / login session',
            payloadDetail: 'the bearer token',
        });
    });
    it('classifies by MEMBERSHIP, not by the edge flag', () => {
        // A stale/unflagged edge between two trees is still a boundary crossing —
        // trusting data.kind alone would let it become an import.
        const p = twoAppProject();
        p.edges.push({ id: 'stray', source: 'node_b', target: 'node_d' });
        const r = resolveTreeScopes(p);
        expect(r.links.map((l) => l.edgeId)).toContain('stray');
        expect(r.intraEdges.map((e) => e.id)).not.toContain('stray');
    });
    it('treats a pre-Tree-Mode project as ONE tree with no boundary', () => {
        const legacy = {
            name: 'Old App',
            nodes: [
                { ...node('master-node', undefined, 'master'), data: { label: 'App Blueprint', appGoal: 'Notes', description: '', status: 'pending' } },
                node('node_1', undefined, 'logic'),
                node('node_2', undefined, 'ui'),
            ],
            edges: [edge('node_1', 'node_2')],
        };
        const r = resolveTreeScopes(legacy);
        expect(r.trees).toHaveLength(1);
        expect(r.trees[0].rootNodeId).toBe('master-node');
        expect(r.trees[0].goal).toBe('Notes');
        expect(r.links).toEqual([]);
        // Every edge stays intra-tree, so the single-app build is unchanged.
        expect(r.intraEdges).toHaveLength(1);
    });
    it('keeps a root in the tree that claims it, whatever its data says', () => {
        const p = twoAppProject();
        p.nodes.find((n) => n.id === 'master-node').data.treeId = 'tree_2'; // contradictory
        const r = resolveTreeScopes(p);
        expect(r.treeIdByNode.get('master-node')).toBe('tree_1');
        expect(r.treeIdByNode.get('master-tree_2')).toBe('tree_2');
    });
    it('does not treat a root as a module of any tree', () => {
        const r = resolveTreeScopes(twoAppProject());
        expect(r.trees.flatMap((t) => t.nodeIds)).not.toContain('master-node');
        expect(r.trees.flatMap((t) => t.nodeIds)).not.toContain('master-tree_2');
    });
    it('leaves an edge with an unknown endpoint alone instead of inventing a tree', () => {
        const p = twoAppProject();
        p.edges.push(edge('node_a', 'ghost_node'));
        const r = resolveTreeScopes(p);
        expect(r.links.map((l) => l.edgeId)).not.toContain('node_a->ghost_node');
        expect(r.intraEdges.map((e) => e.id)).toContain('node_a->ghost_node');
    });
    it('falls back to the first tree for a node whose treeId is gone', () => {
        const p = twoAppProject();
        p.nodes.find((n) => n.id === 'node_c').data.treeId = 'tree_deleted';
        const r = resolveTreeScopes(p);
        expect(r.treeIdByNode.get('node_c')).toBe('tree_1');
    });
});
// ─── planBridges ───────────────────────────────────────────────────
describe('planBridges', () => {
    it('makes one bridge for the whole (apps, payload) contract', () => {
        const r = resolveTreeScopes(twoAppProject());
        const bridges = planBridges(r);
        expect(bridges).toHaveLength(1);
        expect(bridges[0]).toMatchObject({
            sourceTreeId: 'tree_1',
            targetTreeId: 'tree_2',
            sourceTreeName: 'Auth',
            targetTreeName: 'Shop',
            payloadType: 'auth-session',
        });
        // Named for WHAT crosses, not for the tree ids.
        expect(bridges[0].name).toBe('bridge-auth-session');
    });
    it('groups a second, same-payload handoff into the SAME bridge', () => {
        // Two modules in Auth both feeding Shop's session is ONE contract; two
        // bridges would give the apps two competing integration points.
        const p = twoAppProject();
        p.edges.push(edge('node_b', 'node_d', { kind: 'cross-tree', payloadType: 'auth-session', payloadLabel: 'Authentication / login session' }));
        const bridges = planBridges(resolveTreeScopes(p));
        expect(bridges).toHaveLength(1);
        expect(bridges[0].links).toHaveLength(2);
    });
    it('keeps different payloads as different bridges', () => {
        const p = twoAppProject();
        p.edges.push(edge('node_b', 'node_d', { kind: 'cross-tree', payloadType: 'records', payloadLabel: 'Database records' }));
        const bridges = planBridges(resolveTreeScopes(p));
        expect(bridges.map((b) => b.name).sort()).toEqual(['bridge-auth-session', 'bridge-records']);
    });
    it('disambiguates two payloads that slug to the same file name', () => {
        const p = twoAppProject();
        p.edges.push(edge('node_b', 'node_d', { kind: 'cross-tree', payloadType: 'user profile', payloadLabel: 'User profile' }), edge('node_d', 'node_a', { kind: 'cross-tree', payloadType: 'user-profile', payloadLabel: 'User profile' }));
        const names = planBridges(resolveTreeScopes(p)).map((b) => b.name);
        expect(new Set(names).size).toBe(names.length); // no two bridges collide
        expect(names).toContain('bridge-user-profile-2');
    });
    it('names a custom payload from its label', () => {
        const p = twoAppProject();
        p.edges.push(edge('node_b', 'node_d', { kind: 'cross-tree', payloadType: 'custom', payloadLabel: 'Custom data', payloadDetail: 'the active cart' }));
        const names = planBridges(resolveTreeScopes(p)).map((b) => b.name);
        expect(names).toContain('bridge-custom-data');
    });
    it('plans nothing for a single-app project', () => {
        const p = { name: 'Solo', nodes: [node('master-node', undefined, 'master'), node('n1')], edges: [], trees: undefined };
        expect(planBridges(resolveTreeScopes(p))).toEqual([]);
    });
});
// ─── buildCrossTreeBoundarySection ─────────────────────────────────
describe('buildCrossTreeBoundarySection', () => {
    const resolved = resolveTreeScopes(twoAppProject());
    const bridges = planBridges(resolved);
    it('is empty for a node on no boundary (ordinary builds unaffected)', () => {
        expect(buildCrossTreeBoundarySection('node_b', resolved, bridges)).toBe('');
    });
    it('tells the GIVING side what it supplies and to go through the bridge', () => {
        const s = buildCrossTreeBoundarySection('node_a', resolved, bridges);
        expect(s).toContain('CROSS-APP BOUNDARY');
        expect(s).toContain('SUPPLIES');
        expect(s).toContain('Authentication / login session');
        expect(s).toContain('Shop');
        expect(s).toContain('bridge-auth-session');
        expect(s).toContain('the bearer token');
    });
    it('tells the RECEIVING side what it gets and to go through the bridge', () => {
        const s = buildCrossTreeBoundarySection('node_c', resolved, bridges);
        expect(s).toContain('RECEIVES');
        expect(s).toContain('Auth');
        expect(s).toContain('bridge-auth-session');
    });
    it('forbids importing the other app, which is the whole point', () => {
        const s = buildCrossTreeBoundarySection('node_a', resolved, bridges);
        expect(s).toMatch(/never import the other app's source files/i);
        expect(s).toMatch(/different programs/i);
    });
});
// ─── buildBridgePrompt ─────────────────────────────────────────────
describe('buildBridgePrompt', () => {
    const resolved = resolveTreeScopes(twoAppProject());
    const bridge = planBridges(resolved)[0];
    const prompt = buildBridgePrompt({
        bridge,
        projectName: 'Shop + Auth',
        targetOS: 'linux',
        sourceNodes: [{ label: 'Login', type: 'api', description: 'validates credentials' }],
        targetNodes: [{ label: 'Cart', type: 'logic', description: 'holds the basket' }],
    });
    it('names both apps and the payload', () => {
        expect(prompt).toContain('Auth');
        expect(prompt).toContain('Shop');
        expect(prompt).toContain('Authentication / login session');
        expect(prompt).toContain('the bearer token');
    });
    it('states the apps cannot import each other', () => {
        expect(prompt).toMatch(/SEPARATE programs/i);
        expect(prompt).toMatch(/cannot import each other/i);
    });
    it('asks for an explicit shared data shape and no external packages', () => {
        expect(prompt).toMatch(/SHARED DATA SHAPE/);
        expect(prompt).toMatch(/No external npm packages/);
    });
    it('carries the user description verbatim so intent survives', () => {
        expect(prompt).toContain('Login hands the session to the shop');
    });
    it('demands raw code, not a markdown fence', () => {
        expect(prompt).toMatch(/no markdown fences/i);
    });
});
// ─── parseBridgeResponse ───────────────────────────────────────────
describe('parseBridgeResponse', () => {
    it('strips a typescript fence', () => {
        expect(parseBridgeResponse('```typescript\nexport const x = 1;\n```')).toBe('export const x = 1;');
    });
    it('strips a bare fence', () => {
        expect(parseBridgeResponse('```\nexport const x = 1;\n```')).toBe('export const x = 1;');
    });
    it('unwraps a JSON {"code": ...} wrapper', () => {
        expect(parseBridgeResponse('{"code": "export const x = 1;"}')).toBe('export const x = 1;');
    });
    it('unwraps a JSON {"content": ...} wrapper inside a fence', () => {
        expect(parseBridgeResponse('```json\n{"content":"export const y = 2;"}\n```')).toBe('export const y = 2;');
    });
    it('passes raw code through untouched', () => {
        const raw = 'export const x = 1;\nexport const y = 2;';
        expect(parseBridgeResponse(raw)).toBe(raw);
    });
    it('returns empty for empty input', () => {
        expect(parseBridgeResponse('   ')).toBe('');
    });
    it('handles a JSX generic without eating it', () => {
        const raw = 'export const wrap = <T,>(x: T): T => x;';
        expect(parseBridgeResponse(raw)).toBe(raw);
    });
});
// ─── bridgeFileName ────────────────────────────────────────────────
describe('bridgeFileName', () => {
    const bridge = planBridges(resolveTreeScopes(twoAppProject()))[0];
    it('uses the language extension', () => {
        expect(bridgeFileName(bridge, 'typescript')).toBe('bridge-auth-session.ts');
        expect(bridgeFileName(bridge, 'javascript')).toBe('bridge-auth-session.js');
        expect(bridgeFileName(bridge, 'python')).toBe('bridge-auth-session.py');
        expect(bridgeFileName(bridge, 'go')).toBe('bridge-auth-session.go');
        expect(bridgeFileName(bridge, 'rust')).toBe('bridge-auth-session.rs');
    });
    it('falls back to .ts for an unknown language', () => {
        expect(bridgeFileName(bridge, 'cobol')).toBe('bridge-auth-session.ts');
    });
});
// ─── planExportLayout / exportDirFor ───────────────────────────────
describe('planExportLayout', () => {
    it('keeps a single app flat (no separate app directories)', () => {
        const plan = planExportLayout([{ id: 'tree_1', name: 'App 1' }]);
        expect(plan.separateApps).toBe(false);
        expect(plan.appDirByTree).toEqual({ tree_1: 'app-1' });
    });
    it('keeps a project with no trees flat', () => {
        const plan = planExportLayout([]);
        expect(plan.separateApps).toBe(false);
        expect(plan.appDirByTree).toEqual({});
    });
    it('separates two app trees into their own directories, named after the app', () => {
        const plan = planExportLayout([
            { id: 'tree_1', name: 'Expense Tracker' },
            { id: 'tree_2', name: 'Report Mailer' },
        ]);
        expect(plan.separateApps).toBe(true);
        expect(plan.appDirByTree).toEqual({ tree_1: 'expense-tracker', tree_2: 'report-mailer' });
    });
    it('disambiguates two trees that share a name', () => {
        const plan = planExportLayout([
            { id: 'tree_1', name: 'App' },
            { id: 'tree_2', name: 'App' },
        ]);
        expect(plan.appDirByTree).toEqual({ tree_1: 'app', tree_2: 'app-2' });
    });
    it('falls back to the index for a missing id or name', () => {
        const plan = planExportLayout([{}, { id: 'tree_2' }]);
        expect(plan.separateApps).toBe(true);
        expect(plan.appDirByTree.tree_1).toBe('app-1');
        expect(plan.appDirByTree.tree_2).toBe('app-2');
    });
});
describe('exportDirFor', () => {
    it('lays a single-app file out flat', () => {
        expect(exportDirFor({}, 'timer-input')).toBe('src/timer-input');
        expect(exportDirFor({ appDir: '' }, 'timer-input')).toBe('src/timer-input');
    });
    it('nests a multi-app file under its app directory', () => {
        expect(exportDirFor({ appDir: 'apps/app-2' }, 'timer-input')).toBe('apps/app-2/src/timer-input');
    });
    it('tolerates stray slashes around the app directory', () => {
        expect(exportDirFor({ appDir: '/apps/app-2/' }, 'x')).toBe('apps/app-2/src/x');
    });
    it('always sends a bridge module to the shared bridge/ dir', () => {
        expect(exportDirFor({ isBridge: true }, 'bridge-auth-session')).toBe('bridge');
        expect(exportDirFor({ isBridge: true, appDir: 'apps/app-1' }, 'bridge-auth-session')).toBe('bridge');
    });
});
