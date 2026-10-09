// ---------------------------------------------------------------------------
// Tavily provider (primary)
// ---------------------------------------------------------------------------
async function searchWithTavily(apiKey, opts) {
    const { tavily } = await import("@tavily/core");
    const tvly = tavily({ apiKey });
    const response = await tvly.search(opts.query, {
        searchDepth: opts.searchDepth ?? "basic",
        maxResults: opts.maxResults ?? 5,
    });
    return {
        results: response.results.map((r) => ({
            title: r.title ?? "",
            url: r.url ?? "",
            content: r.content ?? "",
            score: r.score,
        })),
        provider: "tavily",
        totalResults: response.results.length,
    };
}
function parseDdgHtml(html, maxResults) {
    const results = [];
    // Each result lives inside a <div class="result"> container.
    const resultBlocks = html.match(/<div[^>]*class="[^"]*result[^"]*"[^>]*>[\s\S]*?<\/div>\s*<\/div>\s*<\/div>/g);
    if (!resultBlocks)
        return results;
    for (const block of resultBlocks) {
        if (results.length >= maxResults)
            break;
        const linkMatch = block.match(/<a[^>]*rel="nofollow"[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/);
        if (!linkMatch)
            continue;
        let url = linkMatch[1];
        const title = linkMatch[2].replace(/<[^>]*>/g, "").trim();
        if (!title || !url)
            continue;
        if (url.startsWith("//"))
            url = "https:" + url;
        const snippetMatch = block.match(/<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>([\s\S]*?)<\/a>/);
        const content = snippetMatch
            ? snippetMatch[1].replace(/<[^>]*>/g, "").trim()
            : "";
        results.push({ title, url, content });
    }
    return results;
}
async function searchWithFallback(opts) {
    const maxResults = Math.min(opts.maxResults ?? 5, 20);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);
    try {
        const response = await fetch("https://html.duckduckgo.com/html/", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            body: new URLSearchParams({ q: opts.query }),
            signal: controller.signal,
        });
        const html = await response.text();
        const results = parseDdgHtml(html, maxResults);
        return {
            results,
            provider: "duckduckgo-fallback",
            totalResults: results.length,
        };
    }
    catch (err) {
        console.warn("[search] DuckDuckGo fallback failed:", err instanceof Error ? err.message : String(err));
        return {
            results: [],
            provider: "fallback-error",
            totalResults: 0,
        };
    }
    finally {
        clearTimeout(timeout);
    }
}
// ---------------------------------------------------------------------------
// Public search service
// ---------------------------------------------------------------------------
export class WebSearchService {
    config;
    constructor(config = {}) {
        this.config = {
            tavilyApiKey: config.tavilyApiKey ?? "",
            defaultMaxResults: config.defaultMaxResults ?? 5,
        };
    }
    /** Check whether Tavily (the premium provider) is configured. */
    get hasTavily() {
        return !!this.config.tavilyApiKey;
    }
    /** The name of the active provider. */
    get activeProvider() {
        return this.hasTavily ? "tavily" : "duckduckgo-fallback";
    }
    /**
     * Search the web for the given query.
     *
     * When a Tavily API key is set, Tavily is used.  Otherwise a DuckDuckGo
     * HTML-scrape fallback is used (no API key required).
     */
    async search(opts) {
        const options = typeof opts === "string" ? { query: opts, maxResults: this.config.defaultMaxResults } : { ...opts };
        // Apply default maxResults from config if not specified in the options
        if (options.maxResults === undefined) {
            options.maxResults = this.config.defaultMaxResults;
        }
        if (this.hasTavily) {
            return searchWithTavily(this.config.tavilyApiKey, options);
        }
        return searchWithFallback(options);
    }
    /**
     * Convenience: search and return just the text results, useful as
     * context for an LLM prompt.
     */
    async searchAsText(query, maxResults) {
        const response = await this.search({ query, maxResults });
        if (response.results.length === 0) {
            return "No web search results found.";
        }
        return response.results
            .map((r, i) => `[${i + 1}] ${r.title}\n    URL: ${r.url}\n    ${r.content}`)
            .join("\n\n");
    }
}
/** Singleton instance initialised from environment variables. */
let defaultService = null;
/**
 * Get (or create) the default WebSearchService instance.
 *
 * Reads `TAVILY_API_KEY` from the environment.  You can override
 * settings by passing a custom config on the first call or by
 * calling `initSearchService` beforehand.
 */
export function getSearchService(config) {
    if (!defaultService || config) {
        defaultService = new WebSearchService(config ?? {
            tavilyApiKey: process.env.TAVILY_API_KEY || "",
        });
    }
    return defaultService;
}
/** Explicitly initialise the default search service. */
export function initSearchService(config) {
    defaultService = new WebSearchService(config ?? {
        tavilyApiKey: process.env.TAVILY_API_KEY || "",
    });
    return defaultService;
}
