import { Router } from "express";
import { getSearchService } from "../search/webSearch.js";
const router = Router();
// ---------------------------------------------------------------------------
// POST /api/search  –  perform a web search
// ---------------------------------------------------------------------------
router.post("/", async (req, res) => {
    try {
        const { query, maxResults, searchDepth } = req.body;
        if (!query || typeof query !== "string" || query.trim().length === 0) {
            res.status(400).json({ error: "A non-empty 'query' string is required." });
            return;
        }
        const service = getSearchService();
        const response = await service.search({
            query: query.trim(),
            maxResults: typeof maxResults === "number"
                ? Math.min(Math.max(1, maxResults), 20)
                : undefined,
            searchDepth: searchDepth === "advanced" ? "advanced" : "basic",
        });
        res.json(response);
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error("[search] Error:", message);
        res.status(500).json({ error: "Search failed.", details: message });
    }
});
// ---------------------------------------------------------------------------
// GET /api/search/status  –  check which search provider is active
// ---------------------------------------------------------------------------
router.get("/status", (_req, res) => {
    const service = getSearchService();
    res.json({
        provider: service.activeProvider,
        hasTavily: service.hasTavily,
        message: service.hasTavily
            ? "Tavily is configured and ready."
            : "No TAVILY_API_KEY set. Using DuckDuckGo fallback (limited). Set TAVILY_API_KEY for better results.",
    });
});
export default router;
