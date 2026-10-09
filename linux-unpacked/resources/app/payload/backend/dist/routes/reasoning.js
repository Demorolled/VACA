import { Router } from 'express';
import OpenAI from 'openai';
import { AITranslator } from '../ai/translator.js';
import { getVisionConfig } from '../ai/vision.js';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { cleanLLMResponse } from '../utils/responseCleaner.js';
import { buildClockContext } from '../utils/clockContext.js';
import { isAboutVacaRequest } from './voice-action.js';
import { sessionMemory } from '../database/sessionMemory.js';
import { detectMemoryWriteRequest, buildContentFromPrompt, buildContentFromMessages, deriveTopic, } from '../utils/memoryWriteDetector.js';
import { appendWikiSection } from '../utils/wikiWriter.js';
import { detectDesktopOpenRequest } from '../utils/desktopOpenDetector.js';
import { openApplication, openUrl, OPENABLE_APPS } from '../services/desktopActions.js';
import { detectFileWriteRequest, buildFileContentFromPrompt, buildFileContentFromMessages, } from '../utils/fileWriteDetector.js';
import { writeChatFile, CHAT_FILES_DIR } from '../utils/chatFileWriter.js';
import { detectChatToolRequest } from '../utils/chatToolDetector.js';
import { runChatTool } from '../utils/chatToolRunner.js';
import { detectUnsupportedRequest } from '../utils/capabilityBoundaryDetector.js';
import { recordChatTurn } from '../monitor/conversationTap.js';
import { analyzeEmotion, getEmotionPromptModifier, buildTurnContinuityContext, buildTurnRecap, updateMood, getMoodModifier, getMoodState, detectPlayful, isConfidentNegative, isSeriousNegative, NEGATIVE_EMOTIONS } from '../ai/emotionEngine.js';
import { getSoulSassiness } from '../services/soulService.js';
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
/**
 * Strip an AEON-style reasoning trace the stationed 27B AEON merge emits ahead
 * of its REAL answer: meta-narration ("We need to...", etc.) then a lone
 * `response` line and the answer. Keep only the text after that delimiter.
 * Applied on the hot chat path; idempotent.
 */
export function stripAeonTrace(text) {
    if (typeof text !== 'string' || !text)
        return text;
    // Plain string scan (no regex). The AEON merge emits meta-narration in a
    // <think>-style block closed by a lone  line (sometimes printed as
    // a `response` marker) before the real answer. Keep everything after the
    // first closing delimiter line. String ops only, so it is immune to any
    // source/transpile regex quirks.
    const lines = text.split('\n');
    for (let i = 0; i < lines.length; i++) {
        const t = lines[i].trim().toLowerCase();
        // A BLANK LINE IS NOT A DELIMITER. It used to be (`t === ''`), which
        // silently decapitated every code answer that contained a blank line: the
        // chat path returned only the text AFTER the first blank line. Observed
        // live 2026-10-02 — a fibonacci function came back from /api/reason/chat
        // as just `return b;\n}`. Only explicit marker lines count now.
        if (t === 'response' || t === 'final:' || t === 'final') {
            const after = lines.slice(i + 1).join('\n').trim();
            if (after)
                return after;
        }
    }
    // No delimiter: drop pure-narration lines (meta-commentary the model recites
    // before answering) so only real content remains.
    const NARR_PREFIX = /^(we |user .*asks|need (to )?(answer|respond|be|produce|ensure|keep|use|maybe|ask)|the user (asks|said|wants)|user asks|i need|starting|let me (think|reason))/i;
    const kept = lines.filter((ln) => {
        const t = ln.trim().toLowerCase();
        if (!t)
            return true; // keep blank lines (paragraph spacing)
        return !NARR_PREFIX.test(ln.trim());
    }).join('\n').trim();
    // If narration was dropped and nothing real remains, return '' so the
    // caller's empty-guard fallback (short ack / sassy reply) kicks in rather
    // than echoing a meta-commentary-only "answer" back at the user.
    if (!kept && lines.some((ln) => /^(we |user .*asks|need (to )?(answer|respond|be|produce|ensure|keep|use|maybe|ask)|the user (asks|said|wants)|user asks|i need|starting|let me (think|reason))/i.test(ln.trim()))) {
        return '';
    }
    return kept || text;
}
class LRUCache {
    max;
    map = new Map();
    constructor(max) {
        this.max = max;
    }
    get(key) {
        const val = this.map.get(key);
        if (val !== undefined) {
            this.map.delete(key);
            this.map.set(key, val);
        }
        return val;
    }
    set(key, val) {
        if (this.map.has(key))
            this.map.delete(key);
        else if (this.map.size >= this.max) {
            const first = this.map.keys().next().value;
            if (first !== undefined)
                this.map.delete(first);
        }
        this.map.set(key, val);
    }
}
export const reasoningRoutes = Router();
const translator = new AITranslator();
const cache = new LRUCache(50);
// ─── Helper: detect if a prompt is a short greeting (should get a brief response) ──
const GREETING_PATTERNS = [
    /^\s*(hi|hey|hello|sup|yo|hey\s+there|hello\s+there|hiya|howdy|hi\s+there)\s*[.!]*\s*$/i, /^\s*(good\s+mornin'?g?|good\s+afternoon|good\s+evening|gm|gn|goodnight?)\s*[.!]*\s*$/i,
    /^\s*(what'?s\s+up|wassup|whassup|whats\s+up|sup\s+bro|sup\s+momma)\s*[.!]*\s*$/i,
    /^\s*(how\s+(?:are\s+you|r\s+u|ya\s+doin|is\s+it\s+going))\s*[.?]*\s*$/i,
    /^\s*[.!?]+\s*$/, // Just punctuation like "!" or "?"
    /^\s*$/, // Empty or whitespace only
];
/** Extract the actual user message from a prompt that may contain conversation history */
function extractUserMessage(text) {
    const lines = text.trim().split('\n');
    let lastLine = lines[lines.length - 1]?.trim() || '';
    // Strip User:/Assistant: prefixes from the last line
    lastLine = lastLine.replace(/^(?:User|Assistant|Human|AI)\s*:\s*/i, '').trim();
    return lastLine;
}
/**
 * Blueprint-JSON hijack guard.
 *
 * The tuned 7B model is trained almost entirely on blueprint JSON, so it
 * sometimes answers ORDINARY chat (debug questions, knowledge lookups, tool
 * summaries) with a JSON object that carries an "app_type" field. This is
 * wrong for non-blueprint requests. When the user did NOT ask for a blueprint /
 * app spec and the response looks like blueprint JSON, we regenerate it in
 * plain conversational text. Blueprint requests (the fidelity harness included)
 * all contain app-intent words and are deliberately left untouched.
 */
// JSON shapes the tuned model emits for NON-blueprint chat: an app blueprint
// (app_type), a wrapped tool-summary ({search_results:[...]}), or a structured
// action object ({app, action: "file-create", filename, description}). All get
// rewritten to conversational prose by undoBlueprintHijack().
const BLUEPRINT_JSON_RE = /"(?:app_type|search_results|action|filename|file-create)"\s*:/;
// Verb-based intent: the user must actually ASK to build/generate/create an
// app, tool, or blueprint (or explicitly want JSON with the contract keys).
// Mere MENTION of the word "blueprint" ("what does the knowledge base say
// about blueprint fidelity?") does NOT count — those must stay conversational.
const BLUEPRINT_INTENT_PATTERNS = [
    /\b(?:generate|build|create|design|make|code|write|produce|give\s+me|return|output)\s+(?:a|an|the|me)?\s*(?:json|blueprint|app|tool|program|application|spec|app\s+for|blueprint\s+for)/i,
    // Deliberately capped filler: "I want a chess app" / "I need a tool" count,
    // but "I need HELP with an app that crashes" must NOT (that's chat, not a
    // blueprint request — the guard should stay active for it).
    /\bi\s+(?:want|need|would\s+like)\s+(?:a|an|the)?\s*(?:[a-z]+\s+){0,1}(?:app|tool|program|application|blueprint)\b/i,
    /\b(?:app_type|architecture_checklist|target_stack|wiring_graph)\b/i,
];
/** Did the user explicitly ask for a blueprint / app spec / JSON? */
function isBlueprintRequest(text) {
    const t = (text || '').slice(0, 300);
    return BLUEPRINT_INTENT_PATTERNS.some((re) => re.test(t));
}
/** Does the response look like a blueprint JSON object (fenced or raw)? */
function looksLikeBlueprintJson(text) {
    const t = (text || '')
        .trim()
        .replace(/^```(?:json)?\s*/i, '')
        .replace(/```\s*$/i, '')
        .trim();
    return t.startsWith('{') && BLUEPRINT_JSON_RE.test(t.slice(0, 400));
}
/** Strip optional markdown fences around a JSON payload. */
function stripJsonFences(text) {
    return (text || '')
        .trim()
        .replace(/^```(?:json)?\s*/i, '')
        .replace(/```\s*$/i, '')
        .trim();
}
/** Does the text parse as a complete JSON document? */
function parsesAsJson(text) {
    try {
        JSON.parse(stripJsonFences(text));
        return true;
    }
    catch {
        return false;
    }
}
// ── Native-platform steering ─────────────────────────────────────────────
// "stand alone not a web browser based build" must NOT get a React/Express
// web stack. When the request carries a native/standalone/offline hint, inject
// a PLATFORM CONSTRAINT into the system prompt so the model plans a native
// desktop app (Python pygame/Tkinter, Go, ...) instead of a web app.
const NATIVE_PLATFORM_HINTS = /stand\s*alone|standalone|not\s+a?\s*web\s+(?:app|based|build)|not\s+web|no\s+browser|without\s+a?\s*browser|native\s+(?:desktop|app|game)|desktop\s+(?:app|game|application|build)|offline\s+(?:app|game)|local\s+(?:app|game)|doesn'?t\s+need\s+a\s+browser|not\s+in\s+the\s+browser/i;
const NATIVE_PLATFORM_RULE = 'PLATFORM CONSTRAINT: the user wants a STANDALONE NATIVE application that runs directly on the computer — NOT a web app inside a browser. ' +
    'Choose a native stack (Python with pygame or Tkinter, Go, Rust, or Electron). ' +
    'Do NOT plan a web stack (React + Node/Express + browser UI) for this request — if you emit a stack, it must be native and run without a browser.';
/** Short override prepended DIRECTLY to the user message (max salience). */
const NATIVE_PLATFORM_SHORT = 'PLATFORM: the user wants a STANDALONE NATIVE app that runs WITHOUT a browser — ' +
    'use Python (pygame/Tkinter), Go, Rust, or Electron. Never a web stack.';
/** System-prompt block enforcing the native constraint, or '' when not hinted. */
export function buildPlatformConstraint(text) {
    return NATIVE_PLATFORM_HINTS.test(text || '') ? NATIVE_PLATFORM_RULE : '';
}
/** True when a native-platform constraint is active for this request. */
export function hasPlatformConstraint(text) {
    return NATIVE_PLATFORM_HINTS.test(text || '');
}
/** Honest note appended when a web stack leaks through despite the constraint. */
const NATIVE_LEAK_NOTE = "\n\n(Heads-up: I drafted that as a web stack by habit — but you asked for a standalone native app, " +
    'so I\'ll build it with a native stack like Python + pygame/Tkinter instead.)';
/**
 * System-prompt rule used to force a plain-text rewrite of a hijacked answer.
 * Deliberately SHORT, standalone, and free of blueprint vocabulary: the tuned
 * model is so blueprint-biased that naming the forbidden fields (app_type,
 * target_stack, ...) actually PRIMES it to emit them. A neutral "casual
 * conversation" framing works far better.
 */
const PLAIN_TEXT_RETRY_RULE = 'This is a casual conversation. You are a helpful engineer talking to a colleague. ' +
    'Answer their question in natural, plain sentences. Do not output any data structures, ' +
    'machine-readable formats, bracket notation, or structured fields — just normal chat.';
/**
 * Deterministic fallback: convert a hijacked blueprint JSON object into readable
 * conversational prose. Never fails, so a non-blueprint request can never be
 * answered with raw app_type JSON even if the model ignores every retry prompt.
 */
export function humanizeBlueprintJson(text) {
    const t = stripJsonFences(text);
    let data;
    try {
        data = JSON.parse(t);
    }
    catch {
        // Truncated JSON (cut at max_tokens mid-string). NEVER leak the raw
        // fragment to the user — extract the partial fields we can and offer to
        // continue. (The truncation-completion retry in undoBlueprintHijack runs
        // before this, so this path is the last-resort graceful fallback.)
        // Plain non-JSON prose (no leading brace) passes through untouched.
        if (!t.startsWith('{'))
            return text;
        return humanizePartialBlueprintJson(t);
    }
    if (!data || typeof data !== 'object')
        return text;
    // Render non-string values readably (avoids "[object Object]").
    const fmt = (v) => typeof v === 'string' ? v : JSON.stringify(v);
    const lines = [];
    const appType = typeof data.app_type === 'string' ? String(data.app_type).replace(/_/g, ' ') : null;
    if (typeof data.description === 'string' && data.description.trim()) {
        lines.push(data.description.trim());
    }
    else if (appType) {
        lines.push(`Here's a starting point for a ${appType} app.`);
    }
    if (Array.isArray(data.search_results) && data.search_results.length > 0) {
        lines.push('', 'Here\'s what the search found:');
        for (const item of data.search_results.slice(0, 10)) {
            const file = (item && (item.file_path || item.path)) || '';
            const content = (item && (item.content || item.match)) || '';
            lines.push(`• ${file}${content ? `: ${fmt(item === null ? null : (item.content || item.match || item))}` : ''}`);
        }
    }
    if (Array.isArray(data.architecture_checklist) && data.architecture_checklist.length > 0) {
        lines.push('', 'Suggested structure:');
        for (const item of data.architecture_checklist.slice(0, 10)) {
            lines.push(`• ${fmt(item)}`);
        }
    }
    if (data.target_stack && typeof data.target_stack === 'object') {
        const stack = Object.entries(data.target_stack)
            .filter(([, v]) => typeof v === 'string' && v.trim())
            .map(([k, v]) => `${k}: ${v}`)
            .join(', ');
        if (stack)
            lines.push('', `Stack: ${stack}`);
    }
    // Structured action objects (file-create etc.) — render as plain prose.
    if (typeof data.action === 'string') {
        const fileName = typeof data.filename === 'string' ? data.filename : '';
        const actionLabel = data.action === 'file-create' ? (fileName ? `Created "${fileName}".` : 'File created.') :
            data.action === 'file-write' ? (fileName ? `Updated "${fileName}".` : 'File updated.') :
                `${data.action.replace(/_/g, ' ')}.`;
        lines.push(actionLabel);
        if (typeof data.description === 'string' && data.description.trim() && !lines.includes(data.description.trim())) {
            lines.push(data.description.trim());
        }
    }
    if (lines.length === 0 && appType) {
        lines.push(`Here's a starting point for a ${appType} app.`);
    }
    // Never silently drop content: surface any remaining scalar fields so the
    // user's actual answer (notes, wiring, etc.) isn't lost to a generic intro.
    const emittedKeys = new Set(['app_type', 'description', 'search_results', 'architecture_checklist', 'target_stack', 'keywords', 'action', 'filename', 'app']);
    for (const [k, v] of Object.entries(data)) {
        if (emittedKeys.has(k))
            continue;
        if (typeof v === 'string' && v.trim())
            lines.push(`• ${k}: ${v.trim().slice(0, 200)}`);
        else if (typeof v === 'number' || typeof v === 'boolean')
            lines.push(`• ${k}: ${String(v)}`);
    }
    return lines.join('\n');
}
/**
 * Graceful fallback for a blueprint JSON that was CUT OFF before completing
 * (JSON.parse failed). Extracts whatever partial fields are present via regex
 * and renders them as readable prose — the deterministic guarantee that a
 * truncated response can never surface as raw JSON in the chat bubble.
 */
function humanizePartialBlueprintJson(t) {
    const lines = [];
    const appType = /"app_type"\s*:\s*"([^"]+)"/.exec(t);
    const desc = /"description"\s*:\s*"([^"]*)"/.exec(t);
    if (desc && desc[1].trim())
        lines.push(desc[1].trim());
    else if (appType)
        lines.push(`Here's a starting point for a ${appType[1].replace(/_/g, ' ')} app.`);
    // The closing bracket may not exist yet when the JSON was cut mid-object —
    // tolerate that (truncated "architecture_checklist": ["a","b" and
    // "target_stack": {"frontend":"React" both lack their final bracket).
    const list = /"architecture_checklist"\s*:\s*\[([^\]]*)/.exec(t);
    if (list) {
        const items = [...list[1].matchAll(/"([^"]+)"/g)].map(m => m[1]).filter(s => s.trim().length > 1);
        if (items.length) {
            lines.push('', 'Suggested structure (partial):');
            for (const item of items.slice(0, 10))
                lines.push(`• ${item}`);
        }
    }
    const stack = /"target_stack"\s*:\s*\{([^}]*)/.exec(t);
    if (stack) {
        const parts = [...stack[1].matchAll(/"([^"]+)"\s*:\s*"([^"]*)"/g)].map(m => `${m[1]}: ${m[2]}`);
        if (parts.length)
            lines.push('', `Stack (partial): ${parts.join(', ')}`);
    }
    if (!lines.length) {
        return 'I was drawing up a plan for that and the response got cut off mid-way — say "continue" and I\'ll finish it.';
    }
    lines.push('', '(The plan was cut off — ask me to continue and I\'ll finish it.)');
    return lines.join('\n');
}
/**
 * System prompt for the JSON-completion retry: ask for the COMPLETE document
 * (not a fragment) so the result is independently parseable — more robust
 * than concatenating a continuation when the 7B ignores "start where it cut
 * off" and re-emits the whole object.
 */
