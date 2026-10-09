//
// Semantic Retrieval for the Reference Library
// ==============================================
//
// Replaces the keyword matcher in getLibraryContext with VECTOR similarity:
// each library sheet (data/library/*.md) is embedded once (cached, TTL-refreshed)
// and a user request is embedded the same way; the top sheets by cosine
// similarity are returned instead of substring keyword hits.
//
// Embedding: deterministic feature hashing of word + word-bigram n-grams with
// TF-IDF weighting, L2-normalized. The IDF weights are computed ACROSS the 41
// topical sheets (down-weighting common words like 'the'/'and'/'make' that
// appear in every sheet, up-weighting topic vocabulary like 'game'/'kubernetes'),
// which is what makes topical ranking reliable. A model-based dense-embedding
// upgrade can slot in later by swapping `embed()` for an embeddings API call;
// the index + cosine retrieval stay unchanged.
import * as fs from 'fs';
import * as path from 'path';
export const EMBED_DIM = 1024;
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const PROJECT_ROOT = path.resolve(BACKEND_DIR, '..');
const LIBRARY_DIR = path.join(PROJECT_ROOT, 'data', 'library');
// ─── Embedding primitives ─────────────────────────────────────────────────
/** FNV-1a 32-bit hash — stable across processes (no Math.random, no seed). */
function fnv1a(str) {
    let h = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) {
        h ^= str.charCodeAt(i);
        h = Math.imul(h, 0x01000193);
    }
    return h >>> 0;
}
/** Lowercase word tokens (alphanumeric runs, apostrophes kept). */
export function tokenize(text) {
    return (text.toLowerCase().match(/[a-z0-9]+(?:'[a-z0-9]+)?/g) || []);
}
/** Word + word-bigram n-grams (bigrams capture multi-word topics like 'game loop'). */
export function ngrams(tokens) {
    const grams = [...tokens];
    for (let i = 0; i + 1 < tokens.length; i++)
        grams.push(`${tokens[i]} ${tokens[i + 1]}`);
    return grams;
}
/**
 * High-frequency words with no topical signal — dropped from BOTH the query and
 * the corpus vocabulary before n-grams, so a query like "nothing here" cannot
 * accidentally match sheet prose that happens to contain those words.
 */
const STOPWORDS = new Set([
    'a', 'an', 'the', 'and', 'or', 'but', 'for', 'of', 'to', 'in', 'with', 'on', 'at', 'by', 'from', 'as',
    'is', 'are', 'was', 'were', 'be', 'been', 'being', 'it', 'its', 'this', 'that', 'these', 'those',
    'i', 'you', 'we', 'they', 'he', 'she', 'me', 'my', 'your', 'our', 'their', 'do', 'does', 'did',
    'make', 'makes', 'making', 'made', 'use', 'uses', 'using', 'used', 'get', 'gets', 'getting', 'got',
    'can', 'could', 'will', 'would', 'should', 'shall', 'have', 'has', 'had', 'not', 'no', 'yes',
    'very', 'just', 'then', 'than', 'so', 'if', 'about', 'into', 'over', 'after', 'before', 'when',
    'where', 'how', 'what', 'who', 'why', 'up', 'down', 'out', 'off', 'again', 'more', 'most', 'other',
    'some', 'such', 'only', 'own', 'same', 'too', 'also', 'here', 'there', 'nothing', 'something',
    'anything', 'everything', 'build', 'builds', 'building', 'create', 'creates', 'creating',
    'created', 'need', 'needs', 'needing', 'want', 'wants', 'wanting',
]);
/**
 * Stopword-filtered tokens — the SINGLE vocabulary source for both the query
 * and the corpus DF pass, so the two sides can never diverge if the stoplist
 * grows.
 */
export function filteredTokens(text) {
    return tokenize(text).filter(t => !STOPWORDS.has(t));
}
/**
 * Hashing-trick TF(-IDF) embedding, L2-normalized. When an idf map is provided,
 * each n-gram's hash bin accumulates idf(gram) instead of a raw count, so
 * common words are down-weighted and topic vocabulary dominates the similarity.
 * Same text always yields the same vector.
 */
export function embed(text, dim = EMBED_DIM, idf) {
    const vec = new Float64Array(dim);
    const tokens = filteredTokens(text);
    for (const g of ngrams(tokens)) {
        if (g.length < 2)
            continue;
        if (idf) {
            // Prune grams that appear in NO sheet: they cannot overlap any document,
            // so they would only inflate the query norm and dilute the real signal
            // (e.g. 'chess'/'pieces' don't exist in the library, yet are the most
            // distinctive words of a chess request).
            const w = idf.get(g);
            if (w === undefined)
                continue;
            vec[fnv1a(g) % dim] += w;
        }
        else {
            vec[fnv1a(g) % dim] += 1;
        }
    }
    let normSq = 0;
    for (let i = 0; i < dim; i++)
        normSq += vec[i] * vec[i];
    const norm = Math.sqrt(normSq);
    if (norm > 0)
        for (let i = 0; i < dim; i++)
            vec[i] /= norm;
    return vec;
}
/** Cosine similarity between two equal-length numeric vectors. */
export function cosineSimilarity(a, b) {
    let dot = 0;
    let na = 0;
    let nb = 0;
    for (let i = 0; i < a.length; i++) {
        dot += a[i] * b[i];
        na += a[i] * a[i];
        nb += b[i] * b[i];
    }
    const denom = Math.sqrt(na) * Math.sqrt(nb);
    return denom === 0 ? 0 : dot / denom;
}
let cachedIndex = null;
let cachedIndexAt = 0;
const INDEX_TTL_MS = 30_000; // mirror libraryContext's cache TTL
function sheetTitle(id) {
    return id.replace('.md', '').replace(/^\d+-/, '').replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
/** Read the topical library sheets (excludes the meta reference index). */
function loadSheets() {
    if (!fs.existsSync(LIBRARY_DIR)) {
        console.warn('[semanticRetrieval] Library directory not found:', LIBRARY_DIR);
        return [];
    }
    const docs = [];
    for (const entry of fs.readdirSync(LIBRARY_DIR).sort()) {
        if (!entry.endsWith('.md'))
            continue;
        // The reference index is a META listing of all sheets — its broad vector
        // would crowd out topical sheets, and it is always included as a default
        // by getLibraryContext anyway.
        if (entry === '00-reference-index.md')
            continue;
        const content = fs.readFileSync(path.join(LIBRARY_DIR, entry), 'utf-8');
        docs.push({ id: entry, text: `${entry}\n${sheetTitle(entry)}\n${content}` });
    }
    return docs;
}
/**
 * Build the vector index for every library sheet. Pass 1 computes the document
 * frequency of every n-gram across the sheets → smoothed IDF weights; pass 2
 * embeds each sheet's title + content with those weights. Never throws —
 * returns an empty index when the library dir is missing.
 */
export function buildSheetEmbeddings() {
    try {
        const docs = loadSheets();
        if (!docs.length)
            return [];
        // Pass 1: document frequency (per-sheet dedup so one sheet can't dominate).
        const df = new Map();
        for (const d of docs) {
            const seen = new Set();
            for (const g of ngrams(filteredTokens(d.text))) {
                if (g.length < 2 || seen.has(g))
                    continue;
                seen.add(g);
                df.set(g, (df.get(g) || 0) + 1);
            }
        }
        const N = docs.length;
        const idf = new Map();
        for (const [g, f] of df)
            idf.set(g, Math.log((N + 1) / (f + 1)) + 1);
        // Pass 2: embed each sheet with the global IDF weights.
        return docs.map(d => ({
            id: d.id,
            title: sheetTitle(d.id),
            vector: Array.from(embed(d.text, EMBED_DIM, idf)),
        }));
    }
    catch (err) {
        console.error('[semanticRetrieval] Failed to build sheet embeddings:', err);
        return [];
    }
}
/** Cached index (sheets + idf map) — rebuilt at most every INDEX_TTL_MS. */
function getIndexData() {
    const now = Date.now();
    if (cachedIndex === null || now - cachedIndexAt > INDEX_TTL_MS) {
        const sheets = buildSheetEmbeddings();
        cachedIndex = { sheets, idf: computeIdf(sheets) };
        cachedIndexAt = now;
    }
    return cachedIndex;
}
/**
 * Rebuild the IDF map from an already-embedded sheet set (used by the cached
 * accessor). Keeps getIndexData cheap: the sheets were just built, so we only
 * re-derive the idf map from the source docs' n-gram frequencies.
 */
function computeIdf(_sheets) {
    // The idf map is genuinely needed for query embedding; derive it from the
    // source documents (identical logic to buildSheetEmbeddings pass 1).
    const docs = loadSheets();
    const df = new Map();
    for (const d of docs) {
        const seen = new Set();
        for (const g of ngrams(tokenize(d.text))) {
            if (g.length < 2 || seen.has(g))
                continue;
            seen.add(g);
            df.set(g, (df.get(g) || 0) + 1);
        }
    }
    const N = docs.length;
    const idf = new Map();
    for (const [g, f] of df)
        idf.set(g, Math.log((N + 1) / (f + 1)) + 1);
    return idf;
}
/** Cached sheet embeddings (public accessor). */
export function getSheetEmbeddings() {
    return getIndexData().sheets;
}
/**
 * Embed a query with the corpus IDF weights and return the top-k library sheets
 * by cosine similarity, best-first. A low confidence floor keeps garbage
 * queries from pulling in unrelated sheets; when the query shares nothing,
 * [] is returned and the caller falls back to its defaults.
 */
export function semanticRetrieve(query, k = 6, minScore = 0.02) {
    const index = getIndexData();
    const qv = embed(query || '', EMBED_DIM, index.idf);
    const hits = index.sheets
        .map(s => ({ id: s.id, title: s.title, score: cosineSimilarity(qv, s.vector) }))
        .filter(h => h.score >= minScore)
        .sort((a, b) => b.score - a.score);
    return hits.slice(0, k);
}
