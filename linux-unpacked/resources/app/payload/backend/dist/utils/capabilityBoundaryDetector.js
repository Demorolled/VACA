/**
 * capabilityBoundaryDetector — catches chat requests that the platform does
 * NOT support (filesystem-wide scans, "read everything" asks, "sync the wiki
 * with everything newer") and returns a deterministic, honest decline.
 *
 * This is the guaranteed safety net: a 7B model may not always follow the
 * system-prompt "decline what you can't do" rule, so the platform intercepts
 * these intents BEFORE the LLM runs and answers honestly itself — the model
 * never gets a chance to fake a scan ("🚀 Starting file system search…").
 */
const SCAN_PATTERNS = [
    // "scan all files / the filesystem / every folder / the hard drive / the computer"
    // (stacked qualifiers handled: "your whole filesystem", "all my files")
    /\bscan\s+(?:(?:all|the|your|my|entire|whole|every)\s+)*(?:filesystem|file\s+system|files|director(?:ies|y)|folders?|drives?|hard\s+drives?|computer|system|disk|machine|everything)\b/i,
    // "read all files in your system" / "read every file on the computer"
    /\bread\s+(?:all\s+|every\s+|each\s+|the\s+)?(?:file|files|folder|folders)\s+(?:in\s+|on\s+|from\s+|across\s+)?(?:your\s+|my\s+|the\s+)?(?:system|computer|machine|drive|disk|filesystem|hard\s+drive)\b/i,
    // "read everything" / "read all of it" — but NOT depth questions like
    // "read everything about React hooks" (negative lookahead keeps those in chat).
    /\bread\s+(?:everything|all\s+of\s+(?:my|your|the)\s+files|all\s+my\s+files)(?!\s*(?:about|regarding|concerning))\b/i,
    // "survey / inventory / list all files on ..."
    /\b(?:survey|inventory|list)\s+(?:all\s+|every\s+|the\s+)?(?:file|files|folder|folders|drives?|director(?:ies|y))\s+(?:on\s+|in\s+|of\s+)?(?:my\s+|your\s+|the\s+)?(?:computer|system|machine|drive|disk)\b/i,
    // "sync/update the wiki/memory/knowledge with anything newer / the filesystem"
    /\b(?:sync|update|refresh)\s+(?:your\s+|my\s+|the\s+)?(?:wiki|memory|knowledge)(?:\s+file)?\s+(?:with\s+|from\s+)?(?:anything|everything|all|any)\s+new(?:er)?\b/i,
    /\b(?:sync|update|refresh)\s+(?:your\s+|my\s+|the\s+)?(?:wiki|memory|knowledge)(?:\s+file)?\s+with\s+(?:the\s+)?(?:filesystem|file\s+system|system files|my\s+files|your\s+files)\b/i,
    // "check all files for changes/newer content"
    /\b(?:check|find|look\s+for)\s+(?:all\s+|any\s+|every\s+)?(?:newer|new|changed|updated)\s+(?:files?|content|stuff|things)\s+(?:on|in|across)\s+(?:my\s+|your\s+|the\s+)?(?:system|computer|machine|drive|disk|filesystem)\b/i,
    // "what's new/newer than the wiki"
    /\bwhat(?:'s| is| are)\s+(?:the\s+)?(?:newer|new|latest)\s+(?:files?|things|stuff|changes|updates)\s+(?:on|in|since)\b/i,
];
/**
 * Shell-command intents. The chat LLM has NO shell access — only the power-user
 * "/desktop run <cmd>" endpoint executes commands, and that is a deliberate,
 * explicit desktop action, not something the model can do from a conversation.
 * These patterns decline imperative requests BEFORE the model can hallucinate
 * a fake command output.
 */
const SHELL_PATTERNS = [
    // "run the shell command X" / "execute (the) command X"
    /\b(?:run|execute)\s+(?:the\s+)?(?:shell\s+)?command\b/i,
    // "run `ls -la`" / "run 'git status'" / "execute \"pwd\""
    /\b(?:run|execute)\s+[`'"][^`'"]+[`'"]/i,
    // "run this command in the terminal" / "execute this in bash"
    /\b(?:run|execute)\s+(?:this|the|a|an)\s+(?:command|instruction)\s+(?:in|on|via|using)\s+(?:the\s+)?(?:terminal|shell|bash|command\s+line|cli)\b/i,
    // "open a terminal and run X" / "open terminal and execute X"
    /\bopen\s+(?:a\s+)?terminal\s+(?:and|to)\s+(?:run|execute)\b/i,
    // Verb + known CLI binary: "run ls -la", "execute sudo apt install", "run npm install"
    /\b(?:run|execute)\s+(?:sudo\s+)?(?:ls|cat|rm|mv|cp|mkdir|chmod|chown|apt|apt-get|npm|yarn|pnpm|pip|pip3|curl|wget|grep|ps|kill|docker|git|python3?|node|bash|sh|echo|touch|tail|head|find|tar|unzip|zip|systemctl|service|ifconfig|ip\s+addr)\b/i,
    // Explicit "run/execute a shell/terminal command" phrasing. Deliberately
    // REQUIRES a run/execute verb: a bare "explain shell commands to me" or
    // "how do shell commands work" is educational, not an execution request.
    /\b(?:run|execute)\s+(?:a|an|the|this|some|these)?\s*(?:shell|terminal|command-line|cli)\s+command\b/i,
    // "type/enter/paste this terminal command: df -h" — imperative console phrasing
    /\b(?:type|enter|paste)\s+(?:this|the|a|an)\s+(?:shell|terminal|command-line|cli)\s+command\b/i,
];
/**
 * Advice / educational requests about commands must NOT be declined as if the
 * user were asking us to execute them. This catches "how do I run X", "please
 * tell me how to run X", "is there a way to run X", "explain shell commands",
 * "how do shell commands work", and greeting-prefixed variants — wherever the
 * phrase appears, not just at the string start.
 */
const SHELL_ADVICE_RE = /(?:how\s+(?:do|can|would|should|to)\s+(?:i|you|we)|how\s+to\b|how\s+do\s+[a-z]+\s+commands?\s+work|explain(?:\s+to\s+me)?|teach\s+me|tell\s+me\s+(?:how|about)|is\s+there\s+a\s+way|what\s+(?:is|are|does|do)|why\s+(?:is|do|does)|can\s+you\s+(?:explain|teach|tell\s+me\s+how|show\s+me\s+how))/i;
/** The honest decline message — lists what the platform CAN actually do. */
export const DECLINE_MESSAGE = [
    "⚠️ I can't scan the whole filesystem or run shell commands — that's outside what I can actually do from chat (I have no file handle or shell of my own). Here's what I CAN do for real:",
    '• Read a specific file you name — e.g. "read backend/src/index.ts"',
    '• Search the codebase — e.g. "search the code for permissionManager"',
    '• Search the web — e.g. "search the web for X"',
    '• Query my knowledge base — e.g. "what do you know about X"',
    '• Create files in data/chat-files/ — e.g. "create a file called app.py with this content: ..."',
    '• Write to my memory or wiki — e.g. "remember this", "write this into your wiki"',
    '• Open apps on your desktop — e.g. "open firefox"',
    '',
    'For shell commands, use the power-user "/desktop run <command>" tool in the desktop panel, or run it yourself in your terminal.',
    'Tell me exactly which file you want read (or what to update in the wiki) and I\'ll do it for real.',
].join('\n');
/**
 * Detect an unsupported filesystem-scan / read-everything / sync-wiki intent.
 * Returns a decline message, or null when the request is supported (falls
 * through to the real interceptors / normal chat).
 */
export function detectUnsupportedRequest(text) {
    const t = (text || '').trim();
    if (!t || t.length > 400)
        return null;
    for (const re of SCAN_PATTERNS) {
        if (re.test(t))
            return { message: DECLINE_MESSAGE };
    }
    // Shell commands: decline imperative "run/execute" requests, but NEVER
    // advice questions ("how do I run X?") — those are answerable in chat.
    if (!SHELL_ADVICE_RE.test(t)) {
        for (const re of SHELL_PATTERNS) {
            if (re.test(t))
                return { message: DECLINE_MESSAGE };
        }
    }
    return null;
}
