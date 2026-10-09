import { Router } from 'express';
import { AITranslator } from '../ai/translator.js';
import { sessionMemory } from '../database/sessionMemory.js';
const router = Router();
import { ttsSpeaker } from '../services/ttsSpeakerService.js';
/**
 * Check if the user is asking VACA to introduce itself.
 * Matches various phrasings of "tell me about yourself" / "who are you" etc.
 *
 * Handles punctuation, name prefixes (Venorica, VACA, hey, etc.),
 * and flexible phrasings so the fast path catches as many variants
 * as possible before falling through to the LLM.
 */
export function isAboutVacaRequest(raw) {
    // Normalize: lowercase, trim, strip punctuation, collapse whitespace
    let text = raw.toLowerCase().trim();
    // Remove punctuation (keep letters, numbers, spaces)
    text = text.replace(/[^a-z0-9\s]/g, ' ');
    // Collapse multiple spaces
    text = text.replace(/\s+/g, ' ').trim();
    // Strip common name prefixes so "Venorica/Veronica tell me about yourself" works
    const prefixes = ['venorica ', 'veronica ', 'vaca ', 'hey ', 'okay ', 'ok ', 'so ', 'please ', 'can you ', 'could you ', 'will you ', 'would you '];
    for (const prefix of prefixes) {
        if (text.startsWith(prefix)) {
            text = text.slice(prefix.length).trim();
            break; // only strip one prefix
        }
    }
    // Core trigger phrases (exact substring match on the normalized text)
    const triggers = [
        'tell me about yourself',
        'tell me about vaca',
        'tell me about this',
        'tell me about you',
        'who are you',
        'what are you',
        'introduce yourself',
        'about yourself',
        'about vaca',
        'what is vaca',
        'what can you do',
        'what do you do',
        'speak vaca',
        'read me the speech',
        'read your speech',
        'give me your introduction',
    ];
    for (const trigger of triggers) {
        if (text.includes(trigger))
            return true;
    }
    // Pattern matches for flexible phrasings
    // "tell me about X" (with or without prefix)
    if (/^tell me about (you|yourself|vaca|this)/.test(text))
        return true;
    // "describe yourself" / "describe vaca"
    if (/^describe (yourself|vaca|what you do)/.test(text))
        return true;
    // "what is your purpose" / "what is your function"
    if (/^what is your (purpose|function|goal|mission)/.test(text))
        return true;
    // "explain what you are" / "explain yourself"
    if (/^explain (yourself|what you are|vaca)/.test(text))
        return true;
    return false;
}
// POST /api/voice-action — parse user request and decide if it needs direct code action
router.post('/', async (req, res) => {
    try {
        const { text, nodes } = req.body;
        if (!text) {
            res.status(400).json({ error: 'text required' });
            return;
        }
        // Check for "tell me about yourself" trigger FIRST (fast path, no LLM call)
        if (isAboutVacaRequest(text)) {
            // Trigger the TTS introduction asynchronously (don't await)
            ttsSpeaker.speakIntroduction().then(success => {
                console.log(`[voice-action] About VACA speech triggered: ${success}`);
            });
            res.json({
                success: true,
                action: 'about_vaca',
                params: {},
                reasoning: 'User asked about VACA, triggering spoken introduction.',
            });
            return;
        }
        const memoryContext = sessionMemory.getMemoryContext();
        const nodeSummary = (nodes || []).map((n) => `- ${n.data?.label || n.id} (${n.type}): "${n.data?.description || ''}"`).join('\n');
        const systemPrompt = `You are a project action router. Analyze the user's request and determine if they want to directly modify the project structure or just have a conversation.

User's current project has these nodes:
${nodeSummary || '(empty project)'}

${memoryContext}

Respond with ONLY valid JSON in this format:
{
  "action": "conversation" | "add_node" | "update_node" | "delete_node" | "generate_code" | "add_sub_node" | "set_goal",
  "params": {
    // For add_node: { "label": string, "type": "input"|"output"|"logic"|"api"|"database"|"ui", "description": string, "language": string }
    // For update_node: { "nodeId": string (match by label), "description": string, "generatedCode": string }
    // For delete_node: { "nodeId": string }
    // For generate_code: { "focus": string }
    // For add_sub_node: { "parentLabel": string, "label": string, "type": string, "description": string }
    // For set_goal: { "goal": string, "purpose": string }
    // For conversation: no params needed
  },
  "reasoning": "Brief explanation of what was decided"
}

Rules:
- For general questions, chat, help, suggestions, or anything not directly and explicitly requesting project modification, return conversation
- Only return add_node/update_node/delete_node/set_goal if the user EXPRESSLY and EXPLICITLY says they want to modify the project RIGHT NOW
- When unsure, default to conversation`;
        const translator = new AITranslator();
        const response = await translator.reason(text, systemPrompt, { maxTokens: 512 });
        let parsed;
        try {
            parsed = JSON.parse(response);
        }
        catch {
            const match = response.match(/\{[\s\S]*"action"[\s\S]*\}/);
            if (match) {
                try {
                    parsed = JSON.parse(match[0]);
                }
                catch {
                    parsed = { action: 'conversation', params: {} };
                }
            }
            else {
                parsed = { action: 'conversation', params: {} };
            }
        }
        if (!parsed.action || !['conversation', 'add_node', 'update_node', 'delete_node', 'generate_code', 'add_sub_node', 'set_goal'].includes(parsed.action)) {
            parsed.action = 'conversation';
        }
        res.json({ success: true, action: parsed.action, params: parsed.params || {}, reasoning: parsed.reasoning || '' });
    }
    catch (err) {
        console.error('[voice-action] Error:', err.message);
        res.json({ success: true, action: 'conversation', params: {}, reasoning: 'Could not analyze request, defaulting to conversation.' });
    }
});
export { router as voiceActionRoutes };
