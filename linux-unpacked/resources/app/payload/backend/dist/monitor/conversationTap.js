/**
 * conversationTap — records every chat turn (user message → response) to a
 * JSONL monitor log so an operator can review what the app actually said and
 * flag incorrections (canned fallbacks, echoed prompts, role confusion, etc.)
 *
 * Deliberately tiny and failure-proof: never throws, never blocks the request,
 * appends best-effort. The log lives at data/monitor/conversations.jsonl and
 * can be tailed live with `scripts/monitor-vaca.py` (or any tail -f).
 */
import { appendFileSync, mkdirSync } from 'fs';
import path from 'path';
const MONITOR_DIR = process.env.VACA_MONITOR_DIR
    || path.resolve(import.meta.dirname, '..', '..', '..', 'data', 'monitor');
const LOG = path.join(MONITOR_DIR, 'conversations.jsonl');
try {
    mkdirSync(MONITOR_DIR, { recursive: true });
}
catch { /* best-effort */ }
/** Responses that are "the app gave up / dodged" rather than a real answer. */
const CANNED_MARKERS = [
    [/I'm not sure how to respond to that/i, 'canned:not-sure-how-to-respond'],
    [/can you tell me what you'd like to build/i, 'canned:redirect-to-build'],
    [/you're the user, and i'm the assistant/i, 'role-confusion-interceptor'],
    [/you're the user here, and i'm veronica/i, 'role-confusion-interceptor'],
    [/you're the user, i'm the assistant/i, 'role-confusion-interceptor'],
];
/** Classify a response: normal, canned, or interceptor-flavored. */
export function classifyResponse(response, meta) {
    const flags = [];
    if (!response || response.trim().length < 3)
        flags.push('empty-response');
    for (const [re, tag] of CANNED_MARKERS) {
        if (re.test(response))
            flags.push(tag);
    }
    if (meta.fileWrite)
        flags.push('file-write-handled');
    if (meta.memoryWrite)
        flags.push('memory-write-handled');
    if (meta.declined)
        flags.push('declined');
    if (meta.cached)
        flags.push('served-from-cache');
    if (meta.toolUsed)
        flags.push('tool-used');
    return flags;
}
/** Append a chat turn to the monitor log. Never throws. */
export function recordChatTurn(turn) {
    try {
        const flags = classifyResponse(turn.response, turn.meta);
        const line = JSON.stringify({ ...turn, flags }) + '\n';
        appendFileSync(LOG, line, 'utf8');
    }
    catch { /* best-effort — monitoring must never break chat */ }
}
