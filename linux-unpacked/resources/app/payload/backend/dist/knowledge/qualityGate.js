/**
 * qualityGate — the ONE quality check for anything that enters the knowledge
 * store or training capture paths.
 *
 * Extracted from learningEngine.ts so knowledgeStore.addPattern() (the funnel
 * every capture path dumps into) can enforce the same deterministic gate as the
 * learning engine, without a circular import. Any code-like content that fails
 * this gate is never stored as a pattern, regardless of what the caller says.
 *
 * The gate catches the 2026-08-13 "3d chees game" poisoning class:
 *   - ``` markdown fences written into .ts files (TS1443/TS1160)
 *   - `---` batched-response separators (one answer smuggling many files)
 *   - trailing explanation prose ("In this solution...", "This code defines...")
 *   - prompt scaffolding echoed into the file ("REAL FILE CONTENT")
 *   - JSX-in-.ts (TS1005) and stub/placeholder bodies
 */
// Stub / placeholder bodies — never valid training examples.
const STUB_PATTERNS = [
    /not implemented/i,
    /placeholder\s+for/i,
    /coming soon/i,
    /lorem ipsum/i,
    /unimplemented/i,
    /throw new Error\(['"]not/i,
    /TODO: Implement/i,
    /auto-generated placeholder/i,
];
// JSX-in-.ts: a .ts file containing JSX element syntax (<div className=...>,
// </div>) breaks tsc with TS1005. If it appears outside a string/comment, the
// file is not a clean example and must not be learned from.
//
// IMPORTANT — must NOT false-positive on legitimate TypeScript generics such
// as Promise<Foo>, Map<string>, Array<Item>, Record<string, X>: those have NO
// whitespace after the tag name (and are often capitalized). So we only flag:
//   - opening tags with attributes:  <div className="x">, <li key={i}>, <br />
//   - closing tags:                  </div>, </li>
const JSX_IN_TS_RE = /<\/?[a-z][a-z0-9]*\s[^>]*>|<\/[a-z][a-z0-9]*\s*>/;
// Markdown leaks that break tsc (TS1443/TS1160): a ``` fence line or a
// batched-response `---` separator inside what should be a pure source file
// means the LLM's markdown answer was written into the file.
export const MARKDOWN_FENCE_RE = /^\s*```/m;
export const BATCH_SEPARATOR_RE = /^\s*---\s*$/m;
// Prompt scaffolding echoed into a source file. The model sometimes copies the
// platform's own tool-marker convention into generated code (seen in the
// 2026-08-13 chess build: "// REAL FILE CONTENT: Real file content injected by
// the platform...") — those artifacts are never valid code.
export const PROMPT_ARTIFACT_RE = /REAL FILE CONTENT|injected by the platform|generated for the "[^"]+" node|entry point for the node/i;
// Prose lines that break tsc (TS1434/TS1435): markdown bullets, bold runs,
// note/explanation prefixes at line start that are NOT code. Includes the
// trailing-explanation phrasing the model emits after code ("In this
// solution...", "This code defines...", "For a chess game...").
const PROSE_RE = /^\s*(?:\*\*[^*]+\*\*|[-*]\s+[A-Za-z]|Note:|NOTE:|> |Explanation:|Here's|Below is|In this (?:solution|implementation|file|module|example)|This (?:code|file|module|implementation|class|function) (?:defines|implements|handles|provides|is|shows)|For (?:a|an) .* (?:game|app|application)|The .* (?:function|class|module|implementation))/;
/** Strip string literals so JSX-in-ts detection doesn't match strings. */
function stripStringLiterals(code) {
    return code.replace(/(['"`])(?:\\.|(?!\1)[^\\])*\1/g, '');
}
/**
 * Deterministic quality gate. Returns true only for content that is plausibly
 * clean source code (or a clean non-code payload like architecture JSON).
 * Rejects markdown leaks, prose, stubs, prompt artifacts, JSX-in-ts, and
 * anything too short to be a meaningful example.
 */
