/**
 * rosettaCode — pure, network-free parsing of Rosetta Code page wikitext into
 * knowledge-store patterns, for the 11 languages the non-TS compile gate
 * supports.
 *
 * Rosetta Code is a wiki of the SAME small task solved in hundreds of
 * languages, which is exactly the shape of this repo's micro-build catalog and
 * curated language patterns — but hand-writing one worked example per language
 * does not scale. This module turns a fetched page's wikitext into clean,
 * stdlib-only, single-file reference snippets the writer can copy the shape of.
 *
 * The page fetch lives in `scripts/fetch-rosetta.ts`; everything here is pure
 * so the extractor can be unit-tested against an inline wikitext fixture with
 * no network.
 *
 * Output is gated through the same `isQualityCode` funnel every capture path
 * uses (`knowledgeStore.addPattern`), PLUS a substantive-snippet check so a
 * one-line `print("Hello world!")` never masquerades as a "worked example".
 */
import { isQualityCode } from './qualityGate.js';
/** The 11 languages `nonTsCompileGate.GATE_LANGUAGES` can build. */
export const ROSETTA_TARGETS = [
    { language: 'go', headerAliases: ['go'], langAttrs: ['go'] },
    { language: 'python', headerAliases: ['python'], langAttrs: ['python', 'py', 'python3'] },
    { language: 'rust', headerAliases: ['rust'], langAttrs: ['rust'] },
    { language: 'c', headerAliases: ['c'], langAttrs: ['c'] },
    { language: 'cpp', headerAliases: ['c++'], langAttrs: ['cpp', 'c++', 'c++11', 'cpp11'] },
    { language: 'java', headerAliases: ['java'], langAttrs: ['java'] },
    { language: 'csharp', headerAliases: ['c sharp', 'c#'], langAttrs: ['csharp', 'c#'] },
    { language: 'swift', headerAliases: ['swift'], langAttrs: ['swift'] },
    { language: 'kotlin', headerAliases: ['kotlin'], langAttrs: ['kotlin'] },
    { language: 'php', headerAliases: ['php'], langAttrs: ['php'] },
    { language: 'ruby', headerAliases: ['ruby'], langAttrs: ['ruby'] },
];
/**
 * Small, self-contained, standard-library-only tasks that read well as
 * copyable idioms. Deliberately excludes anything needing a dictionary file,
 * a third-party package, a GUI, or a network.
 *
 * ORDER MATTERS: only the first `maxPerLanguage` tasks per language are seeded
 * by default, so the most instructive tasks lead. Everything here still feeds
 * the committed corpus.
 */
export const ROSETTA_TASKS = [
    // Seeded by default (maxPerLanguage = 4) — core control flow and functions.
    '99 bottles of beer',
    'FizzBuzz',
    'Factorial',
    'Fibonacci sequence',
    // Next most instructive.
    'Command-line arguments',
    'Apply a callback to an array',
    'Binary search',
    'Balanced brackets',
    'Caesar cipher',
    'Palindrome detection',
    'Reverse a string',
    'Averages/Arithmetic mean',
    'Arithmetic/Integer',
    'Copy a string',
    'Count occurrences of a substring',
    'Dot product',
    'Entropy',
    'Ethiopian multiplication',
    'Even or odd',
    'Factors of an integer',
    'Generate lower case ASCII alphabet',
    'Generic swap',
    'Gray code',
    'Greatest common divisor',
    'Primality by trial division',
    'Sum and product of an array',
    'Temperature conversion',
    'Array concatenation',
    'Binary digits',
    '100 doors',
    'A+B',
    'Combinations',
];
function normalizeHeader(name) {
    return name.trim().toLowerCase().replace(/_/g, ' ').replace(/\s+/g, ' ');
}
/** HTML entity unescape — Rosetta serves `<` as `&lt;` inside code blocks. */
export function htmlUnescape(s) {
    return s
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .replace(/&#0?39;/g, "'")
        .replace(/&apos;/g, "'")
        .replace(/&nbsp;/g, ' ')
        .replace(/&amp;/g, '&');
}
/** Strip wiki markup that leaks into a code block (links, templates, nowiki). */
export function stripWikiMarkup(s) {
    return s
        .replace(/<!--[\s\S]*?-->/g, '')
        .replace(/<\/?nowiki\s*>/gi, '')
        .replace(/<\/?pre\s*>/gi, '')
        .replace(/\[\[[^\]|]*\|([^\]]*)\]\]/g, '$1')
        .replace(/\[\[([^\]]*)\]\]/g, '$1')
        .replace(/\{\{[^{}]*\}\}/g, '');
}
/**
 * Drop a trailing "output"-style comment block. Rosetta snippets often end
 * with `/* Output: … *\/` or `// Output: …`, whose prose trips the quality
 * gate's markdown-bullet rule and would otherwise reject good code.
 * Only touches trailing comment material — never code.
 */
