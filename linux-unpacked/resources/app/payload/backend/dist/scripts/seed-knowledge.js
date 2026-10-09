/**
 * seed-knowledge — add the curated Rust/C++/Go/Java patterns AND the
 * Rosetta Code corpus patterns to the knowledge store (idempotent; run after
 * checkout or whenever the curated set changes).
 *
 *   cd backend && npm run seed:knowledge
 *
 * Run `npm run fetch:rosetta` first (or commit the generated
 * `src/knowledge/rosettaCorpus.json`) to populate the non-TS worked examples.
 */
import { knowledgeStore } from '../knowledge/knowledgeStore.js';
import { seedCuratedLanguagePatterns } from '../knowledge/curatedLanguagePatterns.js';
import { seedRosettaPatterns, loadRosettaCorpus } from '../knowledge/rosettaPatterns.js';
const before = knowledgeStore.count();
const { added, skipped } = seedCuratedLanguagePatterns({ store: knowledgeStore });
console.log(`\nKnowledge store: ${before} → ${knowledgeStore.count()} pattern(s)`);
if (added.length) {
    console.log(`Added ${added.length} curated pattern(s):`);
    for (const title of added)
        console.log(`  + ${title}`);
}
else {
    console.log('No curated patterns added.');
}
console.log(`Skipped ${skipped} curated (already present or rejected by the quality gate).`);
const corpus = loadRosettaCorpus();
if (corpus.length === 0) {
    console.log('\nNo Rosetta corpus found — run `npm run fetch:rosetta` to generate it.');
}
else {
    const rosetta = seedRosettaPatterns({ store: knowledgeStore, corpus });
    console.log(`\nRosetta corpus: ${corpus.length} candidate(s) available.`);
    console.log(`Added ${rosetta.added.length} Rosetta pattern(s), skipped ${rosetta.skipped}.`);
    if (rosetta.truncated > 0) {
        console.log(`Truncated ${rosetta.truncated} (store head-room kept below the ${100}-pattern ` +
            'sheet cap, which would otherwise archive ALL patterns).');
    }
}
console.log(`\nKnowledge store now holds ${knowledgeStore.count()} pattern(s).\n`);
