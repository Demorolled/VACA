/**
 * languageInference — domain-aware language selection for the architect plan
 * stage.
 *
 * ROOT CAUSE this fixes: the plan stage mapped language by OS alone
 * (linux→Go), so "a simple countdown timer web app" was planned as
 * main.go/service.go/ui.go and every downstream gate (tsc, smoke, export)
 * then produced false verdicts on files that were never written in the right
 * language. Language must be chosen by the APP'S DOMAIN first (web/CLI →
 * TypeScript, which the whole pipeline — tsc gate, esbuild preview, TS
 * scaffold — actually supports end-to-end), with the OS-native mapping
 * reserved for apps that are genuinely native desktop/mobile targets.
 */
export const OS_LANGUAGE_MAP = {
    linux: 'go',
    windows: 'csharp',
    mac: 'swift',
    ios: 'swift',
    android: 'kotlin',
};
// Browser / GUI / widget apps — the pipeline's strongest path is TypeScript
// (tsc gate + esbuild preview + TS scaffold), so any goal that describes an
// interface the user opens in a browser or widget-like UI resolves to TS.
const WEB_DOMAIN_KEYWORDS = [
    'web app', 'webpage', 'web page', 'website', 'landing page', 'frontend',
    'front end', 'single page', 'single-page', 'spa', 'browser', 'gui app',
    'dashboard', 'widget', 'countdown', 'timer', 'calculator', 'todo app',
    'todo list', 'notepad', 'note pad', 'note taking', 'quiz', 'game',
    'interface', 'html', 'pomodoro', 'stopwatch', 'desktop app', 'app with a ui',
    'online store', 'e-commerce', 'shop', 'web store',
];
const CLI_DOMAIN_KEYWORDS = [
    'cli', 'command line', 'command-line', 'terminal', 'console tool',
    'cli tool', 'shell tool', 'command line tool',
];
// Explicit language mentions ("in Go", "using Python", "a Rust CLI"). Short
// ambiguous tokens ('go', 'ts', 'js', 'py') are excluded — 'go' alone false-
// positives on phrases like "let's go build a todo app". 'go' is matched only
// when preceded by in/using/with/on.
const LANGUAGE_KEYWORDS = [
    { re: /\btypescript\b/i, lang: 'typescript' },
    { re: /\bjavascript\b/i, lang: 'javascript' },
    { re: /\bpython\b/i, lang: 'python' },
    { re: /\bgolang\b/i, lang: 'go' },
    { re: /(?:in|using|with|on)\s+go\b/i, lang: 'go' },
    { re: /\brust\b/i, lang: 'rust' },
    { re: /\bc#|csharp\b/i, lang: 'csharp' },
    { re: /\bswift\b/i, lang: 'swift' },
    { re: /\bkotlin\b/i, lang: 'kotlin' },
    { re: /\bjava\b/i, lang: 'java' },
    { re: /\bphp\b/i, lang: 'php' },
    { re: /\bruby\b/i, lang: 'ruby' },
    { re: /\bcpp\b|\bc\+\+\b/i, lang: 'cpp' },
];
/** Languages the generation pipeline can actually validate/export. */
export const SUPPORTED_CODING_LANGUAGES = new Set([
    'typescript', 'javascript', 'python', 'go', 'rust', 'java',
    'csharp', 'swift', 'kotlin', 'php', 'ruby', 'cpp', 'c',
]);
/** Non-code files keep their natural format. */
const NATURAL_FORMAT_LANGUAGES = new Set([
    'html', 'css', 'sql', 'json', 'yaml', 'yml', 'xml', 'md', 'markdown',
    'txt', 'sh', 'bash', 'dockerfile', 'env', 'ini', 'toml', 'csv', 'svg',
]);
const LANGUAGE_ALIASES = {
    ts: 'typescript',
    js: 'javascript',
    py: 'python',
    golang: 'go',
    'c++': 'cpp',
    markdown: 'md',
};
/**
 * Pick a language the user EXPLICITLY named in the goal/purpose ("a todo app
 * in Go", "Python script that..."). Returns null when no language is named.
 */
export function detectExplicitLanguage(goal, purpose) {
    const text = `${goal || ''} ${purpose || ''}`;
    for (const { re, lang } of LANGUAGE_KEYWORDS) {
        if (re.test(text))
            return lang;
    }
    return null;
}
/**
 * Classify the app's domain from the goal/purpose text. An explicit
 * uiPreference of 'cli' overrides text inference (the user set a global
 * CLI-only preference).
 */
export function inferDomainKind(goal, purpose, uiPreference) {
    if (uiPreference === 'cli')
        return 'cli';
    const text = `${goal || ''} ${purpose || ''}`.toLowerCase();
    if (WEB_DOMAIN_KEYWORDS.some((k) => text.includes(k)))
        return 'web';
    if (CLI_DOMAIN_KEYWORDS.some((k) => text.includes(k)))
        return 'cli';
    return 'native';
}
/**
 * THE fix: language for a build request. Explicit user language wins; then
 * the domain; only for genuine native/desktop targets does the OS mapping
 * apply — web and CLI apps are TypeScript, never Go.
 */
export function inferLanguageForGoal(goal, purpose, targetOS, uiPreference) {
    const explicit = detectExplicitLanguage(goal, purpose);
    if (explicit)
        return explicit;
    const kind = inferDomainKind(goal, purpose, uiPreference);
    if (kind === 'web' || kind === 'cli')
        return 'typescript';
    return OS_LANGUAGE_MAP[(targetOS || '').trim()] || 'typescript';
}
/**
 * Normalize a single node's language. Unknown/typo'd languages (e.g. 'jsx',
 * 'pyton', 'c#'-as-'csharp' variants) collapse to the inferred language so a
 * plan can never produce a mixed-language graph of Go + TS + mystery.
 */
export function normalizeNodeLanguage(language, inferredLang) {
    if (!language)
        return inferredLang;
    const raw = language.trim().toLowerCase();
    const lang = LANGUAGE_ALIASES[raw] || raw;
    if (SUPPORTED_CODING_LANGUAGES.has(lang) || NATURAL_FORMAT_LANGUAGES.has(lang))
        return lang;
    return inferredLang;
}
/**
 * Force every node of a CLIENT-SIDE (browser) app to the web language —
 * the plan stage may still emit Go/other nodes for web goals, and a browser
 * app with a single Go file is a build guaranteed to fail. Natural-format
 * files (html/css/json/...) pass through untouched.
 */
export function normalizeClientSideLanguages(languages) {
    return languages.map((l) => {
        const raw = (l || '').trim().toLowerCase();
        const lang = LANGUAGE_ALIASES[raw] || raw;
        if (NATURAL_FORMAT_LANGUAGES.has(lang))
            return lang;
        return 'typescript';
    });
}
