/**
 * Memory-write intent detection.
 *
 * Detects when the user asks VACA to write/save/remember something to its
 * memory or wiki ("write this into your wiki", "save this to your notes",
 * "remember that I like dark mode"). The chat LLM previously hallucinated
 * these writes (printing fake file trees). Now the platform detects the
 * intent, performs the write itself, and returns a deterministic
 * confirmation — the model never fakes a write again.
 */
// Never intercept questions ABOUT the capability itself.
const QUESTION_RE = /^(how|what|why|where|when|who|can you|do you|are you|will you|is it|does it|tell me|explain|show me|is there|have you)\b/i;
const TARGET_PHRASE_RE = /\b(your|the|my|our)?\s*(wiki|memory|note|notes|brain|knowledge\s*base|operating\s*folder)\b/i;
/** Build a short topic from content, falling back to a supplied default. */
export function deriveTopic(content, fallback) {
    const first = content.split('\n').map(l => l.trim()).find(l => l.length > 0) || fallback;
    return first.length > 60 ? first.slice(0, 57) + '...' : first;
}
/**
 * Detect a request to write/save/remember content to memory or the wiki.
 * Returns null when the message is a question, too long, or not a write
 * request.
 */
export function detectMemoryWriteRequest(text) {
    const t = (text || '').trim();
    if (!t || t.length > 4000)
        return null;
    if (QUESTION_RE.test(t))
        return null;
    // 1) "remember this" / "remember that" / "remember this: <content>"
    if (/^remember\s+(this|that)\s*$/i.test(t)) {
        return { target: 'memory', instruction: t, hasInlineContent: false };
    }
    const rem = t.match(/^remember\s+(?:this|that)\s*[:\-–—]?\s*([\s\S]+)$/i);
    if (rem && rem[1].trim().length > 0) {
        return {
            target: 'memory',
            instruction: 'remember',
            hasInlineContent: true,
            inlineContent: rem[1].trim(),
        };
    }
    // 2) "write/save/store/put/record/log/add ... (this|that|it|the following...)
    //      ... (into|to|in|on) ... (your|the) (wiki|memory|notes|brain|...)"
    const verb = t.match(/\b(write|save|store|put|record|log|add)\b/i);
    if (verb) {
        const objMatch = t.match(/\b(this|that|it|the\s+(?:following|above|conversation|chat|idea|question|answer|app|feature|information|content|text|note))\b/i);
        if (!objMatch)
            return null;
        const targetMatch = t.match(TARGET_PHRASE_RE);
        if (!targetMatch || targetMatch.index === undefined)
            return null;
        const target = /wiki/i.test(targetMatch[0]) ? 'wiki' : 'memory';
        // Inline content only when explicitly delimited with a colon after the target
        // phrase ("save this to memory: <content>"). Without a delimiter the request
        // refers to prior context ("save this to memory") — never guess a fragment
        // like "about the project" as the content to save.
        const after = t.slice(targetMatch.index + targetMatch[0].length).trim();
        const hasInline = after.length > 0 && /^[:：]/.test(after);
        return {
            target,
            instruction: t,
            hasInlineContent: hasInline,
            inlineContent: hasInline ? after.replace(/^[:：]\s*/, '') : undefined,
        };
    }
    return null;
}
/**
 * Build the content to persist from a single-prompt request. Uses the inline
 * content when present; otherwise strips the trailing instruction line from
 * the prompt (single-prompt requests may embed history as "User:/Assistant:"
 * lines) and saves the remainder.
 */
export function buildContentFromPrompt(req, prompt) {
    if (req.hasInlineContent && req.inlineContent)
        return req.inlineContent;
    const lines = (prompt || '').trim().split('\n');
    // Drop the last line (assumed to be the instruction itself)
    lines.pop();
    const rest = lines.join('\n').trim();
    return rest.length > 0 ? rest : prompt.trim();
}
/**
 * Build the content to persist from a chat message array. Uses inline content
 * when present; otherwise serializes all prior messages (everything before
 * the latest user message).
 */
export function buildContentFromMessages(req, messages) {
    if (req.hasInlineContent && req.inlineContent)
        return req.inlineContent;
    const prior = messages.slice(0, -1); // drop the "write this" instruction message
    if (prior.length === 0) {
        // Nothing before the instruction → nothing to save (the route will tell the
        // user there's no content yet instead of persisting the instruction itself).
        return '';
    }
    const serialized = prior
        .map(m => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`)
        .join('\n\n');
    const MAX = 6000;
    return serialized.length > MAX ? serialized.slice(0, MAX) + '\n[...truncated]' : serialized;
}