export function stripOutputComments(code) {
    let out = code.replace(/\s+$/, '');
    // Trailing block comment that starts with an output-ish word.
    const block = /\/\*\s*(?:output|sample output|result|prints?|returns?)\b[\s\S]*?\*\/\s*$/i;
    while (block.test(out))
        out = out.replace(block, '').replace(/\s+$/, '');
    // Trailing run of line comments that each start with an output-ish word.
    const lines = out.split('\n');
    while (lines.length) {
        const last = lines[lines.length - 1].trim();
        if (/^(?:\/\/|#|--)\s*(?:output|sample output|result|prints?|returns?)\b/i.test(last)) {
            lines.pop();
        }
        else {
            break;
        }
    }
    out = lines.join('\n').replace(/\s+$/, '');
    return out;
}
/** Split page wikitext on `=={{header|Lang}}==` headers into per-language sections. */
export function parseSections(wikitext) {
    const cleaned = wikitext.replace(/<!--[\s\S]*?-->/g, '');
    const headerRe = /^==\s*\{\{header\|([^}]*)\}\}\s*==\s*$/gm;
    const headers = [];
    let m;
    while ((m = headerRe.exec(cleaned)) !== null) {
        const aliases = m[1].split('|').map((a) => a.trim()).filter(Boolean);
        headers.push({ index: m.index, end: m.index + m[0].length, aliases });
    }
    const sections = [];
    for (let i = 0; i < headers.length; i++) {
        const end = i + 1 < headers.length ? headers[i + 1].index : cleaned.length;
        sections.push({ aliases: headers[i].aliases, body: cleaned.slice(headers[i].end, end) });
    }
    return sections;
}
/**
 * `lang=` values that label a sample RUN (expected output) rather than source.
 * Rosetta often appends one after the implementation.
 */
const OUTPUT_LANGS = new Set(['text', 'output', 'console', 'shell', 'bash', 'sh', 'plain', 'none', 'stdout']);
/** Extract every `<syntaxhighlight>` / `<source>` code block from a section. */
export function extractCodeBlocks(sectionBody) {
    const blocks = [];
    const re = /<(syntaxhighlight|source)\b([^>]*)>([\s\S]*?)<\/\1\s*>/gi;
    let m;
    while ((m = re.exec(sectionBody)) !== null) {
        const attrs = m[2] || '';
        const langMatch = attrs.match(/\blang\s*=\s*"([^"]*)"/i) || attrs.match(/\blang\s*=\s*'([^']*)'/i) || attrs.match(/\blang\s*=\s*([^\s>]+)/i);
        const lang = (langMatch?.[1] || '').trim().toLowerCase();
        blocks.push({ lang, code: m[3] });
    }
    return blocks;
}
/**
 * Find the primary reference implementation of `task` for `target`, or null.
 *
 * The SECTION HEADER is the authoritative language signal — the `lang=`
 * attribute is frequently wrong or approximate on Rosetta (the Kotlin "99
 * bottles" block is labelled `lang="scala"`), so trusting it alone silently
 * drops whole languages. Order of preference:
 *   1. a block whose `lang` names the language (most precise),
 *   2. the first block that is not an output/sample block,
 *   3. a lone block, whatever it is labelled.
 */
