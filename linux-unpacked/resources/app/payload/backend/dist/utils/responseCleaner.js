/**
 * cleanLLMResponse — strips hallucinated tool-call patterns, meta-instructions,
 * AND truncates multi-turn conversation continuations from LLM responses.
 *
 * CRITICAL BUG FIX: The conversation prompt uses "User:" and "Assistant:" prefixes
 * to format history. The model sometimes continues generating this pattern,
 * hallucinating entire follow-up turns ("Bot:", "User:", "Assistant:" lines).
 * This cleaner now truncates at the first sign of the model generating a new turn.
 *
 * Known hallucination patterns:
 *   "🔧 emotion_analyze → Unknown tool: ..."
 *   "**Analysis:**\n- The result shows..."
 *   "1. Let me retrieve your question..."
 *   "Bot: I think...\nUser: ok goodnight\nBot: Goodnight!" — multi-turn continuation
 */
/**
 * Truncate degenerated responses: when the same sentence (≥ ~24 chars) appears
 * 3+ times, cut everything from the second occurrence. This catches the classic
 * small-model repetition loop (e.g. "I'm going to assume you're using a
 * formatter to format the code" × 30) which otherwise passes through intact.
 */
function truncateRepeatedSentences(text) {
    // Split into sentences on . ! ? followed by space/end, preserving delimiters.
    const sentences = text.match(/[^.!?]+[.!?]+\s*|[^.!?]+$/g) || [];
    const seen = new Map(); // normalized sentence -> occurrence indexes
    sentences.forEach((s, i) => {
        const norm = s.trim().toLowerCase().replace(/\s+/g, ' ');
        if (norm.length >= 24) {
            if (!seen.has(norm))
                seen.set(norm, []);
            seen.get(norm).push(i);
        }
    });
    let cutIndex = -1;
    for (const occ of seen.values()) {
        if (occ.length >= 3 && occ[1] !== undefined) {
            const second = occ[1];
            if (cutIndex === -1 || second < cutIndex)
                cutIndex = second;
        }
    }
    if (cutIndex === -1)
        return text;
    // Rebuild from the first occurrence's start, keeping the first sentence of
    // the loop and everything before it, but dropping the repeats after it.
    const firstOccStart = sentences.slice(0, cutIndex).join('').length;
    return text.substring(0, firstOccStart).trim();
}
/**
 * True when `text` is just the user's own message mirrored back verbatim
 * ("moo" → "moo."). The 7B sometimes echoes instead of answering; the chat
 * route passes its userText so the cleaner can collapse that to '' and let
 * the caller fall back to a real reply.
 */
export function isEchoOfUser(text, userText) {
    const norm = (s) => s.trim().toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    const t = norm(text);
    const u = norm(userText);
    return t.length > 0 && t === u;
}
/**
 * Minimum length for the prior-turn-repeat strip to fire. Kept small (8): a
 * reply that STARTS with the previous assistant message verbatim is almost
 * always regurgitation — legit replies essentially never begin that way. Only
 * the LEADING case is stripped (the observed failure, live, twice:
 * A3.startswith(A2)); a mid-response copy is left intact on purpose — the
 * user asking "what did you just say?" legitimately quotes the prior reply,
 * and deleting a mid-response copy would mangle that answer.
 */
const MIN_PRIOR_REPEAT_CHARS = 8;
/**
 * Strip a leading verbatim re-emission of the PREVIOUS assistant reply.
 *
 * The tuned 7B, when its own prior reply sits in the conversation context,
 * frequently re-emits it verbatim at the START of the next response before
 * generating new content. Live example: reply N+1 = <reply N, byte-for-byte>
 * + "Your momma was such a broken toaster…" (and in the user's transcript,
 * reply N+1 WAS reply N, byte-for-byte). Pass the prior assistant text and
 * this removes the leading copy, keeping everything after it.
 */
export function stripPriorAssistantRepeat(text, prior) {
    if (!prior)
        return text;
    const p = prior.trim();
    if (p.length < MIN_PRIOR_REPEAT_CHARS)
        return text;
    const lead = text.trimStart();
    if (lead.startsWith(p)) {
        return lead.slice(p.length).trimStart().trim();
    }
    return text;
}
/**
 * Cut at the first system-prompt leak. The tuned model sometimes regurgitates
 * the ENTIRE identity/personality block into a chat reply ("Your name is
 * Veronica. You are Veronica, the assistant of the VACA platform… [CURRENT
 * PROJECT]… [RECENT CONVERSATION]…"). These markers never legitimately appear
 * inside an answer, so everything from the first one onward is dropped.
 */
