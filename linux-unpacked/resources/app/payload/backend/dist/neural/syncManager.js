/**
 * Venorica -- Sync Manager
 * Tracks the total size of Venorica's training data and automatically
 * exports patterns as JSONL to the LLM Training Studio
 * when the 50MB threshold is exceeded.
 */
import { existsSync, writeFileSync, mkdirSync, readdirSync, statSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { knowledgeStore } from '../knowledge/knowledgeStore.js';
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const KNOWLEDGE_DIR = join(__dirname, '..', '..', 'knowledge');
const TRAINING_STUDIO_DIR = join(__dirname, '..', '..', '..', 'llm-training-app', 'data', 'uploads');
/** Default threshold: 50 MB */
const DEFAULT_THRESHOLD_BYTES = 50 * 1024 * 1024;
let syncState = {
    lastSyncTimestamp: null,
    lastSyncResult: null,
    lastPatternCount: 0,
};
function formatBytes(bytes) {
    if (bytes === 0)
        return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    const val = bytes / Math.pow(1024, i);
    return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}
export function getKnowledgeDirSize() {
    try {
        if (!existsSync(KNOWLEDGE_DIR)) {
            return { bytes: 0, human: '0 B' };
        }
        const entries = readdirSync(KNOWLEDGE_DIR);
        let totalBytes = 0;
        for (const entry of entries) {
            try {
                const stats = statSync(join(KNOWLEDGE_DIR, entry));
                if (stats.isFile())
                    totalBytes += stats.size;
            }
            catch { /* skip unreadable */ }
        }
        return { bytes: totalBytes, human: formatBytes(totalBytes) };
    }
    catch (e) {
        console.warn('[Venorica Sync] Failed to calculate knowledge dir size:', e);
        return { bytes: 0, human: '0 B' };
    }
}
function ensureStudioDir() {
    try {
        if (!existsSync(TRAINING_STUDIO_DIR)) {
            mkdirSync(TRAINING_STUDIO_DIR, { recursive: true });
        }
        return true;
    }
    catch (e) {
        console.warn('[Venorica Sync] Cannot create Training Studio directory:', e);
        return false;
    }
}
function exportToStudio() {
    try {
        if (!ensureStudioDir())
            return null;
        const allPatterns = knowledgeStore.getAll();
        if (allPatterns.length === 0)
            return null;
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `venorica-sync-${timestamp}.jsonl`;
        const exportPath = join(TRAINING_STUDIO_DIR, filename);
        // Generate JSONL using PatternEntry properties
        const lines = allPatterns.map(function (p) {
            return JSON.stringify({
                text: p.code,
                title: p.title,
                language: p.language,
                nodeType: p.nodeType,
                tags: p.tags,
                source: 'venorica',
                timestamp: p.createdAt,
            });
        });
        writeFileSync(exportPath, lines.join('\n'), 'utf-8');
        console.log(`[Venorica Sync] Exported ${allPatterns.length} patterns to ${exportPath}`);
        return exportPath;
    }
    catch (e) {
        console.error('[Venorica Sync] Export failed:', e);
        return null;
    }
}
export function checkAndSync(thresholdBytes = DEFAULT_THRESHOLD_BYTES) {
    const { bytes, human } = getKnowledgeDirSize();
    const patternCount = knowledgeStore.count();
    const thresholdReached = bytes >= thresholdBytes;
    const pct = bytes > 0 ? ((bytes / thresholdBytes) * 100).toFixed(1) : '0.0';
    const result = {
        totalBytes: bytes,
        totalSize: human,
        thresholdReached,
        thresholdPercent: pct,
        patternCount,
        currentSheet: knowledgeStore.getCurrentSheet(),
        sheetCap: 100,
        lastSyncTimestamp: syncState.lastSyncTimestamp,
        lastSyncResult: syncState.lastSyncResult,
    };
    if (thresholdReached) {
        const hasNewData = patternCount !== syncState.lastPatternCount;
        const hasNotExportedYet = !syncState.lastSyncTimestamp;
        if (hasNewData || hasNotExportedYet) {
            const exportPath = exportToStudio();
            if (exportPath) {
                const now = new Date().toISOString();
                syncState.lastSyncTimestamp = now;
                syncState.lastSyncResult = 'synced';
                syncState.lastPatternCount = patternCount;
                result.lastSyncTimestamp = now;
                result.lastSyncResult = 'synced';
                console.log(`[Venorica Sync] Auto-synced ${human} of training data to LLM Training Studio`);
            }
            else {
                syncState.lastSyncResult = 'export-failed';
                result.lastSyncResult = 'export-failed';
            }
        }
        else {
            result.lastSyncResult = 'up-to-date';
        }
    }
    else {
        console.log(`[Venorica Sync] Training data at ${human} (${pct}% of 50 MB threshold)`);
    }
    return result;
}
export function forceSync() {
    const { bytes, human } = getKnowledgeDirSize();
    const exportPath = exportToStudio();
    if (exportPath) {
        const now = new Date().toISOString();
        syncState.lastSyncTimestamp = now;
        syncState.lastSyncResult = 'synced';
        syncState.lastPatternCount = knowledgeStore.count();
        return { success: true, path: exportPath, message: `Exported ${human} of training data to LLM Training Studio` };
    }
    return { success: false, path: null, message: 'Export failed -- check console for details' };
}
export function getSyncStatus() {
    const { bytes, human } = getKnowledgeDirSize();
    const patternCount = knowledgeStore.count();
    const pct = bytes > 0 ? ((bytes / DEFAULT_THRESHOLD_BYTES) * 100).toFixed(1) : '0.0';
    return {
        totalBytes: bytes,
        totalSize: human,
        thresholdReached: bytes >= DEFAULT_THRESHOLD_BYTES,
        thresholdPercent: pct,
        patternCount,
        currentSheet: knowledgeStore.getCurrentSheet(),
        sheetCap: 100,
        lastSyncTimestamp: syncState.lastSyncTimestamp,
        lastSyncResult: syncState.lastSyncResult,
    };
}
