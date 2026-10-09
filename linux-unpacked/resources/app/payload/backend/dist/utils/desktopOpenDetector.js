/**
 * Desktop open-request detector.
 *
 * Detects chat requests like "open firefox", "open the browser", "open
 * https://example.com", "launch calculator". Includes a typo map so common
 * misspellings ("firefix" → "firefox") resolve to the real app — the chat
 * model used to repeat the typo instead of opening anything.
 */
/** Common misspellings → canonical app name. */
const TYPO_MAP = {
    firefix: 'firefox',
    firfix: 'firefox',
    firfox: 'firefox',
    foxfire: 'firefox',
    googel: 'google',
    goole: 'google',
    chrom: 'chrome',
    chromimum: 'chromium',
    termial: 'terminal',
    calculater: 'calculator',
    calcualtor: 'calculator',
    nautalis: 'nautilus',
    filesmgr: 'files',
};
/** App names the executor knows about (normalized lower-case, plus typos). */
const KNOWN_APPS = new Set([
    'browser', 'chrome', 'chromium', 'firefox', 'terminal', 'file manager',
    'files', 'nautilus', 'editor', 'vscode', 'vs code', 'settings', 'calculator',
    'text editor', ...Object.keys(TYPO_MAP),
]);
const QUESTION_SKIP_RE = /^(how|what|why|where|when|who|explain|tell me|show me|is it possible|does it)\b/i;
function extractApp(text) {
    const t = text.trim();
    // Try the full remainder first, then progressively shorter tokens so
    // multi-word apps ("file manager", "vs code", "text editor") match.
    const candidates = [t];
    const words = t.split(/\s+/);
    for (let i = words.length; i >= 1; i--) {
        candidates.push(words.slice(0, i).join(' '));
    }
    for (const cand of candidates) {
        const key = cand.toLowerCase();
        if (KNOWN_APPS.has(key)) {
            return TYPO_MAP[key] || key;
        }
    }
    return null;
}
/**
 * Detect an imperative open request. Returns null for questions ("how do I
 * open…"), non-open text, or anything not clearly an open/launch/start/go-to.
 */
export function detectDesktopOpenRequest(text) {
    const t = (text || '').trim();
    if (!t || t.length > 200)
        return null;
    if (QUESTION_SKIP_RE.test(t))
        return null;
    // ── URL first: "open https://…", "open www…", "go to <url>" ──
    const urlMatch = t.match(/\b(https?:\/\/[^\s]+|www\.[^\s]+)\b/i);
    if (urlMatch && /^(open|launch|start|go to|visit|navigate to)\b/i.test(t)) {
        const url = urlMatch[1].startsWith('www.') ? `https://${urlMatch[1]}` : urlMatch[1];
        return { kind: 'url', url };
    }
    // ── App: "open/launch/start/run [up] [the] [web browser/app] <app>" ──
    const m = t.match(/^(?:please\s+)?(?:open|launch|start|run)\s+(?:up\s+)?(.+)$/i);
    if (!m)
        return null;
    let rest = m[1].trim();
    // Strip articles and qualifiers: "the", "my", "web browser named", "app"…
    rest = rest
        .replace(/^(?:a|an|the|my|our)\s+/i, '')
        .replace(/^(?:(?:web\s+)?browser|app|application|website|web\s+site)\s+(?:named|called|known\s+as)?\s*/i, '')
        .replace(/^(?:named|called|known\s+as)\s+/i, '');
    const app = extractApp(rest);
    if (!app)
        return null;
    return { kind: 'app', app, matched: m[1] };
}
