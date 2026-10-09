/**
 * OpenSourceAlternative.to Search Service
 * =========================================
 *
 * Searches https://www.opensourcealternative.to/ for open-source projects
 * that match the user's app idea. Since the site has no public API, we
 * scrape category pages and project detail pages to find relevant matches.
 *
 * Strategy:
 * 1. Map user's app goal keywords to known categories on the site
 * 2. Scrape matching category pages for project listings
 * 3. Optionally fetch individual project details
 * 4. Return structured results that can be used as LLM reference context
 */
// ─── Known categories on opensourcealternative.to ──────────────────────
// Maps app-related keywords to categories on the site.
// The site uses hyphenated category slugs in URLs.
const KEYWORD_CATEGORY_MAP = {
    // Productivity / Note-taking / Documentation
    note: ['notetaking', 'documentation', 'project-management'],
    notes: ['notetaking', 'documentation'],
    notebook: ['notetaking', 'documentation'],
    journal: ['notetaking'],
    docs: ['documentation'],
    document: ['documentation'],
    wiki: ['documentation', 'project-management'],
    task: ['project-management', 'productivity'],
    todo: ['project-management', 'productivity'],
    'to-do': ['project-management', 'productivity'],
    kanban: ['project-management'],
    project: ['project-management'],
    productivity: ['productivity', 'project-management'],
    // Chat / Communication
    chat: ['communication'],
    messaging: ['communication'],
    message: ['communication'],
    messenger: ['communication'],
    team: ['communication', 'project-management'],
    slack: ['communication'],
    discord: ['communication', 'social-media'],
    social: ['social-media'],
    forum: ['communication'],
    // CRM / Business
    crm: ['crm'],
    sales: ['crm'],
    business: ['crm', 'e-commerce'],
    erp: ['crm'],
    invoice: ['e-commerce', 'crm'],
    accounting: ['crm', 'e-commerce'],
    // E-commerce
    shop: ['e-commerce'],
    store: ['e-commerce'],
    ecommerce: ['e-commerce'],
    'e-commerce': ['e-commerce'],
    marketplace: ['e-commerce'],
    // Database
    database: ['database'],
    db: ['database'],
    sql: ['database'],
    nosql: ['database'],
    storage: ['database', 'cloud-storage'],
    // Analytics / BI
    analytics: ['analytics', 'business-intelligence'],
    dashboard: ['analytics', 'business-intelligence', 'visual-database'],
    bi: ['business-intelligence'],
    metrics: ['analytics', 'observability-and-monitoring'],
    monitoring: ['observability-and-monitoring'],
    observability: ['observability-and-monitoring'],
    logging: ['observability-and-monitoring'],
    // Developer tools
    ide: ['developer-tools'],
    editor: ['developer-tools'],
    code: ['developer-tools'],
    dev: ['developer-tools'],
    developer: ['developer-tools'],
    api: ['developer-tools', 'api-platform'],
    'api platform': ['api-platform'],
    // Media
    media: ['gaming', 'video', 'music'],
    video: ['video'],
    music: ['music', 'audio'],
    audio: ['music', 'audio'],
    stream: ['video', 'music'],
    streaming: ['video', 'music'],
    player: ['video', 'music', 'gaming'],
    gaming: ['gaming'],
    game: ['gaming'],
    // Automation / Workflow
    automation: ['automation'],
    workflow: ['automation'],
    pipeline: ['automation', 'developer-tools'],
    ci: ['developer-tools', 'automation'],
    cd: ['developer-tools'],
    // Auth / Security
    auth: ['auth-and-sso', 'cybersecurity'],
    login: ['auth-and-sso'],
    authentication: ['auth-and-sso'],
    security: ['cybersecurity', 'auth-and-sso'],
    password: ['auth-and-sso', 'cybersecurity'],
    encryption: ['cybersecurity'],
    // CMS / Content
    cms: ['cms'],
    blog: ['cms'],
    website: ['cms'],
    content: ['cms'],
    // Design
    design: ['design-and-ux'],
    ui: ['design-and-ux'],
    ux: ['design-and-ux'],
    prototyping: ['design-and-ux'],
    // Cloud / Infrastructure
    cloud: ['cloud-storage', 'cloud-computing'],
    hosting: ['cloud-computing'],
    infrastructure: ['cloud-computing', 'devops'],
    devops: ['devops'],
    // Maps / Location
    map: ['maps-and-location'],
    maps: ['maps-and-location'],
    location: ['maps-and-location'],
    gps: ['maps-and-location'],
};
/** All available categories on the site (from sitemap inspection) */
const ALL_CATEGORIES = [
    'api-platform', 'automation', 'auth-and-sso', 'analytics',
    'business-intelligence', 'cms', 'crm', 'cloud-computing',
    'cloud-storage', 'communication', 'cybersecurity', 'database',
    'design-and-ux', 'developer-tools', 'devops', 'documentation',
    'e-commerce', 'gaming', 'internal-tool', 'maps-and-location',
    'music', 'notetaking', 'observability-and-monitoring',
    'productivity', 'project-management', 'social-media',
    'video', 'visual-database',
];
// ─── Category Mapping ──────────────────────────────────────────────────
/**
 * Map a user's goal text to relevant categories on opensourcealternative.to.
 * Splits the goal into words/phrases and looks them up in the keyword map.
 */
