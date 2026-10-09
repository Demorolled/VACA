import { describe, it, expect } from 'vitest';
import { mergeGraphs } from './graphMerge.js';
function node(id, type = 'logic', label = id, x = 0) {
    return { id, type, position: { x, y: 0 }, data: { label, description: `desc ${label}` } };
}
function edge(id, source, target) {
    return { id, source, target };
}
function graph(name, nodes, edges = []) {
    return { name, nodes, edges };
}
describe('mergeGraphs', () => {
    it('combines two disjoint graphs and offsets B to the right', () => {
        const a = graph('A', [node('n1', 'input', 'Input', 0), node('n2', 'logic', 'Logic', 200)]);
        const b = graph('B', [node('n3', 'ui', 'UI', 0)], [edge('e3', 'n3', 'n1')]);
        const r = mergeGraphs(a, b);
        expect(r.nodes.length).toBe(3);
        expect(r.edges.length).toBe(1); // only B's e3 (A had no edges)
        // B offset: n1 at x=0, n2 at x=200 → maxX=200 → B node at 200+250=450
        const ui = r.nodes.find(n => n.id === 'n3');
        expect(ui.position.x).toBe(450);
        // Edge into A still resolves
        expect(r.edges.some(e => e.id === 'e3' && e.source === 'n3' && e.target === 'n1')).toBe(true);
        expect(r.summary.totalNodes).toBe(3);
        expect(r.summary.totalEdges).toBe(1);
    });
    it('re-ids B nodes whose ids collide with A, remapping edges', () => {
        const a = graph('A', [node('n1', 'logic', 'Logic')]);
        const b = graph('B', [node('n1', 'ui', 'UI B'), node('n2', 'logic', 'Logic B')], [edge('e1', 'n1', 'n2')]);
        const r = mergeGraphs(a, b);
        const b1 = r.nodes.find(n => n.data?.label === 'UI B');
        expect(b1.id).toBe('b_n1');
        expect(r.nodes.filter(n => n.id === 'n1').length).toBe(1); // A keeps n1
        const e = r.edges.find(e => e.id === 'e1');
        expect(e.source).toBe('b_n1');
        expect(e.target).toBe('n2');
        expect(r.summary.renamedNodes.length).toBe(1);
        expect(r.summary.renamedNodes[0]).toEqual({ oldId: 'n1', newId: 'b_n1', label: 'UI B' });
    });
    it('renames label conflicts with a source suffix (only vs project A)', () => {
        const a = graph('A', [node('n1', 'logic', 'Dashboard')]);
        const b = graph('B', [
            node('n2', 'ui', 'Dashboard'), // conflicts with A label → renamed
            node('n3', 'ui', 'Settings'), // no A conflict
            node('n4', 'ui', 'Settings'), // B-internal duplicate → left alone
        ]);
        const r = mergeGraphs(a, b);
        const renamed = r.nodes.filter(n => n.data?.label.includes('(from B)'));
        expect(renamed.length).toBe(1); // only the cross-project conflict
        expect(r.summary.labelRenames.length).toBe(1);
        expect(r.summary.labelRenames[0].label).toBe('Dashboard');
        expect(r.summary.labelRenames[0].newLabel).toBe('Dashboard (from B)');
        // B-internal duplicates keep their original labels
        expect(r.nodes.filter(n => n.data?.label === 'Settings').length).toBe(2);
    });
    it('drops dangling edges and reports them', () => {
        const a = graph('A', [node('n1', 'logic', 'L')]);
        const b = graph('B', [node('n2', 'ui', 'U')], [
            edge('e1', 'n2', 'n1'), // valid (after remap n2 → n2)
            edge('e2', 'n2', 'ghost'), // dangling target
            edge('e3', 'ghost2', 'n2'), // dangling source
        ]);
        const r = mergeGraphs(a, b);
        expect(r.edges.length).toBe(1); // only the valid e1 (A had no edges)
        expect(r.summary.droppedEdges.length).toBe(2);
        expect(r.edges.some(e => e.id === 'e2')).toBe(false);
    });
    it('excludes master nodes (keeps only the caller-provided master)', () => {
        const a = graph('A', [node('master', 'master', 'Master'), node('n1', 'logic', 'L')]);
        const b = graph('B', [node('master2', 'master', 'Master B'), node('n2', 'ui', 'U')]);
        const r = mergeGraphs(a, b);
        expect(r.nodes.some(n => n.type === 'master')).toBe(false);
        expect(r.summary.droppedMasters).toEqual(['master2']);
        expect(r.summary.aNodeCount).toBe(1);
    });
    it('re-ids colliding edge ids and drops self-loops', () => {
        const a = graph('A', [node('n1'), node('n2')], [edge('e1', 'n1', 'n2')]);
        const b = graph('B', [node('n3'), node('n4')], [
            edge('e1', 'n3', 'n4'), // collides with A's e1
            edge('e2', 'n4', 'n4'), // self-loop
        ]);
        const r = mergeGraphs(a, b);
        const kept = r.edges.filter(e => e.source === 'n3');
        expect(kept.length).toBe(1);
        expect(kept[0].id).not.toBe('e1');
        expect(r.summary.droppedEdges.some(d => d.reason === 'self-loop dropped')).toBe(true);
    });
    it('warns when B has no nodes', () => {
        const a = graph('A', [node('n1')]);
        const b = graph('B', [], []);
        const r = mergeGraphs(a, b);
        expect(r.summary.warnings.some(w => w.includes('has no nodes'))).toBe(true);
        expect(r.nodes.length).toBe(1);
    });
    it('merging the same project twice re-ids deterministically without id collision', () => {
        const p = graph('P', [node('n1', 'logic', 'L')]);
        const first = mergeGraphs(p, p); // A=P, B=P → B's n1 becomes p_n1
        const ids1 = first.nodes.map(n => n.id);
        expect(new Set(ids1).size).toBe(ids1.length);
        // Merge the merged result again with P: still no id collisions
        const again = mergeGraphs({ name: 'M', nodes: first.nodes, edges: first.edges }, p);
        const ids2 = again.nodes.map(n => n.id);
        expect(new Set(ids2).size).toBe(ids2.length);
    });
});
