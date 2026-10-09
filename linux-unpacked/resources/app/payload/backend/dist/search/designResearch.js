/**
 * Design Research Service
 * ========================
 *
 * Orchestrates three search sources to find reference designs and apps
 * similar to the user's request:
 *
 * 1. Web Search (via WebSearchService / Tavily or DuckDuckGo)
 * 2. GitHub Search (via GitHub API)
 * 3. OpenSourceAlternative.to (via custom scraper)
 *
 * The combined results are formatted as context for the LLM to use as
 * reference when generating the app architecture.
 */
import { getSearchService } from './webSearch.js';
import { searchOpenSourceAlt, formatOpenSourceAltForContext, } from './opensourceAltSearch.js';
// ─── GitHub Search ─────────────────────────────────────────────────────
/**
 * Search GitHub for repositories related to the user's app goal.
 * Uses the public GitHub search API (no auth required for basic search).
 */
async function searchGitHub(goal, maxResults = 5) {
    try {
        // Search repo names and descriptions for the goal — simpler query without
        // restrictive language filters gives more comprehensive results
        const query = encodeURIComponent(`${goal} in:name,description`);
        const response = await fetch(`https://api.github.com/search/repositories?q=${query}&sort=stars&per_page=${maxResults}`, {
            headers: {
                Accept: 'application/vnd.github.v3+json',
                'User-Agent': 'VisualAIArchitect/1.0',
            },
            signal: AbortSignal.timeout(10000),
        });
        if (!response.ok) {
            console.warn(`[designResearch] GitHub API returned ${response.status}`);
            return [];
        }
        const data = await response.json();
        return (data.items || []).slice(0, maxResults).map((repo) => ({
            name: repo.name,
            full_name: repo.full_name,
            description: repo.description || '',
            stars: repo.stargazers_count,
            url: repo.html_url,
            language: repo.language || null,
            topics: repo.topics || [],
            license: repo.license?.spdx_id || null,
        }));
    }
    catch (err) {
        console.warn('[designResearch] GitHub search error:', err.message);
        return [];
    }
}
// ─── Format Helpers ────────────────────────────────────────────────────
/**
 * Format GitHub results as text for LLM context.
 */
function formatGitHubForContext(repos) {
    if (repos.length === 0)
        return '';
    const lines = [
        `\n🐙 Similar Open-Source Projects on GitHub:`,
        `   Found ${repos.length} relevant repositories:\n`,
    ];
    for (const repo of repos) {
        lines.push(`   • ${repo.full_name}`);
        lines.push(`     Description: ${repo.description || 'N/A'}`);
        lines.push(`     ⭐ ${repo.stars.toLocaleString()} stars`);
        lines.push(`     URL: ${repo.url}`);
        if (repo.language)
            lines.push(`     Language: ${repo.language}`);
        if (repo.topics.length > 0)
            lines.push(`     Topics: ${repo.topics.slice(0, 5).join(', ')}`);
        lines.push('');
    }
    return lines.join('\n');
}
/**
 * Format web search results as text for LLM context.
 */
function formatWebForContext(results) {
    if (results.length === 0)
        return '';
    const lines = [
        `\n🌐 Web Search Results for Similar Apps:`,
        `   Found ${results.length} relevant articles/pages:\n`,
    ];
    for (const result of results) {
        lines.push(`   • ${result.title}`);
        lines.push(`     URL: ${result.url}`);
        lines.push(`     Summary: ${result.content.substring(0, 400)}${result.content.length > 400 ? '...' : ''}`);
        lines.push('');
    }
    return lines.join('\n');
}
// ─── Main Research Function ────────────────────────────────────────────
/**
 * Build a COMPACT research context for injection into a generation prompt.
 * Unlike `DesignResearchResult.context` (the full verbose report), this keeps
 * only the top few results per source so the prompt stays small — important
 * for local models that slow down on very large prompts. Pure function, so it
 * is unit-testable without any network access.
 */
export function formatResearchContext(research, maxPerSource = 2) {
    const lines = [];
    lines.push('📋 Reference designs found from the web, GitHub, and open source alternatives:');
    for (const w of research.webResults.slice(0, maxPerSource)) {
        lines.push(`  • ${w.title}`);
        lines.push(`    ${w.content.substring(0, 200)}`);
    }
    for (const g of research.githubResults.slice(0, maxPerSource)) {
        lines.push(`  • ⭐${g.stars} ${g.full_name}: ${g.description.substring(0, 150)}`);
    }
    for (const a of research.altResults.projects.slice(0, maxPerSource)) {
        lines.push(`  • ${a.name} (${a.category}): ${a.description.substring(0, 150)}`);
    }
    lines.push('\nUse these as inspiration for designing the app architecture.');
    return lines.join('\n');
}
/**
 * Perform comprehensive design research for the user's app idea.
 * Searches the web, GitHub, and opensourcealternative.to in parallel,
 * then formats everything as a single context string for the LLM.
 *
 * @param goal - The user's app description / goal
 * @param searchService - Optional WebSearchService instance
 * @param maxResults - Max results per source
 * @returns Combined research result with context and structured data
 */
export async function researchDesign(goal, searchService, maxResults = 5) {
    const webResults = [];
    const searchSvc = searchService || getSearchService();
    // Run all three searches in parallel
    const [webSearchResult, githubRepos, altResult] = await Promise.all([
        // 1. Web search
        (async () => {
            try {
                const query = `best open source ${goal} app similar projects`;
                const response = await searchSvc.search({ query, maxResults: maxResults + 2 });
                return response.results.map((r) => ({
                    title: r.title,
                    url: r.url,
                    content: r.content,
                }));
            }
            catch (err) {
                console.warn('[designResearch] Web search error:', err.message);
                return [];
            }
        })(),
        // 2. GitHub search
        searchGitHub(goal, maxResults),
        // 3. OpenSourceAlternative.to search
        searchOpenSourceAlt(goal, maxResults),
    ]);
    // Build combined context string
    const parts = [
        `📋 DESIGN RESEARCH REPORT`,
        `=======================`,
        `Research performed for: "${goal}"`,
        `\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`,
        formatWebForContext(webSearchResult),
        `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`,
        formatGitHubForContext(githubRepos),
        `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`,
        formatOpenSourceAltForContext(altResult),
        `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`,
    ];
    const context = parts.filter((p) => p).join('\n');
    const totalReferences = webSearchResult.length + githubRepos.length + altResult.totalFound;
    return {
        context,
        webResults: webSearchResult,
        githubResults: githubRepos,
        altResults: altResult,
        totalReferences,
    };
}
