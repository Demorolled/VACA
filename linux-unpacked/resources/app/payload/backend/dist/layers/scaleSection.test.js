import { describe, it, expect } from 'vitest';
import { buildScaleSection } from '../layers/fileGenerator.js';
describe('buildScaleSection', () => {
    it('emits a PROGRAM SCALE block for every tier', () => {
        for (const s of ['small', 'medium', 'large', 'enterprise']) {
            const t = buildScaleSection(s);
            expect(t).toContain('PROGRAM SCALE:');
            expect(t).toContain('this file is one module in');
        }
    });
    it('defaults to Medium when scale is missing', () => {
        expect(buildScaleSection(undefined)).toContain('PROGRAM SCALE: Medium');
        expect(buildScaleSection('')).toContain('PROGRAM SCALE: Medium');
        expect(buildScaleSection('huge')).toContain('PROGRAM SCALE: Medium');
    });
    it('tailors depth per tier', () => {
        expect(buildScaleSection('small')).toContain('do NOT over-engineer');
        expect(buildScaleSection('large')).toContain('PRODUCTION-GRADE');
        expect(buildScaleSection('enterprise')).toContain('testable and auditable');
    });
});