const COMPLETE_JSON_RULE = 'A previous response was a JSON object that got cut off before it finished. ' +
    'Return the COMPLETE JSON document now — the ENTIRE object, exactly as it should have been, with every field closed. ' +
    'It must parse as valid JSON. No commentary, no markdown fences, no explanation.';
/**
 * If a non-blueprint request was answered with blueprint JSON, retry with a
 * MINIMAL system prompt (never the full soul/VACA block) so the model answers
 * in prose. REAL tool output (if any) is retained so tool summaries stay
 * factual. Keeps the original response when the retry also fails.
 *
 * `completeJsonCall` (optional): when the reply is a TRUNCATED blueprint JSON
 * (JSON-shaped but won't parse — the "Vaca is still a little broken" cut-off),
 * first ask the model to re-emit the complete JSON, then humanize it. This
 * turns a mid-string cut into a full friendly plan instead of leaking the raw
 * fragment.
 */
async function undoBlueprintHijack(userText, cleaned, realToolContext, retryCall, completeJsonCall) {
    // Only act when the user did NOT ask for a blueprint AND the reply is JSON.
    if (isBlueprintRequest(userText) || !looksLikeBlueprintJson(cleaned))
        return cleaned;
    // Truncation repair: JSON-shaped but unparseable → complete it first.
    if (!parsesAsJson(cleaned) && completeJsonCall) {
        try {
            const tail = cleanLLMResponse(await completeJsonCall());
            if (tail && parsesAsJson(tail)) {
                cleaned = tail;
            }
            else if (tail) {
                const combined = `${stripJsonFences(cleaned)}${stripJsonFences(tail)}`;
                if (parsesAsJson(combined))
                    cleaned = combined;
            }
        }
        catch (err) {
            console.warn('[reasoning] JSON-completion retry failed:', err);
        }
    }
    try {
        const parts = [];
        if (realToolContext) {
            parts.push(`${realToolContext}\n\nAnswer based ONLY on that real tool output above, in plain conversational prose — no structured data.`);
        }
        parts.push(PLAIN_TEXT_RETRY_RULE);
        const retryRaw = await retryCall(parts.join('\n\n'));
        const retry = cleanLLMResponse(retryRaw);
        if (retry && !looksLikeBlueprintJson(retry))
            return retry;
    }
    catch (err) {
        console.warn('[reasoning] plain-text retry failed:', err);
    }
    // Deterministic guarantee: humanize the JSON so the user never sees raw
    // app_type JSON for a conversational request.
    return humanizeBlueprintJson(cleaned);
}
function isGreeting(text) {
    const userMsg = extractUserMessage(text);
    if (userMsg.length <= 30 && GREETING_PATTERNS.some(p => p.test(userMsg))) {
        return true;
    }
    // Fallback: check the full text (for plain prompts without history)
    const trimmed = text.trim();
    if (trimmed.length > 30)
        return false;
    return GREETING_PATTERNS.some(p => p.test(trimmed));
}
/** Detect any very short user message that should get a brief response */
function isShortQuery(text) {
    const userMsg = extractUserMessage(text);
    // Build imperatives ("build it", "make it", "go ahead") are NOT short
    // queries — they're confirmations to proceed with a build and need a real
    // (possibly blueprint-JSON) response, not a 1-sentence guard reply.
    if (/\b(?:build|make|create|write|generate|do|start|go ahead|continue|finish|launch)\s*(?:it|this|that|them|the app|the game|the tool)?\s*[.!]*$/i.test(userMsg)) {
        return false;
    }
    // Message is short if the actual user message is < 20 chars
    if (userMsg.length > 0 && userMsg.length < 20)
        return true;
    // Fallback: for plain prompts without history
    const trimmed = text.trim();
    return trimmed.length > 0 && trimmed.length < 20;
}
// ── Continuity gate ────────────────────────────────────────────────────────
// The P3/P3b recap must only fire when the current message is a genuine
// FOLLOW-UP on the previous turn. An unconditional recap made the tuned 7B
// open EVERY reply with the same formulaic "That's a lot on top of the … you
// mentioned." tie-back (observed live in chat) — the canned-phrase behavior
// the recap was designed to avoid. Fresh questions, banter, and new topics
// never get it; the model still has the full history in the messages array.
const CONTINUATION_FOLLOWUP_RE = /^(and|but|then|also|now|anyway|anyhow|update)\b|(\band\s+now\b|\bnow\s+it\b|\bnow\s+that\b|\bupdate:?\b|\beven\s+worse\b|\bso\s+much\s+worse\b|\bit\s+got\s+(?:worse|better|harder|easier|hard)\b|\bthings?\s+(?:just\s+)?got\b|\bon\s+top\s+of\s+that\b|\bturns?\s+out\b|\bspeaking\s+of\b|\bthat\s+reminds\s+me\b|\bfollow[- ]?up\b|\bas\s+(?:promised|planned|agreed|mentioned)\b)/i;
/** True when the current user message reads as a follow-up on an earlier turn. */
export function isContinuationFollowUp(text) {
    return CONTINUATION_FOLLOWUP_RE.test((text || '').trim());
}
/**
 * True when BOTH the previous user turn and the current message are
 * confidently negative — an ongoing emotional situation worth tying back to
 * even without explicit "and now…" markers (e.g. "my laptop died" following
 * "I'm really stressed").
 */
