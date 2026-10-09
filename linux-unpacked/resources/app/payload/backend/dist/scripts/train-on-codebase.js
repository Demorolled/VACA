/**
 * Venorica RNN Training Script
 *
 * Scans all project source files and trains Venorica RNN on them.
 * Run with: npx tsx backend/src/scripts/train-on-codebase.ts
 */
import * as fs from 'fs';
import * as path from 'path';
import { knowledgeStore } from '../knowledge/knowledgeStore.js';
import { rnnEngine } from '../neural/trainer.js';
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const PROJECT_ROOT = path.resolve(BACKEND_DIR, '..');
const EXTENSIONS = ['.ts', '.tsx', '.css', '.py', '.html', '.js'];
const EXCLUDE_DIRS = ['node_modules', 'dist', '.git', 'exports'];
function collectSourceFiles(dir) {
    const files = [];
    function walk(currentDir) {
        let entries;
        try {
            entries = fs.readdirSync(currentDir, { withFileTypes: true });
        }
        catch {
            return;
        }
        for (const entry of entries) {
            const fullPath = path.join(currentDir, entry.name);
            const relativePath = path.relative(PROJECT_ROOT, fullPath);
            // Skip excluded directories
            if (entry.isDirectory()) {
                if (EXCLUDE_DIRS.includes(entry.name))
                    continue;
                walk(fullPath);
                continue;
            }
            const ext = path.extname(entry.name).toLowerCase();
            if (!EXTENSIONS.includes(ext))
                continue;
            let content;
            try {
                content = fs.readFileSync(fullPath, 'utf-8');
            }
            catch {
                continue;
            }
            // Skip empty or very small files
            if (content.trim().length < 10)
                continue;
            // Determine language
            let language = 'unknown';
            switch (ext) {
                case '.ts':
                case '.tsx':
                    language = 'typescript';
                    break;
                case '.css':
                    language = 'css';
                    break;
                case '.py':
                    language = 'python';
                    break;
                case '.html':
                    language = 'html';
                    break;
                case '.js':
                    language = 'javascript';
                    break;
            }
            files.push({ path: fullPath, relativePath, content, language });
        }
    }
    walk(dir);
    return files;
}
async function main() {
    console.log('='.repeat(60));
    console.log('  Venorica RNN — Codebase Knowledge Training');
    console.log('='.repeat(60));
    // Check existing patterns count
    const existingCount = knowledgeStore.count();
    console.log(`\n[scan] Existing patterns: ${existingCount}`);
    // Collect all source files
    const srcDirs = [
        path.join(PROJECT_ROOT, 'backend', 'src'),
        path.join(PROJECT_ROOT, 'frontend', 'src'),
    ];
    const allFiles = [];
    for (const dir of srcDirs) {
        if (fs.existsSync(dir)) {
            allFiles.push(...collectSourceFiles(dir));
        }
    }
    console.log(`[scan] Found ${allFiles.length} source files to learn from`);
    // Filter out files we've already learned from (check relative paths)
    const existingPatterns = knowledgeStore.getAll();
    const existingPaths = new Set(existingPatterns
        .filter(p => p.tags.includes('source-file'))
        .map(p => p.description.split('Source: ')[1] || ''));
    const newFiles = allFiles.filter(f => !existingPaths.has(f.relativePath));
    console.log(`[scan] New files to add: ${newFiles.length} (already have ${allFiles.length - newFiles.length})`);
    if (newFiles.length === 0 && existingCount > 0) {
        console.log('[scan] All files already learned. Proceeding to train with more iterations...');
    }
    // Add each file as a pattern
    let addedCount = 0;
    for (const file of newFiles) {
        // Check if we're near the sheet cap — if so, skip remaining
        if (knowledgeStore.count() >= 90) {
            console.log(`[scan] Approaching pattern cap (${knowledgeStore.count()}/100), stopping addition`);
            break;
        }
        const fileName = path.basename(file.path);
        const fileDir = path.dirname(file.relativePath);
        // Generate tags
        const tags = ['source-file', file.language, 'codebase'];
        if (fileDir.includes('/')) {
            tags.push(fileDir.split('/').join('-'));
        }
        try {
            knowledgeStore.addPattern({
                category: 'code_pattern',
                title: `${fileName} — Source code pattern`,
                code: file.content,
                description: `Full source code from ${file.relativePath}. Source: ${file.relativePath}`,
                tags,
                projectId: 'codebase-scan',
                targetOS: 'linux',
                nodeType: 'source-file',
                language: file.language,
                success: true,
                qualityScore: 7.0,
            });
            addedCount++;
        }
        catch (err) {
            console.error(`[scan] Failed to add ${file.relativePath}: ${err.message}`);
        }
    }
    console.log(`\n[add] Added ${addedCount} new patterns to knowledge store`);
    console.log(`[add] Total patterns: ${knowledgeStore.count()}`);
    // Now train the RNN on all patterns
    console.log(`\n${'='.repeat(60)}`);
    console.log('  Training Venorica RNN...');
    console.log(`  ${'='.repeat(60)}`);
    console.log('\n[venorica] Model status before training:');
    console.log(JSON.stringify(rnnEngine.getStatus(), null, 2));
    // Train with substantial iterations
    const ITERATIONS = 3000;
    console.log(`\n[venorica] Starting ${ITERATIONS} training iterations...`);
    try {
        const result = await rnnEngine.learnFromKnowledge(ITERATIONS);
        console.log(`\n[venorica] ✅ Training complete!`);
        console.log(`  Final loss: ${result.loss.toFixed(4)}`);
        console.log(`  Characters seen: ${result.chars.toLocaleString()}`);
        // Generate sample output to verify model learned
        console.log(`\n${'='.repeat(60)}`);
        console.log('  Generation Samples');
        console.log(`  ${'='.repeat(60)}`);
        const seeds = [
            'import',
            'function',
            'const',
            'class',
            'interface',
        ];
        for (const seed of seeds) {
            try {
                const output = rnnEngine.generate(seed, 150, 0.6);
                console.log(`\n--- Seed: "${seed}" (temp=0.6) ---`);
                console.log(output.substring(0, 300));
            }
            catch (e) {
                console.log(`\n--- Seed: "${seed}" --- Error: ${e.message}`);
            }
        }
    }
    catch (err) {
        console.error(`[venorica] Training failed: ${err.message}`);
        process.exit(1);
    }
    // Final stats
    console.log(`\n${'='.repeat(60)}`);
    console.log('  Training Summary');
    console.log(`  ${'='.repeat(60)}`);
    const status = rnnEngine.getStatus();
    console.log(`  Total patterns:      ${knowledgeStore.count()}`);
    console.log(`  New patterns added:  ${addedCount}`);
    console.log(`  Vocab size:          ${status.vocabSize}`);
    console.log(`  Hidden size:         ${status.hiddenSize}`);
    console.log(`  Total iterations:    ${status.iterations}`);
    console.log(`  Final loss:          ${status.loss?.toFixed(4) || 'N/A'}`);
    console.log(`  Characters trained:  ${status.trainedChars?.toLocaleString() || 0}`);
    console.log(`  Model saved to:      ${path.join(PROJECT_ROOT, 'knowledge', 'rnn-model.json')}`);
    console.log(`\n✅ Venorica RNN training complete!`);
}
main().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});
