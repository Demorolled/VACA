/**
 * Lightweight Intent Extractor — Part 3 of the intent upgrade.
 *
 * Turns the user's RAW request into a structured spec BEFORE planning:
 *   { goal, targetUser, coreFeatures, uiStyle, language }
 *
 * Rule-based + deterministic: zero latency, zero LLM cost, runs synchronously so
 * the planner and the writer both see a normalized "what the user wants" instead
 * of raw free text. Extracted fields are ADVISORY — the plan prompt tells the LLM
 * to correct the spec if it misreads the request. (A fast-coder refinement pass
 * can be layered on later for genuinely ambiguous requests; rule-first keeps the
 * common path instant and free.)
 */
function emptySpec() {
    return { goal: '', targetUser: '', coreFeatures: [], uiStyle: '', language: '' };
}
// ── Language detection ────────────────────────────────────────────────────
// Distinctive language names match anywhere; ambiguous ones ("go", "js", "ts")
// only match with context ("in go", "using go") to avoid false positives.
const BARE_LANGUAGES = [
    [/\btypescript\b/i, 'typescript'],
    [/\bjavascript\b/i, 'javascript'],
    [/\bpython\b/i, 'python'],
    [/\bgolang\b/i, 'go'],
    [/\brust\b/i, 'rust'],
    [/\bc\+\+\b|\bcpp\b/i, 'c++'],
    [/\bc#\b/i, 'c#'],
    [/\bjava\b/i, 'java'], // \bjava\b never matches inside "javascript" (no word boundary between java|script)
    [/\bswift\b/i, 'swift'],
    [/\bkotlin\b/i, 'kotlin'],
    [/\bhtml\b/i, 'html'],
    [/\bcss\b/i, 'css'],
    [/\bbash\b|\bzsh\b/i, 'bash'],
];
const CONTEXT_LANGUAGES = [
    [/\b(?:in|using|with)\s+(?:the\s+)?go\b/i, 'go'],
    [/\b(?:in|using|with)\s+(?:the\s+)?js\b/i, 'javascript'],
    [/\b(?:in|using|with)\s+(?:the\s+)?ts\b/i, 'typescript'],
];
/** Conservative inference when the user named no language at all. */
function inferLanguage(text) {
    const t = text.toLowerCase();
    if (/(game|drag.?and.?drop|puzzle|quiz|drawing|paint|whiteboard|code editor|music (player|studio|daw)|video editor|photo editor|dashboard|simulator|canvas|animation studio|pixel art)/.test(t))
        return 'html';
    if (/(web scrap|crawl|automation|data analysis|analy[sz]e data|parser|csv|backup|report generator|api (server|backend)|web server|bot)/.test(t))
        return 'python';
    return '';
}
function detectLanguage(text) {
    for (const [re, lang] of BARE_LANGUAGES) {
        if (re.test(text))
            return lang;
    }
    for (const [re, lang] of CONTEXT_LANGUAGES) {
        if (re.test(text))
            return lang;
    }
    return inferLanguage(text);
}
// ── UI style detection ────────────────────────────────────────────────────
// Platform style first (one), then visual style appended ("web, dark").
function detectUiStyle(text) {
    const t = text.toLowerCase();
    const styles = [];
    if (/(terminal|cli|console|command.?line)/.test(t))
        styles.push('cli');
    // Native/standalone constraints take PRIORITY over the web/game patterns —
    // "stand alone not a web browser based build" contains both "browser" and
    // "stand alone", and must classify as DESKTOP, not web (the old order made
    // the bare word "browser" win and VACA planned a React/Express web stack
    // for an explicitly non-web request).
    else if (/(desktop|native\s+app|stand\s*alone|standalone|not\s+a?\s*web|no\s+browser|without\s+a?\s*browser|offline\s+app|local\s+(?:app|game)|doesn'?t\s+need\s+a\s+browser)/.test(t))
        styles.push('desktop');
    else if (/(game|playable|arcade)/.test(t))
        styles.push('game');
    else if (/(website|\bweb\b|dashboard|browser)/.test(t))
        styles.push('web');
    else if (/(mobile app|ios|android|phone app)/.test(t))
        styles.push('mobile');
    else if (/(chat|messenger|chatbot)/.test(t))
        styles.push('web');
    if (/(dark|night mode)/.test(t))
        styles.push('dark');
    else if (/(light|bright)/.test(t))
        styles.push('light');
    if (/(minimal|minimalist)/.test(t))
        styles.push('minimal');
    return styles.join(', ');
}
// ── Target user detection ─────────────────────────────────────────────────
// "for my family", "for developers", "for kids" — cut at the first stop word so
// "for kids with ai" → "kids". Bails on cardinal quantifiers ("for two players").
function detectTargetUser(text) {
    const m = text.match(/\bfor\s+(?:me\s+and\s+)?((?:my|the|your|a|an|all)\s+)?([a-z][a-z0-9\s'-]{1,60})/i);
    if (!m)
        return '';
    // Combine the article group ("my ") with the captured noun so "for my family"
    // yields "my family" (not just "family").
    let user = `${m[1] || ''}${m[2] || ''}`.trim();
    if (/^(two|both|one|multi|up\s+to\s+\d+)/i.test(user))
        return ''; // "for two players"
    if (/^(me|myself|us|ourselves)\b/i.test(user))
        return ''; // "for me" ≠ a target user
    user = user.split(/\s+(?:that|which|who|with|where|so|and|to|it|they|using|on|in)\b/i)[0].trim();
    return user.replace(/\s+/g, ' ').slice(0, 60);
}
// ── Goal extraction ───────────────────────────────────────────────────────
// Strip polite/auxiliary fillers and keep the essence of the first sentence:
//   "can you please build me a todo app" → "todo app"
//   "I want a dark-themed python web scraper" → "dark-themed python web scraper"
function extractGoal(text) {
    let t = text.trim();
    t = t.split(/(?<=[.!?])\s+/)[0]; // first sentence only
    t = t.replace(/^(?:hey|hi|hello|ok|okay|so)\s*,?\s*/i, '');
    t = t.replace(/^(?:please|kindly|just)\s+/i, '');
    t = t.replace(/^(?:please\s+)?(?:can|could|would|will|do|did)\s+you\s+(?:please\s+)?/i, '');
    t = t.replace(/^(?:i\s+)?(?:'?d\s+)?(?:want|need|would\s+like|like|love|wanna)\s+(?:you\s+to\s+)?(?:to\s+)?/i, '');
    t = t.replace(/^(?:help\s+me\s+)?(?:make|build|create|generate|develop|write|code|design|implement|program)\s+(?:me\s+)?(?:an?\s+|the\s+|some\s+)?/i, '');
    t = t.replace(/^(?:a|an|the|some)\s+/i, '');
    t = t.replace(/\s+for\s+me\s*$/i, ''); // "chess game for me" → "chess game"
    t = t.trim().replace(/\s+/g, ' ');
    return t.slice(0, 160);
}
// ── Core features ─────────────────────────────────────────────────────────
// NOTE: every pattern is case-insensitive (/i) — requests routinely say "AI player",
// "HTML", "SQLite" etc. and the /i flag is what makes "AI player" match.
const FEATURE_PATTERNS = [
    [/\btodo\b|\bto-do\b|\btask\s*list\b|\bchecklist\b|\btask\s*manager\b/i, 'todo / task list'],
    [/\bhabit\b|\bstreak\b/i, 'habit tracking / streaks'],
    [/\bnotes?\b|\bnote[- ]taking\b/i, 'note-taking'],
    [/\bai\s+(?:player|opponent|bot|computer)\b|\bplay\s+against\b|\bminimax\b/i, 'AI opponent'],
    [/\bdrag.?and.?drop\b/i, 'drag-and-drop'],
    [/\b(?:move|movement)\s*rules\b|\bcheckmate\b|\ben\s+passant\b|\bcastling\b/i, 'full move rules (castling, en passant, checkmate)'],
    [/\bhigh\s?score\b|\bpoints\b|\bscore\b/i, 'score tracking'],
    [/\blevels?\b/i, 'levels'],
    [/\bnew\s+(?:item|task|note)\b|\badd\b|\bcreate\b/i, 'create items'],
    [/\bdelete\b|\bremove\b/i, 'delete items'],
    [/\bedit\b|\bupdate\b|\bmodify\b/i, 'edit items'],
    [/\bmark\s+(?:as\s+)?(?:done|complete)\b|\bcheck\s+off\b|\bcomplete\s+(?:tasks?|items?|todos?)\b/i, 'mark complete'],
    [/\bsave\b|\bpersist\b|\bstore\b|\bdatabase\b|\bjson\b|\bsqlite\b/i, 'persistent storage'],
    [/\blog\s?in\b|\bsign\s?up\b|\bregister\b|\bauthenticate\b|\baccount\b/i, 'user accounts / auth'],
    [/\btimer\b|\bcountdown\b|\bstopwatch\b/i, 'timing (timer/countdown)'],
    [/\bnotif|\bremind|\breminder/i, 'notifications/reminders'],
    [/\bchat\b|\bmessages?\b|\bconversation\b/i, 'chat/messages'],
    [/\bweb\s*scrap|\bcrawl/i, 'web scraping'],
    [/\bexport\b|\bdownload\b/i, 'export/download'],
    [/\bimport\b|\bupload\b/i, 'import/upload'],
    [/\bsearch\b|\bfilter\b|\bsort\b/i, 'search/filter/sort'],
    [/\bsettings\b|\bpreferences\b|\boptions\b/i, 'settings/preferences'],
    [/\bmultiplayer\b|\bmulti.?player\b|\bonline\b/i, 'multiplayer'],
    [/\bundo\b|\breplay\b|\bhistory\b/i, 'undo/history'],
];
function detectCoreFeatures(text) {
    const found = [];
    for (const [re, feature] of FEATURE_PATTERNS) {
        if (found.length >= 6)
            break;
        if (re.test(text) && !found.some(f => f.toLowerCase() === feature.toLowerCase()))
            found.push(feature);
    }
    return found;
}
// ── Public API ────────────────────────────────────────────────────────────
/**
 * Extract a structured intent spec from a raw request. Pure + deterministic.
 * Never throws — returns an empty spec for non-string/empty input.
 */
export function extractIntent(request) {
    if (typeof request !== 'string' || !request.trim())
        return emptySpec();
    const text = request.trim();
    return {
        goal: extractGoal(text) || text.slice(0, 160),
        targetUser: detectTargetUser(text),
        coreFeatures: detectCoreFeatures(text),
        uiStyle: detectUiStyle(text),
        language: detectLanguage(text),
    };
}
/**
 * Render the spec as a compact block for prompt injection. Empty string when the
 * spec carries nothing worth saying (so callers can skip it cleanly).
 */
export function formatIntentSection(spec) {
    const lines = [];
    if (spec.goal)
        lines.push(`Goal: ${spec.goal}`);
    if (spec.targetUser)
        lines.push(`Target user: ${spec.targetUser}`);
    if (spec.coreFeatures.length)
        lines.push(`Core features: ${spec.coreFeatures.join(', ')}`);
    if (spec.uiStyle)
        lines.push(`UI style: ${spec.uiStyle}`);
    if (spec.language)
        lines.push(`Preferred language: ${spec.language}`);
    if (!lines.length)
        return '';
    return `━━━ UNDERSTOOD INTENT (auto-extracted from your request) ━━━\n${lines.join('\n')}\nTreat this as your understanding of what the user asked for — if it misreads the request, correct it in your plan.\n`;
}
/**
 * Low-confidence signal for the fast-coder refinement pass (roadmap Phase 3).
 * A spec is ambiguous when the rules found no language, no UI style, and fewer
 * than 2 core features — i.e. the request didn't name a stack, a platform, or
 * enough concrete features for the rules to act on. Anything more specific
 * skips refinement entirely (zero LLM cost on the common path).
 */
export function isLowConfidenceIntent(spec) {
    return !spec.language && !spec.uiStyle && spec.coreFeatures.length < 2;
}
/**
 * Merge a fast-model's refinement over the rule-based spec (fill-the-gaps):
 * the deterministic rule output wins wherever it found something; the refined
 * values only fill fields the rules left EMPTY. coreFeatures are replaced
 * wholesale only when the rules found none (a union would drown the precise
 * rule hits in model noise). Never throws.
 */
export function mergeIntentSpecs(base, refined) {
    return {
        goal: base.goal || refined.goal,
        targetUser: base.targetUser || refined.targetUser,
        coreFeatures: base.coreFeatures.length ? base.coreFeatures : refined.coreFeatures,
        uiStyle: base.uiStyle || refined.uiStyle,
        language: base.language || refined.language,
    };
}
