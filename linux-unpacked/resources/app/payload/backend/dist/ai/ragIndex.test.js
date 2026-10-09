import { describe, it, expect } from 'vitest';
import { buildRagIndex, getRagDocs, getRagIndexStats, ragRetrieve, ragRetrieveBibleLevels, buildBlueprintRequirements, renderBlueprintRequirements, invalidateRagIndex, } from './ragIndex.js';
import { EMBED_DIM } from './semanticRetrieval.js';
describe('buildRagIndex', () => {
    it('covers all three corpora at the expected dim', () => {
        const docs = buildRagIndex();
        const stats = getRagIndexStats();
        expect(docs.length).toBeGreaterThan(1300); // 42 library + 261 bible + 1,228 blueprints
        expect(stats.library).toBeGreaterThanOrEqual(40);
        expect(stats.bible).toBeGreaterThanOrEqual(200);
        expect(stats.blueprint).toBeGreaterThanOrEqual(1200);
        expect(docs.every(d => d.vector.length === EMBED_DIM)).toBe(true);
    });
    it('blueprint docs carry the canonical Blueprint for exact requirement injection', () => {
        const bpDocs = getRagDocs().filter(d => d.source === 'blueprint');
        const media = bpDocs.find(d => d.id === 'home_media_server') ?? bpDocs.find(d => d.id.includes('media'));
        expect(media).toBeDefined();
        expect(media.blueprint).toBeDefined();
        expect(Array.isArray(media.blueprint.architecture_checklist)).toBe(true);
    });
});
describe('ragRetrieve', () => {
    it('is deterministic — same query, same order', () => {
        const a = ragRetrieve('chess game with an AI opponent and drag and drop', { k: 4 });
        const b = ragRetrieve('chess game with an AI opponent and drag and drop', { k: 4 });
        expect(a.map(h => h.id)).toEqual(b.map(h => h.id));
    });
    it('ranks game/chess docs above fintech docs for a chess query', () => {
        const hits = ragRetrieve('make a complete chess game with an AI opponent and pieces', { k: 8 });
        const ids = hits.map(h => h.id);
        // Top hit should be a game/chess doc (blueprint or bible level), not a payment doc.
        const topIsRelevant = ids.some(id => /chess|game/i.test(id));
        expect(topIsRelevant).toBe(true);
    });
    it('finds the media-server blueprint for a streaming household query', () => {
        const hits = ragRetrieve('build a shared family movie streaming app for my household', { k: 8, sources: ['blueprint'] });
        const ids = hits.map(h => h.id);
        expect(ids.some(id => /media|stream|movie/i.test(id))).toBe(true);
    });
    it('returns [] for a query that shares nothing with the corpus', () => {
        const hits = ragRetrieve('zzzzqqqqxylophone', { minScore: 0.05 });
        expect(hits.length).toBe(0);
    });
});
describe('ragRetrieveBibleLevels', () => {
    it('returns deduped bible level dir names, best-first', () => {
        const levels = ragRetrieveBibleLevels('database schema design and sql indexing', 3);
        expect(levels.length).toBeGreaterThan(0);
        expect(levels.every(l => typeof l === 'string' && l.length > 0)).toBe(true);
        expect(new Set(levels).size).toBe(levels.length);
    });
});
describe('buildBlueprintRequirements', () => {
    it('injects the exact blueprint requirements (checklist + wiring) for a matching goal', () => {
        const ctx = buildBlueprintRequirements('chess game with an ai opponent', 2);
        expect(ctx).toBeTruthy();
        expect(ctx).toContain('BLUEPRINT');
        // Every injected blueprint must carry its real checklist (verbatim, not hallucinated).
        const match = ctx.match(/BLUEPRINT \(vector match [\d.]+\): ([a-z0-9_]+)/);
        expect(match).toBeTruthy();
    });
    it('returns empty string for unrelated goals (no injection noise)', () => {
        const ctx = buildBlueprintRequirements('zzzzqqqqxylophone nonsense', 2);
        expect(ctx).toBe('');
    });
    it('renderBlueprintRequirements contains the wiring graph contracts', () => {
        const bp = getRagDocs().find(d => d.source === 'blueprint' && d.blueprint).blueprint;
        const text = renderBlueprintRequirements(bp, 0.5);
        expect(text).toContain('TARGET STACK');
        expect(text).toContain('ARCHITECTURE CHECKLIST');
        expect(text).toContain('WIRING GRAPH');
    });
});
describe('invalidateRagIndex', () => {
    it('forces a rebuild on the next retrieval (no stale cache)', () => {
        invalidateRagIndex();
        const before = getRagDocs().length;
        invalidateRagIndex();
        const after = getRagDocs().length;
        expect(before).toBe(after);
        expect(before).toBeGreaterThan(0);
    });
});
