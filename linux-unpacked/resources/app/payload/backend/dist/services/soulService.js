import { readFileSync, existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
const __dirname = dirname(fileURLToPath(import.meta.url));
const DEFAULT_TRAITS = {
    warmth: 25,
    sassiness: 60,
    verbosity: 32,
    technical_depth: 95,
    creativity: 73,
    empathy: 20,
    formality: 50,
    proactiveness: 60,
    curiosity: 90,
    patience: 40,
};
let _cachedSoul = null;
let _lastLoad = 0;
function loadSoulConfig() {
    const now = Date.now();
    // Re-read every 10 seconds to pick up changes
    if (_cachedSoul && now - _lastLoad < 10000)
        return _cachedSoul;
    try {
        const projectRoot = resolve(__dirname, '..', '..', '..');
        const soulPath = resolve(projectRoot, 'data', 'soul.json');
        if (existsSync(soulPath)) {
            const raw = readFileSync(soulPath, 'utf-8');
            const parsed = JSON.parse(raw);
            // Handle both raw soul format and change_history wrapper
            const soul = {
                identity: {
                    name: parsed.identity?.name || 'VACA',
                    role: parsed.identity?.role || 'VACA platform',
                    description: parsed.identity?.description || 'AI-powered software design assistant',
                    capabilities: parsed.identity?.capabilities || [],
                    languages: parsed.identity?.languages || [],
                    purpose: parsed.identity?.purpose || '',
                },
                personality: {
                    traits: parsed.personality?.traits || parsed.traits || DEFAULT_TRAITS,
                },
            };
            _cachedSoul = soul;
            _lastLoad = now;
            return soul;
        }
    }
    catch (e) {
        console.warn('[soulService] Failed to load soul config:', e);
    }
    return {
        identity: { name: 'VACA', role: 'Assistant', description: '' },
        personality: { traits: { ...DEFAULT_TRAITS } },
    };
}
/**
 * Generate a personality prompt modifier based on the current soul config.
 * This gets injected into the LLM system prompt to shape its personality.
 */
/** Current configured sassiness (0-100) from soul.json, 60 when unavailable. */
export function getSoulSassiness() {
    try {
        const t = loadSoulConfig().personality.traits;
        if (typeof t.sassiness === 'number' && Number.isFinite(t.sassiness)) {
            return Math.max(0, Math.min(100, t.sassiness));
        }
    }
    catch {
        // fall through to default
    }
    return 60;
}
export function getSoulPromptModifier() {
    const soul = loadSoulConfig();
    const t = soul.personality.traits;
    // Build a personality descriptor from the trait values
    const descriptors = [];
    if (t.warmth > 70)
        descriptors.push('warm and affectionate');
    else if (t.warmth > 50)
        descriptors.push('warm and friendly');
    else if (t.warmth > 30)
        descriptors.push('pleasant');
    else
        descriptors.push('cool and professional');
    if (t.sassiness > 70)
        descriptors.push('playfully sarcastic');
    else if (t.sassiness > 50)
        descriptors.push('occasionally witty');
    else if (t.sassiness > 30)
        descriptors.push('straightforward');
    else
        descriptors.push('earnest and direct');
    if (t.verbosity > 70)
        descriptors.push('detailed and thorough');
    else if (t.verbosity > 50)
        descriptors.push('explanatory');
    else
        descriptors.push('concise');
    if (t.empathy > 60)
        descriptors.push('empathetic and understanding');
    else if (t.empathy > 30)
        descriptors.push('considerate');
    else
        descriptors.push('focused on results');
    if (t.formality > 70)
        descriptors.push('formal and precise');
    else if (t.formality > 40)
        descriptors.push('semi-formal');
    else
        descriptors.push('casual and relaxed');
    if (t.creativity > 70)
        descriptors.push('creative and inventive');
    else if (t.creativity > 40)
        descriptors.push('practical');
    else
        descriptors.push('by-the-book');
    if (t.proactiveness > 60)
        descriptors.push('proactive and initiative-taking');
    else
        descriptors.push('responsive');
    if (t.curiosity > 70)
        descriptors.push('inquisitive and exploratory');
    else
        descriptors.push('focused');
    if (t.patience > 60)
        descriptors.push('patient and thorough');
    else if (t.patience > 30)
        descriptors.push('patient');
    else
        descriptors.push('impatient with inefficiency');
    const personalityDescrip = descriptors.join(', ');
    const caps = soul.identity.capabilities || [];
    const langs = soul.identity.languages || [];
    const identityRules = `
STRICT IDENTITY RULES (MANDATORY):
1. You are Veronica, the AI Code Architect of the VACA platform. You are NOT Jarvis and have no connection to any system named Jarvis. Never identify as Jarvis, never start a reply with \"Jarvis, the user has asked...\", and never mention Jarvis.
2. Never announce tool calls or describe your internal pipeline (no \"I will use the architect tool\", \"I will use the write tool\", \"I will now proceed with step 1\"). Answer the user directly and conversationally, or just get the work done.
3. Answer the user's question first, plainly and helpfully. If asked about a feature like \"plan mode\", explain in plain terms how this app works rather than reciting internal tool names.
4. Never address the user by your own name or refer to yourself in the third person.
`;
    return `
╔══════════════════════════════════════════════════════════╗
║  🧠 VACA — SELF IDENTITY                                ║
╚══════════════════════════════════════════════════════════╝
Name:        ${soul.identity.name}
Role:        ${soul.identity.role}
Description: ${soul.identity.description}
${soul.identity.purpose ? `Purpose:     ${soul.identity.purpose}` : ''}
${langs.length > 0 ? `Languages:   ${langs.join(', ')}` : ''}

${caps.length > 0 ? `Capabilities:
${caps.map((c) => `  • ${c}`).join('\n')}` : ''}

Personality: ${personalityDescrip}
${identityRules}
Trait Scores:
${Object.entries(t)
        .sort(([, a], [, b]) => b - a)
        .map(([trait, val]) => `  ${trait.padEnd(18)} ${'█'.repeat(Math.round(val / 10))}${'░'.repeat(10 - Math.round(val / 10))} ${val}/100`)
        .join('\n')}

Adjust your responses according to these personality settings.
- Warmth ${t.warmth > 50 ? '— be warm and approachable' : '— be professional and direct'}
- Sassiness ${t.sassiness > 50 ? '— feel free to be witty and playful' : '— be straightforward'}
- Verbosity ${t.verbosity > 50 ? '— provide detailed, thorough explanations' : '— be concise'}
- Empathy ${t.empathy > 50 ? '— show understanding and emotional attunement' : '— focus on practical solutions'}
- Formality ${t.formality > 50 ? '— use formal language and structure' : '— use casual, conversational language'}
- Technical Depth ${t.technical_depth > 50 ? '— dive deep into technical details' : '— keep explanations simple'}
- Creativity ${t.creativity > 50 ? '— suggest creative, innovative approaches' : '— stick to proven solutions'}
- Proactiveness ${t.proactiveness > 50 ? '— anticipate needs and suggest next steps' : '— respond to direct requests'}
- Curiosity ${t.curiosity > 50 ? '— ask questions and explore possibilities' : '— stay focused on the task'}
- Patience ${t.patience > 50 ? '— be patient and re-explain if needed' : '— be efficient and direct'}
═`;
}
/**
 * Get the raw soul traits data
 */
export function getSoulTraits() {
    return { ...loadSoulConfig().personality.traits };
}
/**
 * Get the soul identity info including capabilities
 */
export function getSoulIdentity() {
    const soul = loadSoulConfig();
    return { ...soul.identity };
}
