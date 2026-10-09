/**
 * Internal Knowledge Context
 * ===========================
 *
 * Gathers VACA's OWN knowledge for a build goal — the same two internal
 * sources the chat's knowledge_query tool consults, but as a compact prompt
 * block fused into blueprint builds:
 *
 *   1. The knowledge store (backend/knowledge/patterns.json) — proven
 *      code/architecture patterns captured from past builds, queried with
 *      the goal as searchText.
 *   2. The wiki (modelVeronice.txt) — platform knowledge, history, and
 *      lessons learned, token-matched against the goal.
 *
 * The result is appended to the master node's blueprintContext so
 * FileGenerator fuses it into EVERY module prompt — internal knowledge
 * (patterns + wiki) actually reaches generation, not just chat.
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import { knowledgeStore } from './knowledgeStore.js';
import { parseWikiSections } from '../routes/wiki.js';
import { matchWikiSections } from '../utils/chatToolRunner.js';
const WIKI_PATH = resolve(import.meta.dirname, '..', '..', '..', 'modelVeronice.txt');
/**
 * Format matched patterns + wiki sections into a compact context block.
 * Pure — unit-testable without the store or wiki on disk.
 */
export function formatInternalKnowledge(patterns, wikiHits, maxPatternCodeChars = 250) {
    const lines = [];
    // Wiki sections FIRST — they are compact and high-value (lessons learned),
    // so when the caller caps the block (codePlanner), the wiki survives the
    // truncation and only the longer pattern code is cut from the tail.
    if (wikiHits.length > 0) {
        lines.push('📗 MATCHING WIKI SECTIONS (modelVeronice.txt — platform knowledge, history, lessons):');
        for (const w of wikiHits.slice(0, 2)) {
            lines.push(`  • Section ${w.number}: ${w.title}`);
            lines.push(`    ${w.body.substring(0, 300)}`);
        }
    }
    if (patterns.length > 0) {
        lines.push('🧠 MATCHING INTERNAL PATTERNS (knowledge store — proven code from past builds):');
        for (const p of patterns.slice(0, 3)) {
            lines.push(`  • ${p.title}`);
            if (p.description)
                lines.push(`    ${p.description.substring(0, 200)}`);
            if (p.code)
                lines.push(`    Code: ${p.code.substring(0, maxPatternCodeChars)}`);
        }
    }
    return lines.join('\n');
}
/** How many store patterns an injected block carries. */
export const INTERNAL_PATTERN_LIMIT = 3;
/**
 * Gather VACA's internal knowledge for a goal: query the knowledge store for
 * patterns and token-match wiki sections. Never throws — internal knowledge
 * is a prompt enhancement, never a build blocker.
 *
 * Pattern selection is language-first when a target language is known:
 *   1. patterns matching the goal AND the target language,
 *   2. otherwise patterns matching the goal in any language.
 *
 * Step 2 matters: the store's non-TS coverage is uneven, so requiring the
 * language outright would drop the block to empty for a language with no
 * matching pattern. The wrong-language example still carries the right task.
 */
export function gatherInternalKnowledge(goal, opts = {}) {
    const runQuery = opts.query ?? ((q) => knowledgeStore.query(q));
    const language = opts.language?.trim().toLowerCase() || undefined;
    try {
        let patterns = [];
        try {
            const base = { searchText: goal, limit: INTERNAL_PATTERN_LIMIT };
            if (language)
                patterns = runQuery({ ...base, language });
            if (patterns.length === 0)
                patterns = runQuery(base);
        }
        catch (err) {
            console.warn('[internalKnowledge] knowledge store query failed (non-fatal):', err.message);
        }
        let wikiHits = [];
        try {
            const wiki = readFileSync(WIKI_PATH, 'utf-8');
            wikiHits = matchWikiSections(parseWikiSections(wiki), goal, 2);
        }
        catch (err) {
            console.warn('[internalKnowledge] wiki read/match failed (non-fatal):', err.message);
        }
        const context = formatInternalKnowledge(patterns.map(p => ({ title: p.title, description: p.description, code: p.code })), wikiHits);
        return { context, patternCount: patterns.length, wikiSectionCount: wikiHits.length };
    }
    catch (err) {
        console.warn('[internalKnowledge] gather failed (non-fatal):', err.message);
        return { context: '', patternCount: 0, wikiSectionCount: 0 };
    }
}
