/**
 * Extended Venorica RNN Training
 *
 * Runs 10,000 more iterations on the current model and compares loss.
 * Run with: npx tsx backend/src/scripts/extend-training.ts
 */
import * as path from 'path';
import { rnnEngine } from '../neural/trainer.js';
import { perplexityOf, fmtPpl, describeImprovement } from './trainingMetrics.js';
async function main() {
    const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
    const MODEL_PATH = path.join(BACKEND_DIR, 'knowledge', 'rnn-model.json');
    console.log('='.repeat(70));
    console.log('  Venorica RNN — Extended Training (10,000 more iterations)');
    console.log('='.repeat(70));
    // Show pre-training status
    const preStatus = rnnEngine.getStatus();
    console.log('\n📊 PRE-TRAINING STATUS:');
    console.log(`  Iterations so far:  ${preStatus.iterations}`);
    console.log(`  Current loss:       ${preStatus.loss?.toFixed(4) ?? 'N/A'}`);
    console.log(`  Perplexity:         ${fmtPpl(perplexityOf(preStatus))}`);
    console.log(`  Trained chars:      ${(preStatus.trainedChars ?? 0).toLocaleString()}`);
    console.log(`  Vocabulary size:    ${preStatus.vocabSize}`);
    console.log(`  Pattern count:      ${preStatus.patternCount}`);
    // Generate pre-training samples
    console.log(`\n${'='.repeat(70)}`);
    console.log('  PRE-TRAINING GENERATION SAMPLES');
    console.log(`  ${'='.repeat(70)}`);
    const seeds = [
        { seed: 'import', temp: 0.6, label: 'Seed: "import" (temp=0.6)' },
        { seed: 'function', temp: 0.4, label: 'Seed: "function" (temp=0.4)' },
        { seed: 'const', temp: 0.8, label: 'Seed: "const" (temp=0.8)' },
        { seed: 'export', temp: 0.5, label: 'Seed: "export" (temp=0.5)' },
        { seed: 'class', temp: 0.6, label: 'Seed: "class" (temp=0.6)' },
        { seed: 'interface', temp: 0.3, label: 'Seed: "interface" (temp=0.3, low entropy)' },
    ];
    for (const { seed, temp, label } of seeds) {
        try {
            const output = rnnEngine.generate(seed, 200, temp);
            console.log(`\n--- ${label} ---`);
            console.log(output.substring(0, 250).replace(/\n/g, '\\n'));
        }
        catch (e) {
            console.log(`\n--- ${label} --- Error: ${e.message}`);
        }
    }
    // Run extended training
    const ADDITIONAL_ITERATIONS = 10000;
    console.log(`\n${'='.repeat(70)}`);
    console.log(`  🚀 Training for ${ADDITIONAL_ITERATIONS.toLocaleString()} more iterations...`);
    console.log(`  ${'='.repeat(70)}`);
    const startTime = Date.now();
    try {
        const result = await rnnEngine.learnFromKnowledge(ADDITIONAL_ITERATIONS);
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        // Show post-training status
        const postStatus = rnnEngine.getStatus();
        console.log(`\n✅ TRAINING COMPLETE (${elapsed}s)`);
        console.log('='.repeat(70));
        console.log('  PERPLEXITY COMPARISON (vocab-independent — see trainingMetrics.ts)');
        console.log('  ' + '-'.repeat(50));
        console.log(`  Before:  loss ${(preStatus.loss ?? 0).toFixed(4)}, ppl ${fmtPpl(perplexityOf(preStatus))} (after ${preStatus.iterations} iters)`);
        console.log(`  After:   loss ${(postStatus.loss ?? 0).toFixed(4)}, ppl ${fmtPpl(perplexityOf(postStatus))} (after ${postStatus.iterations} iters)`);
        console.log(`  Change:  ${describeImprovement(preStatus, postStatus)}`);
        console.log(`\n  OTHER METRICS:`);
        console.log(`  More characters:   ${result.chars.toLocaleString()}`);
        console.log(`  Total chars:       ${(postStatus.trainedChars ?? 0).toLocaleString()}`);
        console.log(`  Total iterations:  ${postStatus.iterations}`);
        // Generate post-training samples
        console.log(`\n${'='.repeat(70)}`);
        console.log('  POST-TRAINING GENERATION SAMPLES');
        console.log(`  ${'='.repeat(70)}`);
        for (const { seed, temp, label } of seeds) {
            try {
                const output = rnnEngine.generate(seed, 200, temp);
                console.log(`\n--- ${label} ---`);
                console.log(output.substring(0, 250).replace(/\n/g, '\\n'));
            }
            catch (e) {
                console.log(`\n--- ${label} --- Error: ${e.message}`);
            }
        }
        // Summary
        console.log(`\n${'='.repeat(70)}`);
        console.log('  SUMMARY');
        console.log(`  ${'='.repeat(70)}`);
        console.log(`  Training time:     ${elapsed}s`);
        console.log(`  Loss:              ${(preStatus.loss ?? 0).toFixed(4)} → ${(postStatus.loss ?? 0).toFixed(4)}`);
        console.log(`  Perplexity:        ${fmtPpl(perplexityOf(preStatus))} → ${fmtPpl(perplexityOf(postStatus))}`);
        console.log(`  Improvement:       ${describeImprovement(preStatus, postStatus)}`);
        console.log(`  Additional chars:  ${result.chars.toLocaleString()}`);
        console.log(`  Model saved at:    ${MODEL_PATH}`);
        console.log(`\n✅ Extended training complete!`);
    }
    catch (err) {
        console.error(`\n❌ Training failed: ${err.message}`);
        process.exit(1);
    }
}
main().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});
