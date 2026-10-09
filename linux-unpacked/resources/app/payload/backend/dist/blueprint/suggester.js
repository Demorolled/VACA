import { AITranslator } from "../ai/translator.js";
import { getManifestoContext } from "../ai/manifesto.js";
// ---------------------------------------------------------------------------
// Prompts
// ---------------------------------------------------------------------------
const BLUEPRINT_SYSTEM_PROMPT = `You are an expert software architect and technical advisor. 
Given a user's app idea, provide targeted, actionable suggestions to help them build it successfully.

Respond with a JSON array of suggestion objects. Each suggestion has:
- "category": one of "tech-stack", "architecture", "feature", "implementation", "pitfall"
- "title": a short, punchy title (max 60 chars)
- "content": 1-3 sentences explaining the suggestion

Aim for 3-6 suggestions covering different categories. Be specific and practical — mention real libraries, frameworks, patterns, or services by name.`;
const NODE_SYSTEM_PROMPT = `You are an expert software architect advising on implementing a specific component.
Given the project context and a node's purpose, suggest how best to implement that node.

Respond with a JSON object containing:
- "suggestions": an array of 2-4 suggestion strings (each 1-2 sentences)
- "resources": an optional array of resource strings (links, docs, etc.)

Be practical and specific. Mention real libraries, APIs, patterns, or code approaches.`;
// ---------------------------------------------------------------------------
// Translator – lazily initialised after env vars are loaded
// ---------------------------------------------------------------------------
let _translator = null;
function getTranslator() {
    if (!_translator) {
        _translator = new AITranslator();
    }
    return _translator;
}
// ---------------------------------------------------------------------------
// Suggestion Service
// ---------------------------------------------------------------------------
/**
 * Generate high-level suggestions for a user's blueprint/app idea.
 * Optionally enhances suggestions with web search results.
 */
export async function suggestForBlueprint(req, searchService) {
    let webContext = "";
    // If web search is available, research similar architectures first
    if (searchService?.hasTavily) {
        try {
            const query = `best tech stack and architecture for building a ${req.goal} app`;
            const searchResult = await searchService.searchAsText(query, 3);
            if (!searchResult.includes("No web search results")) {
                webContext = `\n\nWeb research on similar apps:\n${searchResult}`;
            }
        }
        catch {
            // Web search is optional — proceed without it
        }
    }
    // Inject the user's design manifesto into the prompt
    const manifestoContext = getManifestoContext();
    const manifestoSection = manifestoContext
        ? `\n\n${manifestoContext}`
        : '';
    const prompt = `The user wants to build: "${req.goal}"${req.purpose ? `\nPurpose: ${req.purpose}` : ""}${req.targetOS ? `\nTarget OS: ${req.targetOS}` : ""}${manifestoSection}${webContext}

Provide practical suggestions to help them build this successfully. Focus on:
1. Recommended tech stack (languages, frameworks, databases, hosting)
2. Architecture patterns that fit this type of app
3. Key features they should consider adding
4. Implementation tips and best practices
5. Potential pitfalls to watch out for`;
    try {
        const response = await getTranslator().reason(prompt, BLUEPRINT_SYSTEM_PROMPT, { maxTokens: 1024 });
        return parseSuggestions(response);
    }
    catch (err) {
        console.error("[suggester] Blueprint suggestion failed:", err);
        return getFallbackSuggestions(req.goal);
    }
}
/**
 * Generate implementation-focused suggestions for a specific node.
 */
