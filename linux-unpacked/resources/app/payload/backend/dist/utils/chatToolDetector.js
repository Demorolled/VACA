/**
 * chatToolDetector — detects when a chat request maps to one of VACA's REAL
 * tools (read_file, search_file, web_search, knowledge_query).
 *
 * This is the "Proactive Problem Solving" layer: instead of the LLM promising
 * it will read a file / search the code / look something up (and then
 * fabricating results), the platform detects the intent, executes the real
 * tool, and feeds the REAL result back to the model. The model answers from
 * actual data or says honestly that it found nothing.
 *
 * Detection is deliberately conservative: a request is only intercepted when
 * the intent is explicit (a file-looking path, a "search the code" verb, a
 * "search the web" verb, or a "what do you know" query). Everything else
 * falls through to normal LLM chat.
 */
/** Known file extensions — makes a captured token look like a real file. */
const KNOWN_FILE_EXT_RE = /\.(?:ts|tsx|mts|cts|js|jsx|mjs|cjs|py|pyw|json|jsonc|md|markdown|mdx|html|htm|css|scss|sass|less|yaml|yml|txt|sh|bash|zsh|go|rs|java|c|cpp|cc|cxx|h|hpp|hh|cs|rb|php|swift|kt|kts|scala|clj|ex|exs|erl|hs|lua|r|pl|pm|sql|env|ini|cfg|conf|toml|xml|svg|png|jpg|jpeg|gif|webp|ico|bmp|pdf|csv|tsv|log|lock|map|vue|svelte|astro|gradle|properties|gitignore|dockerfile|makefile|editorconfig|prettierrc|eslintrc|babelrc|npmrc|htaccess|db|sqlite|sqlite3|wasm|woff|woff2|ttf|eot|otf|doc|docx|xls|xlsx|ppt|pptx|zip|tar|gz|rar|7z|webmanifest|gql|graphql|proto|zig|dart|nim|cl|el|fs|ml|vb|cbl|cob|pas|asm|cshtml|razor|ejs|hbs|njk|ipynb|dat|bin|exe|dll|so|apk|deb|rpm)$/i;
/** Does this captured target plausibly refer to a file on disk? */
function looksLikeFilePath(candidate) {
    if (!candidate || candidate.length > 220)
        return false;
    // Reject shell-unsafe / weird characters outright.
    if (/[<>|&"'`;(){}]/.test(candidate))
        return false;
    // A known extension is a strong signal ("config.yaml", "index.ts", "app.py").
    if (KNOWN_FILE_EXT_RE.test(candidate))
        return true;
    // Path separators make it path-like even without a known extension.
    if (/[\\/]/.test(candidate) && /[a-zA-Z0-9_\-.]/.test(candidate))
        return true;
    return false;
}
/**
 * Find the best path-like token inside a capture. Natural phrasings like
 * "read backend/src/index.ts and tell me what it does" capture trailing words
 * too; this pulls the path so the file is still resolved correctly.
 */
function extractPathTarget(candidate) {
    const leading = candidate.match(/^[A-Za-z0-9_.\-/]+/);
    if (leading && looksLikeFilePath(leading[0]))
        return leading[0];
    const tokens = candidate.match(/[A-Za-z0-9_.\-/]+/g) || [];
    let best = null;
    for (const tok of tokens) {
        if (looksLikeFilePath(tok) && (!best || tok.length > best.length))
            best = tok;
    }
    return best;
}
/**
 * Resolve a captured read target to a file path. Whole captures that contain
 * spaces are sentences ("read X and tell me what it does"), so we extract the
 * path token instead of treating the whole sentence as a path.
 */
function resolveFilePath(candidate) {
    const t = cleanTarget(candidate);
    if (t.includes(' '))
        return extractPathTarget(t);
    return looksLikeFilePath(t) ? t : null;
}
/** Strip quotes, backticks, trailing punctuation, and politeness. */
function cleanTarget(s) {
    return s
        .trim()
        .replace(/^["'`]+|["'`]+$/g, '')
        .replace(/[?!.,;:]+$/, '')
        .replace(/\s*(?:please|for me|now|thanks|thank you|thx)\s*$/i, '')
        .trim();
}
/** Web queries also lose a leading "for/about" and a trailing location. */
function cleanWebQuery(s) {
    return cleanTarget(s)
        .replace(/^(?:for|about|on)\s+/i, '')
        .replace(/\s+(?:online|on\s+the\s+(?:web|internet))\s*$/i, '')
        .trim();
}
/** A captured value that looks like a real query (not empty/too long). */
function validQuery(q, min = 3, max = 160) {
    return !!q && q.length >= min && q.length <= max;
}
/** Words that are never a meaningful search pattern on their own. */
const SEARCH_STOPWORDS = new Set([
    'the', 'a', 'an', 'and', 'or', 'of', 'in', 'on', 'for', 'is', 'it', 'to',
    'with', 'from', 'how', 'what', 'that', 'this', 'file', 'code', 'project',
    'are', 'was', 'were', 'do', 'does', 'did', 'which', 'who', 'when', 'why',
    'configured', 'configuration', 'configure', 'configuring', 'works', 'working',
    'used', 'using', 'use', 'usage', 'its', 'you', 'your', 'me', 'my', 'we',
    'they', 'them', 'there', 'here', 'where', 'find', 'show', 'tell', 'about',
    'help', 'please', 'can', 'could', 'would', 'should', 'want', 'need',
]);
/**
 * Extract the best search pattern from a natural-language capture.
 *
 * Single identifiers / paths / dotted symbols pass through unchanged. For
 * multi-word phrasings ("search the code for how the LLM client base URL is
 * configured") the capture is tokenized, stopwords stripped, and the most
 * code-like token is preferred (contains uppercase / underscore / digits).
 * This lets natural phrasing trigger the REAL search tool instead of falling
 * through to a hallucinated answer.
 */
function extractSearchPattern(capture) {
    const c = (capture || '')
        .trim()
        .replace(/^["'`]+|["'`]+$/g, '')
        .replace(/[?!.,;:]+$/, '')
        .trim();
    if (!c || c.length > 120)
        return null;
    // Single identifier / path / dotted symbol → use directly.
    if (/^[A-Za-z0-9_.\-/]{2,80}$/.test(c))
        return c;
    const tokens = c.split(/[^A-Za-z0-9_.-]+/).filter(Boolean);
    const meaningful = tokens.filter((t) => t.length >= 2 && !SEARCH_STOPWORDS.has(t.toLowerCase()));
    if (meaningful.length === 0)
        return null;
    // Prefer code-like tokens (uppercase, underscore, digits, camelCase).
    const codeLike = meaningful.filter((t) => /[A-Z]/.test(t) || t.includes('_') || /\d/.test(t));
    const best = (codeLike.length > 0 ? codeLike : meaningful).sort((a, b) => b.length - a.length)[0];
    return best || null;
}
/**
 * Does this capture contain evidence of an actual code symbol (camelCase,
 * snake_case, dotted path, digits, or all-caps)? Used to keep casual chat
 * like "search for a good restaurant nearby" out of the search tool.
 */
function looksCodeLike(capture) {
    return /(?:[a-z][A-Z])|(?:[A-Z]{2,})|_|\d|\./.test(capture);
}
/**
 * Detect a chat request that maps to a real tool. Returns null when the
 * request is not clearly a tool intent (falls through to normal chat).
 */
export function detectChatToolRequest(text) {
    const t = (text || '').trim();
    if (!t || t.length > 400)
        return null;
    // ── 1. web_search — explicit web intent wins over everything else ──
    // The trailing \s* (not \s+) matters: alternatives like "google " and
    // "look up " already consume their space, so the boundary must tolerate
    // zero extra whitespace.
    const web = t.match(/\b(?:search\s+the\s+(?:web|internet)|search\s+online|look\s+(?:it\s+)?up\s+|google\s+|find\s+(?:out|information|info)\s+(?:about|on)|browse\s+the\s+(?:web|internet)\s+for|what\s+does\s+the\s+(?:web|internet)\s+(?:say|know)\s+about)\s*["']?([A-Za-z0-9_.\-\s]{3,160})["']?/i);
    if (web && web[1]) {
        // "look up X in your knowledge base / KB / wiki" is a knowledge_query, not
        // a web search — let it fall through to the knowledge branch below. Narrow
        // to target phrases only, so a legit web search that merely MENTIONS
        // "wiki" ("search the web for how wikis work") still runs the web tool.
        if (/\b(?:in|of|your|the)\s+(?:my|your|the)?\s*(?:knowledge\s*base|knowledgebase|kb|wiki|bible)\b/i.test(web[1])) {
            // fall through — knowledge_query branch handles it
        }
        else {
            const q = cleanWebQuery(web[1]);
            if (validQuery(q)) {
                return { tool: 'web_search', input: { query: q, maxResults: 5 }, display: `web search: "${q}"` };
            }
        }
    }
    // ── 2. read_file — "read/show me X", "what's in X", "what does X do" ──
    const read = t.match(/^(?:(?:please|hey|hi)\s+)?(?:(?:can|could|will|would)\s+you\s+)?(?:read|show|open|view|display|cat|get|dump|give me|tell me)\s+(?:me\s+)?(?:the|my|our)?\s*(?:files?\s+(?:called|named)\s+|file\s+|contents?\s+of\s+|content\s+of\s+|code\s+in\s+|from\s+)?(.+)$/i);
    if (read && read[1]) {
        const path = resolveFilePath(read[1]);
        if (path) {
            return { tool: 'read_file', input: { path }, display: `file: ${path}` };
        }
    }
    // Note: the capture class allows dots ([^\n?!]) so "config.yaml" is NOT cut
    // at the dot. Trailing "?" / "!" get stripped by cleanTarget.
    const inMatch = t.match(/what('?s| is| are)?\s+(?:in|inside|in\s+the\s+file)\s+([^\n?!]+)/i);
    if (inMatch && inMatch[2]) {
        const path = resolveFilePath(inMatch[2]);
        if (path) {
            return { tool: 'read_file', input: { path }, display: `file: ${path}` };
        }
    }
    const doesMatch = t.match(/what\s+(?:does|is)\s+(.+?)\s+(?:do|contain|about)\s*[.!?]*$/i);
    if (doesMatch && doesMatch[1]) {
        const path = resolveFilePath(doesMatch[1]);
        if (path) {
            return { tool: 'read_file', input: { path }, display: `file: ${path}` };
        }
    }
    // ── 3. search_file — "search the code for X", "find where X is used" ──
    // Natural-language captures ("search the code for how X is configured") are
    // allowed — extractSearchPattern() pulls the code-like token out of them so
    // the REAL search tool runs instead of the LLM hallucinating an answer.
    const codeSearch = t.match(/\b(?:search|grep)\s+(?:the\s+)?(?:[A-Za-z0-9_.\-/]+\s+)?(?:code|codebase|project|repo|repository|source|files)\s+(?:for|using)\s+(.+?)\s*[.!?]?$/i);
    if (codeSearch && codeSearch[1]) {
        const pattern = extractSearchPattern(codeSearch[1]);
        if (pattern) {
            return { tool: 'search_file', input: { pattern, maxResults: 25 }, display: `code search: "${pattern}"` };
        }
    }
    // Scoped search: "search <dir> for <pattern>" (e.g. "search backend/src for baseURL")
    const dirSearch = t.match(/\b(?:search|grep)\s+([A-Za-z0-9_.\-/]{2,80})\s+(?:for|using)\s+(.+?)\s*[.!?]?$/i);
    if (dirSearch && dirSearch[1] && dirSearch[2]) {
        const dir = cleanTarget(dirSearch[1]);
        const pattern = extractSearchPattern(dirSearch[2]);
        if (pattern && /[\\/]/.test(dir) && looksLikeFilePath(dir)) {
            return { tool: 'search_file', input: { pattern, path: dir, maxResults: 25 }, display: `code search in ${dir}: "${pattern}"` };
        }
    }
    // Bare "search X" / "grep X" — knowledge / memory / wiki lookups fall through
    // to the knowledge_query branch below, and all-lowercase casual phrases ("search
    // for a good restaurant") stay in normal chat. Only code-like captures (camelCase,
    // snake_case, digits, all-caps, or a single identifier) become real searches.
    const bareSearch = t.match(/\b(?:search|grep)\s+(?:for\s+)?(.+?)\s*(?:in\s+the\s+(?:code|codebase|project|repo|repository|source))?\s*[.!?]?$/i);
    if (bareSearch && bareSearch[1] && !/\b(knowledge|memory|wiki)\b/i.test(bareSearch[1])) {
        const capture = bareSearch[1].trim();
        const pattern = extractSearchPattern(capture);
        const isSingleToken = /^[A-Za-z0-9_.\/-]+$/.test(capture);
        if (pattern && (isSingleToken || looksCodeLike(capture))) {
            // Bare "search <file-path>" where the target is a whole file → read it instead.
            if (looksLikeFilePath(pattern) && !/^[A-Za-z0-9_.\/-]+$/.test(pattern)) {
                return { tool: 'read_file', input: { path: pattern }, display: `file: ${pattern}` };
            }
            return { tool: 'search_file', input: { pattern, maxResults: 25 }, display: `code search: "${pattern}"` };
        }
    }
    const where = t.match(/find\s+where\s+([A-Za-z0-9_.\-]+)\s+(?:is|are)\s+(?:used|defined|referenced|declared|configured|set|created|initialized)/i) ||
        t.match(/where\s+(?:is|are)\s+([A-Za-z0-9_.\-]+)\s+(?:used|defined|referenced|declared|configured|set|created|initialized)/i) ||
        t.match(/find\s+["']?([A-Za-z0-9_.\-]{2,60})["']?\s+in\s+the\s+(?:code|codebase|project)/i);
    if (where && where[1]) {
        const pattern = cleanTarget(where[1]);
        if (validQuery(pattern, 2, 60)) {
            return { tool: 'search_file', input: { pattern, maxResults: 25 }, display: `code search: "${pattern}"` };
        }
    }
    // ── 4. knowledge_query — VACA's own knowledge base ──
    // Broad phrasings: "what does your knowledge base say about X", "what do you
    // know about X", "query/search your knowledge base for X", "do you have any
    // patterns/examples for X", "what does the KB/wiki say about X", "look up X
    // in your knowledge base".
    const know = t.match(/what\s+do\s+you\s+(?:know|have)\s+(?:about|on|for)\s+([^\n?!]{3,120})/i) ||
        t.match(/what\s+does\s+(?:your|the)\s+(?:knowledge\s+base|knowledgebase|kb|wiki|bible)\s+say\s+(?:about|on|regarding)\s+([^\n?!]{3,120})/i) ||
        t.match(/(?:query|search|look\s+up|check)\s+(?:your|the)\s+(?:knowledge\s+base|knowledgebase|kb|wiki|bible)(?:\s+base)?\s*(?:for|about|on|regarding)?\s*["']?([A-Za-z0-9_.\-\s]{3,120})["']?/i) ||
        t.match(/do\s+you\s+have\s+(?:any\s+)?(?:pattern|patterns|snippet|snippets|example|examples|knowledge)\s+(?:for|about|on)\s+([^\n?!]{3,120})/i) ||
        t.match(/tell\s+me\s+(?:what\s+)?(?:your\s+)?(?:knowledge\s+base|kb|wiki)\s+(?:says?|has|knows)\s+(?:about|on|for)\s+([^\n?!]{3,120})/i) ||
        t.match(/in\s+(?:your|the)\s+knowledge\s+base[,\s]+(?:what|tell\s+me)\s+(?:do\s+you\s+know|about)\s+([^\n?!]{3,120})/i) ||
        t.match(/look\s+up\s+([^\n?!]{3,120})\s+in\s+(?:your|the)\s+(?:knowledge\s+base|knowledgebase|kb|wiki|bible)\b/i);
    if (know && know[1]) {
        const q = cleanTarget(know[1]);
        if (validQuery(q)) {
            return { tool: 'knowledge_query', input: { query: q, maxResults: 10 }, display: `knowledge: "${q}"` };
        }
    }
    return null;
}
