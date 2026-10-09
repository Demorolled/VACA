/**
 * chatToolRunner — executes a detected chat tool request against the real
 * ToolRegistry (the same tools the code-generation pipeline uses) and formats
 * the REAL results into a context block that gets injected into the LLM call.
 *
 * The LLM never fakes a read/search/lookup: the platform does the work and the
 * model only ever summarizes actual data (or honestly reports a failure).
 */
import { dirname, isAbsolute, join, resolve } from 'path';
import { fileURLToPath } from 'url';
import { readFileSync } from 'fs';
import { getRegistry } from '../tools/ToolRegistry.js';
import { parseWikiSections } from '../routes/wiki.js';
const __dirname = dirname(fileURLToPath(import.meta.url));
/** backend/src/utils → project root. */
export const PROJECT_ROOT = resolve(__dirname, '..', '..', '..');
/** project root → modelVeronice.txt (the wiki). */
const WIKI_PATH = join(PROJECT_ROOT, 'modelVeronice.txt');
const MAX_FILE_CHARS = 6000;
const MAX_SEARCH_CHARS = 3000;
const MAX_WEB_CHARS = 3000;
const MAX_KNOWLEDGE_CHARS = 3000;
/** Truncate the middle of a long result, keeping head + tail readable. */
export function truncateMid(s, max) {
    if (s.length <= max)
        return s;
    const head = Math.floor(max * 0.6);
    const tail = max - head;
    return s.slice(0, head) + `\n… [truncated, ${s.length - max} chars omitted] …\n` + s.slice(-tail);
}
/**
 * Tokenize a query into matchable words (≥3 chars).
 */
export function tokenizeQuery(query) {
    return query
        .toLowerCase()
        .split(/[^a-z0-9]+/)
        .filter(t => t.length >= 3);
}
/**
 * Rank wiki sections by how many query tokens appear in title+body, returning
 * the top `max` matches. Pure — unit-testable without the wiki on disk.
 */
