/**
 * Venorica RNN — Background Training Script
 *
 * Loads the current model and patterns, trains for N iterations,
 * saves the model, and reports results.
 *
 * Run with: npx tsx backend/src/scripts/train-venorica.ts [iterations]
 */
import { rnnEngine } from '../neural/trainer.js';
import { perplexityOf, fmtPpl, describeImprovement } from './trainingMetrics.js';
const requestedIters = parseInt(process.argv[2] || '5000', 10);
const ITERATIONS = isNaN(requestedIters) || requestedIters < 1 ? 5000 : requestedIters;
async function main() {
    const startTime = Date.now();
    console.log('╔══════════════════════════════════════════════════════════════╗');
    console.log(`║       Venorica RNN — Training (${ITERATIONS.toLocaleString()} iterations)            ║`);
    console.log('╚══════════════════════════════════════════════════════════════╝');
    console.log();
    // Pre-training status
    const preStatus = rnnEngine.getStatus();
    console.log('📊 BEFORE TRAINING:');
    console.log(`  Loss:       ${(preStatus.loss ?? 0).toFixed(4)}`);
    console.log(`  Perplexity: ${fmtPpl(perplexityOf(preStatus))}`);
    console.log(`  Iterations: ${preStatus.iterations?.toLocaleString() || 0}`);
    console.log(`  Vocab:      ${preStatus.vocabSize}`);
    console.log(`  Patterns:   ${preStatus.patternCount}`);
    console.log(`  Chars:      ${(preStatus.trainedChars ?? 0).toLocaleString()}`);
    console.log();
    // Generate a sample before training
    try {
        const sample = rnnEngine.generate('import', 200, 0.5);
        console.log('🔮 PRE-TRAINING SAMPLE (seed="import", temp=0.5):');
        console.log(`  ${sample.substring(0, 200).replace(/\n/g, '\n  ')}`);
        console.log();
    }
    catch { /* skip */ }
    // Train
    console.log(`🚀 Training for ${ITERATIONS.toLocaleString()} iterations...`);
    console.log();
    const result = await rnnEngine.learnFromKnowledge(ITERATIONS);
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    console.log(`✅ Training complete! (${elapsed}s)`);
    console.log();
    // Post-training status
    const postStatus = rnnEngine.getStatus();
    console.log('📊 AFTER TRAINING:');
    console.log(`  Loss:       ${(postStatus.loss ?? 0).toFixed(4)}`);
    console.log(`  Perplexity: ${fmtPpl(perplexityOf(postStatus))}`);
    console.log(`  Iterations: ${postStatus.iterations?.toLocaleString() || 0}`);
    // Improvement on PERPLEXITY (vocab-independent) — see trainingMetrics.ts for
    // why raw loss comparisons are misleading across vocab changes.
    console.log(`  Improvement: ${describeImprovement(preStatus, postStatus)}`);
    console.log(`  Patterns:   ${postStatus.patternCount}`);
    console.log(`  Chars:      ${(postStatus.trainedChars ?? 0).toLocaleString()}`);
    console.log();
    // Generate a sample after training
    try {
        const sample = rnnEngine.generate('import', 200, 0.5);
        console.log('🔮 POST-TRAINING SAMPLE (seed="import", temp=0.5):');
        console.log(`  ${sample.substring(0, 200).replace(/\n/g, '\n  ')}`);
        console.log();
    }
    catch { /* skip */ }
    // Multiple seed comparison
    console.log('🔮 MULTI-SEED GENERATION (temp=0.4):');
    for (const seed of ['import', 'function', 'const', 'class', 'export']) {
        try {
            const s = rnnEngine.generate(seed, 150, 0.4);
            console.log(`  [${seed}] ${s.substring(0, 120).replace(/\n/g, ' ')}`);
        }
        catch { /* skip */ }
    }
    console.log();
    // Understanding score — reuse perplexityOf so this value always matches the
    // AFTER-TRAINING Perplexity line above (same formula, same seqLength default).
    if (postStatus.loss && postStatus.vocabSize) {
        const vocabSize = postStatus.vocabSize;
        // Guard above guarantees loss is truthy, so perplexityOf cannot return null here.
        const perplexity = perplexityOf(postStatus);
        const randomP = vocabSize;
        const understanding = Math.max(0, Math.min(100, ((randomP - perplexity) / randomP) * 100));
        console.log('📈 UNDERSTANDING SCORE:');
        console.log(`  Perplexity:         ${fmtPpl(perplexity)}`);
        console.log(`  Random perplexity:  ${randomP.toFixed(2)}`);
        console.log(`  Understanding:      ${understanding.toFixed(2)}%`);
        console.log(`  Status:             ${understanding > 50 ? '✅ Learning well!' :
            understanding > 20 ? '📖 Making progress' :
                understanding > 5 ? '🔤 Starting to learn' :
                    '❄️  Random (needs more training)'}`);
    }
    console.log(`\n✅ Training complete! Model saved to knowledge/rnn-model.json`);
}
main().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});
