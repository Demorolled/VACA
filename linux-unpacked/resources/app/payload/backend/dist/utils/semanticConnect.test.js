/**
 * semanticConnect.test.ts — unit tests for the pure semantic-connect helpers
 * (prompt building, response parsing, codegen prompt-injection section).
 */
import { describe, it, expect } from 'vitest';
import { buildConnectPrompt, parseConnectResponse, buildSemanticSection, } from './semanticConnect.js';
describe('parseConnectResponse', () => {
    it('parses a plain JSON object with side-specific hints', () => {
        const conn = parseConnectResponse('{"label":"Widget Feed","relation":"parsed widgets flow into the core engine","sourceHint":"export parseWidgets(): Widget[]","targetHint":"import parseWidgets and feed it into process()","codeHint":"parseWidgets feeds process"}');
        expect(conn.label).toBe('Widget Feed');
        expect(conn.relation).toContain('widgets flow');
        expect(conn.sourceHint).toContain('parseWidgets');
        expect(conn.targetHint).toContain('import parseWidgets');
        expect(conn.codeHint).toContain('process');
    });
    it('falls each side back to the combined hint when side hints are missing', () => {
        const conn = parseConnectResponse('{"label":"Bridge","codeHint":"export wire() and call it from main"}');
        expect(conn.sourceHint).toBe(conn.codeHint);
        expect(conn.targetHint).toBe(conn.codeHint);
    });
    it('parses JSON wrapped in markdown fences with trailing prose', () => {
        const conn = parseConnectResponse('Here is the connection:\n```json\n{"label":"Auth Bridge","relation":"session tokens flow into the engine","codeHint":"export createSession()"}\n```\nHope that helps!');
        expect(conn.label).toBe('Auth Bridge');
        expect(conn.relation).toContain('tokens');
        expect(conn.codeHint).toBe('export createSession()');
    });
    it('falls back to line-based parsing for prose-y output', () => {
        const conn = parseConnectResponse('Here is the wiring:\nlabel: Widget Feed\nrelation: widgets flow into engine\ncodeHint: export getWidgets().');
        expect(conn.label).toBe('Widget Feed');
        expect(conn.relation).toContain('widgets flow');
        expect(conn.codeHint).toBe('export getWidgets().');
    });
    it('returns safe defaults for garbage output', () => {
        const conn = parseConnectResponse('I am sorry, I cannot do that.');
        expect(conn.label).toBe('connection');
        expect(conn.relation).toBe('');
        expect(conn.codeHint).toBe('');
    });
    it('caps runaway field lengths', () => {
        const conn = parseConnectResponse(JSON.stringify({
            label: 'x'.repeat(500),
            relation: 'y'.repeat(500),
            codeHint: 'z'.repeat(900),
        }));
        expect(conn.label.length).toBeLessThanOrEqual(61);
        expect(conn.relation.length).toBeLessThanOrEqual(241);
        expect(conn.codeHint.length).toBeLessThanOrEqual(421);
    });
});
const PROJECT = {
    nodes: [
        { id: 'a3', data: { label: 'Core Engine', type: 'logic' } },
        { id: 'n1', data: { label: 'Widget Loader', type: 'input' } },
        { id: 'a1', data: { label: 'User Input', type: 'input' } },
    ],
    edges: [
        {
            id: 'sem_1',
            source: 'n1',
            target: 'a3',
            data: {
                label: 'Widget Feed',
                relation: 'parsed widgets flow into the core engine',
                codeHint: 'export parseWidgets(): Widget[]',
                semantic: true,
            },
        },
    ],
};
describe('buildSemanticSection', () => {
    it('injects consumption instructions into the TARGET file', () => {
        const section = buildSemanticSection({ id: 'a3' }, PROJECT);
        expect(section).toContain('SEMANTIC CONNECTIONS');
        expect(section).toContain('Data flows INTO this file from "Widget Loader"');
        expect(section).toContain('export parseWidgets(): Widget[]');
        expect(section).toContain('Implement (consume)');
    });
    it('injects exposure instructions into the SOURCE file', () => {
        const section = buildSemanticSection({ id: 'n1' }, PROJECT);
        expect(section).toContain('output FEEDS "Core Engine"');
        expect(section).toContain('[Widget Feed]');
        expect(section).toContain('Implement (export)');
    });
    it('uses side-specific hints when present', () => {
        const project = {
            nodes: PROJECT.nodes,
            edges: [{
                    id: 'sem_2',
                    source: 'n1',
                    target: 'a3',
                    data: {
                        label: 'Widget Feed',
                        sourceHint: 'export parseWidgets(): Widget[]',
                        targetHint: 'import { parseWidgets } and call process(parseWidgets())',
                        semantic: true,
                    },
                }],
        };
        expect(buildSemanticSection({ id: 'a3' }, project)).toContain('import { parseWidgets }');
        expect(buildSemanticSection({ id: 'n1' }, project)).toContain('export parseWidgets(): Widget[]');
    });
    it('returns empty for nodes not involved in any semantic edge', () => {
        expect(buildSemanticSection({ id: 'a1' }, PROJECT)).toBe('');
    });
    it('returns empty when no semantic edges exist (ordinary builds unaffected)', () => {
        const plain = { nodes: PROJECT.nodes, edges: [{ id: 'e1', source: 'a1', target: 'a3' }] };
        expect(buildSemanticSection({ id: 'a3' }, plain)).toBe('');
    });
});
describe('buildConnectPrompt', () => {
    it('names both modules, the user intent, and the edge direction semantics', () => {
        const prompt = buildConnectPrompt({
            nodes: PROJECT.nodes.map(n => ({ id: n.id, label: n.data.label, type: n.data.type })),
            sourceNodeId: 'n1',
            targetNodeId: 'a3',
            description: 'Widget Loader feeds parsed widgets into Core Engine',
            projectName: 'Merged App',
            targetOS: 'linux',
        });
        expect(prompt).toContain('Widget Loader');
        expect(prompt).toContain('Core Engine');
        expect(prompt).toContain('feeds parsed widgets into Core Engine');
        expect(prompt).toContain('TARGET depends on the SOURCE');
    });
});
