//
// Unified RAG Vector Index — bible-reference/ + backend/blueprints/
// ==================================================================
//
// The hybrid strategy's prong 2 (knowledge/RAG): a single deterministic
// hashing-trick TF-IDF vector index over the ENTIRE knowledge bank, so a
// natural-language request can pull its exact bible pages and blueprint
// requirements at prompt time:
//
//     "build a shared family movie stream"  ──▶  home_media_server blueprint
//                                                  (target_stack, checklist,
//                                                   wiring_graph) + bible pages
//                                                  on streaming/media
//
// Corpora indexed (one vector per doc, L2-normalized, EMBED_DIM):
//   1. library sheets   data/library/*.md          (patterns/rules/templates)
//   2. bible pages      bible-reference/*/00-index.* (deep technical guides)
//   3. blueprints       backend/blueprints/**/*.json (exact app architectures)
//
// Reuses the SAME embedding primitives as semanticRetrieval.ts (embed(),
// cosineSimilarity(), tokenize(), filteredTokens(), ngrams()) so the unified
// index and the existing sheet index can never drift apart, and a
// model-based dense-embedding upgrade later only swaps embed().
//
// Runtime builds in-process (TTL-cached) so it never goes stale; the
// generate-rag-index.ts script writes a reproducible snapshot + smoke tests.
import * as fs from 'fs';
import * as path from 'path';
import { embed, cosineSimilarity, EMBED_DIM, filteredTokens, ngrams, } from './semanticRetrieval.js';
import { loadBlueprints, detectLanguage, lexicalHitCount } from '../blueprint/bible.js';
export { EMBED_DIM };
/** Lexical bonus per exact goal-token hit on a blueprint's vocabulary — the
 * SAME reinforcement bible.ts matchBlueprint() uses, because the hashing-trick
 * embeddings under-score keyword-perfect domains ('movie streaming' losing to
 * a buffer lab). */
