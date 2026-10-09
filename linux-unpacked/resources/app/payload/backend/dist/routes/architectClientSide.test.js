import { describe, it, expect } from 'vitest';
import { isClientSideRequest, enforceRequiredTypes } from './architect.js';
function node(label, type) {
    return { label, description: '', type, language: 'typescript', position: { x: 0, y: 0 } };
}
describe('isClientSideRequest', () => {
    it('treats targetOS=web as client-side', () => {
        expect(isClientSideRequest('anything', '', 'web', [])).toBe(true);
    });
    it('treats linux server apps as server-side', () => {
        expect(isClientSideRequest('build a REST api with auth', '', 'linux', [])).toBe(false);
    });
    it('detects countdown/timer/widget goals', () => {
        expect(isClientSideRequest('Build a countdown timer app', 'counts down from a user-set time', 'linux', [])).toBe(true);
    });
    it('detects an all-UI node graph', () => {
        const nodes = [node('ui.ts', 'ui'), node('input.ts', 'input'), node('output.ts', 'output')];
        expect(isClientSideRequest('a generic app', '', 'linux', nodes)).toBe(true);
    });
});
describe('enforceRequiredTypes (client-side aware)', () => {
    const fourLogicNodes = [
        node('main.ts', 'logic'),
        node('config.ts', 'logic'),
        node('types.ts', 'logic'),
        node('service.ts', 'logic'),
    ];
    it('does NOT inject database/API layers for a client-side app (the countdown-timer bug)', () => {
        const result = enforceRequiredTypes(fourLogicNodes, 'countdown timer', 'typescript', true);
        expect(result.some(n => n.type === 'database')).toBe(false);
        expect(result.some(n => n.type === 'api')).toBe(false);
        // A ui layer is still ensured so the app is renderable.
        expect(result.some(n => n.type === 'ui')).toBe(true);
    });
    it('still injects database + API for a server-side app', () => {
        const result = enforceRequiredTypes(fourLogicNodes, 'multi-user service', 'typescript', false);
        expect(result.some(n => n.type === 'database')).toBe(true);
        expect(result.some(n => n.type === 'api')).toBe(true);
    });
    it('leaves small apps untouched regardless of mode', () => {
        const small = [node('main.ts', 'logic'), node('ui.ts', 'ui')];
        expect(enforceRequiredTypes(small, 'anything', 'typescript', false)).toHaveLength(2);
        expect(enforceRequiredTypes(small, 'anything', 'typescript', true)).toHaveLength(2);
    });
});
