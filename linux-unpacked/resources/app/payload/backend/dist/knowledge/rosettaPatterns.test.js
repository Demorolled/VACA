import { describe, it, expect } from 'vitest';
import { ROSETTA_TARGETS } from './rosettaCode.js';
import { seedRosettaPatterns, loadRosettaCorpus, clearRosettaPatterns } from './rosettaPatterns.js';
function fakeStore(seed = []) {
    const items = [...seed];
    return {
        items,
        getAll: () => items,
        addPattern: (p) => {
            items.push({ title: p.title });
            return p;
        },
    };
}
const seed = (language, task) => ({
    category: 'code_pattern',
    title: `rosetta — ${task} (${language})`,
    description: 'd',
    language,
    nodeType: 'logic',
    tags: [language, 'rosetta'],
    projectId: 'rosetta',
    targetOS: 'linux',
    success: true,
    qualityScore: 7,
    code: 'x',
});
const corpus = [
    seed('go', 'A'),
    seed('go', 'B'),
    seed('go', 'C'),
    seed('python', 'A'),
    seed('python', 'B'),
    seed('rust', 'A'),
];
describe('seedRosettaPatterns', () => {
    it('adds the corpus and is idempotent on a second run', () => {
        const store = fakeStore();
        const first = seedRosettaPatterns({ store, corpus });
        expect(first.added.length).toBe(corpus.length);
        expect(store.items.length).toBe(corpus.length);
        const second = seedRosettaPatterns({ store, corpus });
        expect(second.added.length).toBe(0);
        expect(second.skipped).toBe(corpus.length);
        expect(store.items.length).toBe(corpus.length);
    });
    it('caps how many patterns per language are taken', () => {
        const store = fakeStore();
        seedRosettaPatterns({ store, corpus, maxPerLanguage: 1 });
        expect(store.items.map((i) => i.title).sort()).toEqual([
            'rosetta — A (go)',
            'rosetta — A (python)',
            'rosetta — A (rust)',
        ]);
    });
    it('round-robins across languages so none is starved', () => {
        const store = fakeStore();
        seedRosettaPatterns({ store, corpus, maxPerLanguage: 1 });
        // go/python/rust each contribute their first item before go's second.
        expect(store.items[0].title).toBe('rosetta — A (go)');
        expect(store.items[1].title).toBe('rosetta — A (python)');
        expect(store.items[2].title).toBe('rosetta — A (rust)');
    });
    it('uses the bulk path when available so the store trains once, not per pattern', () => {
        const items = [];
        let batchCalls = 0;
        let singleCalls = 0;
        const store = {
            getAll: () => items,
            addPattern: (p) => { singleCalls += 1; items.push({ title: p.title }); return p; },
            batchAddPatterns: (ps) => {
                batchCalls += 1;
                const stored = ps.map((p) => { items.push({ title: p.title }); return { title: p.title }; });
                return stored;
            },
        };
        const result = seedRosettaPatterns({ store, corpus });
        expect(batchCalls).toBe(1);
        expect(singleCalls).toBe(0);
        expect(result.added.length).toBe(corpus.length);
    });
    it('never crosses the sheet cap — which would archive and CLEAR the store', () => {
        const store = fakeStore([{ title: 'existing-1' }, { title: 'existing-2' }]);
        const result = seedRosettaPatterns({ store, corpus, sheetCap: 4, safetyMargin: 1 });
        // room = 4 - 1 - 2 = 1
        expect(result.added.length).toBe(1);
        expect(result.truncated).toBe(corpus.length - 1);
        expect(store.items.length).toBe(3);
    });
});
describe('clearRosettaPatterns', () => {
    it('removes only the imported rosetta patterns', () => {
        const items = [
            { id: '1', projectId: 'rosetta', title: 'a' },
            { id: '2', projectId: 'curated', title: 'b' },
            { id: '3', projectId: 'rosetta', title: 'c' },
        ];
        let seq = 0;
        const store = {
            getAll: () => items,
            deletePattern: (id) => {
                const i = items.findIndex((x) => x.id === id);
                if (i < 0)
                    return false;
                items.splice(i, 1);
                seq += 1;
                return true;
            },
        };
        expect(clearRosettaPatterns(store)).toBe(2);
        expect(seq).toBe(2);
        expect(items.map((i) => i.title)).toEqual(['b']);
    });
    it('is a no-op on a store that cannot delete', () => {
        expect(clearRosettaPatterns({ getAll: () => [{ id: '1', projectId: 'rosetta' }] })).toBe(0);
    });
});
describe('committed rosetta corpus', () => {
    const corpus = loadRosettaCorpus();
    it('is present and covers every gate language', () => {
        expect(corpus.length).toBeGreaterThan(0);
        const langs = new Set(corpus.map((p) => p.language));
        for (const t of ROSETTA_TARGETS)
            expect(langs.has(t.language)).toBe(true);
    });
    it('is ordered so the leading tasks per language are the instructive ones', () => {
        // deterministic order: 99 bottles / FizzBuzz / Factorial / Fibonacci first.
        const goTitles = corpus.filter((p) => p.language === 'go').slice(0, 4).map((p) => p.title);
        for (const t of ['99 bottles of beer', 'FizzBuzz', 'Factorial', 'Fibonacci sequence']) {
            expect(goTitles).toContain(`rosetta — ${t} (go)`);
        }
    });
    it('carries no repl transcripts or unparsed wiki markup', () => {
        for (const p of corpus) {
            expect(/\{\{|<\/?(nowiki|pre|syntaxhighlight)/i.test(p.code)).toBe(false);
            if (p.language === 'python')
                expect(/^\s*>>>/m.test(p.code)).toBe(false);
        }
    });
});