export function matchWikiSections(sections, query, max = 2) {
    const tokens = tokenizeQuery(query);
    if (tokens.length === 0)
        return [];
    return sections
        .map(s => {
        const hay = `${s.title} ${s.body}`.toLowerCase();
        const hits = tokens.filter(t => hay.includes(t)).length;
        return { s, hits };
    })
        .filter(x => x.hits > 0)
        .sort((a, b) => b.hits - a.hits)
        .slice(0, max)
        .map(x => x.s);
}
/** Format one search match into a readable line. */
function formatMatch(m) {
    const file = m.path || '';
    const line = m.line != null ? `:${m.line}` : '';
    const text = (m.content || '').trim();
    return text ? `${file}${line}: ${text}` : `${file}${line}`;
}
export async function runChatTool(req) {
    const registry = getRegistry();
    const startedAt = Date.now();
    const ms = () => Date.now() - startedAt;
    // These tools are read-only / low-risk and the user explicitly asked for
    // them in chat, so they run without the approval gate (the registry defaults
    // to 'ask_each' — resolution order in PermissionManager honors this field).
    const ctx = { sessionId: 'chat', permissionMode: 'allow_all' };
    // ── read_file ──
    if (req.tool === 'read_file') {
        const rawPath = String(req.input.path || '');
        const target = isAbsolute(rawPath) ? rawPath : join(PROJECT_ROOT, rawPath);
        const result = await registry.execute('read_file', { path: target }, ctx);
        if (!result.success || typeof result.data?.content !== 'string') {
            return {
                handled: true,
                tool: req.tool,
                display: req.display,
                contextBlock: `[REAL TOOL RESULT — read_file FAILED]\n` +
                    `The platform tried to read "${req.display}" but got: ${result.error || 'no content returned'}.\n` +
                    `Reply honestly: the file could not be read. Offer to create it, or ask the user for the correct path.`,
            };
        }
        const data = result.data;
        const content = truncateMid(data.content, MAX_FILE_CHARS);
        return {
            handled: true,
            tool: req.tool,
            display: req.display,
            contextBlock: `[REAL FILE CONTENT — read_file tool, ${ms()}ms]\n` +
                `Path: ${data.path || target}\n` +
                `Size: ${data.size ?? '?'} bytes, ${data.lines ?? '?'} lines\n` +
                `──────\n${content}\n──────\n` +
                `Answer the user's question based ONLY on this real file content above. ` +
                `If the content is empty or unclear, say so honestly.`,
        };
    }
    // ── search_file ──
    if (req.tool === 'search_file') {
        const result = await registry.execute('search_file', {
            pattern: String(req.input.pattern),
            path: String(req.input.path || PROJECT_ROOT),
            maxResults: Number(req.input.maxResults) || 25,
        }, ctx);
        if (!result.success) {
            return {
                handled: true,
                tool: req.tool,
                display: req.display,
                contextBlock: `[REAL TOOL RESULT — search_file FAILED]\n` +
                    `The platform tried to search the code for "${req.input.pattern}" but got: ${result.error}.\n` +
                    `Reply honestly about the failure and suggest a simpler search.`,
            };
        }
        const matches = Array.isArray(result.data?.matches) ? result.data.matches : [];
        const text = matches.length > 0
            ? truncateMid(matches.map(formatMatch).join('\n'), MAX_SEARCH_CHARS)
            : `(no matches found for "${req.input.pattern}")`;
        return {
            handled: true,
            tool: req.tool,
            display: req.display,
            contextBlock: `[REAL CODE SEARCH — search_file tool, ${ms()}ms]\n` +
                `Pattern: "${req.input.pattern}" — ${matches.length} match${matches.length === 1 ? '' : 'es'}\n` +
                `──────\n${text}\n──────\n` +
                `Answer the user's question based ONLY on these real search results. ` +
                `If nothing matched, say so honestly and suggest a different search.`,
        };
    }
    // ── web_search ──
    if (req.tool === 'web_search') {
        const result = await registry.execute('web_search', { query: String(req.input.query), maxResults: Number(req.input.maxResults) || 5 }, ctx);
        if (!result.success) {
            return {
                handled: true,
                tool: req.tool,
                display: req.display,
                contextBlock: `[REAL TOOL RESULT — web_search FAILED]\n` +
                    `The platform tried to search the web for "${req.input.query}" but got: ${result.error}.\n` +
                    `Reply honestly that the web search could not be completed.`,
            };
        }
        const text = result.data?.text || '(no readable results returned)';
        return {
            handled: true,
            tool: req.tool,
            display: req.display,
            contextBlock: `[REAL WEB RESULTS — web_search tool, ${ms()}ms]\n` +
                `Query: "${req.input.query}"\n` +
                `──────\n${truncateMid(String(text), MAX_WEB_CHARS)}\n──────\n` +
                `Answer the user's question based ONLY on these real web results. ` +
                `If the results are thin or empty, say so honestly instead of inventing facts.`,
        };
    }
    // ── knowledge_query ──
    if (req.tool === 'knowledge_query') {
        const result = await registry.execute('knowledge_query', { query: String(req.input.query), maxResults: Number(req.input.maxResults) || 10 }, ctx);
        if (!result.success) {
            return {
                handled: true,
                tool: req.tool,
                display: req.display,
                contextBlock: `[REAL TOOL RESULT — knowledge_query FAILED]\n` +
                    `The platform tried to query the knowledge base for "${req.input.query}" but got: ${result.error}.\n` +
                    `Reply honestly about the failure.`,
            };
        }
        const data = result.data;
        const patterns = Array.isArray(data?.patterns) ? data.patterns : [];
        const patternText = patterns.length > 0
            ? truncateMid(JSON.stringify(patterns, null, 1), MAX_KNOWLEDGE_CHARS)
            : `(no knowledge-base patterns found for "${req.input.query}")`;
        // Also pull matching WIKI sections (modelVeronice.txt) so knowledge
        // lookups retrieve the wiki too — e.g. §59 (void raider game builds)
        // for an "arcade games" query. Tokenized match against title + body.
        let wikiText = '';
        try {
            const wiki = readFileSync(WIKI_PATH, 'utf-8');
            const wikiHits = matchWikiSections(parseWikiSections(wiki), String(req.input.query || ''), 2);
            if (wikiHits.length > 0) {
                wikiText =
                    `\n\n📗 MATCHING WIKI SECTIONS (modelVeronice.txt):\n` +
                        wikiHits
                            .map(h => `\n— Section ${h.number}: ${h.title}\n` +
                            truncateMid(h.body, 1200))
                            .join('\n');
            }
        }
        catch {
            wikiText = ''; // wiki unreadable — patterns alone are enough
        }
        return {
            handled: true,
            tool: req.tool,
            display: req.display,
            contextBlock: `[REAL KNOWLEDGE — knowledge_query tool, ${ms()}ms]\n` +
                `Query: "${req.input.query}" — ${patterns.length} pattern${patterns.length === 1 ? '' : 's'}\n` +
                `──────\n${patternText}${wikiText}\n──────\n` +
                `Answer the user's question based ONLY on these real knowledge-base results. ` +
                `If the knowledge base has nothing relevant, say so honestly and rely on what you actually know.`,
        };
    }
    return { handled: false };
}
