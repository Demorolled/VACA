/**
 * duplicateDeclarations — deterministic cross-file duplicate-declaration
 * resolution for the GENERATED non-TS sources.
 *
 * WHY THIS EXISTS
 * Each architecture node is generated as its own file, and with no wiring graph
 * (or a wiring graph that does not mention the shared domain model) nothing
 * tells a node which types it owns. Every node then declares the domain type it
 * needs, and the whole-project compile fails on the redeclaration. Measured on
 * the round-3 retest apps:
 *
 *   swift   swift-temp-log ....... 'TemperatureLog' in cli.swift AND stats.swift
 *                                 -> "invalid redeclaration of 'TemperatureLog'"
 *   csharp  csharp-budget-cli .... 'BudgetStore' in report.cs AND budget-store.cs
 *                                 -> "CS0101 ... already contains a definition"
 *                                 'BudgetEntry' in cli.cs AND budget-store.cs
 *   java    (smoke repair) ....... a second `class Board` -> "duplicate class"
 *
 * The gates REPORT those correctly — what was missing is the REMEDY. The only
 * one wired up is a bounded full-file LLM rewrite, which is not convergent for
 * this defect class: the model is not told which file OWNS the symbol, so it
 * deletes from the wrong file, renames, or re-emits — and it can even ADD a
 * duplicate (measured: a CLI smoke repair added a second `class Board`).
 *
 * WHAT THIS DOES
 * One language-aware pass over the finished file set that:
 *   1. extracts every top-level TYPE declaration (name + span + member set),
 *   2. groups by symbol,
 *   3. picks exactly ONE owner per symbol with a deterministic rule, then
 *   4. fixes the others — deterministic and LLM-free:
 *        DELETE the redundant copy when the owner's definition CONTAINS it, so
 *        every call still resolves against the owner;
 *        RENAME it when the two definitions genuinely diverge (the real
 *        swift/csharp apps: neither definition contains the other, so deleting
 *        either one would orphan its file's own calls).
 *
 * Step 4 is sufficient WITHOUT an import for the languages where the whole
 * project is one namespace: Swift (one module), C# (one assembly), Kotlin (one
 * module), Java (the scaffold never emits a `package`, so one package). Those
 * four are the ONLY languages considered — see RESOLVABLE_LANGS.
 *
 * Always deterministic. When neither fix is safe (another file consumes the
 * non-owner's API, or a declaration carries the program entry point) nothing is
 * mutated: the case is returned as an ATTRIBUTED failure naming the owner, so
 * the existing repair loop fixes it with the fact the old prompt never had.
 */
// ─── What may be resolved ────────────────────────────────────────────────
/**
 * Languages whose generated project is ONE namespace, so a type declared twice
 * is always a compile error AND fixing it needs no import.
 *
 * Deliberately excludes every other gateable language, because a cross-file
 * duplicate there is LEGAL or needs a different remedy:
 *   go / rust / python / ruby — every file is its own package/module/class
 *       scope, so the same type name in two of them is not a collision at all.
 *   c / cpp — a `struct` used by two translation units MUST exist in both
 *       (the one-definition rule), so removing one is a REGRESSION; a duplicate
 *       is not even an error. (A duplicated `main` is a different defect, owned
 *       by the scaffolder's entry-promotion rule.)
 */
