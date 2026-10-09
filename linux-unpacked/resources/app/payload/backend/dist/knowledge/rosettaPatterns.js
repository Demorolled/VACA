/**
 * rosettaPatterns — seed the knowledge store from the committed Rosetta Code
 * corpus (`rosettaCorpus.json`, produced by `npm run fetch:rosetta`).
 *
 * Same contract as `seedCuratedLanguagePatterns`: idempotent (matched by
 * title), never throws on a rejected pattern.
 *
 * ONE extra guard matters here. `knowledgeStore.addPattern` ARCHIVES and CLEARS
 * the whole store the moment it reaches `KnowledgeStore.SHEET_CAP` (100). A
 * bulk import that crosses the cap would silently rotate every previously
 * learned pattern out. So this seeds at most `sheetCap - existing - margin`
 * patterns, round-robin across languages so no language is starved, and
 * reports what it truncated.
 */
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { ROSETTA_TARGETS } from './rosettaCode.js';
const DEFAULT_CORPUS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'rosettaCorpus.json');
/**
 * Remove every previously imported Rosetta pattern. Titles are one-per
 * (task, language), so when `ROSETTA_TASKS` changes the new titles do not
 * collide with the old ones, so `seedRosettaPatterns` would ADD alongside them
 * instead of replacing them and the store count would only grow. Call this
 * first when re-seeding a changed corpus.
 */
export function clearRosettaPatterns(store) {
    const doomed = store.getAll().filter((p) => p.projectId === 'rosetta');
    if (typeof store.deletePattern !== 'function')
        return 0;
    let removed = 0;
    for (const p of doomed) {
        if (store.deletePattern(p.id))
            removed += 1;
    }
    return removed;
}
/** Load the committed corpus (empty array if it has not been fetched yet). */
export function loadRosettaCorpus(file = DEFAULT_CORPUS) {
    if (!fs.existsSync(file))
        return [];
    try {
        const parsed = JSON.parse(fs.readFileSync(file, 'utf-8'));
        return Array.isArray(parsed) ? parsed : [];
    }
    catch {
        return [];
    }
}
/** Interleave per-language buckets so a tight budget still covers every language. */
function roundRobin(corpus, maxPerLanguage) {
    const buckets = ROSETTA_TARGETS.map((t) => ({
        language: t.language,
        items: corpus.filter((p) => p.language === t.language).slice(0, maxPerLanguage),
    }));
    const out = [];
    const depth = Math.max(0, ...buckets.map((b) => b.items.length));
    for (let i = 0; i < depth; i++) {
        for (const b of buckets) {
            if (i < b.items.length)
                out.push(b.items[i]);
        }
    }
    return out;
}
export function seedRosettaPatterns(opts) {
    const corpus = opts.corpus ?? loadRosettaCorpus();
    const maxPerLanguage = opts.maxPerLanguage ?? 4;
    const sheetCap = opts.sheetCap ?? 100;
    const safetyMargin = opts.safetyMargin ?? 5;
    const existing = new Set(opts.store.getAll().map((p) => p.title));
    const selected = roundRobin(corpus, maxPerLanguage);
    const candidates = selected.filter((p) => !existing.has(p.title));
    const room = Math.max(0, sheetCap - safetyMargin - opts.store.getAll().length);
    // Already-present patterns count as skipped, matching seedCuratedLanguagePatterns.
    let skipped = selected.length - candidates.length;
    const toAdd = candidates.slice(0, room);
    const truncated = candidates.length - toAdd.length;
    if (toAdd.length > 0 && typeof opts.store.batchAddPatterns === 'function') {
        const stored = opts.store.batchAddPatterns(toAdd);
        skipped += toAdd.length - stored.length;
        return { added: stored.map((p) => p.title), skipped, truncated };
    }
    const added = [];
    for (const pattern of toAdd) {
        const stored = opts.store.addPattern(pattern);
        if (stored) {
            added.push(pattern.title);
            existing.add(pattern.title);
        }
        else {
            skipped += 1;
        }
    }
    return { added, skipped, truncated };
}