export function isQualityCode(code, language) {
    if (code.trim().length < 30)
        return false;
    if (STUB_PATTERNS.some(re => re.test(code)))
        return false;
    // Markdown fences / batched `---` separators = answer prose leaked into the
    // file. They break tsc AND mean the snippet isn't clean code — reject.
    if (MARKDOWN_FENCE_RE.test(code))
        return false;
    if (BATCH_SEPARATOR_RE.test(code))
        return false;
    // Prompt scaffolding echoed into the file is never valid code — reject.
    if (PROMPT_ARTIFACT_RE.test(code))
        return false;
    // Plain .ts/.js files must not contain JSX syntax (outside strings)
    if (['typescript', 'javascript'].includes((language || '').toLowerCase())) {
        if (JSX_IN_TS_RE.test(stripStringLiterals(code)))
            return false;
    }
    // Reject markdown-prose lines that would break tsc
    for (const line of code.split('\n')) {
        const t = line.trim();
        if (PROSE_RE.test(line) && !/[;{}()=<>]/.test(t)) {
            return false;
        }
    }
    return true;
}
/**
 * Deterministic stub-body detector for the GENERATION path (as opposed to the
 * learning path, where isQualityCode gates storage). A file that never
 * implements its node's contract — the generator's own "TODO: Implement"
 * fallback, comment-only bodies, prompt scaffolding echoed into source — is
 * never a shippable file, no matter how cleanly it compiles.
 */
// ── Placeholder-body detection ─────────────────────────────────────────────
/** A TODO/FIXME/XXX marker inside a COMMENT — the generator's own write prompt
 *  forbids TODOs, so any one marks a body that was left unfinished. Broader
 *  than the exact `TODO: Implement` string in STUB_PATTERNS. */
const TODO_COMMENT_RE = /\/\/[^\n]*\b(?:TODO|FIXME|XXX)\b|\/\*[\s\S]*?\b(?:TODO|FIXME|XXX)\b[\s\S]*?\*\//i;
/** A body that is a single trivial `return <literal>;` — the "compiles but does
 *  nothing" placeholder class (e.g. `boolean checkWin(...) { return false; }`). */
