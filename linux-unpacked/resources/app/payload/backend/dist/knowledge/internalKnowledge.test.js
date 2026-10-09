import { describe, it, expect } from 'vitest';
import { formatInternalKnowledge, gatherInternalKnowledge } from './internalKnowledge.js';
/** A PatternEntry for the language-filter tests. */
const row = (over) => ({
    id: over.title || 'id',
    category: 'code_pattern',
    title: 't',
    description: '',
    tags: [],
    projectId: 'test',
    targetOS: 'linux',
    nodeType: 'logic',
    language: 'go',
    success: true,
    usageCount: 0,
    qualityScore: 7,
    createdAt: '2026-01-01T00:00:00.000Z',
    code: 'package main',
    ...over,
});
/** Mimics knowledgeStore.query's filter semantics (language + substring). */
const fakeQuery = (rows) => (q) => rows
    .filter((r) => !q.language || r.language === q.language)
    .filter((r) => {
    if (!q.searchText)
        return true;
    const hay = `${r.title} ${r.description} ${r.tags.join(' ')}`.toLowerCase();
    return q.searchText.split(/\s+/).some((t) => t.length >= 3 && hay.includes(t));
})
    .slice(0, q.limit ?? 5);
const ROWS = [
    row({ title: 'go — Factorial', language: 'go', description: 'factorial in go' }),
    row({ title: 'java — Factorial', language: 'java', description: 'factorial in java' }),
    row({ title: 'go — stdin reader', language: 'go', description: 'reads stdin' }),
];
describe('formatInternalKnowledge', () => {
    it('formats patterns with title/description/code', () => {
        const out = formatInternalKnowledge([{ title: 'void_raider game architecture', description: '5-module arcade blueprint', code: 'Ship Controls → Combat Engine' }], []);
        expect(out).toContain('MATCHING INTERNAL PATTERNS');
        expect(out).toContain('void_raider game architecture');
        expect(out).toContain('Ship Controls → Combat Engine');
    });
    it('formats wiki sections with number/title/body', () => {
        const out = formatInternalKnowledge([], [{ number: 59, title: 'VOID RAIDER GAME BUILDS', body: 'Four full builds of the arcade space-shooter' }]);
        expect(out).toContain('MATCHING WIKI SECTIONS');
        expect(out).toContain('Section 59');
        expect(out).toContain('VOID RAIDER GAME BUILDS');
    });
    it('caps pattern code to keep the prompt compact', () => {
        const long = 'x'.repeat(1000);
        const out = formatInternalKnowledge([{ title: 't', description: '', code: long }], [], 100);
        expect(out).toContain('x'.repeat(100));
        expect(out).not.toContain('x'.repeat(200));
    });
    it('returns empty string for no matches', () => {
        expect(formatInternalKnowledge([], [])).toBe('');
    });
});
describe('gatherInternalKnowledge language filtering', () => {
    const query = fakeQuery(ROWS);
    it('prefers patterns in the target language', () => {
        const r = gatherInternalKnowledge('factorial', { language: 'go', query });
        expect(r.patternCount).toBe(1);
        expect(r.context).toContain('go — Factorial');
        expect(r.context).not.toContain('java — Factorial');
    });
    it('falls back to any language when the target has no match', () => {
        // No rust pattern exists: the wrong-language example still carries the task.
        const r = gatherInternalKnowledge('factorial', { language: 'rust', query });
        expect(r.patternCount).toBeGreaterThan(0);
        expect(r.context).toContain('Factorial');
    });
    it('does not filter when no language is given', () => {
        const r = gatherInternalKnowledge('factorial', { query });
        expect(r.patternCount).toBeGreaterThan(1);
    });
    it('normalizes a messy language token', () => {
        const r = gatherInternalKnowledge('factorial', { language: '  GO  ', query });
        expect(r.context).toContain('go — Factorial');
    });
});
describe('gatherInternalKnowledge (live store + wiki)', () => {
    it('finds the void-raider patterns and wiki section for an arcade-game goal', () => {
        const result = gatherInternalKnowledge('classic arcade game void raider');
        expect(result.context.length).toBeGreaterThan(0);
        // The knowledge store holds the void_raider patterns we added.
        expect(result.patternCount).toBeGreaterThan(0);
        // The wiki holds §59 (void raider game builds).
        expect(result.wikiSectionCount).toBeGreaterThan(0);
        expect(result.context).toContain('MATCHING INTERNAL PATTERNS');
        expect(result.context).toContain('MATCHING WIKI SECTIONS');
    });
});
