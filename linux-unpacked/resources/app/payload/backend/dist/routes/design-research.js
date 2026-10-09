/**
 * Design Research API Route
 * ==========================
 *
 * Provides endpoints to search the internet, GitHub, and
 * opensourcealternative.to for reference designs similar to
 * the user's app idea.
 *
 * Endpoints:
 *   POST /api/design-research/search  — Full combined research
 *   POST /api/design-research/web      — Web search only
 *   POST /api/design-research/github   — GitHub search only
 *   POST /api/design-research/alt      — OpenSourceAlternative.to only
 */
import { Router } from 'express';
import { researchDesign } from '../search/designResearch.js';
import { searchOpenSourceAlt } from '../search/opensourceAltSearch.js';
import { getSearchService } from '../search/webSearch.js';
import { formatOpenSourceAltForContext } from '../search/opensourceAltSearch.js';
export const designResearchRoutes = Router();
// ─── Full combined research ──────────────────────────────────────────
// POST /api/design-research/search
// Body: { goal: string, purpose?: string, maxResults?: number }
designResearchRoutes.post('/search', async (req, res) => {
    try {
        const { goal, purpose, maxResults } = req.body;
        if (!goal || typeof goal !== 'string' || goal.trim().length === 0) {
            res.status(400).json({ error: 'A non-empty goal string is required.' });
            return;
        }
        // Use both goal and purpose for richer search context
        const searchText = purpose
            ? `${goal} ${purpose}`
            : goal;
        const searchService = getSearchService();
        const result = await researchDesign(searchText.trim(), searchService, typeof maxResults === 'number' ? Math.min(Math.max(1, maxResults), 10) : 5);
        res.json({
            success: true,
            ...result,
        });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error('[design-research] Error:', message);
        res.status(500).json({
            success: false,
            error: 'Research failed.',
            details: message,
        });
    }
});
// ─── Web search only ─────────────────────────────────────────────────
// POST /api/design-research/web
designResearchRoutes.post('/web', async (req, res) => {
    try {
        const { query, maxResults } = req.body;
        if (!query || typeof query !== 'string' || query.trim().length === 0) {
            res.status(400).json({ error: 'A non-empty query string is required.' });
            return;
        }
        const searchService = getSearchService();
        const response = await searchService.search({
            query: query.trim(),
            maxResults: typeof maxResults === 'number' ? Math.min(Math.max(1, maxResults), 20) : 5,
        });
        const results = response.results.map((r) => ({
            title: r.title,
            url: r.url,
            content: r.content,
        }));
        res.json({
            success: true,
            results,
            totalResults: results.length,
            provider: response.provider,
        });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        res.status(500).json({ success: false, error: message });
    }
});
// ─── GitHub search only ──────────────────────────────────────────────
// POST /api/design-research/github
designResearchRoutes.post('/github', async (req, res) => {
    try {
        const { query, maxResults } = req.body;
        if (!query || typeof query !== 'string' || query.trim().length === 0) {
            res.status(400).json({ error: 'A non-empty query string is required.' });
            return;
        }
        // Use in:name,description to find repos whose name or description matches
        // This is more effective than using multiple language: qualifiers which can be restrictive
        const query2 = encodeURIComponent(`${query} in:name,description`);
        const ghResponse = await fetch(`https://api.github.com/search/repositories?q=${query2}&sort=stars&per_page=${typeof maxResults === 'number' ? Math.min(maxResults, 10) : 5}`, {
            headers: {
                Accept: 'application/vnd.github.v3+json',
                'User-Agent': 'VisualAIArchitect/1.0',
            },
            signal: AbortSignal.timeout(10000),
        });
        if (!ghResponse.ok) {
            res.status(502).json({ success: false, error: `GitHub API returned ${ghResponse.status}` });
            return;
        }
        const data = await ghResponse.json();
        const repos = (data.items || []).map((repo) => ({
            name: repo.name,
            full_name: repo.full_name,
            description: repo.description || '',
            stars: repo.stargazers_count,
            url: repo.html_url,
            language: repo.language || null,
            topics: repo.topics || [],
            license: repo.license?.spdx_id || null,
        }));
        res.json({ success: true, repos, totalCount: data.total_count });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        res.status(500).json({ success: false, error: message });
    }
});
// ─── OpenSourceAlternative.to search only ────────────────────────────
// POST /api/design-research/alt
designResearchRoutes.post('/alt', async (req, res) => {
    try {
        const { query, maxResults } = req.body;
        if (!query || typeof query !== 'string' || query.trim().length === 0) {
            res.status(400).json({ error: 'A non-empty query string is required.' });
            return;
        }
        const result = await searchOpenSourceAlt(query.trim(), typeof maxResults === 'number' ? Math.min(Math.max(1, maxResults), 10) : 8);
        res.json({
            success: true,
            ...result,
            context: formatOpenSourceAltForContext(result),
        });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        res.status(500).json({ success: false, error: message });
    }
});
