/**
 * Venorica RNN — Comprehensive Learning Test
 *
 * Tests what the model has learned by:
 * 1. Showing model status (loss, iterations, vocab)
 * 2. Computing perplexity and understanding score
 * 3. Generating code samples at multiple temperatures
 * 4. Comparing randomness vs learned patterns
 *
 * Run with: npx tsx backend/src/scripts/test-venorica.ts
 */
import { rnnEngine } from '../neural/trainer.js';
async function main() {
    console.log('╔══════════════════════════════════════════════════════════════╗');
    console.log('║       Venorica RNN — Learning Progress Test                ║');
    console.log('╚══════════════════════════════════════════════════════════════╝');
    console.log();
    // ── 1. Model Status ──
    console.log('📊 1. MODEL STATUS');
    console.log('─'.repeat(50));
    const status = rnnEngine.getStatus();
    console.log(`  Initialized:      ${status.initialized}`);
    console.log(`  Vocabulary size:  ${status.vocabSize}`);
    console.log(`  Hidden size:      ${status.hiddenSize}`);
    console.log(`  Total iterations: ${status.iterations?.toLocaleString() || 0}`);
    console.log(`  Current loss:     ${status.loss?.toFixed(4) ?? 'N/A'}`);
    console.log(`  Trained chars:    ${(status.trainedChars ?? 0).toLocaleString()}`);
    console.log(`  Patterns in store: ${status.patternCount}`);
    console.log(`  GPU accelerated:  ${status.gpuAccelerated}`);
    console.log(`  Learning rate:    ${status.learningRate}`);
    console.log(`  Seq length:       ${status.seqLength}`);
    console.log();
    // ── 2. Perplexity & Understanding Score ──
    console.log('📈 2. UNDERSTANDING SCORE (Perplexity Analysis)');
    console.log('─'.repeat(50));
    if (status.loss && status.initialized) {
        const vocabSize = status.vocabSize || 1;
        const seqLength = status.seqLength || 64;
        const loss = status.loss;
        // Perplexity = exp(loss / seq_len) — lower is better
        const basePerplexity = Math.exp(loss / seqLength);
        // Random guessing perplexity = vocab size (uniform distribution)
        const randomPerplexity = Math.exp(Math.log(vocabSize));
        // Understanding % = how much better than random
        const understandingPct = Math.max(0, Math.min(100, ((randomPerplexity - basePerplexity) / randomPerplexity) * 100));
        console.log(`  Current loss:          ${loss.toFixed(4)}`);
        console.log(`  Perplexity:           ${basePerplexity.toFixed(2)}`);
        console.log(`  Random perplexity:    ${randomPerplexity.toFixed(2)}`);
        console.log(`  Understanding score:  ${understandingPct.toFixed(2)}%`);
        console.log(`  Status:               ${understandingPct > 50 ? '✅ Learning well!' :
            understandingPct > 20 ? '📖 Making progress' :
                understandingPct > 5 ? '🔤 Starting to learn' :
                    '❄️  Random (needs more training)'}`);
        // Show what the loss means qualitatively
        console.log();
        console.log('  What the loss values mean:');
        console.log(`    Random guessing:  ~${(Math.log(vocabSize) * seqLength).toFixed(1)} (no learning)`);
        console.log(`    Current:           ${loss.toFixed(1)}`);
        console.log(`    Good code gen:    ~${(Math.log(vocabSize) * 0.5 * seqLength).toFixed(1)} or lower`);
    }
    else {
        console.log('  ❌ Model not initialized or no loss available');
    }
    console.log();
    // ── 3. Code Generation Samples ──
    console.log('🔮 3. CODE GENERATION SAMPLES');
    console.log('─'.repeat(50));
    const seeds = [
        { seed: 'import', temp: 0.4, label: 'Seed "import" — low temp (0.4, conservative)' },
        { seed: 'function', temp: 0.6, label: 'Seed "function" — mid temp (0.6)' },
        { seed: 'const', temp: 0.8, label: 'Seed "const" — high temp (0.8, creative)' },
        { seed: 'class', temp: 0.5, label: 'Seed "class" — med-low temp (0.5)' },
        { seed: 'package', temp: 0.3, label: 'Seed "package" — very low temp (0.3)' },
        { seed: 'export', temp: 0.7, label: 'Seed "export" — med-high temp (0.7)' },
        { seed: 'def', temp: 0.6, label: 'Seed "def" — Python-style, mid temp (0.6)' },
        { seed: 'type', temp: 0.4, label: 'Seed "type" — low temp (0.4)' },
    ];
    for (const { seed, temp, label } of seeds) {
        try {
            const output = rnnEngine.generate(seed, 400, temp);
            const firstLine = output.split('\n')[0].substring(0, 100);
            console.log(`\n  ${label}`);
            console.log(`  ${'·'.repeat(50)}`);
            console.log(`  ${output.substring(0, 350).replace(/\n/g, '\n  ')}`);
            if (output.length > 350)
                console.log('  ...');
        }
        catch (e) {
            console.log(`\n  ${label} — ❌ Error: ${e.message}`);
        }
    }
    console.log();
    // ── 4. Structural Analysis ──
    console.log('🔬 4. STRUCTURAL ANALYSIS');
    console.log('─'.repeat(50));
    console.log('  Testing whether generated code uses correct syntax patterns...');
    const testSeeds = ['func', 'import React', 'interface'];
    let validCount = 0;
    let totalChecks = 0;
    for (const seed of testSeeds) {
        try {
            const output = rnnEngine.generate(seed, 200, 0.5);
            totalChecks++;
            // Check for basic structural elements
            const hasKeywords = /\b(function|const|let|var|import|export|class|if|for|return)\b/.test(output);
            const hasBraces = /[{}()]/.test(output);
            const hasOperators = /[=+\-*/<>]/.test(output);
            const hasSemicolons = /;/.test(output);
            const hasStrings = /['"`]/.test(output);
            const score = [hasKeywords, hasBraces, hasOperators, hasSemicolons, hasStrings].filter(Boolean).length;
            if (score >= 3)
                validCount++;
            console.log(`\n  Seed "${seed}":`);
            console.log(`    Keywords: ${hasKeywords ? '✅' : '❌'} | Braces: ${hasBraces ? '✅' : '❌'} | Operators: ${hasOperators ? '✅' : '❌'}`);
            console.log(`    Semicolons: ${hasSemicolons ? '✅' : '❌'} | Strings: ${hasStrings ? '✅' : '❌'} — Score: ${score}/5`);
            console.log(`    First 100 chars: ${output.substring(0, 100).replace(/\n/g, ' ')}`);
        }
        catch (e) {
            console.log(`\n  Seed "${seed}" — ❌ Error: ${e.message}`);
        }
    }
    console.log(`\n  Pass rate: ${validCount}/${totalChecks} samples have ≥3/5 structural features`);
    console.log();
    // ── 5. Training Recommendations ──
    console.log('💡 5. TRAINING RECOMMENDATIONS');
    console.log('─'.repeat(50));
    const loss = status.loss || 1000;
    const iters = status.iterations || 0;
    if (loss > 200) {
        console.log('  🟢 Keep training — loss is still high but decreasing');
        console.log('  🔧 Recommended: Run 50,000-100,000 more iterations');
    }
    else if (loss > 100) {
        console.log('  🟡 Model is making progress — keep going!');
        console.log('  🔧 Recommended: Run 20,000-50,000 more iterations');
    }
    else if (loss > 50) {
        console.log('  🟠 Model is learning patterns — getting there');
        console.log('  🔧 Recommended: Run 10,000-20,000 more iterations');
    }
    else {
        console.log('  🟢 Model is well-trained!');
        console.log('  🔧 Consider testing generation quality and fine-tuning');
    }
    const charsPerIter = status.trainedChars / Math.max(1, iters);
    console.log(`  Chars/iteration:   ${charsPerIter.toFixed(1)}`);
    console.log(`  Current iterations: ${iters.toLocaleString()}`);
    const targetIters = loss > 100 ? 50000 : 10000;
    const remaining = Math.max(0, targetIters - iters);
    console.log(`  Estimated remaining: ${remaining.toLocaleString()} iterations`);
    console.log(`  Estimated time:      ~${(remaining / 100).toFixed(0)}s (at ~100 iters/s)`);
    console.log();
    console.log('✅ Test complete!');
}
main().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});
