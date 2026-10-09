#!/usr/bin/env tsx
/**
 * Generate the dense doc-vector snapshot → data/rag-dense-vectors.json
 * ======================================================================
 * Embeds every doc in the unified RAG index (library sheets + bible level
 * pages + blueprints) with Ollama's nomic-embed-text and writes a snapshot
 * that the runtime loads synchronously (see ai/denseEmbedding.ts). Query
 * vectors are embedded at request time with the SAME model, so doc and query
 * live in one vector space.
 *
 * Run on the machine that serves the backend (Ollama on localhost):
 *   npx tsx backend/src/scripts/generate-dense-rag-index.ts
 *
 * Re-run after bible/library/blueprint changes. Non-destructive: the runtime
 * falls back to hashing retrieval when this file is absent or stale.
 */
import * as fs from 'fs';
import * as path from 'path';
import { getRagDocs, getRagIndexStats } from '../ai/ragIndex.js';
import { getSheetEmbeddings } from '../ai/semanticRetrieval.js';
import { denseEmbedBatch, DENSE_DIM } from '../ai/denseEmbedding.js';
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const OUT = path.join(PROJECT_ROOT, 'data', 'rag-dense-vectors.json');
async function main() {
    const ragDocs = getRagDocs();
    const sheets = getSheetEmbeddings();
    const stats = getRagIndexStats();
    // Unify on ragIndex ids; add any library sheet missing from the unified index.
    const seen = new Set();
    const docs = [];
    for (const d of ragDocs) {
        seen.add(d.id);
        docs.push({ id: d.id, text: d.searchText });
    }
    for (const s of sheets) {
        if (!seen.has(s.id)) {
            seen.add(s.id);
            docs.push({ id: s.id, text: `${s.title}\n${s.title.toLowerCase()}` });
        }
    }
    console.log(`Embedding ${docs.length} docs (library=${stats.library}, bible=${stats.bible}, blueprint=${stats.blueprint}) with nomic-embed-text…`);
    if (!docs.length) {
        console.error('No docs to embed — is the project layout right?');
        process.exit(1);
    }
    const vectors = await denseEmbedBatch(docs.map(d => d.text));
    const failed = vectors.filter(v => v === null).length;
    if (failed > 0) {
        console.error(`❌ ${failed}/${docs.length} embeddings failed — is Ollama running (nomic-embed-text pulled)?`);
        process.exit(1);
    }
    const out = {};
    docs.forEach((d, i) => { out[d.id] = vectors[i]; });
    const payload = { model: 'nomic-embed-text', dim: DENSE_DIM, vectors: out };
    fs.mkdirSync(path.dirname(OUT), { recursive: true });
    fs.writeFileSync(OUT, JSON.stringify(payload));
    console.log(`✅ Wrote ${docs.length} vectors → ${OUT} (${(fs.statSync(OUT).size / 1e6).toFixed(1)} MB)`);
}
main().catch(err => {
    console.error('generate-dense-rag-index failed:', err);
    process.exit(1);
});