export function extractRosettaCode(wikitext, target) {
    const wantedHeaders = new Set(target.headerAliases.map(normalizeHeader));
    const wantedLangs = new Set(target.langAttrs.map((l) => l.toLowerCase()));
    for (const section of parseSections(wikitext)) {
        const headerHit = section.aliases.some((a) => wantedHeaders.has(normalizeHeader(a)));
        if (!headerHit)
            continue;
        const blocks = extractCodeBlocks(section.body);
        if (blocks.length === 0)
            continue;
        const usable = blocks.filter((b) => !OUTPUT_LANGS.has(b.lang));
        const chosen = blocks.find((b) => wantedLangs.has(b.lang)) ||
            usable[0] ||
            (blocks.length === 1 ? blocks[0] : undefined);
        if (!chosen)
            continue;
        const code = stripOutputComments(stripWikiMarkup(htmlUnescape(chosen.code)).replace(/^\s*\n/, '').replace(/\s+$/, ''));
        if (code)
            return code;
    }
    return null;
}
/** A snippet needs at least a few real lines to be a useful "worked example". */
export function isSubstantive(code, language) {
    const nonEmpty = code.split('\n').filter((l) => l.trim().length > 0);
    if (nonEmpty.length < 3)
        return false;
    // Residual unparsed wiki markup means the extraction leaked — never store it.
    if (/\{\{|<\/?(?:nowiki|pre|syntaxhighlight|source)\b/i.test(code))
        return false;
    // Python REPL transcripts (`>>> …`) are interactive session logs, not
    // runnable files — Rosetta stores several this way. `>>>` is a valid
    // unsigned-shift operator in Java/Kotlin, but only ever mid-line there, and
    // the check is anchored to line start.
    if ((language === 'python' || language === 'python3') && /^\s*>>>/m.test(code))
        return false;
    return true;
}
/** Stable title so re-seeding is idempotent (matched by title in the store). */
export function rosettaTitle(task, language) {
    return `rosetta — ${task} (${language})`;
}
export const ROSETTA_SOURCE_URL = 'https://rosettacode.org/wiki/';
/**
 * Turn fetched pages into knowledge-store seeds. Every candidate must pass the
 * substantive check AND the shared `isQualityCode` gate, so a fetch can never
 * smuggle prose/stubs into the store.
 *
 * `qualityScore` is 7 — deliberately one below the hand-curated patterns (8) —
 * so the curated idioms still win the store's retrieval ranking on a tie.
 */
/**
 * Order pages by `ROSETTA_TASKS`. The MediaWiki `titles=` response is NOT in
 * request order, so without this the corpus order (and therefore which tasks
 * the per-language seed budget picks) is arbitrary and can shift between
 * fetches. Unknown tasks sort last, keeping their relative order.
 */
function orderPagesByTask(pages) {
    const norm = (t) => t.trim().toLowerCase().replace(/_/g, ' ');
    const index = new Map(ROSETTA_TASKS.map((t, i) => [norm(t), i]));
    return [...pages].sort((a, b) => (index.get(norm(a.task)) ?? Number.MAX_SAFE_INTEGER) -
        (index.get(norm(b.task)) ?? Number.MAX_SAFE_INTEGER));
}
export function buildRosettaPatterns(pages) {
    const patterns = [];
    const rejected = [];
    for (const page of orderPagesByTask(pages)) {
        for (const target of ROSETTA_TARGETS) {
            const code = extractRosettaCode(page.wikitext, target);
            if (!code) {
                rejected.push({ task: page.task, language: target.language, reason: 'no-section' });
                continue;
            }
            if (!isSubstantive(code, target.language)) {
                rejected.push({ task: page.task, language: target.language, reason: 'not-substantive' });
                continue;
            }
            if (!isQualityCode(code, target.language)) {
                rejected.push({ task: page.task, language: target.language, reason: 'quality-gate' });
                continue;
            }
            patterns.push({
                category: 'code_pattern',
                title: rosettaTitle(page.task, target.language),
                description: `Rosetta Code reference — "${page.task}" in ${target.language.toUpperCase()}. A complete, standard-library-only snippet to copy the idiom and structure of. Source: ${ROSETTA_SOURCE_URL}${page.task.replace(/ /g, '_')}`,
                language: target.language,
                nodeType: 'logic',
                tags: [target.language, 'rosetta', page.task.toLowerCase()],
                projectId: 'rosetta',
                targetOS: 'linux',
                success: true,
                qualityScore: 7,
                code,
            });
        }
    }
    return { patterns, rejected };
}
