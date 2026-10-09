/**
 * Wiki writer — appends auto-numbered sections to modelVeronice.txt (the
 * VACA wiki / long-term knowledge base). Used by the memory-write feature so
 * that "write this into your wiki" actually writes, instead of the LLM
 * hallucinating a file write.
 *
 * The wiki path is overridable via VACA_WIKI_PATH so tests can use a temp
 * file instead of the real wiki.
 */
import { readFileSync, appendFileSync, existsSync } from 'fs';
import path from 'path';
export const WIKI_PATH = process.env.VACA_WIKI_PATH ||
    path.resolve(import.meta.dirname, '..', '..', '..', 'modelVeronice.txt');
/** Find the highest existing "NN. " section number in the wiki. */
export function nextWikiSectionNumber(text) {
    const nums = [];
    for (const m of text.matchAll(/^\s*(\d{1,2})\.\s+[A-Z]/gm)) {
        nums.push(parseInt(m[1], 10));
    }
    return nums.length > 0 ? Math.max(...nums) + 1 : 1;
}
/** Format a section body (mirrors the wiki's existing "NN. TITLE" style). */
export function formatWikiSection(sectionNumber, topic, body) {
    const title = topic.trim();
    const sep = '='.repeat(70);
    return [
        '',
        sep,
        `${sectionNumber}. ${title}`,
        sep,
        '',
        body.trim(),
        '',
        sep,
        `END OF SECTION ${sectionNumber}`,
        sep,
        '',
    ].join('\n');
}
/**
 * Append a new numbered section to the wiki. Auto-numbers based on the
 * highest existing section. Throws on read/write failure.
 */
export function appendWikiSection(topic, body) {
    const existing = existsSync(WIKI_PATH) ? readFileSync(WIKI_PATH, 'utf-8') : '';
    const sectionNumber = nextWikiSectionNumber(existing);
    appendFileSync(WIKI_PATH, formatWikiSection(sectionNumber, topic, body), 'utf-8');
    return { sectionNumber, filePath: WIKI_PATH };
}
