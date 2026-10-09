import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';
import * as fs from 'fs';
import { knowledgeStore } from './knowledgeStore.js';
// Redirect the store to a throwaway dir BEFORE the singleton is constructed,
// so these tests never touch the real `backend/knowledge/patterns.json`.
const KB_DIR = vi.hoisted(() => {
    const base = process.env.TMPDIR || process.env.TEMP || '/tmp';
    const dir = `${base}/vaca-kb-query-${process.pid}-${Date.now()}`;
    process.env.VACA_KNOWLEDGE_DIR = dir;
    return dir;
});
afterAll(() => {
    try {
        fs.rmSync(KB_DIR, { recursive: true, force: true });
    }
    catch { /* non-fatal */ }
});
const GO = 'package main\n\nfunc main() {\n\tprintln("hi")\n}';
const PY = 'def main():\n    print("hi")\n\nif __name__ == "__main__":\n    main()';
const pat = (over) => ({
    category: 'code_pattern',
    title: 't',
    description: 'd',
    tags: [],
    projectId: 'test',
    targetOS: 'linux',
    nodeType: 'logic',
    language: 'go',
    success: true,
    qualityScore: 7,
    code: GO,
    ...over,
});
beforeAll(() => {
    knowledgeStore.batchAddPatterns([
        // go: relevance beats a higher quality score.
        pat({ title: 'go — counter utilities', description: 'counter utilities', qualityScore: 8 }),
        pat({
            title: 'rosetta — FizzBuzz (go)',
            description: 'FizzBuzz with modulo and a counter',
            tags: ['go', 'rosetta', 'fizzbuzz'],
            qualityScore: 7,
        }),
        // go: equal relevance -> quality is the tiebreak.
        pat({ title: 'go — alpha helper', description: 'counter alpha', qualityScore: 8 }),
        pat({ title: 'go — beta helper', description: 'counter beta', qualityScore: 6 }),
        // python: goal-aware lookup + fallback.
        pat({ title: 'python — high scorer', description: 'unrelated subject', language: 'python', code: PY, qualityScore: 8 }),
        pat({ title: 'python — palindrome checker', description: 'palindrome detection', language: 'python', code: PY, qualityScore: 7 }),
    ]);
});
const titles = (r) => r.map((p) => p.title);
describe('knowledgeStore.query ranking', () => {
    it('ranks by relevance ABOVE quality score', () => {
        const r = knowledgeStore.query({
            nodeType: 'logic', language: 'go', targetOS: 'linux',
            searchText: 'fizzbuzz modulo counter',
        });
        // rosetta FizzBuzz hits fizzbuzz+modulo+counter (3); the quality-8 helper hits counter (1).
        expect(titles(r)[0]).toBe('rosetta — FizzBuzz (go)');
        expect(r.findIndex((p) => p.title === 'go — counter utilities')).toBeGreaterThan(0);
    });
    it('breaks relevance ties with the quality score', () => {
        const r = knowledgeStore.query({
            nodeType: 'logic', language: 'go', targetOS: 'linux',
            searchText: 'counter',
        });
        const alpha = r.findIndex((p) => p.title === 'go — alpha helper');
        const beta = r.findIndex((p) => p.title === 'go — beta helper');
        expect(alpha).toBeGreaterThanOrEqual(0);
        expect(alpha).toBeLessThan(beta); // same 1 hit, quality 8 > 6
    });
    it('orders purely by quality when no searchText is given', () => {
        const r = knowledgeStore.query({ nodeType: 'logic', language: 'go', targetOS: 'linux' });
        expect(r[0].qualityScore).toBe(8);
        const scores = r.map((p) => p.qualityScore);
        expect(scores).toEqual([...scores].sort((a, b) => b - a));
    });
    it('still filters out patterns with no token match', () => {
        const r = knowledgeStore.query({ nodeType: 'logic', language: 'go', searchText: 'zzzznotpresent' });
        expect(r).toEqual([]);
    });
});
describe('knowledgeStore.getRelevantContext', () => {
    it('is goal-aware: a matching lower-scored pattern beats an unrelated higher one', () => {
        const ctx = knowledgeStore.getRelevantContext('logic', 'python', 'linux', 3, 'palindrome detection');
        expect(ctx).toContain('python — palindrome checker');
        expect(ctx).not.toContain('python — high scorer');
    });
    it('falls back to the top patterns when the goal matches nothing', () => {
        const ctx = knowledgeStore.getRelevantContext('logic', 'python', 'linux', 3, 'zzzznotpresent');
        expect(ctx).not.toBe('');
        expect(ctx).toContain('python — high scorer');
    });
    it('is unchanged without a goal (top by quality)', () => {
        const ctx = knowledgeStore.getRelevantContext('logic', 'python', 'linux', 3);
        expect(ctx).toContain('python — high scorer');
    });
});
