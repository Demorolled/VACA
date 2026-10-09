import { describe, it, expect, beforeAll } from 'vitest';
import { getLibraryContext, getLibraryContextDense } from './libraryContext.js';
import { getDenseDocVectors, hasDenseSnapshot } from './denseEmbedding.js';
describe('getLibraryContextDense', () => {
    beforeAll(() => {
        // The test env has no data/rag-dense-vectors.json and no guaranteed Ollama —
        // the whole point: the dense path must degrade to the hashing path.
        void getDenseDocVectors();
    });
    it('is identical to the hashing path when dense data is unavailable', async () => {
        const q = 'make a complete chess game with an AI opponent and drag and drop';
        const dense = await getLibraryContextDense(q);
        const hashing = getLibraryContext(q);
        if (hasDenseSnapshot()) {
            // Snapshot present (dev machine after generation) — dense may differ, but
            // it must still be a non-empty reference block for a real request.
            expect(dense.length).toBeGreaterThan(0);
        }
        else {
            expect(dense).toBe(hashing);
        }
    });
    it('never throws on garbage input and falls back cleanly', async () => {
        const dense = await getLibraryContextDense('zzzz qqqqq xxxxx nothing here');
        const hashing = getLibraryContext('zzzz qqqqq xxxxx nothing here');
        if (!hasDenseSnapshot()) {
            expect(dense).toBe(hashing);
        }
        expect(typeof dense).toBe('string');
    });
    it('returns the hashing result for empty search text', async () => {
        expect(await getLibraryContextDense()).toBe(getLibraryContext());
    });
});