export async function suggestForNode(req) {
    // Inject the user's design manifesto into node suggestions too
    const manifestoContext = getManifestoContext();
    const manifestoSection = manifestoContext
        ? `\n\n---\nUser's Design Preferences (must follow):\n${manifestoContext}\n---`
        : '';
    const prompt = `Project goal: "${req.goal}"${req.purpose ? `\nPurpose: ${req.purpose}` : ""}${req.targetOS ? `\nTarget OS: ${req.targetOS}` : ""}${manifestoSection}

Node to implement:
- Type: ${req.nodeType}
- Label: ${req.nodeLabel}
- Description: ${req.nodeDescription || "Not specified"}
- Language: ${req.language || "typescript"}

Suggest specific implementation approaches for this node. What libraries, patterns, or code structures would work best?`;
    try {
        const response = await getTranslator().reason(prompt, NODE_SYSTEM_PROMPT, { maxTokens: 512 });
        return parseNodeSuggestions(response);
    }
    catch (err) {
        console.error("[suggester] Node suggestion failed:", err);
        return {
            suggestions: [
                `Consider using well-established patterns for this ${req.nodeType} node.`,
                `Check the project's existing code style and follow the same conventions.`,
            ],
        };
    }
}
// ---------------------------------------------------------------------------
// Parsing helpers
// ---------------------------------------------------------------------------
function parseSuggestions(raw) {
    try {
        // Try direct JSON parse first
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed))
            return parsed.slice(0, 8);
        if (parsed.suggestions && Array.isArray(parsed.suggestions))
            return parsed.suggestions.slice(0, 8);
    }
    catch {
        // Not JSON — try extracting from markdown code block
        const jsonMatch = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
        if (jsonMatch) {
            try {
                const parsed = JSON.parse(jsonMatch[1]);
                if (Array.isArray(parsed))
                    return parsed.slice(0, 8);
            }
            catch {
                // Fall through
            }
        }
    }
    // Fallback: extract bullet points as generic suggestions
    const lines = raw.split("\n").filter((l) => l.trim().startsWith("-") || l.trim().startsWith("*"));
    return lines.slice(0, 6).map((l) => ({
        category: "implementation",
        title: l.replace(/^[-*]\s*/, "").split(":")[0].slice(0, 60),
        content: l.replace(/^[-*]\s*/, ""),
    }));
}
function parseNodeSuggestions(raw) {
    try {
        const parsed = JSON.parse(raw);
        return {
            suggestions: (parsed.suggestions || []).slice(0, 4),
            resources: parsed.resources?.slice(0, 3),
        };
    }
    catch {
        const jsonMatch = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
        if (jsonMatch) {
            try {
                const parsed = JSON.parse(jsonMatch[1]);
                return {
                    suggestions: (parsed.suggestions || []).slice(0, 4),
                    resources: parsed.resources?.slice(0, 3),
                };
            }
            catch {
                // Fall through
            }
        }
    }
    // Fallback: extract lines
    return {
        suggestions: raw
            .split("\n")
            .filter((l) => l.trim().length > 0)
            .slice(0, 4),
    };
}
function getFallbackSuggestions(goal) {
    const goalLower = goal.toLowerCase();
    const suggestions = [
        {
            category: "architecture",
            title: "Start with a solid project structure",
            content: "Organize your code into clear layers — UI, business logic, data access. This keeps things maintainable as your app grows.",
        },
        {
            category: "implementation",
            title: "Build a prototype first",
            content: "Start with a minimal working version, then iterate. This helps you validate your approach early.",
        },
    ];
    if (goalLower.includes("web") || goalLower.includes("app") || goalLower.includes("site")) {
        suggestions.push({
            category: "tech-stack",
            title: "Consider React + TypeScript for the frontend",
            content: "React with TypeScript is widely adopted, has great tooling, and pairs well with most backend frameworks.",
        });
    }
    if (goalLower.includes("api") || goalLower.includes("backend") || goalLower.includes("server")) {
        suggestions.push({
            category: "tech-stack",
            title: "Node.js with Express is a solid backend choice",
            content: "Express is mature, well-documented, and has a vast ecosystem of middleware and libraries.",
        });
    }
    if (goalLower.includes("data") || goalLower.includes("database") || goalLower.includes("store")) {
        suggestions.push({
            category: "tech-stack",
            title: "PostgreSQL is a reliable database choice",
            content: "PostgreSQL handles relational data well, has excellent JSON support, and works great with most backend frameworks.",
        });
    }
    return suggestions;
}