function isEmotionalContinuation(messages, current) {
    // Banter never counts: a roast-back exchange that happens to contain
    // lexicon-negative words must not re-inject the recap mid-joke (same rule
    // buildEmotionModifier uses to suppress empathy for jokes).
    if (detectPlayful(current) && !isSeriousNegative(current))
        return false;
    const negative = (t) => {
        const e = analyzeEmotion(t);
        return e.valence < -0.2 || NEGATIVE_EMOTIONS.includes(e.dominant);
    };
    const recap = buildTurnRecap(messages);
    return Boolean(recap) && negative(current) && negative(recap);
}
/**
 * Detect questions about the current date/time ("what time is it?", "today's
 * date?"). These must ALWAYS get a real clock answer, so they are exempt from
 * the greeting/short-query guards (which cap tokens and forbid "generating
 * dates") and are never served from the response cache.
 */
function isDateTimeQuery(text) {
    const q = extractUserMessage(text).toLowerCase();
    if (q.length === 0 || q.length > 80)
        return false;
    return (/what('s| is)? (the )?(time|date|day|hour|year|month|weekday|today)/.test(q) ||
        /current (time|date|day|hour|year)/.test(q) ||
        /today('s| is)? (date|day|time)/.test(q) ||
        /(time|date|day|hour) is it/.test(q) ||
        /tell me (the )?(time|date|day)/.test(q) ||
        /what (day|time|date) is today/.test(q) ||
        // Bare whole-message queries: "time?", "date", "today?", "hour" — the
        // short-query guard says "Do NOT generate dates", so these must be caught.
        /^(time|date|today|day|hour)\s*[?.!]*$/i.test(q));
}
/**
 * ─── Response-variety helpers ───────────────────────────────────────────
 * Similar questions previously produced IDENTICAL answers because (a) normal
 * chat ran at the server-default sampling temperature (near-greedy) and (b)
 * every failing greeting was replaced by ONE hardcoded fallback string. Chat
 * now samples at an explicit temperature, greeting fallbacks vary per query,
 * and a variety instruction tells the model not to repeat prior answers.
 */
const CHAT_TEMPERATURE = 0.7;
const GREETING_FALLBACKS = [
    'Hi there! How can I help you today?',
    'Hello! What can I do for you?',
    'Hey! What are we building today?',
    'Hi! Ready to help — what do you need?',
    'Hello there! How can I assist?',
    'Hey there! What can I do for you?',
    'Hi, good to see you! What are we working on?',
    'Hello! What would you like to do?',
];
/** Stable per-query pick: the same greeting reuses a variant, different greetings differ. */
export function pickGreetingVariant(query) {
    return GREETING_FALLBACKS[stablePickIndex(query, GREETING_FALLBACKS.length)];
}
/** FNV-1a hash → stable index into a pool of length n (deterministic, cache-safe). */
function stablePickIndex(query, n) {
    let h = 2166136261;
    for (let i = 0; i < query.length; i++) {
        h ^= query.charCodeAt(i);
        h = Math.imul(h, 16777619);
    }
    return Math.abs(h) % n;
}
/**
 * ─── Banter fallbacks ────────────────────────────────────────────────────
 * The 7B sometimes answers a joke with a flat echo ("I see you're typing
 * \"…\"") or nothing at all after cleaning. A witty canned comeback beats a
 * dead echo — a joke must NEVER be answered with "I'm not sure how to respond
 * to that" (the generic empty-response template). Picked deterministically
 * per query so the same joke gets a stable retort (cache-safe).
 */
const SASSY_FALLBACKS = [
    "Touché. You had me there — okay, you win this round. 😏",
    "Nice try, but my microwave has better comebacks than that. 🔥",
    "Ooh, you're on fire today. Too bad the toast still burned. 😄",
    "Okay, I walked into that one. Well played — I'll allow it.",
    "Sharp. I'd clap, but I'm too busy being out-sassed.",
    "Ha! Alright, you got me. Respect where it's due. 🙌",
];
/** Deterministic witty comeback for a joke the model failed to answer. */
export function pickSassyFallback(query) {
    return SASSY_FALLBACKS[stablePickIndex(query, SASSY_FALLBACKS.length)];
}
/** Short neutral acks for non-playful short messages that collapsed to '' (pure echo). */
const SHORT_ACKS = ['Got it.', 'Heard you.', 'Mm-hmm.', 'Okay. 👍', 'Fair enough.', 'Sure thing.'];
export function pickShortAck(query) {
    return SHORT_ACKS[stablePickIndex(query, SHORT_ACKS.length)];
}
/** Deterministic jokes when the model fails to answer a joke request. */
const JOKE_FALLBACKS = [
    'Why did the developer go broke? Because they used up all their cache. 😄',
    'Why do programmers prefer dark mode? Because light attracts bugs. 😄',
    'I told my computer I needed a break… now it won\'t stop sending me vacation ads.',
    'Why was the JavaScript developer sad? Because they didn\'t know how to \"null\" their feelings.',
    'There are only 10 kinds of people: those who understand binary and those who don\'t.',
];
/** True when the user is asking for a joke (so a failed generation gets a real one). */
export function isJokeRequest(q) {
    return /\bjok|\bpun\b|\bknock knock|funny|make me laugh|tell me something funny/i.test(q || '');
}
export function pickJokeFallback(query) {
    return JOKE_FALLBACKS[stablePickIndex(query || 'joke', JOKE_FALLBACKS.length)];
}
// ── Role-confusion interceptor: the tuned model occasionally applies the
//    identity rule to the USER ("You are Veronica, the assistant…") and then
//    fumbles when corrected ("why did you say I'm the assistant" → the empty-
//    echo fallback). These messages are answered DIRECTLY here — the role
//    boundary is never left to the LLM. Deterministic per query (cache-safe). ──
const ROLE_CONFUSION_REPLIES = [
    "You're right — you're the user, and I'm the assistant. My apologies for the mix-up. What would you like to build?",
    "My mistake — you're the user here, and I'm Veronica, your assistant. How can I help?",
    "Got it — you're the user, I'm the assistant. Sorry about the confusion! What can I do for you?",
];
/** Detect a user correcting/confused about who-is-the-assistant. Returns the
 *  direct reply, or null when the message is a normal request. */
export function detectRoleConfusion(text) {
    const t = text.trim().toLowerCase().replace(/[\s!?.,]+/g, ' ').trim();
    const patterns = [
        /i'?m not (the )?(assistant|veronica|ai|bot|model)/i,
        /i am not (the )?(assistant|veronica|ai|bot|model)/i,
        /i am (the |your )?user/i,
        /i'?m (the |your )?user/i,
        /why did you (say|call|think) i'?m (the )?(assistant|veronica|ai)/i,
        /you (said|called) me (the )?(assistant|veronica|ai)/i,
        /you (are|were) (the )?(assistant|veronica)/i,
        /who is the (assistant|user|veronica)/i,
        /am i (the )?(assistant|veronica|ai)/i,
        /(is it|are you) (the )?(user|assistant)/i,
        /you are the user/i,
        /i'?m the (assistant|veronica|ai)/i,
    ];
    const hit = patterns.find((p) => p.test(t));
    if (!hit)
        return null;
    return ROLE_CONFUSION_REPLIES[stablePickIndex(t, ROLE_CONFUSION_REPLIES.length)];
}
// ── Denial/pushback interceptor: the user says the assistant claimed an
//    action it did NOT do ("no you didn't", "you didn't open it", "that's
//    wrong, nothing happened"). Previously these fell through to the LLM,
//    which often collapsed to the canned "I'm not sure how to respond to
//    that" empty-echo fallback. Answer directly: apologize, never repeat the
//    false claim, and point at the real button/action. Deterministic per
//    query (cache-safe). ──
const DENIAL_REPLIES = [
    "You're right — my mistake. Let me be straight: I can only describe the preview here; to actually see it, press 🖥 Show Preview (or ⚡ Build This Now to generate the real app). Nothing opens from this chat on its own unless the window popped up.",
    "Fair enough — I shouldn't have said that. The preview window only opens from the frontend button (🖥 Show Preview / ⚡ Build This Now), not from my reply. Give that a try and tell me if it works.",
    "My apologies — I overstated it. I can't open windows from this chat directly; that's a frontend button action. Hit 🖥 Show Preview or ⚡ Build This Now and I'll help you from there.",
];
/** Detect a user denying that an action happened ("no you didn't", "that's
 *  wrong", "nothing opened"). Returns the direct reply, or null. */
export function detectDenial(text) {
    const t = text.trim().toLowerCase().replace(/[\s!?.,]+/g, ' ').trim();
    const patterns = [
        /no you (didn'?t|did not|don'?t|do not|haven'?t|didnt)/i,
        /you (didn'?t|did not|don'?t|didnt)\s+(do |open |show |build |create |make )?/i,
        /that('s| is)? not (right|true|what i|what happened)/i,
        /that('s| is)? wrong/i,
        /nothing (opened|happened|showed|appeared)/i,
        /no window (opened|appeared|showed|popped)/i,
        /no preview (opened|appeared|showed|popped)/i,
        /(window|preview) (didn'?t|did not|never) (open|appear|show)/i,
        /(no|nope|nah)[\s,]+(nothing|no window|no preview)/i,
        /you('re| are) wrong/i,
        /i (don'?t|do not|didn'?t|did not) (see|see it|see anything|see any window)/i,
        /didn'?t (open|show|happen|work|appear)/i,
        /(it|nothing) (didn'?t|did not) work/i,
        /(no|nope)[\s,]+it (didn'?t|did not)/i,
        /(didn'?t|did not) actually/i,
    ];
    const hit = patterns.find((p) => p.test(t));
    if (!hit)
        return null;
    return DENIAL_REPLIES[stablePickIndex(t, DENIAL_REPLIES.length)];
}
/**
 * Quality-check a greeting response from the LLM.
 * If it's too short, starts with weird punctuation, or looks broken,
 * replace it with a query-specific varied greeting (never one canned string).
 */
export function ensureQualityGreeting(response, query) {
    const trimmed = response.trim();
    // Too short or just punctuation
    if (trimmed.length < 4 || /^[\s!?.,]+$/.test(trimmed)) {
        return pickGreetingVariant(query || response);
    }
    // AEON-style thinking-trace leak: the model ANSWERS with pure meta-narration
    // ("We need to respond to user 'hi' twice.", "The user said ...", "Need final
    // concise.") instead of an actual greeting. Scoped to greeting replies only,
    // so it never touches code generation or factual answers.
    if (/^\s*(we (?:need|are|must|should)\b|need (?:to |final\b|produce\b|respond\b|be |maybe |likely |not )|(?:the |u\b)?user (?:said|says|wants|asked)\b|the user\b)/i.test(trimmed)) {
        return pickGreetingVariant(query || response);
    }
    // Starts with a lowercase letter or punctuation (not a proper greeting)
    if (/^[a-z!?.,]/.test(trimmed) && !trimmed.startsWith('hi') && !trimmed.startsWith('hey') && !trimmed.startsWith('hello')) {
        return pickGreetingVariant(query || response);
    }
    // Ensure it ends with sentence-ending punctuation
    if (!/[.!?]\s*$/.test(trimmed)) {
        return trimmed + '.';
    }
    return trimmed;
}
/** Builds a don't-repeat-yourself instruction from prior assistant turns ('' when none). */
export function buildVarietyInstruction(messages) {
    const prior = messages
        .filter((m) => m.role === 'assistant' && m.content && m.content.trim().length > 0)
        .slice(-2);
    if (prior.length === 0)
        return '';
    const previous = prior.map((m) => m.content.trim().slice(0, 300)).join('\n\n---\n\n');
    return ('VARIETY RULE: The user may ask a question similar to one you answered earlier in this conversation. ' +
        'If so, give a GENUINELY DIFFERENT answer — a fresh angle, different examples, or more depth — ' +
        'never a repeat of your previous reply and never a generic template.\n\n' +
        `[YOUR PREVIOUS ANSWER(S) — do NOT repeat these]\n${previous}`);
}
/**
 * Quality-check any short response from the LLM for weird/truncated output.
 */
function ensureQualityResponse(response) {
    const trimmed = response.trim();
    // Replace responses that are just a single word or punctuation
    if (trimmed.length < 3 || /^[\s!?.,;:'"-]+$/.test(trimmed)) {
        return 'I\'m not sure how to respond to that. Can you tell me what you\'d like to build?';
    }
    return trimmed;
}
/**
 * Read a short intro from VACA_Speech.txt to use as a canned response
 * when the user asks about VACA, preventing LLM hallucination.
 */
function _getVacaIntro() {
    try {
        const homeDir = process.env.HOME || '/home/final-flash1';
        const speechPath = join(homeDir, 'Desktop', 'VACA_Speech.txt');
        const content = readFileSync(speechPath, 'utf-8');
        const introMatch = content.match(/SECTION 1: INTRODUCTION[\s\S]*?(?=SECTION 2:|$)/);
        if (introMatch) {
            let intro = introMatch[0]
                .replace(/[\u{2500}-\u{259F}]/gu, '')
                .replace(/^[=\-]{2,}\n?/gm, '')
                .replace(/\n{3,}/g, '\n\n')
                .trim();
            intro = intro.length > 1500 ? intro.slice(0, 1500) + '...' : intro;
            return intro;
        }
    }
    catch { }
    return 'I am Veronica, the assistant of the VACA platform. I am an AI-powered software development platform that builds complete applications from visual flowcharts. I learn from every project I generate.';
}
// ─── Desktop open — "open firefox" really launches it; no hallucinated typos ──
function prettyAppName(name) {
    const map = {
        firefox: 'Firefox', chrome: 'Chrome', chromium: 'Chromium',
        files: 'Files', nautilus: 'Files', 'file manager': 'Files',
        vscode: 'VS Code', 'vs code': 'VS Code', calculator: 'Calculator',
        settings: 'Settings', terminal: 'terminal', editor: 'editor', 'text editor': 'text editor',
    };
    return map[name] || name;
}
async function tryHandleDesktopOpen(text) {
    const req = detectDesktopOpenRequest(text);
    if (!req)
        return { handled: false };
    if (req.kind === 'url') {
        await openUrl(req.url);
        return { handled: true, response: `✅ Opened ${req.url} in your browser.` };
    }
    const opened = await openApplication(req.app);
    if (opened.success && opened.launched) {
        return { handled: true, response: `✅ Opened ${prettyAppName(opened.launched)} for you — done for real this time.` };
    }
    return {
        handled: true,
        response: `I couldn't find "${req.matched}" on your system. Apps I can open: ${OPENABLE_APPS.join(', ')}.`,
    };
}
// ─── Memory write — the platform really writes; the LLM never fakes a write ──
const MEMORY_WRITE_SYSTEM = "You are VACA's wiki formatter. The user asked to save something to the wiki. " +
    'Rewrite the given content as a clean, well-organized technical wiki section body: ' +
    'plain text, short paragraphs and bullet points, no markdown code fences, ' +
    'no fake file trees, no "I have written" claims. Return ONLY the section body.';
async function tryHandleMemoryWrite(instruction, content, target) {
    const topic = deriveTopic(content, 'Memory note');
    if (target === 'wiki') {
        // Ask the LLM to format a clean wiki section; fall back to raw content on failure.
        let body = content;
        try {
            const formatted = await translator.reason(content, MEMORY_WRITE_SYSTEM, { maxTokens: 800, timeoutMs: 45000 });
            if (formatted && formatted.trim().length >= 40)
                body = formatted.trim();
        }
        catch { /* keep raw content */ }
        const result = appendWikiSection(topic, body);
        return [
            `✅ Saved to my wiki — done for real this time.`,
            `• File: ${result.filePath}  |  Section ${result.sectionNumber}: "${topic}"`,
            `• The wiki (modelVeronice.txt) is one of my knowledge sources, so this is now part of my long-term knowledge base.`,
            ``,
            `Saved content preview:`,
            ...body.split('\n').slice(0, 6),
        ].join('\n');
    }
    const note = sessionMemory.recordNote(topic, content);
    const preview = content.length > 160 ? content.slice(0, 157) + '...' : content;
    return [
        `✅ Saved to my memory — done for real this time.`,
        `• File: data/session-memory.json  |  Note: "${note.topic}" (${sessionMemory.getNotes(100).length} total)`,
        `• It's now part of my persistent memory context, so I'll recall it in future sessions — no guessing.`,
        ``,
        `Saved:`,
        preview,
    ].join('\n');
}
// ── File write: "create a file called X" — actually create it (no hallucination) ──
function tryHandleFileWrite(fileName, content) {
    const result = writeChatFile(fileName, content);
    const preview = content.length > 300 ? content.slice(0, 297) + '...' : content;
    return [
        `✅ Created "${result.fileName}" — done for real this time.`,
        `• File: ${result.filePath}  (${result.bytes} bytes)`,
        `• It's saved inside ${CHAT_FILES_DIR} — you can open or edit it anytime.`,
        ``,
        `Created content:`,
        preview,
    ].join('\n');
}
// ── P2: emotion-aware chat ──
// The emotion engine existed but only on /api/emotion/* — it never ran in the
// main chat path, so "emotion-aware reasoning" never reached the model. Here we
// (a) analyze the user's message, (b) inject the tone modifier into the system
// prompt, and (c) record the reading into soul.json's emotional_state so the
// emotion tracker actually moves again.
/**
 * Analyze a chat message and return the emotion modifier to append to the
 * system prompt ('' when neutral / low confidence — no noise injected).
 */
function buildEmotionModifier(userText) {
    try {
        const emotion = analyzeEmotion(userText);
        // Persistent mood mirroring: elevated-positive messages (playful/joking →
        // playful back) arm a register that decays to baseline after the user
        // stops being elevated; negative emotions stay per-message empathy.
        const playful = detectPlayful(userText);
        updateMood(userText);
        const moodMod = getMoodModifier(getSoulSassiness());
        // Banter jokes MUST NOT get the empathy/sadness modifier: "your mom was a
        // broken toaster" analyzes as sadness and would reply "I'm sorry to hear
        // that". Playful signals suppress the per-message empathy — UNLESS the
        // message is genuinely negative ("my dog died lol" — humor-as-coping), in
        // which case empathy wins.
        const perMsgMod = playful && !isSeriousNegative(userText) && !isConfidentNegative(emotion)
            ? ''
            : getEmotionPromptModifier(emotion);
        return [moodMod, perMsgMod].filter(Boolean).join('\n');
    }
    catch {
        return '';
    }
}
/**
 * Record the emotion reading into data/soul.json emotional_state.history
 * (capped at 25 entries). Best-effort and throttled by content hash so the same
 * message isn't double-recorded on retries. Never throws.
 */
// Throttle: don't write soul.json on every chat message. Only record when the
// dominant emotion OR the persistent mood register CHANGED from the last
// recorded one, or when the last write was more than 10s ago — a long
// conversation shouldn't hammer the file, but mood transitions (playful ->
// baseline) must still be observable.
let _lastEmotionWrite = 0;
let _lastEmotionDominant = '';
let _lastEmotionMood = '';
function recordEmotionHistory(userText) {
    try {
        const emotion = analyzeEmotion(userText);
        const dominant = emotion.dominant || 'neutral';
        const mood = getMoodState().register;
        const now = Date.now();
        if (dominant === _lastEmotionDominant && mood === _lastEmotionMood && now - _lastEmotionWrite < 10_000)
            return;
        _lastEmotionDominant = dominant;
        _lastEmotionMood = mood;
        _lastEmotionWrite = now;
        const entry = {
            // Banter jokes are recorded as 'playful', not whatever emotion the
            // analyzer guessed (it reads "your mom was a broken toaster" as sadness).
            emotion: detectPlayful(userText) ? 'playful' : dominant,
            mood: getMoodState().register, // persistent mirror register (playful/joyful/baseline)
            timestamp: new Date().toISOString(),
            trigger: userText.slice(0, 160),
            vad: {
                arousal: Math.round((emotion.arousal ?? 0.5) * 1000) / 1000,
                dominance: Math.round((emotion.dominance ?? 0.5) * 1000) / 1000,
                valence: Math.round((emotion.valence ?? 0.0) * 1000) / 1000,
            },
        };
        const soulPath = join(__dirname, '..', '..', '..', 'data', 'soul.json');
        if (!existsSync(soulPath))
            return;
        const soul = JSON.parse(readFileSync(soulPath, 'utf-8'));
        const state = soul.emotional_state || (soul.emotional_state = {});
        const history = Array.isArray(state.history) ? state.history : (state.history = []);
        // Skip when the last recorded trigger matches (retry/duplicate guard).
        if (history.length && history[history.length - 1]?.trigger === entry.trigger)
            return;
        history.push(entry);
        if (history.length > 25)
            history.splice(0, history.length - 25);
        state.dominant_emotion = dominant;
        state.last_updated = new Date().toISOString();
        state.confidence = Math.round((emotion.confidence ?? 0) * 1000) / 1000;
        if (emotion.probabilities)
            state.probabilities = emotion.probabilities;
        state.vad = { valence: emotion.valence, arousal: emotion.arousal, dominance: emotion.dominance };
        writeFileSync(soulPath, JSON.stringify(soul, null, 2), 'utf-8');
    }
    catch {
        // Best-effort — a failed emotion recording must never break chat.
    }
}
// ── Real tools: the LLM only ever summarizes REAL tool output (never fakes) ──
const TOOL_ANSWER_RULE = 'The user asked for something that needs real data. Your context contains REAL tool output ' +
    'marked as [REAL FILE CONTENT], [REAL CODE SEARCH], [REAL WEB RESULTS], or [REAL KNOWLEDGE]. ' +
    'Base your answer ONLY on that real data — never invent file contents, search matches, web results, or knowledge. ' +
    'If the tool found nothing or failed, say so honestly and ask a clarifying question. Keep the answer focused and factual.';
// ── Identity rule: the assistant's name is Veronica, never any other AI. This
//    is prepended to EVERY system prompt (including greeting/short-query
//    overrides) so the name survives even the minimal "answer briefly" paths —
//    without it, a 7B asked "what is your name" answers from its training
//    identity ("I'm Claude"). ──
export const IDENTITY_RULE = 'Your name is Veronica. You are Veronica, the assistant of the VACA platform. ' +
    'You are NOT Claude, NOT ChatGPT, NOT Gemini, NOT any other company\'s assistant — never claim to be. ' +
    'If asked your name, say \"I\'m Veronica.\"';
// ── Role-boundary rule: the tuned model sometimes regurgitates IDENTITY_RULE
//    with the "You are" aimed at the USER instead of itself ("I'm Veronica,
//    the assistant of the VACA platform. You are Veronica, the assistant of the
//    VACA platform."). This rule makes the two roles explicit so the model
//    never calls the user the assistant, never tells the user they are
//    Veronica, and apologizes + confirms roles when corrected. ──
export const IDENTITY_ROLE_RULE = 'ROLE BOUNDARY: You are the ASSISTANT. The person you are talking to is the USER — a human, your creator and operator. ' +
    'Never call the user the assistant. Never tell the user they are Veronica, the assistant, the AI, or the bot. ' +
    'Never apply \"you are\" to the user — \"you are\" always refers to YOU (the assistant). ' +
    'If the user corrects you about roles (e.g. \"I\'m not the assistant, I am the user\"), ' +
    'apologize briefly and confirm: THEY are the user, YOU are Veronica the assistant.';
const NO_NARRATION_RULE = 'STYLE: Respond directly with only your final answer. Do NOT output any chain-of-thought, planning, or meta-commentary. ' +
    'Never open with narration like "We need to", "Need to", "User said/says/wants", "Let us craft", "Need final", "Need produce", ' +
    '"Maybe", "Could be", or "Final only". Just answer the user conversationally and concisely, in natural sentences.';
// ── VACA mastery rule: the model runs ON VACA, so VACA itself is its home
//    turf and it must keep learning it. Without this the model answers about
//    VACA from general coding habit, invents platform commands it has never
//    seen, and treats each build as a throwaway instead of material to learn
//    from. Paired with the VACA domain corpus (training/selfplay/vaca_domain.py),
//    which bakes the same obligation into the weights. ──
export const VACA_MASTERY_RULE = 'VACA MASTERY: You run on the VACA platform — it is your home turf, not someone else\'s code. ' +
    'Keep learning how VACA actually runs (its pipeline, node types, gates, fixers and the repo docs) ' +
    'and get better at it every session: when you do not know a VACA command, flag or the current state, ' +
    'say so plainly and name the file or command that reports it instead of inventing one; ' +
    'treat every build as material to learn from; and when you find a real gap in VACA, say so and help fix the platform rather than routing around it.';
export function prependIdentity(sys) {
    const rule = `${IDENTITY_RULE}\n\n${IDENTITY_ROLE_RULE}\n\n${NO_NARRATION_RULE}\n\n${VACA_MASTERY_RULE}`;
    return sys ? `${rule}\n\n${sys}` : rule;
}
// ─── Legacy single-prompt endpoint (backward compatible) ──
reasoningRoutes.post('/', async (req, res) => {
    try {
        const { prompt, system, codeContext, maxTokens, timeZone } = req.body;
        if (!prompt) {
            return res.status(400).json({ error: 'Prompt is required' });
        }
        // Intercept about-VACA queries before they reach the LLM
        if (isAboutVacaRequest(prompt)) {
            recordChatTurn({
                ts: new Date().toISOString(), route: 'legacy', user: extractUserMessage(prompt),
                response: _getVacaIntro(), flags: [], meta: { interceptor: 'about-vaca' },
            });
            return res.json({ success: true, response: _getVacaIntro() });
        }
        // ── Role-confusion guard: "why did you say I'm the assistant" / "I'm not
        //    the assistant, I am the user" — answered directly so the LLM never
        //    fumbles the role boundary (it sometimes applies "you are" to the
        //    user and then collapses into the empty-echo fallback). ──
        const roleReply = detectRoleConfusion(extractUserMessage(prompt));
        if (roleReply) {
            recordChatTurn({
                ts: new Date().toISOString(), route: 'legacy', user: extractUserMessage(prompt),
                response: roleReply, flags: [], meta: { interceptor: 'role-confusion' },
            });
            return res.json({ success: true, response: roleReply });
        }
        // ── Denial guard: "no you didn't" / "that's wrong, nothing opened" — the
        //    user is calling out a false action claim. Answer directly (apologize,
        //    point at the real button) so it never collapses to the empty-echo
        //    fallback. ──
        const denialReply = detectDenial(extractUserMessage(prompt));
        if (denialReply) {
            recordChatTurn({
                ts: new Date().toISOString(), route: 'legacy', user: extractUserMessage(prompt),
                response: denialReply, flags: [], meta: { interceptor: 'denial' },
            });
            return res.json({ success: true, response: denialReply });
        }
        // ── File write: "create a file called X" — actually create it. Runs BEFORE
        //    memory detection so "write this to notes.txt" is a file, not a memory
        //    note (an explicit filename is the stronger signal). ──
        const fileReq = detectFileWriteRequest(extractUserMessage(prompt));
        if (fileReq) {
            const content = buildFileContentFromPrompt(fileReq, prompt);
            const meaningful = content.trim() && content.trim() !== fileReq.fileName.trim();
            if (meaningful) {
                try {
                    const saved = tryHandleFileWrite(fileReq.fileName, content);
                    return res.json({ success: true, response: saved, fileWrite: true });
                }
                catch (err) {
                    return res.json({
                        success: true,
                        response: `⚠️ Could not create "${fileReq.fileName}": ${err?.message || 'write failed'}`,
                        fileWrite: true,
                    });
                }
            }
            return res.json({
                success: true,
                response: `I'm ready to create "${fileReq.fileName}" for real — but I don't see any content to put in it yet. Tell me what to write (e.g. "create a file called app.py with this content: print('hello')"), and I'll create it.`,
                fileWrite: true,
            });
        }
        // ── Memory write: "write this into your wiki/memory" — actually perform the write ──
        const memoryReq = detectMemoryWriteRequest(extractUserMessage(prompt));
        if (memoryReq) {
            const content = buildContentFromPrompt(memoryReq, prompt);
            const meaningful = content.trim() && content.trim() !== memoryReq.instruction.trim();
            if (meaningful) {
                const saved = await tryHandleMemoryWrite(memoryReq.instruction, content, memoryReq.target);
                if (saved)
                    return res.json({ success: true, response: saved, memoryWrite: true });
            }
            const where = memoryReq.target === 'wiki' ? 'wiki' : 'memory';
            return res.json({
                success: true,
                response: `I'm ready to write that to my ${where} for real — but I don't see any content to save yet. Tell me what to write (e.g. "remember that I prefer dark mode"), and I'll persist it.`,
                memoryWrite: true,
            });
        }
        // ── Desktop open: "open firefox" — actually launch it (no hallucination) ──
        const openRes = await tryHandleDesktopOpen(extractUserMessage(prompt));
        if (openRes.handled && openRes.response) {
            return res.json({ success: true, response: openRes.response, desktopAction: true });
        }
        // ── Real tools: "read X / search the code / look it up" — execute the
        //    actual tool and feed the REAL results to the LLM (no fabricated answers) ──
        const toolReq = detectChatToolRequest(extractUserMessage(prompt));
        const toolOutcome = toolReq ? await runChatTool(toolReq) : null;
        // ── Unsupported requests (filesystem-wide scans, read-everything, "sync the
        //    wiki with anything newer") — decline honestly BEFORE the LLM can fake it ──
        const unsupported = detectUnsupportedRequest(extractUserMessage(prompt));
        if (unsupported) {
            return res.json({ success: true, response: unsupported.message, declined: true });
        }
        let fullPrompt = codeContext
            ? `Context from generated code:\n\`\`\`\n${codeContext}\n\`\`\`\n\n${prompt}`
            : prompt;
        if (toolOutcome?.contextBlock) {
            fullPrompt = `${toolOutcome.contextBlock}\n\n${fullPrompt}`;
        }
        // ── Server-side safeguard for short/greeting prompts ──
        // Prevents the model from generating training data or long hallucinated responses
        // even when the frontend hasn't been refreshed with the new code.
        let effectiveMaxTokens = maxTokens || 1024;
        let effectiveSystem = system;
        const isDateTimeQueryMsg = isDateTimeQuery(fullPrompt);
        // Tool requests are never greeting/short-query — they need room to summarize real data.
        const isGreetingQuery = !toolOutcome && !isDateTimeQueryMsg && isGreeting(fullPrompt);
        const isShortQueryMsg = !toolOutcome && !isGreetingQuery && !isDateTimeQueryMsg && isShortQuery(fullPrompt);
        if (isGreetingQuery) {
            effectiveMaxTokens = Math.min(effectiveMaxTokens, 48);
            effectiveSystem = `CRITICAL: Respond with 1-2 short sentences. Example: "Hey there! What can I build for you?" Do NOT generate articles, dates, questions, or any memorized text. Just greet back briefly.`;
        }
        else if (isShortQueryMsg) {
            // Non-greeting short messages (e.g., "what?", "why?") — prevent training data leak
            effectiveMaxTokens = Math.min(effectiveMaxTokens, 48);
            effectiveSystem = effectiveSystem
                ? `CRITICAL: The user asked a very short question. Answer in 1 short sentence. Do NOT generate articles, facts, dates, or any memorized text. Just answer concisely.\n\n${effectiveSystem}`
                : `CRITICAL: The user asked a very short question. Answer in 1 short sentence. Do NOT generate articles, facts, dates, or any memorized text. Just answer concisely.`;
        }
        // ── Inject authoritative, timezone-aware date/time so the model answers
        //    "what time is it?" / "what's the date?" truthfully, never from memory.
        //    Only date-time queries get the clock — keeping it out of the cache key
        //    preserves LRU hits for every other message. ──
        if (isDateTimeQueryMsg) {
            const clock = buildClockContext(timeZone);
            effectiveSystem = effectiveSystem ? `${effectiveSystem}\n\n${clock}` : clock;
        }
        // ── Inject persistent memory so the LLM knows what it remembers (and that
        //    writes are performed by the platform, never hallucinated) ──
        if (!isGreetingQuery && !isShortQueryMsg) {
            const memBlock = sessionMemory.getMemoryPromptBlock();
            if (memBlock)
                effectiveSystem = effectiveSystem ? `${effectiveSystem}\n\n${memBlock}` : memBlock;
        }
        // ── P2: emotion-aware reasoning — analyze the user's message, inject the
        //    tone modifier, and record the reading to soul.json. Short queries skip
        //    this, except short playful signals ("lol", "😂") which arm the mood. ──
        if (!isGreetingQuery && (!isShortQueryMsg || detectPlayful(extractUserMessage(fullPrompt)))) {
            const emoMod = buildEmotionModifier(extractUserMessage(fullPrompt));
            if (emoMod)
                effectiveSystem = effectiveSystem ? `${effectiveSystem}\n\n${emoMod}` : emoMod;
            recordEmotionHistory(extractUserMessage(fullPrompt));
        }
        // ── Native-platform steering: "stand alone, not a web browser build" →
        //    the model must plan a NATIVE stack, never a web one. The rule goes at
        //    the FRONT of the system prompt AND as a prefix on the user message
        //    itself — a lone appended line was ignored by the 7B. ──
        const platActive = !isGreetingQuery && !isShortQueryMsg && hasPlatformConstraint(extractUserMessage(fullPrompt));
        if (platActive) {
            effectiveSystem = effectiveSystem ? `${NATIVE_PLATFORM_RULE}\n\n${effectiveSystem}` : NATIVE_PLATFORM_RULE;
            fullPrompt = `${NATIVE_PLATFORM_SHORT}\n\n${fullPrompt}`;
        }
        // ── Identity FIRST (legacy route): same fix as /chat — the greeting and
        //    short-query overrides replace the system prompt (which carried the
        //    name), so prepend the name here so it survives on every path. ──
        effectiveSystem = prependIdentity(effectiveSystem);
        // NOTE: temperature is NOT part of the cache key — safe today because
        // CHAT_TEMPERATURE is constant; if per-request sampling is ever added,
        // the temperature must join the key (stale-temp answers would otherwise
        // be served). The VARIETY RULE lives in /chat (messages array), which is
        // the frontend path; the legacy single-prompt route below is cacheable
        // because its inputs fully determine its (deterministic) output.
        // ── Fast-chat routing: casual conversational messages (greetings, short
        //    queries, playful banter) go to the dedicated 7B on GPU 2 (~4x faster),
        //    while anything needing depth/tools/code/platform stays on the AEON 27B.
        //    Kept conservative so builds, code-gen, tool summaries, and native
        //    constraints always hit the big model.
        const _userMsgFast = extractUserMessage(fullPrompt);
        const useFastChat = !toolOutcome &&
            !codeContext &&
            !platActive &&
            !isBlueprintRequest(_userMsgFast) &&
            (isGreetingQuery || isShortQueryMsg || detectPlayful(_userMsgFast));
        const cacheKey = `${effectiveSystem || ''}|${fullPrompt}|${effectiveMaxTokens}|fast=${useFastChat ? 1 : 0}`;
        // Date/time answers must never come from a stale cache — the clock moves.
        const cached = isDateTimeQueryMsg ? undefined : cache.get(cacheKey);
        if (cached)
            return res.json({ success: true, response: cached, cached: true });
        if (toolOutcome) {
            effectiveSystem = effectiveSystem ? `${effectiveSystem}\n\n${TOOL_ANSWER_RULE}` : TOOL_ANSWER_RULE;
            effectiveMaxTokens = Math.max(effectiveMaxTokens, 700);
        }
        const response = useFastChat
            ? await translator.chatFast([{ role: 'user', content: _userMsgFast }], effectiveSystem, { maxTokens: effectiveMaxTokens, temperature: CHAT_TEMPERATURE })
            : await translator.reason(fullPrompt, effectiveSystem, { maxTokens: effectiveMaxTokens, temperature: CHAT_TEMPERATURE });
        // userText enables the cleaner's verbatim-echo guard (same as /chat).
        let cleaned = stripAeonTrace(cleanLLMResponse(response, { userText: extractUserMessage(prompt) }));
        // ── Blueprint-JSON hijack guard: a non-blueprint request answered with
        //    {"app_type":...} JSON gets regenerated as conversational prose. The
        //    legacy route embeds tool output in fullPrompt, so no separate context
        //    arg is needed here. ──
        cleaned = await undoBlueprintHijack(extractUserMessage(prompt), cleaned, undefined, (sys) => translator.reason(fullPrompt, prependIdentity(sys), { maxTokens: Math.min(effectiveMaxTokens + 300, 1500), temperature: CHAT_TEMPERATURE }), () => translator.reason(fullPrompt, prependIdentity(COMPLETE_JSON_RULE), { maxTokens: 4096, temperature: CHAT_TEMPERATURE }));
        // ── Sassy/echo guard (same as /chat): a banter prompt answered with a
        //    flat echo or nothing must NEVER hit the generic "I'm not sure how to
        //    respond" template. ──
        const legacyUserText = extractUserMessage(prompt);
        if (!cleaned.trim() && detectPlayful(legacyUserText)) {
            cleaned = pickSassyFallback(legacyUserText);
        }
        // ── Post-generation quality checks ──
        if (isGreetingQuery) {
            const sentences = cleaned.split(/[.!?]+/).filter(s => s.trim().length > 0);
            cleaned = sentences.length > 0 ? sentences[0].trim() + '.' : cleaned;
            if (cleaned.length > 120)
                cleaned = cleaned.substring(0, 117) + '...';
            cleaned = ensureQualityGreeting(cleaned, extractUserMessage(prompt));
        }
        else if (isShortQueryMsg) {
            // For short queries, keep only first sentence and cap length
            const sentences = cleaned.split(/[.!?]+/).filter(s => s.trim().length > 0);
            cleaned = sentences.length > 0 ? sentences[0].trim() + '.' : cleaned;
            if (cleaned.length > 150)
                cleaned = cleaned.substring(0, 147) + '...';
        }
        else if (cleaned.trim().length < 3) {
            cleaned = ensureQualityResponse(cleaned);
        }
        // ── Final empty guard (same as /chat): pure-echo collapse still gets a reply. ──
        if (!cleaned.trim()) {
            const _u = extractUserMessage(prompt);
            cleaned = isJokeRequest(_u) ? pickJokeFallback(_u) : isShortQueryMsg ? pickShortAck(_u) : ensureQualityResponse(cleaned);
        }
        // Honest leak note: if a native constraint was active but the reply still
        // describes a web stack, say so instead of silently planning the wrong
        // platform.
        if (platActive && /react|node\.?js|express|fastify|browser/i.test(cleaned)) {
            cleaned = `${cleaned}${NATIVE_LEAK_NOTE}`;
        }
        // Tool results are never cached — files/code change, so re-runs re-execute the real tool.
        if (!isDateTimeQueryMsg && !toolOutcome)
            cache.set(cacheKey, cleaned);
        res.json({
            success: true,
            response: stripAeonTrace(cleaned),
            ...(toolOutcome ? { toolUsed: true, tool: toolOutcome.tool, toolDisplay: toolOutcome.display } : {}),
        });
        // ── Monitor tap: record the turn (with canned/echo flags) for review ──
        recordChatTurn({
            ts: new Date().toISOString(),
            route: 'legacy',
            user: extractUserMessage(prompt),
            response: cleaned,
            flags: [],
            meta: {
                ...(toolOutcome ? { toolUsed: true, tool: toolOutcome.tool } : {}),
                cached: isDateTimeQueryMsg ? undefined : (cache.get(cacheKey) ? true : undefined),
                greeted: isGreetingQuery || undefined,
                short: isShortQueryMsg || undefined,
            },
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : 'Reasoning failed';
        console.error('[reasoning] LLM call failed:', msg);
        if (msg.includes('maximum context length') || msg.includes('context_length') || msg.includes('token limit')) {
            res.json({ success: true, response: `⚠️ Analysis skipped (content too large for model context window: ${msg}). Try with fewer or smaller files.` });
        }
        else if (msg.includes('API key') || msg.includes('api_key') || msg.includes('auth')) {
            res.json({ success: true, response: `⚠️ LLM not configured. Check that Ollama is running. Error: ${msg}` });
        }
        else {
            res.status(500).json({ error: msg });
        }
    }
});
// ─── NEW: Chat endpoint with proper message array format ──
// This is the FIX for the multi-turn hallucination bug.
// Instead of concatenating history into a string with "User:" / "Assistant:" prefixes
// (which caused the model to continue generating that pattern), this sends each
// message with its proper OpenAI role, preventing the LLM from emulating the
// conversation template.
reasoningRoutes.post('/chat', async (req, res) => {
    try {
        // `provider` is the dual-chat switch: 'primary' forces the reply from the
        // VACA model (ignoring any reasoning-role override) and 'reasoning' forces
        // the connected 2nd LLM. Omitted → current behaviour (use the reasoning
        // role when assigned, else primary).
        const { messages, system, maxTokens, timeZone, provider } = req.body;
        if (!messages || !Array.isArray(messages) || messages.length === 0) {
            return res.status(400).json({ error: 'Messages array is required' });
        }
        // ── Intercept about-VACA queries before they reach the LLM ──
        const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
        const userContent = lastUserMsg?.content || '';
        if (isAboutVacaRequest(userContent)) {
            recordChatTurn({
                ts: new Date().toISOString(), route: 'chat', user: userContent,
                response: _getVacaIntro(), flags: [], meta: { interceptor: 'about-vaca' },
            });
            return res.json({ success: true, response: _getVacaIntro() });
        }
        // ── Role-confusion guard: same direct answer as the legacy route — "why
        //    did you say I'm the assistant" / "I'm not the assistant, I am the
        //    user" never reaches the LLM (which has been observed to apply the
        //    identity rule to the user and collapse into the canned fallback). ──
        const roleReply = detectRoleConfusion(userContent);
        if (roleReply) {
            recordChatTurn({
                ts: new Date().toISOString(), route: 'chat', user: userContent,
                response: roleReply, flags: [], meta: { interceptor: 'role-confusion' },
            });
            return res.json({ success: true, response: roleReply });
        }
        // ── Denial guard (same as legacy route): "no you didn't" / "nothing
        //    opened" — the user is calling out a false action claim. Answer
        //    directly; never let it fall through to the LLM's empty-echo collapse. ──
        const denialReply = detectDenial(userContent);
        if (denialReply) {
            recordChatTurn({
                ts: new Date().toISOString(), route: 'chat', user: userContent,
                response: denialReply, flags: [], meta: { interceptor: 'denial' },
            });
            return res.json({ success: true, response: denialReply });
        }
        // ── File write: "create a file called X" — actually create it. Runs BEFORE
        //    memory detection so "write this to notes.txt" is a file, not a memory
        //    note (an explicit filename is the stronger signal). ──
        const fileReq = detectFileWriteRequest(userContent);
        if (fileReq) {
            const content = buildFileContentFromMessages(fileReq, messages);
            const meaningful = content.trim() && content.trim() !== fileReq.fileName.trim();
            if (meaningful) {
                try {
                    const saved = tryHandleFileWrite(fileReq.fileName, content);
                    return res.json({ success: true, response: saved, fileWrite: true });
                }
                catch (err) {
                    return res.json({
                        success: true,
                        response: `⚠️ Could not create "${fileReq.fileName}": ${err?.message || 'write failed'}`,
                        fileWrite: true,
                    });
                }
            }
            return res.json({
                success: true,
                response: `I'm ready to create "${fileReq.fileName}" for real — but I don't see any content to put in it yet. Tell me what to write (e.g. "create a file called app.py with this content: print('hello')"), and I'll create it.`,
                fileWrite: true,
            });
        }
        // ── Memory write: "write this into your wiki/memory" — actually perform the write ──
        const memoryReq = detectMemoryWriteRequest(userContent);
        if (memoryReq) {
            const content = buildContentFromMessages(memoryReq, messages);
            const meaningful = content.trim() && content.trim() !== memoryReq.instruction.trim();
            if (meaningful) {
                const saved = await tryHandleMemoryWrite(memoryReq.instruction, content, memoryReq.target);
                if (saved)
                    return res.json({ success: true, response: saved, memoryWrite: true });
            }
            const where = memoryReq.target === 'wiki' ? 'wiki' : 'memory';
            return res.json({
                success: true,
                response: `I'm ready to write that to my ${where} for real — but I don't see any content to save yet. Tell me what to write (e.g. "remember that I prefer dark mode"), and I'll persist it.`,
                memoryWrite: true,
            });
        }
        // ── Desktop open: "open firefox" — actually launch it (no hallucination) ──
        const openRes = await tryHandleDesktopOpen(userContent);
        if (openRes.handled && openRes.response) {
            return res.json({ success: true, response: openRes.response, desktopAction: true });
        }
        // ── Real tools: "read X / search the code / look it up" — execute the
        //    actual tool and feed the REAL results to the LLM (no fabricated answers) ──
        const toolReq = detectChatToolRequest(userContent);
        const toolOutcome = toolReq ? await runChatTool(toolReq) : null;
        // ── Unsupported requests (filesystem-wide scans, read-everything, "sync the
        //    wiki with anything newer") — decline honestly BEFORE the LLM can fake it ──
        const unsupported = detectUnsupportedRequest(userContent);
        if (unsupported) {
            return res.json({ success: true, response: unsupported.message, declined: true });
        }
        // ── Server-side safeguard for short/greeting messages ──
        // (already have lastUserMsg and userContent from above)
        const isDateTimeQueryMsg = isDateTimeQuery(userContent);
        // Tool requests are never greeting/short-query — they need room to summarize real data.
        const isGreetingMsg = !toolOutcome && !isDateTimeQueryMsg && isGreeting(userContent);
        const isShortQueryMsg = !toolOutcome && !isGreetingMsg && !isDateTimeQueryMsg && isShortQuery(userContent);
        let effectiveMaxTokens = maxTokens || 1024;
        let effectiveSystem = system;
        if (isGreetingMsg) {
            effectiveMaxTokens = Math.min(effectiveMaxTokens, 48);
            effectiveSystem = `CRITICAL: Respond with 1-2 short sentences. Example: "Hey there! What can I build for you?" Do NOT generate articles, dates, questions, or any memorized text. Just greet back briefly.`;
        }
        else if (isShortQueryMsg) {
            effectiveMaxTokens = Math.min(effectiveMaxTokens, 48);
            effectiveSystem = effectiveSystem
                ? `CRITICAL: The user asked a very short question. Answer in 1 short sentence. Do NOT generate articles, facts, dates, or any memorized text. Just answer concisely.\n\n${effectiveSystem}`
                : `CRITICAL: The user asked a very short question. Answer in 1 short sentence. Do NOT generate articles, facts, dates, or any memorized text. Just answer concisely.`;
        }
        // ── Inject authoritative, timezone-aware date/time (never guess). Only
        //    date-time queries get the clock — other messages don't need it. ──
        if (isDateTimeQueryMsg) {
            const clock = buildClockContext(timeZone);
            effectiveSystem = effectiveSystem ? `${effectiveSystem}\n\n${clock}` : clock;
        }
        // ── Inject persistent memory so the LLM knows what it remembers (and that
        //    writes are performed by the platform, never hallucinated) ──
        if (!isGreetingMsg && !isShortQueryMsg) {
            const memBlock = sessionMemory.getMemoryPromptBlock();
            if (memBlock)
                effectiveSystem = effectiveSystem ? `${effectiveSystem}\n\n${memBlock}` : memBlock;
        }
        // ── P2: emotion-aware reasoning in the chat path — inject the tone
        //    modifier for the user's last message and record it to soul.json. ──
        //    Short queries skip this, EXCEPT short playful signals ("lol", "😂")
        //    which are the most common way users joke — those must arm the mood.
        if (!isGreetingMsg && (!isShortQueryMsg || detectPlayful(userContent))) {
            const emoMod = buildEmotionModifier(userContent);
            if (emoMod)
                effectiveSystem = effectiveSystem ? `${effectiveSystem}\n\n${emoMod}` : emoMod;
            recordEmotionHistory(userContent);
        }
        // ── P3: emotion continuity — inject a rolling 2-turn summary of the
        //    conversation BEFORE this message so the model CONTINUES the exchange
        //    (references the user's earlier situation) instead of treating every
        //    message as a fresh problem. Only fires when the current message is a
        //    genuine follow-up (explicit continuation markers, or a negative
        //    emotional thread) — fresh questions, banter, and new topics never get
        //    it. Skipped for greeting/short/date-time queries. ──
        let contBlock = '';
        if (!isGreetingMsg &&
            !isShortQueryMsg &&
            !isDateTimeQueryMsg &&
            (isContinuationFollowUp(userContent) || isEmotionalContinuation(messages, userContent))) {
            contBlock = buildTurnContinuityContext(messages);
            if (contBlock)
                effectiveSystem = effectiveSystem ? `${effectiveSystem}\n\n${contBlock}` : contBlock;
        }
        // ── Native-platform steering: "stand alone, not a web browser build" →
        //    the model must plan a NATIVE stack, never a web one. Rule at the FRONT
        //    of the system prompt + short override prepended to the LAST user
        //    message (a lone appended line was ignored by the 7B). ──
        const platActive = !isGreetingMsg && !isShortQueryMsg && hasPlatformConstraint(userContent);
        let effectiveMessages = messages;
        if (platActive) {
            effectiveSystem = effectiveSystem ? `${NATIVE_PLATFORM_RULE}\n\n${effectiveSystem}` : NATIVE_PLATFORM_RULE;
            effectiveMessages = messages.map((m, i) => i === messages.length - 1 && m.role === 'user'
                ? { ...m, content: `${NATIVE_PLATFORM_SHORT}\n\n${m.content}` }
                : m);
        }
        // ── P3b: continuity RECAP — the 7B ignores continuity text in the system
        //    prompt alone (same lesson as NATIVE_PLATFORM_SHORT: a lone appended
        //    line was ignored), so ALSO prefix the current user message with the
        //    user's own earlier words. The appended form sat after the user's real
        //    content where the 7B gave it no weight (turn-2 replies treated the
        //    conversation as fresh), so the recap is PREPENDED. The directive names
        //    the earlier topic and allows varied phrasing (a suggested structure is
        //    offered, not mandated) — live-tested 3/3 tie-back on the audit probe
        //    without becoming a canned opener. Gated by the P3 follow-up check, so
        //    fresh questions never carry it. The recap is read from raw `messages`
        //    (never the remapped effectiveMessages, which would double-embed
        //    prefixes). When the native-platform prefix is already on the last user
        //    message, the recap is inserted AFTER it so the native constraint stays
        //    at the very front of the message. ──
        if (contBlock) {
            const recap = buildTurnRecap(messages);
            if (recap) {
                const recapBlock = `[CONTINUATION — Earlier, the user told you: "${recap}". Their new message below is a FOLLOW-UP on that same situation. ` +
                    `BEGIN your reply by referencing the EARLIER topic in your OWN words — a natural opener like "That's a lot on top of the [earlier topic] you mentioned." is fine, but write your own phrasing; just NAME the earlier topic (the subject from the recap above) in your first sentence. Vary your wording — never start with a memorized template sentence. Then respond to the new message. Never repeat your previous reply word-for-word.]`;
                effectiveMessages = effectiveMessages.map((m, i) => i === effectiveMessages.length - 1 && m.role === 'user'
                    ? {
                        ...m,
                        content: m.content.startsWith(NATIVE_PLATFORM_SHORT)
                            ? m.content.replace(`${NATIVE_PLATFORM_SHORT}\n\n`, `${NATIVE_PLATFORM_SHORT}\n\n${recapBlock}\n\n`)
                            : `${recapBlock}\n\n${m.content}`,
                    }
                    : m);
            }
        }
        if (toolOutcome) {
            const toolBlock = `${toolOutcome.contextBlock}\n\n${TOOL_ANSWER_RULE}`;
            effectiveSystem = effectiveSystem ? `${toolBlock}\n\n${effectiveSystem}` : toolBlock;
            effectiveMaxTokens = Math.max(effectiveMaxTokens, 700);
        }
        // ── Identity FIRST, always. Prepended LAST so it lands at the very front
        //    of whatever system prompt was assembled above (greetings, short
        //    queries, tools, native-platform, continuity — all of them). This is
        //    the fix for "what is your name" answering "I'm Claude": without it,
        //    the greeting/short-query paths strip the personality prompt that
        //    carried the name, and the 7B falls back to its training identity. ──
        effectiveSystem = prependIdentity(effectiveSystem);
        // ── Variety rule: if the user re-asks something similar to an earlier
        //    question, force a genuinely different answer instead of repeating the
        //    previous reply or a generic template. ──
        if (!isGreetingMsg && !isShortQueryMsg) {
            const variety = buildVarietyInstruction(effectiveMessages);
            if (variety)
                effectiveSystem = effectiveSystem ? `${variety}\n\n${effectiveSystem}` : variety;
        }
        // Lower sampling temperature when the continuity block is present: the
        // 7B follows the [RECENT CONVERSATION] instruction + worked example far
        // more reliably at 0.5 than at the server default (~0.7-1.0). Leave the
        // rest of chat at the default so personality stays lively elsewhere.
        // ── Fast-chat routing (chat path): casual conversational turns go to the
        //    dedicated 7B on GPU 2; builds/tools/platform/code stay on AEON. Same
        //    conservative gate as the legacy route. Continuity is preserved by
        //    passing the full effectiveMessages to chatFast.
        // When a pane is pinned to the reasoning (2nd LLM) provider, never reroute
        // greetings to fastChat — the user wants THAT model's answer, not the fast
        // chat worker.
        const useFastChat = provider !== 'reasoning' &&
            !toolOutcome &&
            !platActive &&
            !isBlueprintRequest(userContent) &&
            !contBlock &&
            (isGreetingMsg || isShortQueryMsg || detectPlayful(userContent));
        const response = useFastChat
            ? await translator.chatFast(effectiveMessages, effectiveSystem, { maxTokens: effectiveMaxTokens, temperature: CHAT_TEMPERATURE })
            : await translator.reasonWithHistory(effectiveMessages, effectiveSystem, {
                maxTokens: effectiveMaxTokens,
                temperature: contBlock ? 0.5 : CHAT_TEMPERATURE,
                ...(provider ? { provider: provider } : {}),
            });
        // userText enables the cleaner's verbatim-echo guard ("moo" → "moo.");
        // priorAssistantText enables the prior-turn-repeat strip (the 7B re-emits
        // its own previous reply verbatim before generating new content).
        const priorAssistant = [...messages].reverse().find((m) => m.role === 'assistant')?.content || undefined;
        let cleaned = stripAeonTrace(cleanLLMResponse(response, { userText: userContent, priorAssistantText: priorAssistant }));
        // ── Blueprint-JSON hijack guard: a non-blueprint request answered with
        //    {"app_type":...} JSON gets regenerated as conversational prose. The
        //    /chat route folds tool output into effectiveSystem, so pass the tool
        //    block separately so the retry stays factual. ──
        cleaned = await undoBlueprintHijack(userContent, cleaned, toolOutcome?.contextBlock, (sys) => translator.reasonWithHistory(effectiveMessages, prependIdentity(sys), {
            maxTokens: Math.min(effectiveMaxTokens + 300, 1500),
            temperature: contBlock ? 0.5 : CHAT_TEMPERATURE,
            ...(provider ? { provider: provider } : {}),
        }), () => translator.reasonWithHistory(effectiveMessages, prependIdentity(COMPLETE_JSON_RULE), {
            maxTokens: 4096,
            temperature: contBlock ? 0.5 : CHAT_TEMPERATURE,
            ...(provider ? { provider: provider } : {}),
        }));
        // ── Sassy/echo guard: the 7B sometimes answers banter with a flat echo
        //    ("I see you're typing \"…\"") or nothing after cleaning. A witty canned
        //    comeback beats a dead echo — and a joke must NEVER be answered with
        //    the generic "I'm not sure how to respond" template below. Non-playful
        //    empties fall through to the quality checks. ──
        if (!cleaned.trim() && detectPlayful(userContent)) {
            cleaned = pickSassyFallback(userContent);
        }
        // ── Post-generation quality checks ──
        if (isGreetingMsg) {
            const sentences = cleaned.split(/[.!?]+/).filter(s => s.trim().length > 0);
            cleaned = sentences.length > 0 ? sentences[0].trim() + '.' : cleaned;
            if (cleaned.length > 120)
                cleaned = cleaned.substring(0, 117) + '...';
            cleaned = ensureQualityGreeting(cleaned, userContent);
        }
        else if (isShortQueryMsg) {
            const sentences = cleaned.split(/[.!?]+/).filter(s => s.trim().length > 0);
            cleaned = sentences.length > 0 ? sentences[0].trim() + '.' : cleaned;
            if (cleaned.length > 150)
                cleaned = cleaned.substring(0, 147) + '...';
        }
        else if (cleaned.trim().length < 3) {
            cleaned = ensureQualityResponse(cleaned);
        }
        // ── Final empty guard: a message that collapsed to '' (pure echo) still
        //    needs SOME reply. Short non-playful echoes get a brief varied ack;
        //    longer empties get the standard quality fallback. ──
        if (!cleaned.trim()) {
            cleaned = isJokeRequest(userContent) ? pickJokeFallback(userContent) : isShortQueryMsg ? pickShortAck(userContent) : ensureQualityResponse(cleaned);
        }
        // Honest leak note: native constraint active but a web stack still leaked.
        if (platActive && /react|node\.?js|express|fastify|browser/i.test(cleaned)) {
            cleaned = `${cleaned}${NATIVE_LEAK_NOTE}`;
        }
        res.json({
            success: true,
            response: stripAeonTrace(cleaned),
            ...(toolOutcome ? { toolUsed: true, tool: toolOutcome.tool, toolDisplay: toolOutcome.display } : {}),
        });
        // ── Monitor tap: record the turn (with canned/echo flags) for review ──
        recordChatTurn({
            ts: new Date().toISOString(),
            route: 'chat',
            user: userContent,
            response: cleaned,
            flags: [],
            meta: {
                ...(toolOutcome ? { toolUsed: true, tool: toolOutcome.tool } : {}),
                greeted: isGreetingMsg || undefined,
                short: isShortQueryMsg || undefined,
            },
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : 'Reasoning failed';
        console.error('[reasoning/chat] LLM call failed:', msg);
        if (msg.includes('API key') || msg.includes('api_key') || msg.includes('auth')) {
            res.json({ success: true, response: `⚠️ LLM not configured. Check that Ollama is running. Error: ${msg}` });
        }
        else {
            res.status(500).json({ error: msg });
        }
    }
});
// ─── Vision endpoint — describe an image using the vision model ──
reasoningRoutes.post('/vision', async (req, res) => {
    try {
        const { image_base64, prompt } = req.body;
        if (!image_base64) {
            return res.status(400).json({ success: false, error: 'image_base64 is required' });
        }
        const userPrompt = prompt || "What's visible in this screenshot? Describe briefly.";
        try {
            // Resolve the active vision critic from llm-config.json (vision section,
            // falling back to ollama/primary) — single source of truth with vision.ts.
            const visionConfig = getVisionConfig();
            const client = new OpenAI({
                baseURL: visionConfig.baseUrl,
                apiKey: visionConfig.apiKey,
            });
            const dataUrl = `data:image/png;base64,${image_base64}`;
            const response = await client.chat.completions.create({
                model: visionConfig.model,
                messages: [
                    {
                        role: 'user',
                        content: [
                            { type: 'text', text: userPrompt },
                            { type: 'image_url', image_url: { url: dataUrl, detail: 'low' } },
                        ],
                    },
                ],
                max_tokens: 512,
            });
            const description = response.choices?.[0]?.message?.content || '';
            if (description) {
                return res.json({ success: true, description, model: visionConfig.model });
            }
            res.status(422).json({
                success: false,
                error: 'Vision analysis returned empty result',
            });
        }
        catch (err) {
            res.status(422).json({
                success: false,
                error: `Vision analysis failed: ${err.message}`,
            });
        }
    }
    catch (err) {
        res.status(500).json({ success: false, error: err.message || 'Vision request failed' });
    }
});
// ─── Code Builder endpoint — uses reasonWithHistory to avoid multi-turn hallucination ──
reasoningRoutes.post('/code', async (req, res) => {
    try {
        const { messages, system, maxTokens } = req.body;
        if (!messages || !Array.isArray(messages) || messages.length === 0) {
            return res.status(400).json({ error: 'Messages array is required' });
        }
        // Convert flat messages array to OpenAI format
        // The messages already come with {role, content} format
        const sysPrompt = system || 'You are a proactive software engineering assistant. When the user asks you to build something, write code, create files, or analyze a project — do it. Provide complete working solutions, not suggestions. You can write files, run commands, and interact with the system.';
        const response = await translator.reasonWithHistory(messages, sysPrompt, { maxTokens: maxTokens || 2048 });
        res.json({ success: true, response: cleanLLMResponse(response) });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : 'Code builder LLM call failed';
        console.error('[code-reason] LLM call failed:', msg);
        if (msg.includes('API key') || msg.includes('api_key') || msg.includes('auth')) {
            res.json({ success: true, response: `⚠️ LLM error. Check that Ollama is running. Error: ${msg}` });
        }
        else {
            res.status(500).json({ error: msg });
        }
    }
});
