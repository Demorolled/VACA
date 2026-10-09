/**
 * Generate embeddings for the 42 library sheets → data/library-embeddings.json
 * ============================================================================
 * Uses the SAME hashing-ngram embedding module the runtime retrieval uses
 * (backend/src/ai/semanticRetrieval.ts), so the file is a faithful snapshot for
 * inspection/verification. Runtime retrieval computes in-process (TTL-cached),
 * so it never goes stale — this file is a reproducible artifact + a smoke test
 * of the ranking quality (probe queries below).
 *
 * Run with: npx tsx backend/src/scripts/generate-library-embeddings.ts
 */
import { writeFileSync } from 'fs';
import { resolve, join } from 'path';
import { buildSheetEmbeddings, semanticRetrieve, EMBED_DIM } from '../ai/semanticRetrieval.js';
const PROJECT_ROOT = resolve(import.meta.dirname, '..', '..', '..');
const OUT = join(PROJECT_ROOT, 'data', 'library-embeddings.json');
const sheets = buildSheetEmbeddings();
writeFileSync(OUT, JSON.stringify({
    generatedAt: new Date().toISOString(),
    dim: EMBED_DIM,
    count: sheets.length,
    sheets: sheets.map(s => ({ id: s.id, title: s.title, vector: s.vector })),
}, null, 2), 'utf-8');
console.log(`✅ Wrote ${sheets.length} sheet embeddings (dim ${EMBED_DIM}) → ${OUT}`);
console.log('Probe queries (top 3 by cosine similarity):');
for (const q of [
    'make a complete chess game with an AI opponent and drag and drop pieces',
    'deploy kubernetes containers with gitops and a service mesh',
    'build a fintech payment dashboard with ledger and escrow',
    'an iot sensor dashboard with mqtt and edge computing',
]) {
    const top = semanticRetrieve(q, 3).map(r => `  ${r.id} (${r.score.toFixed(3)})`).join('\n');
    console.log(`\n"${q}" →\n${top}`);
}
