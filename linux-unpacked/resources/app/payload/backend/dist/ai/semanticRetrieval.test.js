import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';
import { embed, cosineSimilarity, semanticRetrieve, getSheetEmbeddings, EMBED_DIM } from './semanticRetrieval.js';
describe('embed', () => {
    it('is deterministic and L2-normalized', () => {
        const text = 'make a chess game with an AI player and drag and drop pieces';
        const a = embed(text);
        const b = embed(text);
        expect(Array.from(a)).toEqual(Array.from(b));
        const norm = Math.sqrt(Array.from(a).reduce((s, v) => s + v * v, 0));
        expect(norm).toBeCloseTo(1, 5);
        expect(a.length).toBe(EMBED_DIM);
    });
    it('gives related text higher similarity than unrelated text', () => {
        const chess = embed('chess game with an AI opponent and drag and drop');
        const game = embed('game development patterns, game loop, collision detection, entity component systems');
        const fintech = embed('payment processing, banking ledger, PCI DSS compliance, escrow, insurance');
        expect(cosineSimilarity(chess, game)).toBeGreaterThan(cosineSimilarity(chess, fintech));
    });
    it('returns zero similarity for empty input', () => {
        expect(cosineSimilarity(embed(''), embed('anything'))).toBe(0);
    });
});
describe('getSheetEmbeddings', () => {
    it('embeds the library sheets (index excluded by design) at the expected dim', () => {
        const sheets = getSheetEmbeddings();
        // Durable expected count: computed from the LIVE library dir exactly the
        // way loadSheets() does (all *.md minus the meta reference index), so
        // adding/removing a sheet can never rot this test again (43 was hardcoded
        // and went stale when the 44th/45th sheets were added).
        const libDir = path.resolve(import.meta.dirname, '..', '..', '..', 'data', 'library');
        const expected = fs.readdirSync(libDir)
            .filter(f => f.endsWith('.md') && f !== '00-reference-index.md')
            .length;
        expect(sheets.length).toBe(expected);
        expect(sheets.every(s => s.vector.length === EMBED_DIM)).toBe(true);
        expect(sheets.every(s => !s.id.includes('00-reference-index'))).toBe(true);
    });
});
describe('semanticRetrieve', () => {
    it('ranks the game-development sheet above fintech for a chess request', () => {
        const res = semanticRetrieve('make a complete chess game with an AI player and drag and drop pieces', 6);
        const ids = res.map(r => r.id);
        const gameIdx = ids.indexOf('12-game-development-patterns.md');
        const fintechIdx = ids.indexOf('28-fintech-insurance-systems.md');
        expect(res.length).toBeGreaterThan(0);
        expect(gameIdx).toBeGreaterThanOrEqual(0); // the game sheet is in the top-6
        expect(fintechIdx === -1 || gameIdx < fintechIdx).toBe(true); // and outranks fintech whenever fintech surfaces
    });
    it('ranks cloud-native top for a kubernetes request', () => {
        const res = semanticRetrieve('deploy a kubernetes cluster with containers and gitops', 4);
        expect(res[0].id).toBe('23-cloud-native-infrastructure.md');
    });
    it('returns scores in descending order', () => {
        const res = semanticRetrieve('a realtime chat app with websockets and crdt sync', 5);
        for (let i = 1; i < res.length; i++) {
            expect(res[i - 1].score).toBeGreaterThanOrEqual(res[i].score);
        }
    });
    it('returns [] for a query with no shared vocabulary (below the confidence floor)', () => {
        const res = semanticRetrieve('zzzz qqqqq xxxxx nothing here', 3);
        expect(res.length).toBe(0);
    });
});
