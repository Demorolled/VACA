/**
 * Venorica Massive Training — Cycle Through All 300 MB of Patterns
 *
 * Loads patterns from massive JSONL sheets in batches of 100,
 * trains on each batch, and cycles through the full dataset.
 *
 * Usage: npx tsx src/scripts/train-massive.ts [iterations_per_batch] [max_batches]
 *
 * Defaults: 500 iterations per batch, all batches
 */
import * as fs from 'fs';
import * as path from 'path';
import * as glob from 'glob';
import { rnnEngine } from '../neural/trainer.js';
import { knowledgeStore } from '../knowledge/knowledgeStore.js';
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const PROJECT_ROOT = path.resolve(BACKEND_DIR, '..');
const SHEETS_DIR = path.join(PROJECT_ROOT, 'llm-training-app', 'data', 'uploads');
const rawIters = parseInt(process.argv[2] || '500', 10);
const rawBatches = parseInt(process.argv[3] || '999999', 10);
const ITERS_PER_BATCH = isNaN(rawIters) || rawIters < 1 ? 500 : rawIters;
const MAX_BATCHES = isNaN(rawBatches) || rawBatches < 1 ? 999999 : rawBatches;
async function main() {
    console.log('╔══════════════════════════════════════════════════════════════╗');
    console.log('║    Venorica Massive Training — All 300 MB of Patterns      ║');
    console.log('╚══════════════════════════════════════════════════════════════╝');
    console.log();
    // Find all massive JSONL sheets
    const sheetPattern = path.join(SHEETS_DIR, 'venorica-massive-*.jsonl');
    const sheetFiles = glob.sync(sheetPattern).sort();
    console.log(`  Found ${sheetFiles.length} massive JSONL sheets in ${SHEETS_DIR}`);
    // Also find existing venorica sheets
    const existingPattern = path.join(SHEETS_DIR, 'venorica-sheet-*.jsonl');
    const existingSheets = glob.sync(existingPattern).sort();
    const allSheets = [...sheetFiles, ...existingSheets];
    console.log(`  Total sheets (including existing): ${allSheets.length}`);
    // Count total entries
    let totalEntries = 0;
    let totalBytes = 0;
    for (const sheet of allSheets) {
        const stat = fs.statSync(sheet);
        totalBytes += stat.size;
        const content = fs.readFileSync(sheet, 'utf-8');
        const lines = content.trim().split('\n').filter(l => l.trim());
        totalEntries += lines.length;
    }
    console.log(`  Total entries: ${totalEntries.toLocaleString()}`);
    console.log(`  Total dataset: ${(totalBytes / 1024 / 1024).toFixed(1)} MB`);
    console.log();
    // Show pre-training status
    const status = rnnEngine.getStatus();
    console.log('📊 Pre-training Status:');
    console.log(`  Vocab:       ${status.vocabSize} chars`);
    console.log(`  Hidden:      ${status.hiddenSize} neurons`);
    console.log(`  Iterations:  ${status.iterations}`);
    console.log(`  Loss:        ${status.loss ?? 'N/A'}`);
    console.log(`  Trained:     ${status.trainedChars?.toLocaleString() ?? 0} chars`);
    console.log();
    const BATCH_SIZE = 100;
    const SHEET_CACHE = [];
    // Read all sheets into memory (batch by batch)
    for (const sheet of allSheets) {
        const content = fs.readFileSync(sheet, 'utf-8');
        const lines = content.trim().split('\n').filter(l => l.trim());
        SHEET_CACHE.push(lines);
    }
    let totalIters = 0;
    let totalLoss = 0;
    let batchCount = 0;
    let currentLine = 0;
    const allLines = SHEET_CACHE.flat();
    const startTime = Date.now();
    console.log('🧠 Starting training cycle through all patterns...');
    console.log(`  ${ITERS_PER_BATCH} iterations per batch, ${BATCH_SIZE} patterns per batch`);
    console.log();
    while (batchCount < MAX_BATCHES && currentLine < allLines.length) {
        // Select a batch of patterns
        const batchLines = allLines.slice(currentLine, currentLine + BATCH_SIZE);
        if (batchLines.length === 0)
            break;
        // Parse patterns
        const patterns = batchLines.map((line, idx) => {
            try {
                const parsed = JSON.parse(line);
                return {
                    code: parsed.text,
                    language: parsed.language || 'unknown',
                    title: parsed.title || `pattern-${currentLine + idx}`,
                    tags: parsed.tags || [],
                    source: 'massive-dataset',
                };
            }
            catch {
                return null;
            }
        }).filter(Boolean);
        if (patterns.length === 0) {
            currentLine += BATCH_SIZE;
            continue;
        }
        // Load into knowledge store using batch mode
        knowledgeStore.batchAddPatterns(patterns);
        // Train on this batch
        const result = await rnnEngine.learnFromKnowledge(ITERS_PER_BATCH);
        totalIters += ITERS_PER_BATCH;
        totalLoss += result.loss;
        batchCount++;
        currentLine += BATCH_SIZE;
        const pct = Math.min(100, (currentLine / allLines.length * 100)).toFixed(1);
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        process.stdout.write(`\r  Batch ${batchCount}: ${patterns.length} patterns, ` +
            `loss: ${result.loss.toFixed(2)}, ` +
            `progress: ${pct}% ` +
            `(${(currentLine / 1000).toFixed(0)}K / ${(allLines.length / 1000).toFixed(0)}K patterns) ` +
            `- ${elapsed}s`);
    }
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    const avgLoss = batchCount > 0 ? (totalLoss / batchCount) : 0;
    console.log();
    console.log();
    console.log('='.repeat(55));
    console.log('  TRAINING COMPLETE');
    console.log('='.repeat(55));
    console.log(`  Total time:       ${elapsed}s`);
    console.log(`  Batches trained:  ${batchCount}`);
    console.log(`  Total iterations: ${totalIters}`);
    console.log(`  Avg loss:         ${avgLoss.toFixed(2)}`);
    console.log(`  Patterns seen:    ${currentLine.toLocaleString()} / ${allLines.length.toLocaleString()}`);
    // Show post-training status
    const postStatus = rnnEngine.getStatus();
    console.log();
    console.log('📊 Post-training Status:');
    console.log(`  Vocab:       ${postStatus.vocabSize} chars`);
    console.log(`  Hidden:      ${postStatus.hiddenSize} neurons`);
    console.log(`  Iterations:  ${postStatus.iterations}`);
    console.log(`  Loss:        ${postStatus.loss ?? 'N/A'}`);
    console.log(`  Trained:     ${postStatus.trainedChars?.toLocaleString() ?? 0} chars`);
    console.log();
    // Calculate understanding score
    if (postStatus.loss !== null && postStatus.vocabSize) {
        const randomLoss = Math.log(postStatus.vocabSize);
        const understanding = Math.max(0, Math.min(100, (1 - postStatus.loss / randomLoss) * 100));
        console.log(`📈 Understanding Score: ${understanding.toFixed(2)}%`);
        console.log(`    (Random guessing would be ${randomLoss.toFixed(2)}, our loss is ${postStatus.loss.toFixed(2)})`);
    }
    // Generate a sample
    console.log();
    console.log('🔮 Generation Samples:');
    const seeds = ['import', 'function', 'class', 'const'];
    for (const seed of seeds) {
        try {
            const output = rnnEngine.generate(seed, 150, 0.6);
            console.log(`  Seed "${seed}": ${output.substring(0, 120)}...`);
        }
        catch (err) {
            console.log(`  Seed "${seed}": ❌ Error - ${err}`);
        }
    }
    console.log();
    console.log('✅ Done!');
    console.log(`   To continue training: npx tsx src/scripts/train-massive.ts ${ITERS_PER_BATCH}`);
    console.log(`   To test: npx tsx src/scripts/test-venorica.ts`);
}
main().catch(err => {
    console.error('Training failed:', err);
    process.exit(1);
});