function mapGoalToCategories(goal) {
    const lower = goal.toLowerCase();
    const matched = new Set();
    // Check full phrases first (longer matches)
    const phrases = Object.keys(KEYWORD_CATEGORY_MAP).sort((a, b) => b.length - a.length);
    for (const phrase of phrases) {
        if (lower.includes(phrase)) {
            for (const cat of KEYWORD_CATEGORY_MAP[phrase]) {
                matched.add(cat);
            }
        }
    }
    // If no categories matched, try checking individual words
    if (matched.size === 0) {
        const words = lower.split(/[^a-z0-9]+/).filter(w => w.length > 2);
        for (const word of words) {
            if (KEYWORD_CATEGORY_MAP[word]) {
                for (const cat of KEYWORD_CATEGORY_MAP[word]) {
                    matched.add(cat);
                }
            }
        }
    }
    // If still nothing, return some generic categories as fallback
    if (matched.size === 0) {
        matched.add('developer-tools');
        matched.add('productivity');
        matched.add('cms');
    }
    return Array.from(matched).slice(0, 5); // max 5 categories
}
/**
 * Scrape a single category page for project listings.
 * The site returns HTML with cards containing project name, description,
 * star count, and a link to the project page.
 */
async function scrapeCategoryPage(category) {
    const url = `https://www.opensourcealternative.to/category/${category}`;
    const projects = [];
    try {
        const response = await fetch(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html',
            },
            signal: AbortSignal.timeout(10000),
        });
        if (!response.ok) {
            console.warn(`[opensourceAlt] Category page ${category} returned ${response.status}`);
            return [];
        }
        const html = await response.text();
        // Parse project cards from HTML
        // Each project is typically in a card/div with project name and description
        // We use regex to extract the key details
        const projectBlocks = html.match(/<a[^>]*href="\/project\/([^"]+)"[^>]*>[\s\S]*?<\/a>/gi);
        if (!projectBlocks)
            return [];
        const seen = new Set();
        for (const block of projectBlocks) {
            // Extract project slug from href
            const slugMatch = block.match(/\/project\/([^"\\/]+)/);
            if (!slugMatch)
                continue;
            const projectSlug = slugMatch[1];
            if (seen.has(projectSlug))
                continue;
            seen.add(projectSlug);
            // Extract project name - usually the text content of the link
            const nameMatch = block.match(/<a[^>]*href="\/project\/[^"]*"[^>]*>([^<]+)<\/a>/);
            const name = nameMatch
                ? nameMatch[1].trim()
                : projectSlug;
            // Extract star count if present
            const starsMatch = block.match(/(\d{1,3}(?:,\d{3})*)\s*(?:stars|⭐)/i);
            const stars = starsMatch
                ? parseInt(starsMatch[1].replace(/,/g, ''), 10)
                : 0;
            // Extract description
            const descMatch = block.match(/<p[^>]*>([^<]+)<\/p>/);
            const description = descMatch
                ? descMatch[1].trim()
                : '';
            if (name) {
                projects.push({
                    name,
                    description,
                    category,
                    stars,
                    projectSlug,
                });
            }
            if (projects.length >= 10)
                break; // cap per category
        }
        // If the above regex approach got nothing, try alternative parsing
        if (projects.length === 0) {
            // Fallback: extract from the visible text structure
            const lines = html.split('\n');
            let i = 0;
            while (i < lines.length && projects.length < 10) {
                const line = lines[i].trim();
                // Look for lines that look like project entries (name followed by description)
                if (line.length > 0 &&
                    line.length < 100 &&
                    !line.startsWith('<') &&
                    !line.startsWith('{') &&
                    !line.startsWith('}') &&
                    !line.includes('Sponsored') &&
                    !line.includes('Open Source') &&
                    !line.includes('Discover') &&
                    projects.every(p => p.name !== line)) {
                    const nextLine = lines[i + 1]?.trim() || '';
                    projects.push({
                        name: line,
                        description: nextLine.length > 0 && nextLine.length < 200 ? nextLine : '',
                        category,
                        stars: 0,
                        projectSlug: line.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
                    });
                    i += 2;
                    continue;
                }
                i++;
            }
        }
        console.log(`[opensourceAlt] Scraped category "${category}": ${projects.length} projects`);
        return projects;
    }
    catch (err) {
        console.warn(`[opensourceAlt] Error scraping category "${category}":`, err.message);
        return [];
    }
}
// ─── Project Detail Scraper ────────────────────────────────────────────
/**
 * Fetch details for a specific project from its page.
 */
async function scrapeProjectDetails(slug) {
    try {
        const url = `https://www.opensourcealternative.to/project/${slug}`;
        const response = await fetch(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html',
            },
            signal: AbortSignal.timeout(8000),
        });
        if (!response.ok)
            return null;
        const text = await response.text();
        // Extract license
        const licenseMatch = text.match(/License:\s*\n*\s*([^\n<]+)/i);
        const license = licenseMatch ? licenseMatch[1].trim() : undefined;
        // Extract languages
        const langSection = text.match(/Languages?:[\s\S]*?(?=\n\n|$)/i);
        const languages = langSection
            ? langSection[0]
                .split('\n')
                .filter(l => l.trim().length > 0 && !l.toLowerCase().includes('language'))
                .map(l => l.trim())
            : undefined;
        // Extract alternatives to
        const altMatch = text.match(/Open Source Alternative to:[\s\S]*?(?=\n\n|$)/i);
        const alternativesTo = altMatch
            ? altMatch[0]
                .split('\n')
                .filter(l => l.trim().length > 0 && !l.toLowerCase().includes('alternative'))
                .map(l => l.trim())
            : undefined;
        // Extract description/content (between first <p> tags or after the title block)
        const contentMatch = text.match(/(?:Standardnotes|Appsmith|[\w\s]+)\s+is[\s\S]*?(?=\n\n\w|\nShare:|\nSimilar)/);
        const content = contentMatch
            ? contentMatch[0].trim().substring(0, 1000)
            : undefined;
        return { license, languages, alternativesTo, content };
    }
    catch (err) {
        console.warn(`[opensourceAlt] Error scraping project "${slug}":`, err.message);
        return null;
    }
}
// ─── Main Search Function ──────────────────────────────────────────────
/**
 * Search opensourcealternative.to for projects relevant to the user's goal.
 *
 * @param goal - The user's app description / goal text
 * @param maxResults - Maximum number of projects to return
 * @returns Structured search results with matched projects and categories
 */