const RESOLVABLE_LANGS = new Set(['swift', 'csharp', 'java', 'kotlin']);
/** Type-declaration keywords per language (global regexes; group 1 = name). */
const TYPE_PATTERNS = {
    swift: /\b(?:class|struct|enum|actor|protocol|typealias)\s+([A-Za-z_]\w*)/g,
    csharp: /\b(?:class|struct|interface|enum|record)\s+(?:class\s+|struct\s+)?([A-Za-z_]\w*)/g,
    java: /\b(?:class|interface|enum|record)\s+([A-Za-z_]\w*)/g,
    kotlin: /\b(?:class|object|interface)\s+([A-Za-z_]\w*)/g,
};
/** Declaration modifiers that belong to the declaration and are removed with it. */
const DECL_MODIFIERS = '(?:public|internal|private|protected|static|sealed|abstract|final|open|data|value|annotation|inner|partial|readonly|fileprivate|non-sealed|strictfp|export)';
/** Languages whose `#` starts a line comment (so a `#` is masked, not code). */
const HASH_COMMENT_LANGS = new Set(['python', 'ruby']);
/** Languages with triple-quoted strings. */
const TRIPLE_QUOTE_LANGS = new Set(['python', 'swift', 'kotlin']);
// ─── Masking ─────────────────────────────────────────────────────────────
/**
 * Blank out comments and string literals while KEEPING every offset (blanked
 * characters become spaces; newlines are preserved). Declaration spans are
 * computed on the mask and applied to the original content, so the two always
 * agree — a `class` inside a comment or a log string can never be "found".
 */
