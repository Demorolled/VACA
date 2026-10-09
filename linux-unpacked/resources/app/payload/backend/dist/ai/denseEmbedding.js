//
// Dense Embeddings (Ollama nomic-embed-text)
// ============================================
// The model-based upgrade the hashing-trick embed() was designed to swap in.
// Two halves:
//   1. DOC vectors — precomputed OFFLINE by scripts/generate-dense-rag-index.ts
//      into data/rag-dense-vectors.json (one 768-dim vector per RAG doc id).
//      Loaded synchronously at runtime from the snapshot — no HTTP on the hot
//      path, no drift between restarts.
//   2. QUERY vectors — embedded at request time via Ollama /api/embed (async),
//      cached in a small LRU so repeated/overlapping prompts stay cheap.
//
// Every failure path returns null so callers fall back to the existing
// hashing-trick retrieval — the app never breaks because embeddings are down.
//
import * as fs from 'fs';
import * as path from 'path';
export const DENSE_DIM = 768;
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const PROJECT_ROOT = path.resolve(BACKEND_DIR, '..');
const SNAPSHOT_PATH = path.join(PROJECT_ROOT, 'data', 'rag-dense-vectors.json');
const OLLAMA_URL = process.env.OLLAMA_URL || 'http://192.168.1.234:11434';
const EMBED_MODEL = process.env.VACA_EMBED_MODEL || 'nomic-embed-text';
const EMBED_TIMEOUT_MS = 8_000;
// ─── Doc-vector snapshot (sync, loaded once) ───────────────────────────────
let snapshot; // undefined = not yet tried
function loadSnapshot() {
    if (snapshot !== undefined)
        return snapshot;
    try {
        if (!fs.existsSync(SNAPSHOT_PATH)) {
            console.warn('[denseEmbedding] No doc-vector snapshot at', SNAPSHOT_PATH, '— run scripts/generate-dense-rag-index.ts (falling back to hashing retrieval)');
            snapshot = null;
            return snapshot;
        }
        const raw = JSON.parse(fs.readFileSync(SNAPSHOT_PATH, 'utf-8'));
        const vectors = new Map();
        for (const [id, v] of Object.entries(raw.vectors || {})) {
            if (Array.isArray(v) && v.length > 0)
                vectors.set(id, v);
        }
        snapshot = vectors.size > 0 ? vectors : null;
        console.log(`[denseEmbedding] Loaded ${vectors.size} dense doc vectors (${raw.model || EMBED_MODEL}, dim ${raw.dim || vectors.values().next().value?.length || '?'})`);
    }
    catch (err) {
        console.warn('[denseEmbedding] Failed to load dense snapshot (falling back):', err);
        snapshot = null;
    }
    return snapshot;
}
/** Dense doc vectors keyed by RAG doc id (library sheet filename / bible level / blueprint app_type). */
export function getDenseDocVectors() {
    return loadSnapshot();
}
/** True when the offline snapshot exists — cheap probe for tests/logging. */
export function hasDenseSnapshot() {
    return loadSnapshot() !== null;
}
// ─── Query embedding (async, cached) ───────────────────────────────────────
const QUERY_CACHE_MAX = 256;
const queryCache = new Map();
const inFlight = new Map();
async function callOllamaEmbed(texts) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), EMBED_TIMEOUT_MS);
    try {
        const res = await fetch(`${OLLAMA_URL}/api/embed`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model: EMBED_MODEL, input: texts }),
            signal: controller.signal,
        });
        if (!res.ok)
            return null;
        const data = await res.json();
        return data.embeddings?.length ? data.embeddings : null;
    }
    catch (err) {
        console.warn('[denseEmbedding] Ollama embed failed (falling back to hashing):', err.message);
        return null;
    }
    finally {
        clearTimeout(timer);
    }
}
/** Embed a single query string. LRU-cached; null on any failure. */
export async function denseEmbedQuery(text) {
    const key = text.trim();
    if (!key)
        return null;
    const cached = queryCache.get(key);
    if (cached)
        return cached;
    let pending = inFlight.get(key);
    if (!pending) {
        pending = (async () => {
            const emb = await callOllamaEmbed([key]);
            return emb ? emb[0] : null;
        })();
        inFlight.set(key, pending);
    }
    const vec = await pending;
    inFlight.delete(key);
    if (vec) {
        queryCache.set(key, vec);
        if (queryCache.size > QUERY_CACHE_MAX) {
            const oldest = queryCache.keys().next().value;
            if (oldest !== undefined)
                queryCache.delete(oldest);
        }
    }
    return vec;
}
/** Batch-embed many texts (used by the offline snapshot generator). */
export async function denseEmbedBatch(texts, batchSize = 64) {
    const out = [];
    for (let i = 0; i < texts.length; i += batchSize) {
        const chunk = texts.slice(i, i + batchSize);
        const emb = await callOllamaEmbed(chunk);
        if (!emb)
            return out.concat(chunk.map(() => null));
        out.push(...emb);
    }
    return out;
}
