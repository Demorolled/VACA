/**
 * fetch-rosetta — download the configured Rosetta Code tasks and write
 * `src/knowledge/rosettaCorpus.json`, the committed, network-free corpus that
 * `seedRosettaPatterns` seeds from.
 *
 *   cd backend && npm run fetch:rosetta
 *
 * Splitting fetch from seed keeps `seed:knowledge` runnable offline and makes
 * the imported snippets reviewable in a diff before they reach the store.
 *
 * Uses the MediaWiki API at https://rosettacode.org/w/api.php (the `/mw/` and
 * `/api.php` paths 404). Titles are batched 50 at a time.
 */
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { ROSETTA_TASKS, ROSETTA_TARGETS, buildRosettaPatterns, } from '../knowledge/rosettaCode.js';
const API = 'https://rosettacode.org/w/api.php';
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../knowledge/rosettaCorpus.json');
function chunk(items, size) {
    const out = [];
    for (let i = 0; i < items.length; i += size)
        out.push(items.slice(i, i + size));
    return out;
}
async function fetchPages(titles) {
    const pages = [];
    for (const batch of chunk(titles, 50)) {
        const url = `${API}?action=query&format=json&prop=revisions&rvprop=content&rvslots=main&redirects=1` +
            `&titles=${batch.map((t) => encodeURIComponent(t)).join('|')}`;
        const res = await fetch(url, { headers: { 'User-Agent': 'VACA-rosetta-importer/1.0' } });
        if (!res.ok)
            throw new Error(`Rosetta fetch failed: HTTP ${res.status} for ${batch.join(', ')}`);
        const json = (await res.json());
        for (const page of Object.values(json?.query?.pages || {})) {
            const wikitext = page?.revisions?.[0]?.slots?.main?.['*'];
            if (!wikitext)
                continue;
            pages.push({ task: page.title, wikitext });
        }
    }
    return pages;
}
async function main() {
    console.log(`Fetching ${ROSETTA_TASKS.length} Rosetta Code task page(s)…`);
    const pages = await fetchPages(ROSETTA_TASKS);
    console.log(`Got ${pages.length} page(s), ${pages.reduce((n, p) => n + p.wikitext.length, 0).toLocaleString()} chars of wikitext.`);
    const { patterns, rejected } = buildRosettaPatterns(pages);
    const langs = ROSETTA_TARGETS.map((t) => t.language);
    const perLang = new Map(langs.map((l) => [l, 0]));
    for (const p of patterns)
        perLang.set(p.language, (perLang.get(p.language) || 0) + 1);
    console.log(`\nExtracted ${patterns.length} pattern(s):`);
    for (const l of langs)
        console.log(`  ${l.padEnd(8)} ${perLang.get(l)}`);
    const missing = rejected.filter((r) => r.reason === 'no-section');
    if (missing.length) {
        console.log(`\nMissing sections (${missing.length}):`);
        for (const r of missing)
            console.log(`  ${r.task} — ${r.language}`);
    }
    fs.writeFileSync(OUT, JSON.stringify(patterns, null, 2) + '\n', 'utf-8');
    console.log(`\nWrote ${patterns.length} pattern(s) → ${path.relative(process.cwd(), OUT)}`);
}
main().catch((err) => {
    console.error(err);
    process.exit(1);
});