export function maskCommentsAndStrings(code, language) {
    const out = code.split('');
    const n = code.length;
    const blank = (from, to) => {
        for (let k = from; k < to && k < n; k++)
            if (out[k] !== '\n')
                out[k] = ' ';
    };
    let i = 0;
    while (i < n) {
        const c = code[i];
        const two = code.slice(i, i + 2);
        const three = code.slice(i, i + 3);
        // Line comments
        if (two === '//' || (c === '#' && HASH_COMMENT_LANGS.has(language))) {
            const nl = code.indexOf('\n', i);
            const stop = nl === -1 ? n : nl;
            blank(i, stop);
            i = stop;
            continue;
        }
        // Block comments
        if (two === '/*') {
            const end = code.indexOf('*/', i + 2);
            const stop = end === -1 ? n : end + 2;
            blank(i, stop);
            i = stop;
            continue;
        }
        // Triple-quoted strings (Python docstrings, Swift/Kotlin multiline)
        if ((three === '"""' || three === "'''") && TRIPLE_QUOTE_LANGS.has(language)) {
            const end = code.indexOf(three, i + 3);
            const stop = end === -1 ? n : end + 3;
            blank(i, stop);
            i = stop;
            continue;
        }
        // Verbatim strings (C# @"..." — `""` is an escaped quote, newlines allowed)
        if (c === '"' && language === 'csharp' && code[i - 1] === '@') {
            let k = i + 1;
            while (k < n) {
                if (code[k] === '"' && code[k + 1] === '"') {
                    k += 2;
                    continue;
                }
                if (code[k] === '"') {
                    k += 1;
                    break;
                }
                k += 1;
            }
            blank(i - 1, k);
            i = k;
            continue;
        }
        // Ordinary string / char literals
        if (c === '"' || c === "'") {
            const quote = c;
            let k = i + 1;
            while (k < n) {
                if (code[k] === '\\') {
                    k += 2;
                    continue;
                }
                if (code[k] === quote) {
                    k += 1;
                    break;
                }
                if (code[k] === '\n')
                    break; // unterminated on this line
                k += 1;
            }
            blank(i, k);
            i = k;
            continue;
        }
        i += 1;
    }
    return out.join('');
}
function escapeRe(s) {
    return (s || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
// ─── Declaration extraction ──────────────────────────────────────────────
/**
 * Normalize a member line so formatting can never change the comparison.
 * Both a brace and punctuation are stripped from the ENDS, so a one-line body
 * (`public class Row { }`) normalizes to the same token as the same declaration
 * written across lines — without this, an identical declaration compared as
 * divergent just because one was written inline and the other in Allman style.
 */
function normalizeMemberLine(line) {
    return line
        .replace(/\s+/g, '')
        .toLowerCase()
        .replace(/^[{}]+/, '')
        .replace(/[;,{}\]]+$/, '');
}
/** The set of "member-ish" lines inside a declaration body. */
export function memberSignatures(body) {
    const set = new Set();
    for (const raw of (body || '').split('\n')) {
        const line = raw.trim();
        if (!line)
            continue;
        if (/^[{}();,[\]]*$/.test(line))
            continue;
        if (!/[A-Za-z_]/.test(line))
            continue;
        const norm = normalizeMemberLine(line);
        if (norm.length > 2 && norm.length < 240)
            set.add(norm);
    }
    return set;
}
/** True when every member of `a` is also in `b`. */
function isSubset(a, b) {
    for (const x of a)
        if (!b.has(x))
            return false;
    return true;
}
/** Index just after the `}` matching the `{` at `open`. */
function braceMatchEnd(mask, open) {
    let depth = 0;
    for (let i = open; i < mask.length; i++) {
        if (mask[i] === '{')
            depth += 1;
        else if (mask[i] === '}') {
            depth -= 1;
            if (depth === 0)
                return i + 1;
        }
    }
    return mask.length;
}
/**
 * The start of the declaration: the line start when everything before the
 * keyword on that line is just modifiers (`public class Foo`), else the
 * keyword itself. Deleting from the line start keeps `public` from dangling.
 */
function declarationStart(content, keywordIndex) {
    const lineStart = content.lastIndexOf('\n', keywordIndex - 1) + 1;
    const prefix = content.slice(lineStart, keywordIndex);
    const modifiersOnly = new RegExp(`^[ \\t]*${DECL_MODIFIERS}\\s+(?:${DECL_MODIFIERS}\\s+)*$`);
    return modifiersOnly.test(prefix) ? lineStart : keywordIndex;
}
/**
 * The whole-declaration span for a type whose NAME ends at `nameEnd`.
 *
 * Handles the shapes the generator produces: `class Foo {` / `class Foo: Bar {`
 * (Swift), `class Foo(...) {` (Kotlin primary ctor), `public record Foo(int A);`
 * (C# positional record — no body), and Allman braces on the next line. A bare
 * `class Foo` with neither a body nor a base list ends at its own line, so the
 * NEXT declaration's `{` can never be swallowed.
 */
function declarationEnd(mask, nameEnd) {
    const WINDOW = 12_000;
    const limit = Math.min(mask.length, nameEnd + WINDOW);
    const firstNl = mask.indexOf('\n', nameEnd);
    const segEnd = firstNl === -1 ? mask.length : firstNl;
    const seg = mask.slice(nameEnd, segEnd);
    if (!/[{(:,]/.test(seg)) {
        const rest = mask.slice(segEnd).replace(/^\n/, '');
        const nlAfter = rest.indexOf('\n');
        const nextLine = (nlAfter === -1 ? rest : rest.slice(0, nlAfter)).trim();
        const continues = nextLine.startsWith('{') ||
            nextLine.startsWith(':') ||
            /^(?:extends|implements|where|\(|,)/.test(nextLine);
        if (!continues)
            return segEnd;
    }
    let paren = 0;
    for (let i = nameEnd; i < limit; i++) {
        const ch = mask[i];
        if (ch === '(')
            paren += 1;
        else if (ch === ')')
            paren = Math.max(0, paren - 1);
        else if (ch === '{' && paren === 0)
            return braceMatchEnd(mask, i);
        else if (ch === ';' && paren === 0)
            return i + 1;
    }
    return segEnd;
}
/** Every top-level type declaration in one file, with its span and members. */
export function extractTypeDeclarations(content, language) {
    const lang = (language || '').toLowerCase();
    const pattern = TYPE_PATTERNS[lang];
    if (!pattern)
        return [];
    const mask = maskCommentsAndStrings(content || '', lang);
    const re = new RegExp(pattern.source, 'g');
    const out = [];
    let m;
    while ((m = re.exec(mask)) !== null) {
        const raw = m[1];
        const nameStart = m.index + m[0].lastIndexOf(raw);
        const nameEnd = nameStart + raw.length;
        const start = declarationStart(content, m.index);
        const end = declarationEnd(mask, nameEnd);
        if (end <= start)
            continue;
        const body = content.slice(start, end);
        out.push({ raw, start, end, members: memberSignatures(body), bodyLength: body.length });
    }
    return out;
}
// ─── Entry-point guard ───────────────────────────────────────────────────
/**
 * True when this declaration's body carries the PROGRAM entry point. Entry
 * ownership is the scaffolder's `promotedEntryOwner` rule (and the only way to
 * report "two nodes both define the program" is to leave it alone), so the
 * resolver never touches a declaration that holds one.
 */
export function declarationCarriesProgramEntry(body, language) {
    const text = maskCommentsAndStrings(body, language);
    switch ((language || '').toLowerCase()) {
        case 'csharp':
            return /\bstatic\s+(?:async\s+)?(?:void|int|Task(?:<int>)?)\s+Main\s*\(/.test(text);
        case 'swift':
            // Only main.swift may hold top-level code, so a Swift type never does.
            return false;
        case 'java':
            return /\bpublic\s+static\s+void\s+main\s*\(\s*String/.test(text);
        case 'kotlin':
            // A `fun main` inside a class is not the module entry, so nothing here.
            return false;
        default:
            return false;
    }
}
// ─── Ownership ───────────────────────────────────────────────────────────
function normalizeToken(s) {
    return (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}
/** Normalized path stems: every directory name plus the file name without extension. */
function pathStems(filePath) {
    return (filePath || '')
        .replace(/\\/g, '/')
        .split('/')
        .filter(Boolean)
        .map((part) => normalizeToken(part.replace(/\.[^.]+$/, '')))
        .filter(Boolean);
}
/**
 * The PascalCase node name a scaffold path belongs to (`src/budget-store/x.cs`
 * -> `BudgetStore`) — used to build a unique rename target that reads as
 * belonging to the file it now lives in.
 */
export function nodeStemFromPath(filePath) {
    const parts = (filePath || '').replace(/\\/g, '/').split('/').filter(Boolean);
    const dir = parts.length >= 2 ? parts[parts.length - 2] : '';
    const base = dir || (parts[parts.length - 1] || '').replace(/\.[^.]+$/, '');
    return (base || '')
        .split(/[^A-Za-z0-9]+/)
        .filter(Boolean)
        .map((p) => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase())
        .join('');
}
/** The explicit `package a.b;` a Java file declares, '' when it declares none. */
function javaPackage(content) {
    const m = /^\s*package\s+([\w.]+)\s*;/m.exec(content || '');
    return m ? m[1] : '';
}
/**
 * Pick the single owner of a duplicated symbol. Deterministic, functional
 * before cosmetic:
 *   1. THE SUPER-SET. If exactly one declaration's members contain every
 *      other's, IT owns the name — every caller then still compiles after the
 *      others are deleted. (Measured: stats.swift's TemperatureLog carried the
 *      members the cli's had.)
 *   2. The node whose LABEL derives the symbol (`budget-store` -> `BudgetStore`).
 *   3. The node whose DESCRIPTION names the symbol.
 *   4. The most complete declaration (member count, then body length).
 *   5. The lowest path, so the choice is reproducible on any machine.
 */
export function pickDuplicateOwner(entries) {
    const supersets = entries.filter((e) => entries.every((o) => isSubset(o.decl.members, e.decl.members)));
    if (supersets.length === 1)
        return supersets[0];
    const symbol = normalizeToken(entries[0].decl.raw);
    const byLabel = entries.filter((e) => pathStems(e.path).includes(symbol));
    if (byLabel.length === 1)
        return byLabel[0];
    const word = new RegExp(`\\b${escapeRe(entries[0].decl.raw)}\\b`, 'i');
    const byDescription = entries.filter((e) => word.test(e.summary || ''));
    if (byDescription.length === 1)
        return byDescription[0];
    return [...entries].sort((a, b) => b.decl.members.size - a.decl.members.size ||
        b.decl.bodyLength - a.decl.bodyLength ||
        a.path.localeCompare(b.path))[0];
}
/**
 * True when every OTHER declaration is contained in the owner's, so deleting
 * them cannot orphan a call — a use in the removed file still resolves against
 * the owner's (larger) definition. False means the definitions genuinely
 * diverge and only a RENAME preserves both files' behaviour.
 */
export function deletingOthersIsSafe(entries, owner) {
    return entries.every((e) => e === owner || isSubset(e.decl.members, owner.decl.members));
}
/**
 * References to `name` that a RENAME would leave broken — i.e. real uses of the
 * declaration's API. A bare type witness (`X.self`, `X.class`, `X::class`,
 * `typeof(X)`) carries no API, so it is benign: after the rename it simply
 * resolves to the surviving declaration.
 */
export function nonBenignReferenceCount(content, language, name) {
    const mask = maskCommentsAndStrings(content, language);
    const esc = escapeRe(name);
    const all = (mask.match(new RegExp(`\\b${esc}\\b`, 'g')) || []).length;
    const benign = (mask.match(new RegExp(`\\b${esc}\\s*\\.\\s*(?:self|class|Type)\\b`, 'g')) || []).length +
        (mask.match(new RegExp(`typeof\\s*\\(\\s*${esc}\\s*\\)`, 'g')) || []).length +
        (mask.match(new RegExp(`\\b${esc}\\s*::\\s*class\\b`, 'g')) || []).length;
    return all - benign;
}
/** Replace every masked occurrence of `oldName` with `newName` (comments/strings untouched). */
export function renameTypeInContent(content, language, oldName, newName) {
    const mask = maskCommentsAndStrings(content, language);
    const re = new RegExp(`\\b${escapeRe(oldName)}\\b`, 'g');
    let out = '';
    let last = 0;
    let m;
    while ((m = re.exec(mask)) !== null) {
        out += content.slice(last, m.index) + newName;
        last = m.index + m[0].length;
    }
    return out + content.slice(last);
}
// ─── Resolution ──────────────────────────────────────────────────────────
/** Remove [start, end) and heal the join so no blank-line scar is left behind. */
function removeRange(content, start, end) {
    let before = content.slice(0, start).replace(/[ \t]+$/, '');
    if (before && !before.endsWith('\n'))
        before += '\n';
    const after = content.slice(end).replace(/^[ \t]*\r?\n/, '');
    return before + after;
}
/**
 * Resolve every cross-file (and intra-file) duplicate TYPE declaration in the
 * finished file set. Mutates `files[i].content` when a redundant declaration is
 * deleted or renamed, and the matching `contracts[i].exports` so the stub gate
 * does not then report a renamed/deleted type as an unimplemented export.
 */
export function resolveCrossFileDuplicates(files, contracts = []) {
    const notes = [];
    const failures = [];
    const changed = new Set();
    const hintByPath = new Map();
    for (const c of contracts)
        hintByPath.set(c.path, c);
    /** lang → symbol → candidates */
    const groups = new Map();
    const contentByPath = new Map();
    const langOfPath = new Map();
    /** Every type name in the project, so a rename target can never collide. */
    const takenNames = new Set();
    for (const f of files) {
        const lang = (hintByPath.get(f.path)?.language || '').toLowerCase();
        if (!RESOLVABLE_LANGS.has(lang))
            continue;
        langOfPath.set(f.path, lang);
        contentByPath.set(f.path, f.content);
        const decls = extractTypeDeclarations(f.content, lang);
        if (!decls.length)
            continue;
        let bySymbol = groups.get(lang);
        if (!bySymbol) {
            bySymbol = new Map();
            groups.set(lang, bySymbol);
        }
        for (const decl of decls) {
            takenNames.add(decl.raw);
            const list = bySymbol.get(decl.raw) || [];
            list.push({ path: f.path, decl, summary: hintByPath.get(f.path)?.summary || '' });
            bySymbol.set(decl.raw, list);
        }
    }
    const rewriteExports = (path, from, to) => {
        const hint = hintByPath.get(path);
        if (!hint || !Array.isArray(hint.exports))
            return;
        hint.exports = hint.exports.flatMap((n) => (n === from ? (to ? [to] : []) : [n]));
    };
    // Deletions are applied per file, from the END backwards, so earlier spans
    // stay valid while later ones are removed.
    const removals = new Map();
    for (const [lang, bySymbol] of groups) {
        for (const [symbol, entries] of bySymbol) {
            if (entries.length < 2)
                continue;
            // Two Java files are only in one namespace when they declare the same
            // package — the scaffold declares none, but a model that emits
            // `package a;` in one file and `package b;` in another is not a collision.
            if (lang === 'java') {
                const packages = new Set(entries.map((e) => javaPackage(contentByPath.get(e.path) || '')));
                if (packages.size > 1)
                    continue;
            }
            // The program entry point is never resolved away — two entries is a real
            // defect that the scaffolder's promotion rule reports.
            const carrier = entries.find((e) => declarationCarriesProgramEntry((contentByPath.get(e.path) || '').slice(e.decl.start, e.decl.end), lang));
            if (carrier) {
                for (const e of entries) {
                    if (e === carrier)
                        continue;
                    notes.push({ symbol, path: e.path, ownerPath: carrier.path, action: 'reported' });
                    failures.push(`${e.path}: '${symbol}' is also declared in ${carrier.path}, and one of those declarations holds the program entry point — leave exactly one definition with exactly one entry point.`);
                }
                continue;
            }
            const owner = pickDuplicateOwner(entries);
            const others = entries.filter((e) => e !== owner);
            const deleteMode = deletingOthersIsSafe(entries, owner);
            const declaringPaths = new Set(entries.map((e) => e.path));
            for (const e of others) {
                if (deleteMode) {
                    const list = removals.get(e.path) || [];
                    list.push({ start: e.decl.start, end: e.decl.end });
                    removals.set(e.path, list);
                    rewriteExports(e.path, symbol, null);
                    notes.push({ symbol, path: e.path, ownerPath: owner.path, action: 'deleted' });
                    continue;
                }
                // Divergent definitions: renaming keeps BOTH files' own behaviour. It
                // is only safe when no OTHER file consumes this declaration's API —
                // a bare `Type.self` elsewhere is fine (it just resolves to the owner).
                const consumers = files.filter((f) => f.path !== e.path && !declaringPaths.has(f.path) && langOfPath.get(f.path) === lang);
                const blocked = consumers.filter((f) => nonBenignReferenceCount(f.content, lang, symbol) > 0);
                if (blocked.length > 0) {
                    notes.push({ symbol, path: e.path, ownerPath: owner.path, action: 'reported' });
                    failures.push(`${e.path}: '${symbol}' is also declared in ${owner.path} and ${blocked
                        .map((f) => f.path)
                        .join(', ')} uses this definition — keep ONE definition (${owner.path}'s) and point the other file at it instead of redeclaring it.`);
                    continue;
                }
                const stem = nodeStemFromPath(e.path) || 'Local';
                let newName = `${stem}${symbol}`;
                let i = 2;
                while (takenNames.has(newName))
                    newName = `${stem}${symbol}${i++}`;
                takenNames.add(newName);
                const file = files.find((f) => f.path === e.path);
                if (!file)
                    continue;
                file.content = renameTypeInContent(file.content, lang, symbol, newName);
                contentByPath.set(e.path, file.content);
                changed.add(e.path);
                rewriteExports(e.path, symbol, newName);
                notes.push({ symbol, path: e.path, ownerPath: owner.path, action: 'renamed', newName });
            }
        }
    }
    for (const [filePath, spans] of removals) {
        const file = files.find((f) => f.path === filePath);
        if (!file)
            continue;
        let out = file.content;
        for (const span of [...spans].sort((a, b) => b.start - a.start)) {
            out = removeRange(out, span.start, span.end);
        }
        if (out !== file.content) {
            file.content = out;
            changed.add(filePath);
        }
    }
    return { notes, failures, changedPaths: [...changed] };
}
