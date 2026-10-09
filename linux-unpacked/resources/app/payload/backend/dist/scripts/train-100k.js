/**
 * Train Venorica with 100,000 iterations on diverse patterns from the massive dataset
 * Usage: npx tsx src/scripts/train-100k.ts [iterations]
 */
import * as fs from 'fs';
import * as path from 'path';
import * as glob from 'glob';
import { rnnEngine } from '../neural/trainer.js';
import { knowledgeStore } from '../knowledge/knowledgeStore.js';
import { perplexityOf, fmtPpl, describeImprovement } from './trainingMetrics.js';
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const SHEETS_DIR = path.join(PROJECT_ROOT, 'llm-training-app', 'data', 'uploads');
const rawIters = parseInt(process.argv[2] || '100000', 10);
const ITERATIONS = isNaN(rawIters) || rawIters < 1 ? 100000 : rawIters;
async function main() {
    console.log('╔══════════════════════════════════════════════════════════════╗');
    console.log('║    Venorica — 100K Iterations on Diverse Patterns          ║');
    console.log('╚══════════════════════════════════════════════════════════════╝\n');
    // Show pre-training status
    const pre = rnnEngine.getStatus();
    console.log(`📊 Pre-training: ${pre.iterations ?? 0} iters, loss: ${pre.loss ?? 'N/A'}, ppl: ${fmtPpl(perplexityOf(pre))}\n`);
    // Find all massive sheets
    const sheetFiles = glob.sync(path.join(SHEETS_DIR, 'venorica-massive-*.jsonl')).sort();
    console.log(`📁 Found ${sheetFiles.length} massive sheets`);
    // Sample 200 patterns evenly across all sheets for maximum diversity
    const maxSamples = 200;
    const totalLines = [];
    if (sheetFiles.length === 0) {
        console.log('⚠️ No massive sheets found, using existing patterns');
    }
    else {
        const linesPerSheet = Math.ceil(maxSamples / sheetFiles.length);
        for (const sf of sheetFiles) {
            const content = fs.readFileSync(sf, 'utf-8');
            const lines = content.trim().split('\n').filter(l => l.trim());
            // Take evenly distributed lines from each sheet
            const step = Math.max(1, Math.floor(lines.length / linesPerSheet));
            for (let i = 0; i < lines.length && totalLines.length < maxSamples; i += step) {
                totalLines.push(lines[i]);
            }
            if (totalLines.length >= maxSamples)
                break;
        }
    }
    // Parse and load patterns
    const patterns = totalLines.map((line, idx) => {
        try {
            const parsed = JSON.parse(line);
            return {
                code: parsed.text,
                language: parsed.language || 'unknown',
                title: parsed.title || `pattern-${idx}`,
                tags: parsed.tags || [],
                source: 'massive-100k-training',
            };
        }
        catch {
            return null;
        }
    }).filter(Boolean);
    console.log(`📚 Loaded ${patterns.length} diverse patterns into knowledge store`);
    // Load into knowledge store
    knowledgeStore.batchAddPatterns(patterns);
    // Check status after loading
    const loaded = rnnEngine.getStatus();
    console.log(`   Vocab: ${loaded.vocabSize} chars, hidden: ${loaded.hiddenSize} neurons\n`);
    // 🧠 RUN TRAINING
    console.log(`🧠 Training for ${ITERATIONS.toLocaleString()} iterations...`);
    console.log(`   (This will take ~${Math.round(ITERATIONS / 100)} seconds)\n`);
    const startTime = Date.now();
    const result = await rnnEngine.learnFromKnowledge(ITERATIONS);
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    console.log(`\n✅ Training complete in ${elapsed}s`);
    // Post-training status
    const post = rnnEngine.getStatus();
    console.log(`\n📊 Post-training:`);
    console.log(`   Iterations:  ${post.iterations}`);
    console.log(`   Loss:        ${post.loss?.toFixed(4) ?? 'N/A'}`);
    console.log(`   Perplexity:  ${fmtPpl(perplexityOf(post))}`);
    console.log(`   Trained:     ${post.trainedChars?.toLocaleString() ?? 0} chars`);
    // Improvement on PERPLEXITY (vocab-independent) — see trainingMetrics.ts for
    // why raw-loss deltas are misleading across tokenizer vocab changes.
    console.log(`   Improvement: ${describeImprovement(pre, post)}`);
    // Understanding score (perplexity vs random-vocab baseline)
    const ppl = perplexityOf(post);
    if (ppl !== null && post.vocabSize) {
        const randomP = post.vocabSize;
        const understanding = Math.max(0, Math.min(100, ((randomP - ppl) / randomP) * 100));
        console.log(`   Understanding: ${understanding.toFixed(2)}%`);
    }
    // Generation samples
    console.log(`\n🔮 Generation Samples:`);
    for (const seed of ['import', 'function', 'const', 'class', 'interface']) {
        try {
            const output = rnnEngine.generate(seed, 120, 0.5);
            const preview = output.replace(/\n/g, '↵ ').substring(0, 100);
            console.log(`   "${seed}": ${preview}...`);
        }
        catch (err) {
            console.log(`   "${seed}": ❌ ${err}`);
        }
    }
}
main().catch(err => {
    console.error('❌ Training failed:', err);
    process.exit(1);
});
