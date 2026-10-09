/**
 * Codebuff Training Data Pipeline
 *
 * Captures code changes, conversations, and generated code as structured
 * training data that feeds into:
 *   1. The Venorica RNN knowledge store (for pattern-based learning)
 *   2. The LLM Training Studio upload directory (for LLM fine-tuning data)
 *
 * This makes every codebuff interaction contribute to the system's
 * ongoing learning, creating a virtuous feedback loop.
 *
 * Usage:
 *   npx tsx backend/src/scripts/capture-training-data.ts
 *   npx tsx backend/src/scripts/capture-training-data.ts --watch  (file watcher mode)
 *   npx tsx backend/src/scripts/capture-training-data.ts --from-git  (capture uncommitted changes)
 */
import * as fs from 'fs';
import * as path from 'path';
import { execSync } from 'child_process';
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const PROJECT_ROOT = path.resolve(BACKEND_DIR, '..');
// ─── Configuration ──────────────────────────────────────────────────────────
const TRAINING_STUDIO_DIR = path.join(PROJECT_ROOT, 'llm-training-app', 'data', 'uploads');
const KNOWLEDGE_DIR = path.join(BACKEND_DIR, 'knowledge');
const CAPTURE_LOG = path.join(BACKEND_DIR, 'knowledge', 'capture-log.jsonl');
// ─── Git-based change capture ──────────────────────────────────────────────
function getGitDiff() {
    try {
        const stdout = execSync('git diff --cached --name-status', { cwd: PROJECT_ROOT, encoding: 'utf-8', timeout: 5000 });
        if (!stdout.trim())
            return [];
        const changedFiles = [];
        const lines = stdout.trim().split('\n');
        for (const line of lines) {
            const [status, ...fileParts] = line.trim().split('\t');
            const filePath = fileParts.join('\t');
            if (!filePath)
                continue;
            // Skip binary, large, and node_modules files
            const ext = path.extname(filePath).toLowerCase();
            if (!['.ts', '.tsx', '.js', '.jsx', '.py', '.css', '.html', '.json', '.md', '.yml', '.yaml'].includes(ext))
                continue;
            if (filePath.includes('node_modules') || filePath.includes('dist'))
                continue;
            try {
                const content = execSync(`git diff --cached "${filePath}"`, { cwd: PROJECT_ROOT, encoding: 'utf-8', timeout: 5000 });
                if (content.length > 20 && content.length < 50000) {
                    changedFiles.push({ filePath, content, status });
                }
            }
            catch {
                // skip files that can't be diffed
            }
        }
        return changedFiles;
    }
    catch {
        return [];
    }
}
function getUncommittedChanges() {
    try {
        const stdout = execSync('git diff --name-status', { cwd: PROJECT_ROOT, encoding: 'utf-8', timeout: 5000 });
        if (!stdout.trim())
            return [];
        const changedFiles = [];
        const lines = stdout.trim().split('\n');
        for (const line of lines) {
            const [status, ...fileParts] = line.trim().split('\t');
            const filePath = fileParts.join('\t');
            if (!filePath)
                continue;
            const ext = path.extname(filePath).toLowerCase();
            if (!['.ts', '.tsx', '.js', '.jsx', '.py', '.css', '.html', '.json', '.md', '.yml', '.yaml'].includes(ext))
                continue;
            if (filePath.includes('node_modules') || filePath.includes('dist') || filePath.includes('exports'))
                continue;
            try {
                const content = execSync(`git diff "${filePath}"`, { cwd: PROJECT_ROOT, encoding: 'utf-8', timeout: 5000 });
                if (content.length > 20 && content.length < 100000) {
                    changedFiles.push({ filePath, content, status });
                }
            }
            catch {
                // skip
            }
        }
        return changedFiles;
    }
    catch {
        return [];
    }
}
function detectLanguage(filePath) {
    const ext = path.extname(filePath).toLowerCase();
    const langMap = {
        '.ts': 'typescript', '.tsx': 'typescript', '.js': 'javascript', '.jsx': 'javascript',
        '.py': 'python', '.css': 'css', '.html': 'html', '.json': 'json',
        '.md': 'markdown', '.yml': 'yaml', '.yaml': 'yaml',
    };
    return langMap[ext] || 'unknown';
}
function extractTagsFromDiff(diff, filePath) {
    const tags = [detectLanguage(filePath)];
    // Detect patterns in the diff
    if (diff.includes('function ') || diff.includes('async '))
        tags.push('function-def');
    if (diff.includes('class '))
        tags.push('class-def');
    if (diff.includes('interface '))
        tags.push('interface');
    if (diff.includes('import ') || diff.includes('require('))
        tags.push('import');
    if (diff.includes('export '))
        tags.push('export');
    if (diff.includes('try ') || diff.includes('catch '))
        tags.push('error-handling');
    if (diff.includes('const ') || diff.includes('let '))
        tags.push('variable');
    if (diff.includes('async ') || diff.includes('await '))
        tags.push('async');
    if (diff.includes('type '))
        tags.push('type-def');
    if (diff.includes('=>'))
        tags.push('arrow-function');
    // Extract component/framework hints
    if (diff.includes('React') || diff.includes('useState') || diff.includes('useEffect'))
        tags.push('react');
    if (diff.includes('Express') || diff.includes('Router'))
        tags.push('express');
    if (diff.includes('@') && filePath.endsWith('.ts'))
        tags.push('decorator');
    return tags;
}
function extractCodeFromDiff(diff) {
    // Remove diff metadata (---/+++ lines and @@ hunk headers) and extract added/modified lines
    const lines = diff.split('\n');
    const codeLines = [];
    let inHunk = false;
    for (const line of lines) {
        if (line.startsWith('diff --git') || line.startsWith('index ') || line.startsWith('---') || line.startsWith('+++')) {
            continue;
        }
        if (line.startsWith('@@')) {
            inHunk = true;
            continue;
        }
        if (inHunk) {
            if (line.startsWith('+')) {
                codeLines.push(line.substring(1));
            }
            else if (line.startsWith(' ')) {
                codeLines.push(line.substring(1));
            }
            // Skip removed lines (start with -)
        }
    }
    return codeLines.join('\n').trim();
}
// ─── Direct file capture ─────────────────────────────────────────────────
function captureFileContent(filePath) {
    try {
        const fullPath = path.join(PROJECT_ROOT, filePath);
        if (!fs.existsSync(fullPath))
            return null;
        const content = fs.readFileSync(fullPath, 'utf-8');
        if (content.length < 20 || content.length > 100000)
            return null;
        return content;
    }
    catch {
        return null;
    }
}
// ─── Export to Training Studio ───────────────────────────────────────────
function ensureDir(dir) {
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
}
function exportToTrainingStudio(records) {
    if (records.length === 0)
        return 0;
    ensureDir(TRAINING_STUDIO_DIR);
    ensureDir(KNOWLEDGE_DIR);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `codebuff-capture-${timestamp}.jsonl`;
    const exportPath = path.join(TRAINING_STUDIO_DIR, filename);
    // Write as JSONL — each line is one training example
    const lines = records.map(r => JSON.stringify({
        text: r.text,
        source: r.source,
        title: r.title,
        language: r.language,
        tags: r.tags,
        nodeType: r.nodeType,
        filePath: r.filePath,
        timestamp: r.timestamp,
        sessionId: r.sessionId,
        metadata: r.metadata,
        // Add instruction-response format for LLM fine-tuning
        instruction: `Generate ${r.language} code for: ${r.title}`,
        response: r.text,
    }));
    fs.writeFileSync(exportPath, lines.join('\n') + '\n', 'utf-8');
    console.log(`[capture] Exported ${records.length} training records to ${exportPath}`);
    // Append to master capture log
    const logLines = records.map(r => JSON.stringify({
        ...r,
        _exportedTo: filename,
        _exportedAt: new Date().toISOString(),
    }));
    fs.appendFileSync(CAPTURE_LOG, logLines.join('\n') + '\n', 'utf-8');
    return records.length;
}
// ─── Add to Knowledge Store ──────────────────────────────────────────────
async function addToKnowledgeStore(records) {
    if (records.length === 0)
        return 0;
    try {
        const { knowledgeStore } = await import('../knowledge/knowledgeStore.js');
        let addedCount = 0;
        for (const record of records) {
            try {
                knowledgeStore.addPattern({
                    category: 'code_pattern',
                    title: record.title,
                    code: record.text,
                    description: `Codebuff ${record.source} — ${record.filePath}. Language: ${record.language}`,
                    tags: record.tags,
                    projectId: 'codebuff-capture',
                    targetOS: 'linux',
                    nodeType: 'source-file',
                    language: record.language,
                    success: true,
                    qualityScore: 6.0,
                });
                addedCount++;
            }
            catch {
                // skip
            }
        }
        return addedCount;
    }
    catch (err) {
        console.error(`[capture] Failed to add to knowledge store: ${err.message}`);
        return 0;
    }
}
// ─── Main capture orchestration ──────────────────────────────────────────
let sessionId = `cb_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
async function captureFromGitChanges() {
    const changes = getUncommittedChanges();
    if (changes.length === 0) {
        console.log('[capture] No uncommitted changes found.');
        return { records: [], exported: 0, stored: 0 };
    }
    console.log(`[capture] Found ${changes.length} changed files.`);
    const records = [];
    const timestamp = new Date().toISOString();
    for (const change of changes) {
        const code = extractCodeFromDiff(change.content);
        if (!code || code.length < 30)
            continue;
        const language = detectLanguage(change.filePath);
        const tags = extractTagsFromDiff(change.content, change.filePath);
        const fileName = path.basename(change.filePath);
        const fileDir = path.dirname(change.filePath);
        records.push({
            text: code,
            source: 'codebuff-codechange',
            title: `${fileName} — ${change.status === 'A' ? 'New' : 'Modified'}`,
            language,
            tags: [...new Set(tags)],
            nodeType: 'source-file',
            filePath: change.filePath,
            timestamp,
            sessionId,
            metadata: {
                status: change.status,
                directory: fileDir,
                changeType: change.status === 'A' ? 'creation' : 'modification',
            },
        });
    }
    // Export to training studio
    const exported = exportToTrainingStudio(records);
    // Also add to knowledge store
    const stored = await addToKnowledgeStore(records);
    console.log(`[capture] Done: ${records.length} records captured, ${exported} exported, ${stored} stored`);
    return { records, exported, stored };
}
// ─── Capture from specific file patterns ─────────────────────────────────
async function captureFromDirectory(dir, pattern) {
    const fullDir = path.join(PROJECT_ROOT, dir);
    if (!fs.existsSync(fullDir)) {
        console.error(`[capture] Directory not found: ${fullDir}`);
        return 0;
    }
    const records = [];
    const timestamp = new Date().toISOString();
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
            if (entry.isDirectory()) {
                if (entry.name === 'node_modules' || entry.name === 'dist' || entry.name === '.git' || entry.name === 'exports')
                    continue;
                walk(fullPath);
                continue;
            }
            const ext = path.extname(entry.name).toLowerCase();
            if (!['.ts', '.tsx', '.js', '.py', '.css', '.html', '.json', '.md'].includes(ext))
                continue;
            if (pattern && !pattern.test(relativePath))
                continue;
            const content = captureFileContent(relativePath);
            if (!content)
                continue;
            const language = detectLanguage(relativePath);
            const tags = [language, 'codebuff-work', 'source-file'];
            records.push({
                text: content,
                source: 'codebuff-system',
                title: `${entry.name} — Source File`,
                language,
                tags,
                nodeType: 'source-file',
                filePath: relativePath,
                timestamp,
                sessionId,
                metadata: {
                    directory: path.dirname(relativePath),
                    size: String(content.length),
                },
            });
        }
    }
    walk(fullDir);
    if (records.length === 0) {
        console.log('[capture] No files found in directory.');
        return 0;
    }
    const exported = exportToTrainingStudio(records);
    const stored = await addToKnowledgeStore(records);
    console.log(`[capture] Captured ${records.length} files from ${dir}: ${exported} exported, ${stored} stored`);
    return records.length;
}
// ─── File watcher mode (simple polling) ───────────────────────────────────
let lastSnapshotState = '';
/** Watched source directories for non-git polling fallback */
const WATCHED_DIRS = ['backend/src', 'frontend/src', 'llm-training-app'];
/**
 * Compute a quick hash of file mtimes for the watched directories.
 * Used as a lightweight change detector when git is unavailable.
 */
function hashSourceDirs() {
    const parts = [];
    for (const dir of WATCHED_DIRS) {
        const fullDir = path.join(PROJECT_ROOT, dir);
        if (!fs.existsSync(fullDir))
            continue;
        try {
            walkForHash(fullDir, parts);
        }
        catch { /* skip unreadable */ }
    }
    return parts.join('|');
}
function walkForHash(currentDir, parts) {
    let entries;
    try {
        entries = fs.readdirSync(currentDir, { withFileTypes: true });
    }
    catch {
        return;
    }
    for (const entry of entries) {
        if (entry.name.startsWith('.'))
            continue;
        if (entry.name === 'node_modules' || entry.name === 'dist' || entry.name === 'exports')
            continue;
        const fullPath = path.join(currentDir, entry.name);
        if (entry.isDirectory()) {
            walkForHash(fullPath, parts);
        }
        else {
            const ext = path.extname(entry.name).toLowerCase();
            if (!['.ts', '.tsx', '.js', '.py', '.css', '.html', '.json', '.md'].includes(ext))
                continue;
            try {
                const stat = fs.statSync(fullPath);
                parts.push(`${entry.name}:${stat.mtimeMs}`);
            }
            catch { /* skip */ }
        }
    }
}
function watchMode(intervalMs = 30000) {
    console.log(`[capture] Watch mode active — polling every ${intervalMs / 1000}s for changes...`);
    let useGitFallback = false;
    async function poll() {
        let hasChanges = false;
        // Try git-based detection first
        try {
            const currentState = execSync('git status --porcelain', { cwd: PROJECT_ROOT, encoding: 'utf-8', timeout: 5000 });
            if (currentState !== lastSnapshotState && currentState.trim()) {
                console.log('[capture] Changes detected, capturing...');
                const { records, exported } = await captureFromGitChanges();
                if (records.length > 0) {
                    console.log(`[capture] Captured ${records.length} records from git changes`);
                    // Also re-scan source dirs for full context
                    await captureFromDirectory('backend/src');
                    await captureFromDirectory('frontend/src');
                }
                lastSnapshotState = currentState;
                hasChanges = true;
            }
        }
        catch {
            // git not available — use filesystem mtime fallback
            useGitFallback = true;
        }
        // Fallback: poll filesystem mtimes for non-git repos
        if (useGitFallback && !hasChanges) {
            const currentHash = hashSourceDirs();
            if (currentHash !== lastSnapshotState && currentHash) {
                console.log('[capture] Filesystem changes detected (mtime), capturing...');
                for (const dir of WATCHED_DIRS) {
                    const count = await captureFromDirectory(dir);
                    if (count > 0) {
                        console.log(`[capture] Re-scanned ${dir}: ${count} files`);
                    }
                }
                lastSnapshotState = currentHash;
                hasChanges = true;
            }
        }
        // Initialize state on first poll if not set
        if (!lastSnapshotState) {
            if (useGitFallback) {
                lastSnapshotState = hashSourceDirs();
            }
        }
        setTimeout(poll, intervalMs);
    }
    // Initial capture
    poll();
}
// ─── CLI ─────────────────────────────────────────────────────────────────
async function main() {
    const args = process.argv.slice(2);
    console.log('='.repeat(60));
    console.log('  Codebuff Training Data Pipeline');
    console.log('='.repeat(60));
    if (args.includes('--watch')) {
        // Watch mode — continuously capture changes
        const intervalIndex = args.indexOf('--interval');
        const interval = intervalIndex >= 0 ? parseInt(args[intervalIndex + 1]) || 30000 : 30000;
        await captureFromGitChanges();
        watchMode(interval);
        return;
    }
    if (args.includes('--from-git')) {
        // Capture from uncommitted git changes
        console.log('\n[git] Scanning uncommitted changes...');
        const { records, exported, stored } = await captureFromGitChanges();
        console.log(`\n[complete] ${records.length} records, ${exported} exported to studio, ${stored} stored in knowledge base`);
        return;
    }
    if (args.includes('--dir')) {
        // Capture all files from a directory
        const dirIndex = args.indexOf('--dir');
        const dir = dirIndex >= 0 ? args[dirIndex + 1] : 'backend/src';
        const pattern = args.includes('--pattern') ? new RegExp(args[args.indexOf('--pattern') + 1]) : undefined;
        console.log(`\n[dir] Scanning directory: ${dir}${pattern ? ` (pattern: ${pattern})` : ''}`);
        const count = await captureFromDirectory(dir, pattern);
        console.log(`\n[complete] Captured ${count} files from ${dir}`);
        return;
    }
    if (args.includes('--stats')) {
        // Show capture statistics
        console.log('\n[stats] Capture statistics:');
        let totalRecords = 0;
        let fileCount = 0;
        if (fs.existsSync(CAPTURE_LOG)) {
            const logContent = fs.readFileSync(CAPTURE_LOG, 'utf-8');
            fileCount = logContent.split('\n').filter(l => l.trim()).length;
        }
        const studioFiles = fs.existsSync(TRAINING_STUDIO_DIR)
            ? fs.readdirSync(TRAINING_STUDIO_DIR).filter(f => f.startsWith('codebuff-capture-'))
            : [];
        console.log(`  Capture log records:   ${fileCount}`);
        console.log(`  Studio JSONL files:    ${studioFiles.length}`);
        console.log(`  Knowledge store:       ${getKnowledgeStoreCount()}`);
        console.log(`  Session ID:            ${sessionId}`);
        return;
    }
    // Default: capture from recent changes
    console.log('\n[default] Capturing from uncommitted changes...');
    const { records, exported, stored } = await captureFromGitChanges();
    console.log(`\n[complete] ${records.length} records, ${exported} exported, ${stored} stored`);
    if (records.length === 0) {
        console.log('\n  No changes to capture. Try:');
        console.log('    --watch        Continuous file watching mode');
        console.log('    --dir <path>   Capture all files from a directory');
        console.log('    --from-git     Capture staged/uncommitted git changes');
        console.log('    --stats        Show capture statistics');
    }
}
function getKnowledgeStoreCount() {
    try {
        const patternFile = path.join(KNOWLEDGE_DIR, 'patterns.json');
        if (fs.existsSync(patternFile)) {
            const data = JSON.parse(fs.readFileSync(patternFile, 'utf-8'));
            return Array.isArray(data) ? data.length : 0;
        }
    }
    catch { }
    return 0;
}
main().catch(err => {
    console.error('[capture] Fatal error:', err);
    process.exit(1);
});