const SYSPROMPT_LEAK_MARKERS = [
    /Your name is Veronica\./i,
    /You are NOT Claude/i,
    /NARRATION BAN/i,
    /\[CURRENT PROJECT\]/,
    /\[PERSISTENT MEMORY/i,
    /\[RECENT CONVERSATION/,
    /\[CONTINUATION —/,
    /\[Emotion:/,
    /Follow these personality settings precisely/i,
    // Role-swapped identity regurgitation: the model sometimes re-emits the
    // identity rule with the "You are" aimed at the USER ("I'm Veronica, the
    // assistant of the VACA platform. You are Veronica, the assistant of the
    // VACA platform."). It never legitimately tells the user they are the
    // assistant, so everything from "You are Veronica" onward is dropped — the
    // "I'm Veronica" prefix (a legitimate answer to a name question) survives.
    /You are Veronica, the assistant/i,
    /You are the assistant of the VACA platform/i,
];
export function cleanLLMResponse(text, opts) {
    // ── TRUNCATE repeated-sentence loops (degeneration) before anything else ──
    text = truncateRepeatedSentences(text);
    // ── CUT at any system-prompt leak (identity block, memory block, continuity
    //    block, personality JSON…) — keep everything BEFORE the leak. ──
    for (const marker of SYSPROMPT_LEAK_MARKERS) {
        const m = text.search(marker);
        if (m !== -1) {
            text = text.substring(0, m).trim();
            break;
        }
    }
    // ── STRIP "[REASONING: ...]" meta blocks — the tuned 7B appends a reasoning
    //    summary to ordinary chat replies; it's training-artifact narration, not
    //    content. Removes closed blocks anywhere and any unclosed trailing one. ──
    text = text.replace(/\s*\[REASONING:\s*[\s\S]*?\]\s*/g, ' ').replace(/\s*\[REASONING:\s*[\s\S]*$/, '').trim();
    // ── TRUNCATE at first "User:" or "User (" continuation (model started
    //    generating the next user turn) — keeps everything BEFORE it. This is
    //    the most important fix: prevents the model from simulating entire
    //    conversations. (The old regex matched from the line start and could
    //    nuke the whole answer to '' for single-line responses — search for the
    //    continuation directly instead.) ──
    const userTurnIdx = text.search(/\n\n\s*User(?:\s|\(|:)/);
    if (userTurnIdx !== -1) {
        text = text.substring(0, userTurnIdx).trim();
    }
    // Also truncate at "\nUser:" (inline, no blank line before it)
    const inlineUserMatch = text.match(/\n\s*User\s*:.*$/m);
    if (inlineUserMatch && inlineUserMatch.index !== undefined) {
        text = text.substring(0, inlineUserMatch.index).trim();
    }
    // ── Truncate at "Bot:" or "Assistant:" if they appear AFTER the first line ──
    // Keep first Bot: prefix (strip it below) but truncate at subsequent ones
    const lines = text.split('\n');
    if (lines.length > 1) {
        const truncatedLines = [lines[0]];
        let foundSecondBot = false;
        for (let i = 1; i < lines.length; i++) {
            const line = lines[i];
            // If we see "Bot:" or "Assistant:" or "User:" on a subsequent line, stop
            if (/^\s*(Bot|Assistant|User)\s*:/.test(line)) {
                foundSecondBot = true;
                break;
            }
            truncatedLines.push(line);
        }
        text = truncatedLines.join('\n');
    }
    // ── Strip "Bot:" prefix from the beginning of the response ──
    text = text.replace(/^Bot\s*:\s*/i, '');
    // ── Strip "Assistant:" prefix from the beginning of the response ──
    text = text.replace(/^Assistant\s*:\s*/i, '');
    // ── Strip a leading "Jarvis," / "Jarvis:" address (persona leak from
    //    training data — the app has no Jarvis connection). Leading whitespace
    //    tolerated since the final trim runs after this. ──
    text = text.replace(/^\s*Jarvis\s*[,:!]\s*/i, '');
    // ── Detect and strip training-data regurgitation lines (soft, no full replacement) ──
    // Strip lines that look like rogue date mentions or memorized cultural trivia.
    // These are hallucinated patterns, but we only strip the line — not the whole response.
    const memorizedLinePatterns = [
        /Day of the Dead/i,
        /Día de (los )?Muertos/i,
        // "I'm here to help you with your jokes too!" — canned self-narration the
        // NARRATION BAN forbids; the model recites it instead of answering.
        // Narrowed to the "with your …" variant so a legit helpful line like
        // "I'm here to help you debug this" is never deleted.
        /I['’]?m here to help you with your\b/i,
        // NOTE: "The current date is" is intentionally NOT stripped — the clock
        // context (clockContext.ts) makes date answers authoritative now, and
        // stripping them would delete correct answers to "what's the date?".
    ];
    for (const pattern of memorizedLinePatterns) {
        text = text.replace(new RegExp(`^.*${pattern.source}.*$`, 'gm'), '');
    }
    // ── Strip an AEON-style "thinking-trace" prefix up to its lone `response`
    //    delimiter. The AEON merge is trained to emit a chain-of-thought
    //    narration ("We need to…", "Need to…") followed by a standalone
    //    `response` line, then the REAL answer. Keep only the content after that
    //    delimiter — the narration is training-artifact thinking, never content.
    //    The delimiter is matched as a line containing ONLY the word "response"
    //    so mid-prose uses are never touched, and the rewrite only happens when
    //    real content follows the marker. ──
    const aeonResponseMark = text.search(/^\s*response\s*$/im);
    if (aeonResponseMark !== -1) {
        const afterDelimiter = text.slice(aeonResponseMark).replace(/^\s*response\s*$/im, '').trim();
        if (afterDelimiter)
            text = afterDelimiter;
    }
    // ── Strip DeepSeek R1 <think> reasoning blocks ──
    text = text.replace(/<think>[\s\S]*?<\/think>\s*/g, '').trim();
    // ── Strip generic tool-announcement meta lines the model recites from
    //    agent-training data: "I will use the architect tool to...". Narrowed
    //    to the specific tool names the model recites (architect/write/shell,
    //    or any backtick-quoted tool name) so real prose like "I will use the
    //    terminal tool to deploy" is never deleted. ──
    text = text.replace(/^.*\bI (?:will|am going to|shall)\s+(?:now\s+)?(?:use|invoke|call|proceed with).*(?:`[^`]+`|architect|write|shell)\s+tool\b.*$/gim, '');
    // "I will now proceed with/to step..." meta-framing only — NOT natural prose
    // like "I will now begin by running the tests first."
    text = text.replace(/^.*\bI (?:will|am going to|shall)\s+now\s+proceed\s+(?:with|to|step).*$/gim, '');
    // ── Strip lines with 🔧 tool_name → (or → with no 🔧) ──
    text = text.replace(/^.*🔧\s*\w+(?:\s*[→\-]\s*.*)?$/gm, '');
    // ── Strip lines containing "Unknown tool" (standalone hallucination) ──
    text = text.replace(/^.*\bUnknown tool\b.*$/gm, '');
    // ── Strip "**Analysis:**" or "**Step N:**" meta headers + content ──
    text = text.replace(/\*\*(?:Analysis|Step\s+\d+)\s*\*\*[^]*?(?=\n(?!\s*[-*]\s)|$)/g, '');
    // ── Strip "---" separator lines ──
    text = text.replace(/^---+$/gm, '');
    // ── Strip numbered meta-steps ──
    text = text.replace(/^\d+\.\s*(?:The result shows|The analysis|The output|The response|As we can see|Let me|I will|I would|I need to|First,|Second,|Third,|Finally,).*$/gim, '');
    // ── Strip a leading typing-indicator echo — the tuned model sometimes
    //    answers banter with "I see you're typing \"<user message>\"". Instead of
    //    replying. The rest of the reply (if any) is kept. Also drops the common
    //    meta-narration leftover that follows it ("You're being playful. I'll
    //    play along.") so the caller sees a true empty instead of dead narration. ──
    text = text.replace(/^(?:I see you're typing|You're typing)\b[^.\n]*[.]?\s*(?:(?:You're|they're) being playful[^.]*[.]?\s*)?(?:(?:I'll|I will) play along[^.]*[.]?\s*)?/i, '');
    // ── Strip a verbatim re-emission of the PREVIOUS assistant reply (the
    //    tuned 7B copies its own prior turn into the next response). ──
    text = stripPriorAssistantRepeat(text, opts?.priorAssistantText);
    // ── Static-file degeneration guard: the tuned model sometimes claims
    //    "I'm just a static file, I can't read your input" — always FALSE (the
    //    app responds fine) and banned narration. A SHORT reply built on the
    //    claim is degenerate → '' so the caller falls back to a real reply. A
    //    longer answer (e.g. explaining what a static file is) passes through. ──
    const STATIC_FILE_CLAIMS = /i['’]?m (?:not |just |actually )?(?:a )?static file|can'?t (?:read|process|see) your (?:input|message)|(?:have|got) no real[- ]time (?:input|connection)|not able to (?:read|respond to) your/i;
    if (text.length < 400 && STATIC_FILE_CLAIMS.test(text)) {
        return '';
    }
    // ── Clean up whitespace artifacts from removals ──
    text = text
        .replace(/^\s+/, '') // Leading whitespace
        .replace(/\n{3,}/g, '\n\n') // 3+ blank lines → 2
        .trim();
    // ── Verbatim echo guard: with the user's message known (chat path), a reply
    //    that just mirrors the user's own words back is degenerate — return ''
    //    so the caller can fall back to a real reply instead of showing a parrot. ──
    if (opts?.userText && isEchoOfUser(text, opts.userText))
        return '';
    return text;
}
