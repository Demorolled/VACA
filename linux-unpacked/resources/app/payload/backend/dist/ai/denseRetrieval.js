//
// Dense Retrieval — ranking over the unified RAG index with model embeddings.
// ============================================================================
// Mirrors the hashing-trick path (ragIndex.ragRetrieve / buildBlueprintRequirements
// and semanticRetrieval.semanticRetrieve) but ranks with 768-dim dense vectors
// from data/rag-dense-vectors.json + an Ollama-embedded query. Keeps the SAME
// doc metadata (titles, summaries, blueprints, lexical bonus) so the injected
// prompt text is identical in shape — only the ranking improves.
//
// Every function returns null when dense data is unavailable; callers fall
// back to the sync hashing path. Never throws.
//
import { cosineSimilarity } from './semanticRetrieval.js';
import { getRagDocs, renderBlueprintRequirements } from './ragIndex.js';
import { getDenseDocVectors } from './denseEmbedding.js';
import { lexicalHitCount } from '../blueprint/bible.js';
const LEXICAL_HIT_BONUS = 0.35;
const MAX_LEXICAL_HITS = 2;
/** Cosine against a dense query vector; NaN/0 handled by cosineSimilarity. */
function score(docVec, qv) {
    return cosineSimilarity(qv, docVec);
}
/**
 * Top-k library sheet ids (filenames, same ids semanticRetrieve returns) by
 * dense similarity. null when the query or snapshot is missing.
 */
export function denseRetrieveSheets(qv, k = 6, minScore = 0.02) {
    const docVectors = getDenseDocVectors();
    if (!docVectors || !qv.length)
        return null;
    const sheets = getRagDocs().filter(d => d.source === 'library');
    const hits = sheets
        .map(d => ({ id: d.id, score: docVectors.has(d.id) ? score(docVectors.get(d.id), qv) : -1 }))
        .filter(h => h.score >= minScore)
        .sort((a, b) => b.score - a.score)
        .slice(0, k);
    return hits.length ? hits.map(h => h.id) : null;
}
/** Top bible LEVEL DIR names by dense similarity (deduped, best-first). */
export function denseRetrieveBibleLevels(qv, maxLevels = 3, minScore = 0.02) {
    const docVectors = getDenseDocVectors();
    if (!docVectors || !qv.length)
        return null;
    const seen = new Set();
    const out = [];
    const bible = getRagDocs().filter(d => d.source === 'bible');
    const ranked = bible
        .map(d => ({ level: d.level, score: docVectors.has(d.id) ? score(docVectors.get(d.id), qv) : -1 }))
        .filter(h => h.level && h.score >= minScore)
        .sort((a, b) => b.score - a.score);
    for (const h of ranked) {
        if (h.level && !seen.has(h.level)) {
            seen.add(h.level);
            out.push(h.level);
            if (out.length >= maxLevels)
                break;
        }
    }
    return out.length ? out : null;
}
/**
 * Render the exact blueprint-requirements block (same text as
 * ragIndex.buildBlueprintRequirements) using dense ranking + the lexical bonus
 * re-rank. null when dense data is unavailable.
 */
export function denseBuildBlueprintRequirements(qv, goal, k = 2, minScore = 0.03) {
    const docVectors = getDenseDocVectors();
    if (!docVectors || !qv.length)
        return null;
    const docs = getRagDocs().filter(d => d.source === 'blueprint' && d.blueprint && docVectors.has(d.id));
    const candidates = docs
        .map(d => ({ doc: d, base: score(docVectors.get(d.id), qv) }))
        .filter(c => c.base >= Math.min(minScore, 0.01))
        .map(c => ({
        ...c,
        score: c.base + Math.min(lexicalHitCount(goal, c.doc.blueprint), MAX_LEXICAL_HITS) * LEXICAL_HIT_BONUS,
    }))
        .sort((a, b) => b.score - a.score)
        .slice(0, k);
    if (!candidates.length)
        return null;
    const parts = [
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        '📦 BLUEPRINT REQUIREMENTS — exact pre-approved architecture for apps like this. If the goal matches, implement THESE modules and contracts verbatim:',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
    ];
    for (const c of candidates) {
        if (!c.doc.blueprint)
            continue;
        parts.push('\n' + renderBlueprintRequirements(c.doc.blueprint, c.score));
    }
    return parts.join('\n');
}
