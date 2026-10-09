/**
 * Generate the unified RAG vector index → data/rag-index.json
 * ============================================================
 * Uses the SAME embedding module the runtime retrieval uses
 * (backend/src/ai/ragIndex.ts → semanticRetrieval embed()), so the file is a
 * faithful snapshot for inspection/verification. Runtime retrieval computes
 * in-process (TTL-cached), so it never goes stale — this file is a
 * reproducible artifact + a smoke test of the ranking quality (probe queries
 * below) covering all three corpora: library sheets, bible pages, blueprints.
 *
 * Run with: npx tsx backend/src/scripts/generate-rag-index.ts
 */
import { writeFileSync } from 'fs';
import { resolve, join } from 'path';
import { buildRagIndex, getRagIndexStats, ragRetrieve, EMBED_DIM } from '../ai/ragIndex.js';
const PROJECT_ROOT = resolve(import.meta.dirname, '..', '..', '..');
const OUT = join(PROJECT_ROOT, 'data', 'rag-index.json');
const docs = buildRagIndex();
const stats = getRagIndexStats();
writeFileSync(OUT, JSON.stringify({
    generatedAt: new Date().toISOString(),
    dim: EMBED_DIM,
    sources: stats,
    total: docs.length,
    // Reproducible probe rankings (not the full vectors — the runtime index
    // is authoritative and lives in-process; this file is a verification
    // artifact of retrieval quality).
    probes: [
        'build a shared family movie streaming app for my household',
        'make a complete chess game with an AI opponent and drag and drop pieces',
        'deploy kubernetes containers with gitops and a service mesh',
        'build a fintech payment dashboard with ledger and escrow',
        'an iot sensor dashboard with mqtt and edge computing',
    ].map(q => ({
        query: q,
        top: ragRetrieve(q, { k: 4 }).map(r => ({
            id: r.id,
            source: r.source,
            score: Number(r.score.toFixed(3)),
        })),
    })),
}, null, 2), 'utf-8');
console.log(`✅ Wrote ${docs.length} unified RAG docs (dim ${EMBED_DIM}) → ${OUT}`);
console.log(`   library=${stats.library} bible=${stats.bible} blueprint=${stats.blueprint}`);
console.log('Probe queries (top 4 across all sources by cosine similarity):');
for (const q of [
    'build a shared family movie streaming app for my household',
    'make a complete chess game with an AI opponent and drag and drop pieces',
    'deploy kubernetes containers with gitops and a service mesh',
    'build a fintech payment dashboard with ledger and escrow',
]) {
    const top = ragRetrieve(q, { k: 4 }).map(r => `  ${r.source}:${r.id} (${r.score.toFixed(3)})`).join('\n');
    console.log(`\n"${q}" →\n${top}`);
}
