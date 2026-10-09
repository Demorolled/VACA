/**
 * Auto-Learning Service
 * =====================
 *
 * The app's "learning from every interaction" engine. It:
 *   1. Captures every user interaction in real-time (conversations, code gen, node edits, saves)
 *   2. Buffers interactions and periodically flushes to JSONL training data files
 *   3. Exports to the LLM Training Studio uploads directory automatically
 *   4. Auto-triggers MindSpace progressive training when enough new data accumulates
 *   5. Tracks what the model has learned and reports status
 *
 * This runs as a singleton background service in the backend server.
 */
import * as fs from 'fs';
import * as path from 'path';
import { knowledgeStore } from '../knowledge/knowledgeStore.js';
import { isAutoLearnDisabled } from '../knowledge/qualityGate.js';
// ─── Configuration ────────────────────────────────────────────────────────
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const PROJECT_ROOT = path.resolve(BACKEND_DIR, '..');
const TRAINING_STUDIO_DIR = path.join(PROJECT_ROOT, 'llm-training-app', 'data', 'uploads');
const KNOWLEDGE_DIR = path.join(BACKEND_DIR, 'knowledge');
const AUTO_LEARN_DIR = path.join(KNOWLEDGE_DIR, 'auto-learn');
// ── Additional data source directories (must be after PROJECT_ROOT) ─────
const MINDSAPCE_TRAINER_DIR = path.join(PROJECT_ROOT, 'MindSpace', 'trainer');
// ── External MindSpace (user's dedicated GPU-enabled location) ─────────
const EXTERNAL_MINDSPACE_DIR = '/media/final-flash1/a47f2c6e-f5fa-4e60-bcea-95767738c074/MindSpace';
const EXTERNAL_MINDSPACE_TRAINER_DIR = path.join(EXTERNAL_MINDSPACE_DIR, 'trainer');
const MINDSPACE_DEVICE = 'cuda:1'; // Use 2nd GPU
const MINDSPACE_MEMORY_FRACTION = '0.4'; // Limit to 40% GPU memory
const DATASHEETS_GROWTH_DIR = path.join(PROJECT_ROOT, 'datasheets growth');
// ── Kill switch ────────────────────────────────────────────────────────────
// AUTO_LEARN_DISABLED=true|1 turns OFF all auto-learn capture (buffer, flush,
// JSONL export, Training Studio uploads, knowledge-store pattern export, and
// MindSpace training triggers). Enabled until the poisoning loop is proven
// fixed: the 2026-08-13 chess build stored markdown-fenced prose as "successful"
// patterns with qualityScore 7.5, and triggerMindSpaceTraining() writes every
// captured interaction to the knowledge store with hardcoded success:true.
// Mirrors the existing VENORICA_DISABLED env convention.
//
// IMPORTANT: this is read at CALL time via isAutoLearnDisabled() — never cache
// it at module load. The module is imported before dotenv.config() runs in
// index.ts, so a module-level constant would always see the env as unset.
const FLUSH_INTERVAL_MS = 5 * 60 * 1000; // Flush every 5 minutes
const FLUSH_BATCH_SIZE = 50; // Or every 50 interactions
const MINDSPACE_TRAINING_THRESHOLD = 500; // Trigger MindSpace training at 500+ new interactions
const MAX_BUFFER_SIZE = 2000; // Never buffer more than this
class AutoLearnService {
    buffer = [];
    flushTimer = null;
    running = false;
    state;
    constructor() {
        this.state = this.loadState();
        this.ensureDirectories();
    }
    // ─── Public API ─────────────────────────────────────────────────────────
    /** Record a single interaction. This is the main entry point for all captures. */
    record(interaction) {
        const record = {
            ...interaction,
            id: `learn_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`,
            timestamp: new Date().toISOString(),
            sessionId: this.state.sessionId,
        };
        // Kill switch: capture is disabled until the poisoning loop is proven fixed.
        // Return the record so callers keep working, but never buffer/persist it.
        if (isAutoLearnDisabled()) {
            return record;
        }
        this.buffer.push(record);
        this.state.totalCaptured++;
        this.state.currentBuffer = this.buffer.length;
        this.state.interactionsSinceLastTraining++;
        // Flush if buffer is large enough
        if (this.buffer.length >= FLUSH_BATCH_SIZE) {
            this.flush();
        }
        // Check if we should trigger MindSpace training (fire-and-forget with error handling)
        if (this.state.interactionsSinceLastTraining >= MINDSPACE_TRAINING_THRESHOLD) {
            this.triggerMindSpaceTraining().catch((err) => {
                console.error(`[AutoLearn] Training trigger failed:`, err);
            });
        }
        // Prevent unbounded buffer growth
        if (this.buffer.length > MAX_BUFFER_SIZE) {
            this.buffer = this.buffer.slice(-FLUSH_BATCH_SIZE);
        }
        return record;
    }
    /** Convenience: record a conversation (user prompt + AI response) */
    recordConversation(prompt, response, user, metadata = {}) {
        return this.record({
            type: 'conversation',
            user,
            content: JSON.stringify({ prompt, response }),
            metadata: { ...metadata, promptLength: String(prompt.length), responseLength: String(response.length) },
            source: 'frontend',
        });
    }
    /** Convenience: record code generation */
    recordCodeGeneration(nodeLabel, language, code, user, metadata = {}) {
        return this.record({
            type: 'code_generation',
            user,
            content: code,
            metadata: { ...metadata, nodeLabel, language, codeLength: String(code.length) },
            source: 'frontend',
        });
    }
    /** Convenience: record a design save */
    recordDesignSave(projectName, nodeCount, code, user) {
        return this.record({
            type: 'design_saved',
            user,
            content: code,
            metadata: { projectName, nodeCount: String(nodeCount) },
            source: 'frontend',
        });
    }
    /** Convenience: record terminal interaction */
    recordTerminalMessage(message, role, user) {
        return this.record({
            type: 'terminal_message',
            user,
            content: message,
            metadata: { role },
            source: 'frontend',
        });
    }
    /** Get current learning status/stats */
    getStatus() {
        const flushedFiles = this.getFlushedFiles();
        return {
            ...this.state,
            bufferRecords: this.buffer.length,
            flushedFiles: flushedFiles.length,
            readyForTraining: this.state.interactionsSinceLastTraining >= MINDSPACE_TRAINING_THRESHOLD,
        };
    }
    /** Get all captured training data files */
    getTrainingDataFiles() {
        return this.getFlushedFiles().map(fp => {
            const lines = fs.readFileSync(fp, 'utf-8').trim().split('\n').filter(Boolean);
            return {
                path: fp,
                name: path.basename(fp),
                size: fs.statSync(fp).size,
                records: lines.length,
            };
        });
    }
    /** Start the service (starts periodic flush timer) */
    start() {
        if (isAutoLearnDisabled()) {
            console.log('[AutoLearn] Capture DISABLED (AUTO_LEARN_DISABLED=true) — no interactions will be captured, flushed, or exported');
            return;
        }
        if (this.running)
            return;
        this.running = true;
        // Flush any existing buffer on start
        if (this.buffer.length > 0)
            this.flush();
        // Periodic flush timer
        this.flushTimer = setInterval(() => this.flush(), FLUSH_INTERVAL_MS);
        console.log(`[AutoLearn] Service started — session: ${this.state.sessionId}`);
        console.log(`[AutoLearn] Flush: every ${FLUSH_INTERVAL_MS / 1000}s or ${FLUSH_BATCH_SIZE} interactions`);
        console.log(`[AutoLearn] MindSpace training trigger: ${MINDSPACE_TRAINING_THRESHOLD} interactions`);
    }
    /** Stop the service (flushes remaining buffer and clears timer) */
    stop() {
        if (!this.running)
            return;
        this.running = false;
        if (this.flushTimer) {
            clearInterval(this.flushTimer);
            this.flushTimer = null;
        }
        this.flush(); // Final flush
        console.log(`[AutoLearn] Service stopped — ${this.state.totalFlushed} total interactions flushed`);
    }
    /** Reset all captured data (for testing or clear) */
    reset() {
        this.buffer = [];
        this.state = this.createFreshState();
        this.saveState();
        // Clear auto-learn files
        if (fs.existsSync(AUTO_LEARN_DIR)) {
            for (const f of fs.readdirSync(AUTO_LEARN_DIR)) {
                fs.unlinkSync(path.join(AUTO_LEARN_DIR, f));
            }
        }
        console.log('[AutoLearn] Reset complete');
    }
    /**
     * Import existing training data files from the LLM Training Studio uploads
     * and other datasheet directories into the auto-learning pipeline.
     *
     * This scans multiple sources, converts records to the auto-learn format,
     * writes them as flushed JSONL files, and updates the state so they count
     * toward the MindSpace training threshold.
     *
     * Returns { totalImported, sourceCounts }.
     */
    importExistingData() {
        if (isAutoLearnDisabled()) {
            console.log('[AutoLearn] Import skipped — capture DISABLED (AUTO_LEARN_DISABLED=true)');
            return { totalImported: 0, sourceCounts: {} };
        }
        const sourceCounts = {};
        const allRecords = [];
        // ── 1. LLM Training Studio uploads ──
        const uploadRecords = this._importFromJsonlDir(TRAINING_STUDIO_DIR, 'training-studio', (line) => ({
            type: 'code_generation',
            content: line.text || '',
            metadata: {
                language: line.language || 'mixed',
                nodeLabel: line.title || 'Imported Pattern',
                category: line.category || 'unknown',
                source: line.source || 'training-studio',
                tags: (line.tags || []).join(','),
            },
        }));
        if (uploadRecords.length > 0) {
            allRecords.push(...uploadRecords);
            sourceCounts['llm-training-uploads'] = uploadRecords.length;
            console.log(`[AutoLearn] Imported ${uploadRecords.length} records from Training Studio uploads`);
        }
        // ── 2. MindSpace trainer datasheets ──
        const mindspaceRecords = this._importFromJsonlDir(MINDSAPCE_TRAINER_DIR, 'mindspace-trainer', (line) => ({
            type: 'code_generation',
            content: line.text || '',
            metadata: {
                language: line.language || 'mixed',
                nodeLabel: line.title || 'MindSpace Pattern',
                category: line.category || 'code_pattern',
                source: 'mindspace-trainer',
                tags: (line.tags || []).join(','),
            },
        }));
        if (mindspaceRecords.length > 0) {
            allRecords.push(...mindspaceRecords);
            sourceCounts['mindspace-trainer'] = mindspaceRecords.length;
            console.log(`[AutoLearn] Imported ${mindspaceRecords.length} records from MindSpace trainer`);
        }
        // ── 3. Datasheets growth ──
        const growthRecords = this._importFromJsonlDir(DATASHEETS_GROWTH_DIR, 'growth-datasheets', (line) => ({
            type: 'conversation',
            content: JSON.stringify({
                prompt: (line.user || '') + (line.system ? ` [System: ${line.system}]` : ''),
                response: line.assistant || line.text || '',
            }),
            metadata: {
                source: 'growth-datasheets',
                type: 'conversation',
                promptLength: String((line.user || '').length),
            },
        }));
        if (growthRecords.length > 0) {
            allRecords.push(...growthRecords);
            sourceCounts['growth-datasheets'] = growthRecords.length;
            console.log(`[AutoLearn] Imported ${growthRecords.length} records from growth datasheets`);
        }
        // ── 4. Knowledge store patterns ──
        try {
            const patterns = knowledgeStore.getAll();
            if (patterns.length > 0) {
                const patternRecords = patterns.map(p => ({
                    type: 'code_generation',
                    content: p.code || '',
                    metadata: {
                        language: p.language || 'mixed',
                        nodeLabel: p.title || 'Knowledge Pattern',
                        category: p.category || 'code_pattern',
                        source: 'knowledge-store',
                        tags: (p.tags || []).join(','),
                    },
                }));
                // Create interaction records with IDs, timestamps, session
                for (const pr of patternRecords) {
                    allRecords.push({
                        id: `learn_import_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`,
                        type: pr.type,
                        timestamp: new Date().toISOString(),
                        content: pr.content,
                        metadata: pr.metadata,
                        sessionId: this.state.sessionId,
                        source: 'knowledge-store',
                    });
                }
                sourceCounts['knowledge-store'] = patternRecords.length;
                console.log(`[AutoLearn] Imported ${patternRecords.length} records from knowledge store`);
            }
        }
        catch (err) {
            console.error(`[AutoLearn] Failed to import from knowledge store:`, err);
        }
        if (allRecords.length === 0) {
            console.log('[AutoLearn] No existing data found to import');
            return { totalImported: 0, sourceCounts };
        }
        // ── Write all imported records as auto-learn flush files ──
        // Split into batches of FLUSH_BATCH_SIZE to match the normal flush pattern
        const batchSize = FLUSH_BATCH_SIZE;
        let batchCount = 0;
        for (let i = 0; i < allRecords.length; i += batchSize) {
            const batch = allRecords.slice(i, i + batchSize);
            this._writeFlushFile(batch);
            batchCount++;
        }
        // Update state
        this.state.totalCaptured += allRecords.length;
        this.state.totalFlushed += allRecords.length;
        this.state.interactionsSinceLastTraining += allRecords.length;
        this.state.lastFlushTime = new Date().toISOString();
        this.state.currentBuffer = this.buffer.length;
        this.saveState();
        console.log(`[AutoLearn] ✅ Import complete: ${allRecords.length} records from ${Object.keys(sourceCounts).length} sources (${batchCount} files)`);
        // Check if we should trigger MindSpace training
        if (this.state.interactionsSinceLastTraining >= MINDSPACE_TRAINING_THRESHOLD) {
            this.triggerMindSpaceTraining().catch((err) => {
                console.error(`[AutoLearn] Training trigger failed:`, err);
            });
        }
        return { totalImported: allRecords.length, sourceCounts };
    }
    /** Force-flush the buffer immediately */
    forceFlush() {
        if (isAutoLearnDisabled())
            return 0;
        return this.flush();
    }
    // ─── Import helpers ─────────────────────────────────────────────────────
    /**
     * Scan a directory of JSONL files, parse up to `maxRecords` lines total,
     * and map to auto-learn InteractionRecord objects via the provided mapper.
     *
     * Files are processed newest-first, and we stop once we've collected
     * `maxRecords` records (or run out of files). This prevents memory
     * exhaustion when directories have millions of lines (e.g. 2.7M+).
     */
    _importFromJsonlDir(dirPath, sourceName, mapper, maxRecords = 10_000) {
        const records = [];
        try {
            if (!fs.existsSync(dirPath))
                return records;
            // Sort newest-first so we import the most recent/relevant data
            const files = fs.readdirSync(dirPath)
                .filter(f => f.endsWith('.jsonl') && !f.startsWith('.'))
                .map(f => ({
                name: f,
                path: path.join(dirPath, f),
                mtime: fs.statSync(path.join(dirPath, f)).mtimeMs,
            }))
                .sort((a, b) => b.mtime - a.mtime);
            for (const file of files) {
                if (records.length >= maxRecords)
                    break;
                try {
                    const content = fs.readFileSync(file.path, 'utf-8');
                    const lines = content.trim().split('\n').filter(Boolean);
                    for (const line of lines) {
                        if (records.length >= maxRecords)
                            break;
                        try {
                            const parsed = JSON.parse(line);
                            const mapped = mapper(parsed);
                            records.push({
                                id: `import_${sourceName}_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`,
                                type: mapped.type,
                                timestamp: parsed.timestamp || new Date().toISOString(),
                                content: mapped.content,
                                metadata: { ...mapped.metadata, importFile: file.name },
                                sessionId: this.state.sessionId,
                                source: sourceName,
                            });
                        }
                        catch {
                            // skip malformed lines
                        }
                    }
                }
                catch {
                    // skip unreadable files
                }
            }
            console.log(`[AutoLearn] Scanned ${sourceName}: ${records.length} records from ${files.length} files (capped at ${maxRecords})`);
        }
        catch (err) {
            console.error(`[AutoLearn] Failed to scan ${dirPath}:`, err);
        }
        return records;
    }
    /** Write a batch of interaction records as a JSONL flush file */
    _writeFlushFile(records) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `interactions-import-${timestamp}.jsonl`;
        const filepath = path.join(AUTO_LEARN_DIR, filename);
        const lines = records.map(r => JSON.stringify({
            text: this.recordToTrainingText(r),
            source: `auto-learn-${r.type}`,
            title: `Auto-learned ${r.type}`,
            language: r.metadata.language || 'mixed',
            tags: [r.type, r.source, ...Object.values(r.metadata).filter(v => v.length < 30)],
            nodeType: r.type,
            filePath: r.metadata.projectName || '',
            timestamp: r.timestamp,
            sessionId: r.sessionId,
            metadata: r.metadata,
        }));
        fs.writeFileSync(filepath, lines.join('\n') + '\n', 'utf-8');
        // Also copy to Training Studio uploads
        const studioPath = path.join(TRAINING_STUDIO_DIR, filename);
        try {
            fs.copyFileSync(filepath, studioPath);
        }
        catch {
            // uploads dir might not exist — that's fine
        }
        console.log(`[AutoLearn] Wrote import batch (${records.length} records) → ${filename}`);
    }
    // ─── Internal ───────────────────────────────────────────────────────────
    ensureDirectories() {
        for (const dir of [KNOWLEDGE_DIR, AUTO_LEARN_DIR, TRAINING_STUDIO_DIR]) {
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true });
            }
        }
    }
    createFreshState() {
        return {
            sessionId: `auto_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`,
            startedAt: new Date().toISOString(),
            totalCaptured: 0,
            totalFlushed: 0,
            lastFlushTime: new Date().toISOString(),
            mindspaceTrainingCount: 0,
            lastTrainingTrigger: '',
            interactionsSinceLastTraining: 0,
            currentBuffer: 0,
        };
    }
    stateFilePath() {
        return path.join(AUTO_LEARN_DIR, 'auto-learn-state.json');
    }
    loadState() {
        try {
            const fp = this.stateFilePath();
            if (fs.existsSync(fp)) {
                return JSON.parse(fs.readFileSync(fp, 'utf-8'));
            }
        }
        catch { /* ignore */ }
        return this.createFreshState();
    }
    saveState() {
        try {
            fs.writeFileSync(this.stateFilePath(), JSON.stringify(this.state, null, 2), 'utf-8');
        }
        catch { /* ignore */ }
    }
    /** Flush the buffer to disk as JSONL training data */
    flush() {
        if (isAutoLearnDisabled())
            return 0;
        if (this.buffer.length === 0)
            return 0;
        const records = [...this.buffer];
        this.buffer = [];
        this.state.currentBuffer = 0;
        // Write to auto-learn data directory
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `interactions-${timestamp}.jsonl`;
        const filepath = path.join(AUTO_LEARN_DIR, filename);
        try {
            const lines = records.map(r => JSON.stringify({
                text: this.recordToTrainingText(r),
                source: `auto-learn-${r.type}`,
                title: `Auto-learned ${r.type}`,
                language: r.metadata.language || 'mixed',
                tags: [r.type, r.source, ...Object.values(r.metadata).filter(v => v.length < 30)],
                nodeType: r.type,
                filePath: r.metadata.projectName || '',
                timestamp: r.timestamp,
                sessionId: r.sessionId,
                metadata: r.metadata,
            }));
            fs.writeFileSync(filepath, lines.join('\n') + '\n', 'utf-8');
            // Also copy to Training Studio uploads directory for immediate queueing
            const studioPath = path.join(TRAINING_STUDIO_DIR, filename);
            fs.copyFileSync(filepath, studioPath);
            this.state.totalFlushed += records.length;
            this.state.lastFlushTime = new Date().toISOString();
            this.saveState();
            console.log(`[AutoLearn] Flushed ${records.length} interactions → ${filename}`);
        }
        catch (err) {
            // If write fails, put records back in buffer
            this.buffer = [...records, ...this.buffer];
            if (this.buffer.length > MAX_BUFFER_SIZE) {
                this.buffer = this.buffer.slice(-FLUSH_BATCH_SIZE);
            }
            console.error(`[AutoLearn] Flush failed:`, err);
        }
        return records.length;
    }
    /** Convert an interaction record to training text format */
    recordToTrainingText(record) {
        switch (record.type) {
            case 'conversation': {
                try {
                    const parsed = JSON.parse(record.content);
                    return `${parsed.prompt}\n\n${parsed.response}`;
                }
                catch {
                    return record.content;
                }
            }
            case 'code_generation':
                return `Generate ${record.metadata.language || 'code'} for: ${record.metadata.nodeLabel || 'unknown'}\n\n${record.content}`;
            case 'design_saved':
                return `Design: ${record.metadata.projectName || 'untitled'} (${record.metadata.nodeCount || 0} nodes)\n\n${record.content}`;
            case 'terminal_message':
                return record.content;
            case 'node_created':
                return `Node created: ${record.metadata.nodeLabel || 'unknown'} (${record.metadata.nodeType || 'logic'})\n\n${record.content}`;
            default:
                return record.content;
        }
    }
    /** Get list of flushed JSONL files, sorted newest first */
    getFlushedFiles() {
        try {
            if (!fs.existsSync(AUTO_LEARN_DIR))
                return [];
            return fs.readdirSync(AUTO_LEARN_DIR)
                .filter(f => f.endsWith('.jsonl'))
                .map(f => path.join(AUTO_LEARN_DIR, f))
                .sort()
                .reverse();
        }
        catch {
            return [];
        }
    }
    /** Auto-trigger MindSpace progressive training on the external GPU-enabled MindSpace */
    async triggerMindSpaceTraining() {
        if (isAutoLearnDisabled())
            return;
        if (this.state.interactionsSinceLastTraining < MINDSPACE_TRAINING_THRESHOLD)
            return;
        console.log('[AutoLearn] 🧠 Training threshold reached! Triggering MindSpace training...');
        // 1. Export all captured data to knowledge store for pattern learning (local)
        try {
            const flushedFiles = this.getFlushedFiles();
            for (const fp of flushedFiles.slice(0, 20)) {
                const content = fs.readFileSync(fp, 'utf-8');
                const lines = content.trim().split('\n').filter(Boolean);
                for (const line of lines) {
                    try {
                        const record = JSON.parse(line);
                        knowledgeStore.addPattern({
                            category: 'code_pattern',
                            title: record.title || 'Auto-learned Pattern',
                            code: record.text || '',
                            description: `Auto-learned from ${record.source || 'user interaction'}. Tags: ${(record.tags || []).join(', ')}`,
                            tags: record.tags || ['auto-learned'],
                            projectId: 'auto-learn',
                            targetOS: 'linux',
                            nodeType: record.nodeType || 'generic',
                            language: record.language || 'mixed',
                            success: true,
                            qualityScore: 5.0,
                        });
                    }
                    catch { /* skip */ }
                }
            }
            console.log(`[AutoLearn] Exported patterns to knowledge store`);
        }
        catch (err) {
            console.error(`[AutoLearn] Failed to export to knowledge store:`, err);
        }
        // 2. Sync auto-learn data to external MindSpace trainer directory
        let syncedCount = 0;
        try {
            if (fs.existsSync(EXTERNAL_MINDSPACE_DIR)) {
                // Ensure external trainer dir exists
                fs.mkdirSync(EXTERNAL_MINDSPACE_TRAINER_DIR, { recursive: true });
                // Write current buffer + flushed files as a consolidated datasheet
                // Use a FIXED filename (overwrite) to avoid accumulating duplicate datasheets
                const allRecords = [];
                const flushedFiles = this.getFlushedFiles();
                for (const fp of flushedFiles.slice(0, 200)) {
                    try {
                        const content = fs.readFileSync(fp, 'utf-8');
                        for (const line of content.trim().split('\n').filter(Boolean)) {
                            try {
                                allRecords.push(JSON.parse(line));
                            }
                            catch { /* skip */ }
                        }
                    }
                    catch { /* skip */ }
                }
                if (allRecords.length > 0) {
                    const outPath = path.join(EXTERNAL_MINDSPACE_TRAINER_DIR, 'datasheet-auto-learn.jsonl');
                    const lines = allRecords.map(r => JSON.stringify({
                        text: r.text || '',
                        source: r.source || 'auto-learn',
                        title: r.title || 'Auto-learned Interaction',
                        language: r.language || 'mixed',
                        tags: Array.isArray(r.tags) ? r.tags : ['auto-learned'],
                        timestamp: r.timestamp || new Date().toISOString(),
                    }));
                    fs.writeFileSync(outPath, lines.join('\n') + '\n', 'utf-8');
                    syncedCount = allRecords.length;
                    console.log(`[AutoLearn] Synced ${syncedCount} records → external MindSpace trainer`);
                }
                // Also copy local MindSpace trainer datasheets if external doesn't have them
                if (fs.existsSync(MINDSAPCE_TRAINER_DIR)) {
                    for (const f of fs.readdirSync(MINDSAPCE_TRAINER_DIR)) {
                        if (f.endsWith('.jsonl') && !f.startsWith('.')) {
                            const src = path.join(MINDSAPCE_TRAINER_DIR, f);
                            const dst = path.join(EXTERNAL_MINDSPACE_TRAINER_DIR, f);
                            if (!fs.existsSync(dst)) {
                                fs.copyFileSync(src, dst);
                            }
                        }
                    }
                }
            }
            else {
                console.log(`[AutoLearn] External MindSpace not found at ${EXTERNAL_MINDSPACE_DIR}, using local`);
            }
        }
        catch (err) {
            console.error(`[AutoLearn] Sync to external MindSpace failed:`, err);
        }
        // 3. Signal the daemon by touching the flag file (daemon checks for data changes)
        //    The daemon script `scripts/train-mindspace-daemon.sh` handles actual training.
        //    This avoids duplicate training triggers between the service and the daemon.
        try {
            const { execSync } = await import('child_process');
            execSync('touch /tmp/mindspace-daemon-trigger', { timeout: 2000 });
            console.log(`[AutoLearn] Signaled MindSpace training daemon (sync'd ${syncedCount} records)`);
        }
        catch (err) {
            console.log(`[AutoLearn] Daemon signal skipped — daemon may not be running (${err})`);
        }
        this.state.mindspaceTrainingCount++;
        this.state.lastTrainingTrigger = new Date().toISOString();
        this.state.interactionsSinceLastTraining = 0;
        this.saveState();
    }
}
// ─── Singleton Export ─────────────────────────────────────────────────────
export const autoLearnService = new AutoLearnService();