const LEXICAL_HIT_BONUS = 0.35;
const MAX_LEXICAL_HITS = 2;
// ─── Paths ────────────────────────────────────────────────────────────────
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const PROJECT_ROOT = path.resolve(BACKEND_DIR, '..');
const LIBRARY_DIR = path.join(PROJECT_ROOT, 'data', 'library');
const BIBLE_DIR = path.join(PROJECT_ROOT, 'bible-reference');
// ─── Cache ────────────────────────────────────────────────────────────────
let cachedIndex = null;
let cachedAt = 0;
// Heavier than the 42-sheet index (1,531+ docs incl. 1,228 blueprints), so a
// longer TTL; invalidateRagIndex() forces an immediate rebuild.
const RAG_TTL_MS = 5 * 60_000;
export function invalidateRagIndex() {
    cachedIndex = null;
}
// ─── Doc loading ──────────────────────────────────────────────────────────
function sheetTitle(id) {
    return id.replace('.md', '').replace(/^\d+-/, '').replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
/** Human title for a bible level dir (e.g. '02-games' → '2 — Games'). */
function levelTitle(levelDir) {
    const m = levelDir.match(/^(\d+)-(.+)$/);
    if (m)
        return `${Number(m[1])} — ${m[2].replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}`;
    return levelDir.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
/** Compact plain-text summary of a markdown page (fences/tables stripped). */
function summarize(content, maxChars = 450) {
    const text = content
        .split('\n')
        .map(l => l.trim())
        .filter(l => l && !l.startsWith('```') && !l.startsWith('|') && !l.startsWith('>') && !l.startsWith('---'))
        .map(l => l.replace(/^#+\s*/, '').replace(/\*\*/g, '').replace(/`/g, '').replace(/\[([^\]]*)\]\([^)]*\)/g, '$1'))
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim();
    return text.length > maxChars ? text.slice(0, maxChars) + '…' : text;
}
/**
 * Deterministic bag-of-words text for a blueprint (mirrors bible.ts
 * blueprintText): app_type + description + keywords + first checklist items.
 * Compact on purpose — the full rendered requirements (with wiring contracts)
 * would dilute the vector and let unrelated blueprints outrank a perfect
 * keyword match (e.g. 'movie streaming' losing to a buffer lab).
 */
function blueprintText(bp) {
    return [
        bp.app_type,
        bp.description,
        ...(bp.keywords || []),
        ...(bp.architecture_checklist || []).slice(0, 6),
    ].join(' ');
}
/**
 * Render the EXACT requirements of a blueprint as injectable prompt text —
 * the same fused "blueprint constraints" the /api/blueprint/build flow uses,
 * framed as reference material for any generation prompt.
 */
export function renderBlueprintRequirements(bp, score) {
    const lang = detectLanguage(bp.target_stack);
    const lines = [];
    lines.push(`🧠 BLUEPRINT (vector match ${score.toFixed(2)}): ${bp.app_type}`);
    lines.push(`   DESCRIPTION: ${bp.description}`);
    lines.push(`   TARGET STACK: frontend=${bp.target_stack.frontend}, backend=${bp.target_stack.backend}, database=${bp.target_stack.database}`);
    lines.push(`   SOURCE LANGUAGE: ${lang}`);
    lines.push('   ARCHITECTURE CHECKLIST (the whole app is exactly these modules, each in its own file):');
    for (const m of bp.architecture_checklist)
        lines.push(`     - ${m}`);
    lines.push('   WIRING GRAPH (data contracts between modules — use names verbatim so files connect):');
    for (const w of bp.wiring_graph) {
        lines.push(`     - ${w.source_module} → ${w.destination_module} : ${w.data_passed}`);
    }
    return lines.join('\n');
}
/** Load all library sheet docs (excludes the meta reference index). */
function loadLibraryDocs() {
    if (!fs.existsSync(LIBRARY_DIR))
        return [];
    const docs = [];
    for (const entry of fs.readdirSync(LIBRARY_DIR).sort()) {
        if (!entry.endsWith('.md') || entry === '00-reference-index.md')
            continue;
        try {
            const content = fs.readFileSync(path.join(LIBRARY_DIR, entry), 'utf-8');
            const summary = summarize(content);
            docs.push({
                id: entry,
                source: 'library',
                title: sheetTitle(entry),
                searchText: `${entry}\n${sheetTitle(entry)}\n${summary}`,
                vector: [],
                summary,
            });
        }
        catch { /* skip unreadable sheet */ }
    }
    return docs;
}
/** Load every bible-reference level page (00-index.* per level dir). */
function loadBibleDocs() {
    if (!fs.existsSync(BIBLE_DIR))
        return [];
    const docs = [];
    let dirs = [];
    try {
        dirs = fs.readdirSync(BIBLE_DIR).filter(d => {
            try {
                return fs.statSync(path.join(BIBLE_DIR, d)).isDirectory();
            }
            catch {
                return false;
            }
        });
    }
    catch {
        return docs;
    }
    for (const level of dirs.sort((a, b) => a.localeCompare(b))) {
        let indexFile = null;
        try {
            indexFile = fs.readdirSync(path.join(BIBLE_DIR, level)).find(f => f.startsWith('00-index.')) ?? null;
        }
        catch { /* skip */ }
        if (!indexFile)
            continue;
        try {
            const content = fs.readFileSync(path.join(BIBLE_DIR, level, indexFile), 'utf-8');
            const summary = summarize(content);
            docs.push({
                id: `${level}/${indexFile}`,
                source: 'bible',
                title: levelTitle(level),
                level,
                searchText: `${level}\n${levelTitle(level)}\n${summary}`,
                vector: [],
                summary,
            });
        }
        catch { /* skip unreadable page */ }
    }
    return docs;
}
/** Load every canonical blueprint as a doc (reuses bible.ts cached loader). */
function loadBlueprintDocs() {
    return loadBlueprints().map(bp => ({
        id: bp.app_type,
        source: 'blueprint',
        title: bp.app_type,
        searchText: blueprintText(bp),
        vector: [],
        summary: renderBlueprintRequirements(bp, 0),
        blueprint: bp,
    }));
}
// ─── Index build ──────────────────────────────────────────────────────────
/**
 * Build the unified index. Pass 1 computes per-doc-deduped n-gram document
 * frequency ACROSS all three corpora (so 'chess'/'media server' vocabulary is
 * in the idf map and survives query pruning); pass 2 embeds each doc with the
 * smoothed IDF weights. Never throws — empty index when sources are missing.
 */
export function buildRagIndex() {
    try {
        const docs = [...loadLibraryDocs(), ...loadBibleDocs(), ...loadBlueprintDocs()];
        if (!docs.length)
            return [];
        const df = new Map();
        for (const d of docs) {
            const seen = new Set();
            for (const g of ngrams(filteredTokens(d.searchText))) {
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
        for (const d of docs) {
            d.vector = Array.from(embed(d.searchText, EMBED_DIM, idf));
        }
        cachedIndex = { docs, idf };
        cachedAt = Date.now();
        return docs;
    }
    catch (err) {
        console.error('[ragIndex] Failed to build unified index:', err);
        return [];
    }
}
function getIndexData() {
    const now = Date.now();
    if (cachedIndex === null || now - cachedAt > RAG_TTL_MS) {
        buildRagIndex();
    }
    return cachedIndex ?? { docs: [], idf: new Map() };
}
// ─── Public API ───────────────────────────────────────────────────────────
/** All indexed docs (builds on first call). */
export function getRagDocs() {
    return getIndexData().docs;
}
/** Per-source doc counts (for stats/snapshots/tests). */
export function getRagIndexStats() {
    const docs = getRagDocs();
    return {
        library: docs.filter(d => d.source === 'library').length,
        bible: docs.filter(d => d.source === 'bible').length,
        blueprint: docs.filter(d => d.source === 'blueprint').length,
    };
}
/**
 * Embed a query with the unified-corpus IDF and return top hits, best-first,
 * optionally restricted to specific sources. A low floor keeps garbage
 * queries from pulling in unrelated docs; [] → caller falls back to defaults.
 */
export function ragRetrieve(query, opts = {}) {
    const { sources, k = 6, minScore = 0.02 } = opts;
    const index = getIndexData();
    const qv = embed(query || '', EMBED_DIM, index.idf);
    return index.docs
        .filter(d => !sources || sources.includes(d.source))
        .map(d => ({
        id: d.id,
        title: d.title,
        source: d.source,
        score: cosineSimilarity(qv, d.vector),
        summary: d.summary,
        level: d.level,
        blueprint: d.blueprint,
    }))
        .filter(h => h.score >= minScore)
        .sort((a, b) => b.score - a.score)
        .slice(0, k);
}
/** Top bible LEVEL DIR names for a query (deduped, best-first). */
export function ragRetrieveBibleLevels(searchText, maxLevels = 3) {
    const seen = new Set();
    const out = [];
    for (const h of ragRetrieve(searchText, { sources: ['bible'], k: maxLevels * 2, minScore: 0.02 })) {
        if (h.level && !seen.has(h.level)) {
            seen.add(h.level);
            out.push(h.level);
            if (out.length >= maxLevels)
                break;
        }
    }
    return out;
}
/**
 * Prompt-injection renderer: the exact requirements of the top-k blueprints
 * matching a goal. Returns '' when nothing clears the floor — the caller's
 * existing defaults then apply. This is the "pull the exact blueprint
 * requirements and inject them into the prompt window" step of the strategy.
 */
export function buildBlueprintRequirements(goal, k = 2, minScore = 0.03) {
    // Fetch a WIDE raw candidate pool, then re-rank with the lexical hit bonus
    // (exact goal tokens ∈ blueprint app_type/keywords) — identical to
    // bible.ts matchBlueprint, so a perfect keyword match ('chess game' →
    // chess_game, 'movie streaming' → home_media_server) wins over embedding
    // noise. The pool must be generous: the hashing-trick raw cosine for a
    // keyword-perfect blueprint can sit far down the raw ranking (home_media_server
    // ~0.07 vs top noise ~0.30), and the bonus can only lift candidates that
    // made the pool.
    const POOL_MULT = 40;
    const candidates = ragRetrieve(goal, { sources: ['blueprint'], k: Math.max(40, k * POOL_MULT), minScore: Math.min(minScore, 0.01) });
    const boosted = candidates
        .map(h => h.blueprint
        ? { ...h, score: h.score + Math.min(lexicalHitCount(goal, h.blueprint), MAX_LEXICAL_HITS) * LEXICAL_HIT_BONUS }
        : h)
        .sort((a, b) => b.score - a.score)
        .slice(0, k);
    const hits = boosted;
    if (!hits.length)
        return '';
    const parts = [
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        '📦 BLUEPRINT REQUIREMENTS — exact pre-approved architecture for apps like this. If the goal matches, implement THESE modules and contracts verbatim:',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
    ];
    for (const h of hits) {
        if (!h.blueprint)
            continue;
        parts.push('\n' + renderBlueprintRequirements(h.blueprint, h.score));
    }
    return parts.join('\n');
}
