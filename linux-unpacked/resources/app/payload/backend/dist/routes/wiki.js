/**
 * Wiki routes — serve the VACA wiki (modelVeronice.txt) to the frontend so
 * the chat's "show your wiki" opens a REAL view of it instead of the LLM
 * just claiming one (same pattern as the session-history window).
 *
 * GET /api/wiki → { success, sections: [{ number, title, body }], totalSections, lastUpdated }
 */
import { Router } from 'express';
import { readFileSync, existsSync, statSync } from 'fs';
import { resolve } from 'path';
export const WIKI_PATH = process.env.VACA_WIKI_PATH ||
    resolve(import.meta.dirname, '..', '..', '..', 'modelVeronice.txt');
/**
 * Parse the wiki into numbered sections. A section header is an "NN. TITLE"
 * line preceded by a "====…" separator line; the title may span multiple
 * lines and ends at the NEXT separator line:
 *
 *   ======================================================================
 *   1. PROJECT OVERVIEW
 *   ======================================================================
 *   <body…>
 *
 *   ======================================================================
 *   44. A MULTI-LINE TITLE — …
 *       CONTINUES HERE (CHANGES 31-36)
 *   ======================================================================
 *   <body…>
 *
 * Bodies may contain their own numbered lists ("1. PASSWORD MANAGERS …"), so
 * only "NN. TITLE" lines immediately preceded by a separator are treated as
 * section headers. Sections may or may not carry an "END OF SECTION NN"
 * marker (older ones don't — a following header ends them).
 */
export function parseWikiSections(text) {
    const lines = text.split('\n');
    const sections = [];
    let current = null;
    let currentLines = [];
    // Highest section number seen so far — used by the fallback header rule
    // (bodies may contain their own numbered lists like "1. PASSWORD MANAGERS",
    // but section numbers are monotonic and larger than any body list).
    let maxSeen = 0;
    const isSeparator = (line) => /^={5,}\s*$/.test(line.trim());
    const flush = () => {
        if (current) {
            current.body = currentLines.join('\n').replace(/^\n+|\n+$/g, '');
            sections.push(current);
            current = null;
        }
        currentLines = [];
    };
    const startSection = (number, title) => {
        flush();
        current = { number, title, body: '' };
        if (number > maxSeen)
            maxSeen = number;
    };
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const isSep = isSeparator(line);
        if (isSep) {
            const titleLine = lines[i + 1] || '';
            const titleMatch = titleLine.match(/^(\d{1,2})\.\s+(.+)$/);
            if (titleMatch) {
                // Title may wrap onto following INDENTED lines (continuations like
                // "    CLAIMS AUDIT, …"); it ends at the next separator. A column-0
                // line (e.g. another "NN. TITLE" header) or a blank line stops it —
                // those mean the separator actually closed the previous section and
                // the fallback rule below picks the header up instead.
                let j = i + 1;
                const titleParts = [titleMatch[2].trim()];
                while (j + 1 < lines.length) {
                    const nxt = lines[j + 1];
                    if (isSeparator(nxt))
                        break;
                    if (!/^\s/.test(nxt) || nxt.trim() === '')
                        break;
                    j += 1;
                    titleParts.push(nxt.trim());
                }
                if (j + 1 < lines.length && isSeparator(lines[j + 1])) {
                    startSection(parseInt(titleMatch[1], 10), titleParts.join(' ').replace(/\s+/g, ' '));
                    i = j + 1; // skip title lines + closing separator
                    continue;
                }
            }
        }
        // Fallback: a "NN. TITLE" header with no leading separator (older
        // hand-appended sections like 49–51). Only fires when the number is
        // larger than every section seen so far, so body numbered lists (always
        // small, e.g. "1. PASSWORD MANAGERS…") are never mistaken for headers.
        const fallback = line.match(/^(\d{1,2})\.\s+([A-Z][^\n]{3,})$/);
        if (fallback && parseInt(fallback[1], 10) > maxSeen) {
            startSection(parseInt(fallback[1], 10), fallback[2].trim());
            continue;
        }
        if (current) {
            if (/^END OF SECTION \d+/i.test(line.trim())) {
                flush();
                continue;
            }
            currentLines.push(line);
        }
    }
    flush();
    return sections;
}
export const wikiRoutes = Router();
wikiRoutes.get('/', (_req, res) => {
    try {
        if (!existsSync(WIKI_PATH)) {
            res.status(404).json({ success: false, error: 'Wiki file not found' });
            return;
        }
        const text = readFileSync(WIKI_PATH, 'utf-8');
        const sections = parseWikiSections(text);
        let lastUpdated = null;
        try {
            lastUpdated = statSync(WIKI_PATH).mtime.toISOString();
        }
        catch {
            // mtime unavailable — omit
        }
        res.json({ success: true, sections, totalSections: sections.length, lastUpdated });
    }
    catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});
