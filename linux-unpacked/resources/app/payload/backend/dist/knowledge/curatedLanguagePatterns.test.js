import { describe, it, expect } from 'vitest';
import { CURATED_LANGUAGE_PATTERNS, seedCuratedLanguagePatterns } from './curatedLanguagePatterns.js';
import { MICRO_BUILD_REFERENCES, MICRO_CATALOG } from '../services/microExperimenterReference.js';
/** A tiny in-memory store that mirrors knowledgeStore's contract. */
function fakeStore() {
    const items = [];
    return {
        items,
        getAll: () => items,
        addPattern: (p) => { items.push(p); return p; },
    };
}
describe('curated language patterns', () => {
    it('includes Rust and C++ patterns (the knowledge-base gap)', () => {
        const langs = new Set(CURATED_LANGUAGE_PATTERNS.map((p) => p.language));
        expect(langs.has('rust')).toBe(true);
        expect(langs.has('cpp')).toBe(true);
    });
    it('every pattern carries the fields the store requires', () => {
        for (const p of CURATED_LANGUAGE_PATTERNS) {
            expect(p.title.length).toBeGreaterThan(0);
            expect(p.code.length).toBeGreaterThan(0);
            expect(p.language.length).toBeGreaterThan(0);
            expect(p.nodeType.length).toBeGreaterThan(0);
            expect(p.category).toBe('code_pattern');
        }
    });
    it('seeds once and is idempotent on a second run', () => {
        const store = fakeStore();
        const first = seedCuratedLanguagePatterns({ store });
        expect(first.added.length).toBe(CURATED_LANGUAGE_PATTERNS.length);
        expect(store.items.length).toBe(CURATED_LANGUAGE_PATTERNS.length);
        const second = seedCuratedLanguagePatterns({ store });
        expect(second.added.length).toBe(0);
        expect(second.skipped).toBe(CURATED_LANGUAGE_PATTERNS.length);
        expect(store.items.length).toBe(CURATED_LANGUAGE_PATTERNS.length);
    });
});
describe('reference corpus language coverage', () => {
    it('ships a Rust reference + catalog entry', () => {
        const ref = MICRO_BUILD_REFERENCES.find((r) => r.language === 'rust');
        expect(ref?.id).toBe('rust-word-counter');
        expect(MICRO_CATALOG.some((c) => c.language === 'rust' && c.refId === 'rust-word-counter')).toBe(true);
    });
    it('ships a C++ reference + catalog entry', () => {
        const ref = MICRO_BUILD_REFERENCES.find((r) => r.language === 'cpp');
        expect(ref?.id).toBe('cpp-guessing-game');
        expect(MICRO_CATALOG.some((c) => c.language === 'cpp' && c.refId === 'cpp-guessing-game')).toBe(true);
    });
});