export async function searchOpenSourceAlt(goal, maxResults = 8) {
    const categories = mapGoalToCategories(goal);
    // Scrape all matched category pages in parallel
    const categoryResults = await Promise.all(categories.map(cat => scrapeCategoryPage(cat)));
    // Flatten and deduplicate by name
    const allProjects = new Map();
    for (const projects of categoryResults) {
        for (const proj of projects) {
            const key = proj.name.toLowerCase().replace(/\s+/g, '-');
            // Keep the one with more stars (from a more relevant category)
            const existing = allProjects.get(key);
            if (!existing || proj.stars > existing.stars) {
                allProjects.set(key, proj);
            }
        }
    }
    // Sort by stars (descending) and take top results
    const sorted = Array.from(allProjects.values())
        .sort((a, b) => b.stars - a.stars)
        .slice(0, maxResults);
    // Build output projects
    const projects = sorted.map(p => ({
        name: p.name,
        description: p.description,
        category: p.category,
        stars: p.stars,
        url: `https://www.opensourcealternative.to/project/${p.projectSlug}`,
    }));
    // Optionally fetch details for top projects (skip if too many)
    // This is done in a fire-and-forget manner to not block the response
    if (projects.length <= 4) {
        await Promise.all(projects.map(async (p, idx) => {
            const slug = p.url.split('/').pop() || '';
            const details = await scrapeProjectDetails(slug);
            if (details) {
                if (details.license)
                    projects[idx].license = details.license;
                if (details.languages)
                    projects[idx].languages = details.languages;
                if (details.alternativesTo)
                    projects[idx].alternativesTo = details.alternativesTo;
                if (details.content)
                    projects[idx].content = details.content;
            }
        }));
    }
    return {
        projects,
        matchedCategories: categories,
        totalFound: projects.length,
    };
}
/**
 * Format OpenSourceAlternative.to results as text for LLM context.
 */
export function formatOpenSourceAltForContext(result) {
    if (result.projects.length === 0)
        return '';
    const lines = [
        `\n📦 Open Source Alternatives (opensourcealternative.to):`,
        `   Searched categories: ${result.matchedCategories.join(', ')}`,
        `   Found ${result.totalFound} similar open-source projects:\n`,
    ];
    for (const proj of result.projects) {
        lines.push(`   • ${proj.name}`);
        lines.push(`     Description: ${proj.description || 'N/A'}`);
        lines.push(`     ⭐ ${proj.stars.toLocaleString()} stars`);
        lines.push(`     URL: ${proj.url}`);
        if (proj.license)
            lines.push(`     License: ${proj.license}`);
        if (proj.languages?.length)
            lines.push(`     Languages: ${proj.languages.join(', ')}`);
        if (proj.alternativesTo?.length)
            lines.push(`     Alternative to: ${proj.alternativesTo.join(', ')}`);
        if (proj.content) {
            // Truncate content for context
            const truncated = proj.content.length > 300
                ? proj.content.substring(0, 300) + '...'
                : proj.content;
            lines.push(`     Details: ${truncated}`);
        }
        lines.push('');
    }
    return lines.join('\n');
}