const PLACEHOLDER_RETURN_RE = /^\s*return\s+(?:false|true|null|0|-1|''|""|``|\{\}|\[\]|undefined|nil)\s*;\s*$/;
/** Header text that ends in a signature: `name(args)` (optionally `throws …`). */
const METHOD_HEADER_RE = /[A-Za-z_$][\w$]*\s*\([^)]*\)\s*(?:throws\s+[\w\s,.<>\[\]]+)?$/;
/** Control-flow headers — their braces are NOT method bodies. */
const CONTROL_HEADER_RE = /^(?:if|for|while|switch|catch|else|do|try|finally|synchronized|case|default|when)\b/;
/** Strip // and block comments (best-effort; enough for structural counts). */
export function stripComments(code) {
    return code.replace(/\/\/[^\n]*/g, '').replace(/\/\*[\s\S]*?\*\//g, '');
}
/** Every `{…}` block's HEADER (the text since the previous `;`/`}`/`{`) and its
 *  inner content. Used to tell a method body from an `if`/`for` block. */
export function collectBraceBlocks(code) {
    const blocks = [];
    const stack = [];
    for (let i = 0; i < code.length; i++) {
        if (code[i] === '{')
            stack.push(i);
        else if (code[i] === '}') {
            const start = stack.pop();
            if (start === undefined)
                continue;
            let hs = start;
            while (hs > 0 && !/[;}{]/.test(code[hs - 1]))
                hs--;
            blocks.push({ header: code.slice(hs, start).trim(), inner: code.slice(start + 1, i) });
        }
    }
    return blocks;
}
/** True when some METHOD body (not a control block) is a single placeholder return. */
export function hasPlaceholderMethodBody(code) {
    for (const b of collectBraceBlocks(stripComments(code))) {
        if (!b.header || CONTROL_HEADER_RE.test(b.header))
            continue;
        if (!METHOD_HEADER_RE.test(b.header))
            continue;
        const body = b.inner.trim();
        if (body && PLACEHOLDER_RETURN_RE.test(body))
            return true;
    }
    return false;
}
/** Languages whose members are delimited by INDENTATION, not braces. */
const INDENTED_LANGS = new Set(['python', 'ruby']);
/**
 * Classify `name`'s implementation in an indentation-delimited source
 * (Python / Ruby).
 *
 * The brace-based classifier below finds nothing in these files, so every
 * planned export came back 'absent' — and the contract gate flags 'absent' for
 * non-TS languages. That rejected nodes that were fully implemented (measured
 * live: the generated Python temperature converter's `converter.py` and
 * `arg-parser.py` were both marked "planned export … is not implemented" while
 * their bodies were real code).
 *
 * `trivial` means an empty body, `pass`/`...` only, or comments only; anything
 * else is 'ok'. A one-line `def f(): return 1` is 'ok'.
 */
export function indentedMemberImplementationState(content, name) {
    const lines = (content || '').split('\n');
    const esc = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const headerRe = new RegExp(`^(\\s*)(?:async\\s+)?(?:def|function)\\s+${esc}\\b`);
    for (let i = 0; i < lines.length; i++) {
        const m = headerRe.exec(lines[i]);
        if (!m)
            continue;
        const indent = m[1].length;
        // `def f(): return 1` — the whole body is on the header line.
        const afterColon = lines[i].slice(lines[i].lastIndexOf(':') + 1).replace(/#.*$/, '').trim();
        if (afterColon)
            return 'ok';
        const body = [];
        for (let j = i + 1; j < lines.length; j++) {
            const line = lines[j];
            if (line.trim() === '')
                continue;
            const lineIndent = line.length - line.trimStart().length;
            if (lineIndent <= indent)
                break;
            body.push(line.trim());
        }
        const real = body.filter((b) => !b.startsWith('#') && !/^(?:pass|\.\.\.)$/.test(b));
        return real.length === 0 ? 'trivial' : 'ok';
    }
    return 'absent';
}
/**
 * Classify the body of the callable member `name` in `content`:
 *   - 'ok'           a braced body with real statements
 *   - 'trivial'      an empty body or a single placeholder `return <literal>;`
 *   - 'non-callable' `name` is declared as a class/type (no callable body to judge)
 *   - 'absent'       no declaration found at all
 */
export function memberImplementationState(content, name, language) {
    if (INDENTED_LANGS.has((language || '').toLowerCase()))
        return indentedMemberImplementationState(content, name);
    const nameRe = new RegExp(`(?:^|[^\\w$])${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\(`);
    for (const b of collectBraceBlocks(stripComments(content))) {
        if (CONTROL_HEADER_RE.test(b.header))
            continue;
        if (!nameRe.test(b.header))
            continue;
        const body = b.inner.trim();
        if (!body || PLACEHOLDER_RETURN_RE.test(body))
            return 'trivial';
        return 'ok';
    }
    const typeRe = new RegExp(`(?:class|interface|enum|record|struct|type|typedef|trait)\\s+${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`);
    if (typeRe.test(content))
        return 'non-callable';
    return 'absent';
}
export function isStubBody(code) {
    if (code.trim().length === 0)
        return true;
    if (STUB_PATTERNS.some((re) => re.test(code)))
        return true;
    if (PROMPT_ARTIFACT_RE.test(code))
        return true;
    if (MARKDOWN_FENCE_RE.test(code))
        return true;
    if (BATCH_SEPARATOR_RE.test(code))
        return true;
    // Any TODO/FIXME/XXX comment marks an unfinished body (broader than the
    // exact `TODO: Implement` string above).
    if (TODO_COMMENT_RE.test(code))
        return true;
    // A method whose entire body is a single placeholder `return <literal>;`
    // (e.g. `boolean checkWin(...) { return false; }`) compiles but does nothing.
    if (hasPlaceholderMethodBody(code))
        return true;
    // Comment-only bodies: strip // and /* */ comments; if nothing code-like
    // remains (only a package clause, whitespace, or braces), it's a stub.
    const withoutComments = code
        .replace(/\/\/[^\n]*/g, '')
        .replace(/\/\*[\s\S]*?\*\//g, '');
    const trimmed = withoutComments.trim();
    const codeLike = trimmed.replace(/^\s*(?:package\s+\w+|import\s*\(?\s*\)?|'use strict'|"use strict";?)\s*;?\s*$/g, '').trim();
    if (codeLike.length < 8 && !/[=<>+\-*/&|!?{}();]/.test(codeLike)) {
        return true;
    }
    // Truly EMPTY function bodies only: function foo() {} / func foo() { } with
    // nothing inside (comments already stripped above). The previous `[^{}]*`
    // matched ANY brace-free body, so real one-statement functions — Go
    // `func main() { fmt.Println("hi") }`, JS `function add(a,b) { return a+b; }`
    // — were falsely rejected as stubs.
    if (/(?:function|func)\s+[A-Za-z_$][\w$]*\s*\([^)]*\)\s*\{\s*\}/.test(withoutComments)) {
        return true;
    }
    return false;
}
/** True when the kill switch (AUTO_LEARN_DISABLED=true|1) is active. */
export function isAutoLearnDisabled() {
    return process.env.AUTO_LEARN_DISABLED === 'true' || process.env.AUTO_LEARN_DISABLED === '1';
}
