import { Router } from 'express';
import { existsSync, readFileSync, readdirSync } from 'fs';
import { execSync } from 'child_process';
import path from 'path';
const router = Router();
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const MINDSAPCE_DIR = path.join(PROJECT_ROOT, 'MindSpace');
const STATE_FILE = path.join(MINDSAPCE_DIR, 'progressive_state.json');
const CHECKPOINTS_META = path.join(MINDSAPCE_DIR, 'weights', 'checkpoints', 'checkpoints.json');
const TRAINING_LOG = '/tmp/mindspace-training.log';
// 13M training paths
const TRAIN13M_DIR = path.join(MINDSAPCE_DIR, 'train-13m');
const TRAIN13M_STATE = path.join(TRAIN13M_DIR, 'progressive_state.json');
const TRAIN13M_LOG = '/tmp/mindspace-13m-resume.log';
const TRAIN13M_CHECKPOINTS = path.join(TRAIN13M_DIR, 'weights', 'checkpoints', 'checkpoints.json');
// 350M training paths
const TRAIN350M_DIR = path.join(MINDSAPCE_DIR, 'train-350m');
const TRAIN350M_STATE = path.join(TRAIN350M_DIR, 'progressive_state.json');
const TRAIN350M_LOG = '/tmp/mindspace-350m-ckpt.log';
const TRAIN350M_CHECKPOINTS = path.join(TRAIN350M_DIR, 'weights', 'checkpoints', 'checkpoints.json');
const TIER_NAMES = [
    '01_micro_foundation',
    '02_tiny_patterns',
    '03_small_knowledge',
    '04_medium_knowledge',
    '05_large_knowledge',
    '06_xlarge_knowledge',
    '07_synthetic_vision',
    '08_text_more',
    '09_text_150k',
    '10_text_comprehensive',
    '11_text_massive',
];
/**
 * Format tier name for display: "08_text_more" → "Text More"
 */
function formatTierName(name) {
    return name
        .replace(/^\d+_/, '')
        .split('_')
        .map(w => w.charAt(0).toUpperCase() + w.slice(1))
        .join(' ');
}
/**
 * Check if a specific training process is running
 */
function checkProcessRunning(grepTerm = 'progressive_train') {
    try {
        const output = execSync(`ps aux | grep "${grepTerm}" | grep -v grep`, {
            timeout: 3000,
            encoding: 'utf-8',
        });
        return output.trim().length > 0;
    }
    catch {
        return false;
    }
}
/**
 * Gather training stats for a specific training directory
 */
function gatherTrainingStats(stateFile, logFile, checkpointsMeta, grepTerm, modelName, paramCount, tierNames) {
    // ── 1. Progressive state ──
    let state = {};
    if (existsSync(stateFile)) {
        try {
            state = JSON.parse(readFileSync(stateFile, 'utf-8'));
        }
        catch { /* ignore */ }
    }
    const completedTiers = state.completed_tiers || [];
    const currentTierIdx = state.current_tier_idx ?? 0;
    const bestLoss = state.best_loss ?? null;
    const bestAcc = state.best_acc ?? null;
    const totalEpochs = state.total_epochs ?? 0;
    // ── 2. Tier progress ──
    const tierProgress = tierNames.map((tierName, idx) => ({
        name: tierName,
        label: formatTierName(tierName),
        index: idx,
        completed: completedTiers.includes(tierName),
        current: idx === currentTierIdx,
    }));
    const currentTier = tierNames[currentTierIdx] || null;
    const currentTierLabel = currentTier ? formatTierName(currentTier) : null;
    // ── 3. Checkpoint history ──
    let checkpointHistory = [];
    if (existsSync(checkpointsMeta)) {
        try {
            checkpointHistory = JSON.parse(readFileSync(checkpointsMeta, 'utf-8'));
        }
        catch { /* ignore */ }
    }
    let latestCheckpoint = {};
    if (checkpointHistory.length > 0) {
        latestCheckpoint = checkpointHistory.reduce((a, b) => a.step > b.step ? a : b);
    }
    const lossTrend = checkpointHistory
        .sort((a, b) => a.step - b.step)
        .map((c) => ({ step: c.step, loss: c.loss, accuracy: c.accuracy }));
    // ── 4. Live log ──
    const logLines = tailFile(logFile, 60);
    const logProgress = parseLogProgress(logLines);
    // ── 5. Running? ──
    const isRunning = checkProcessRunning(grepTerm);
    // ── 6. Checkpoint count ──
    let checkpointCount = 0;
    const ckptDir = path.dirname(checkpointsMeta);
    if (existsSync(ckptDir)) {
        try {
            const ckpts = readdirSync(ckptDir).filter(f => f.endsWith('.pt'));
            checkpointCount = ckpts.length;
        }
        catch { /* ignore */ }
    }
    return {
        model: { name: modelName, parameters: paramCount, type: 'transformer' },
        training: {
            isRunning,
            totalEpochs,
            bestLoss: bestLoss !== null ? bestLoss : latestCheckpoint.loss ?? null,
            bestAccuracy: bestLoss !== null ? bestAcc : latestCheckpoint.accuracy ?? null,
            currentTier: currentTierLabel,
            currentTierIndex: currentTierIdx,
            totalTiers: tierNames.length,
            completedTierCount: completedTiers.length,
            tierProgress,
            logProgress: logProgress || {
                epoch: latestCheckpoint.epoch ?? 0,
                maxEpoch: latestCheckpoint.epoch ?? 50,
                step: latestCheckpoint.step ?? 0,
                maxStep: 0,
                loss: latestCheckpoint.loss ?? null,
                accuracy: latestCheckpoint.accuracy ?? null,
            },
            recentLog: logLines.slice(-20),
        },
        checkpoints: {
            total: checkpointCount,
            latest: {
                step: latestCheckpoint.step ?? 0,
                loss: latestCheckpoint.loss ?? null,
                accuracy: latestCheckpoint.accuracy ?? null,
                timestamp: latestCheckpoint.timestamp ?? null,
                epoch: latestCheckpoint.epoch ?? 0,
            },
            history: lossTrend.slice(-100),
        },
    };
}
// TIER names for the 13M and 350M progressive training
const SMALL_TIER_NAMES = [
    '01_micro_foundation',
    '02_tiny_patterns',
    '03_small_knowledge',
    '04_medium_knowledge',
    '05_large_knowledge',
    '06_xlarge_knowledge',
    '07_huge_text',
    '08_massive_text',
    '09_comprehensive',
    '10_final_polish',
];
/**
 * Read the last N lines of a file efficiently
 */
function tailFile(filePath, lines = 50) {
    try {
        const output = execSync(`tail -${lines} "${filePath}" 2>/dev/null`, {
            timeout: 3000,
            encoding: 'utf-8',
        });
        return output.split('\n').filter(Boolean);
    }
    catch {
        return [];
    }
}
/**
 * Parse training progress from a log line like:
 * "Epoch 45/50 | Step 12345/1000000 | Loss: 0.25 | Acc: 93.2%"
 */
function parseLogProgress(lines) {
    for (const line of lines.reverse()) {
        const epochMatch = line.match(/Epoch\s+(\d+)\s*\/\s*(\d+)/i);
        const stepMatch = line.match(/Step\s+([\d,]+)\s*\/\s*([\d,]+)/i);
        const lossMatch = line.match(/Loss[:\s]+([\d.]+)/i);
        const accMatch = line.match(/Acc(?:uracy)?[:\s]+([\d.]+)%?/i);
        if (epochMatch || stepMatch) {
            return {
                epoch: epochMatch ? parseInt(epochMatch[1], 10) : 0,
                maxEpoch: epochMatch ? parseInt(epochMatch[2], 10) : 0,
                step: stepMatch ? parseInt(stepMatch[1].replace(/,/g, ''), 10) : 0,
                maxStep: stepMatch ? parseInt(stepMatch[2].replace(/,/g, ''), 10) : 0,
                loss: lossMatch ? parseFloat(lossMatch[1]) : null,
                accuracy: accMatch ? parseFloat(accMatch[1]) : null,
            };
        }
    }
    return null;
}
// GET /api/mindspace/stats — unified MindSpace training statistics
router.get('/stats', (_req, res) => {
    try {
        // ── 1. Progressive state ──────────────────────────────────────────
        let state = {};
        if (existsSync(STATE_FILE)) {
            try {
                state = JSON.parse(readFileSync(STATE_FILE, 'utf-8'));
            }
            catch { /* ignore corrupt state */ }
        }
        const completedTiers = state.completed_tiers || [];
        const currentTierIdx = state.current_tier_idx ?? 0;
        const bestLoss = state.best_loss ?? null;
        const bestAcc = state.best_acc ?? null;
        const totalEpochs = state.total_epochs ?? 0;
        // Build tier progress info
        const tierProgress = TIER_NAMES.map((tierName, idx) => ({
            name: tierName,
            label: formatTierName(tierName),
            index: idx,
            completed: completedTiers.includes(tierName),
            current: idx === currentTierIdx,
        }));
        const currentTier = TIER_NAMES[currentTierIdx] || null;
        const currentTierLabel = currentTier ? formatTierName(currentTier) : null;
        // ── 2. Checkpoint history ─────────────────────────────────────────
        let checkpointHistory = [];
        if (existsSync(CHECKPOINTS_META)) {
            try {
                checkpointHistory = JSON.parse(readFileSync(CHECKPOINTS_META, 'utf-8'));
            }
            catch { /* ignore */ }
        }
        // Latest checkpoint stats
        let latestCheckpoint = {};
        if (checkpointHistory.length > 0) {
            latestCheckpoint = checkpointHistory.reduce((a, b) => a.step > b.step ? a : b);
        }
        // Compute smoothed loss and accuracy trends
        const lossTrend = checkpointHistory
            .sort((a, b) => a.step - b.step)
            .map((c) => ({ step: c.step, loss: c.loss, accuracy: c.accuracy }));
        // ── 3. Live training log ──────────────────────────────────────────
        const logLines = tailFile(TRAINING_LOG, 60);
        const logProgress = parseLogProgress(logLines);
        // ── 4. Process status ─────────────────────────────────────────────
        const isRunning = checkProcessRunning();
        // ── 5. Datasheet stats ─────────────────────────────────────────────
        const trainerDir = path.join(MINDSAPCE_DIR, 'trainer');
        let totalDatasheets = 0;
        let totalLines = 0;
        if (existsSync(trainerDir)) {
            try {
                const files = readdirSync(trainerDir).filter(f => f.endsWith('.jsonl') && f.startsWith('datasheet-'));
                totalDatasheets = files.length;
                for (const f of files) {
                    try {
                        const content = readFileSync(path.join(trainerDir, f), 'utf-8');
                        totalLines += content.split('\n').filter(l => l.trim()).length;
                    }
                    catch { /* skip */ }
                }
            }
            catch { /* ignore */ }
        }
        // ── 6. Model weights info ─────────────────────────────────────────
        const weightsDir = path.join(MINDSAPCE_DIR, 'weights');
        let checkpointCount = 0;
        let bestPath = '';
        if (existsSync(path.join(weightsDir, 'checkpoints'))) {
            try {
                const ckpts = readdirSync(path.join(weightsDir, 'checkpoints')).filter(f => f.endsWith('.pt'));
                checkpointCount = ckpts.length;
            }
            catch { /* ignore */ }
        }
        if (existsSync(path.join(weightsDir, 'best', 'best.pt'))) {
            bestPath = path.join(weightsDir, 'best', 'best.pt');
        }
        // ── 7. Gather 13M and 350M training stats ───────────────────────────
        const stats13m = gatherTrainingStats(TRAIN13M_STATE, TRAIN13M_LOG, TRAIN13M_CHECKPOINTS, 'train-13m/progressive', 'mindspace-13m', 13100000, SMALL_TIER_NAMES);
        const stats350m = gatherTrainingStats(TRAIN350M_STATE, TRAIN350M_LOG, TRAIN350M_CHECKPOINTS, 'train-350m/progressive', 'mindspace-350m', 285000000, SMALL_TIER_NAMES);
        // ── Assemble response ─────────────────────────────────────────────
        // Try to get GPU info
        let gpuInfo = null;
        try {
            const gpuOut = execSync(`nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader 2>/dev/null`, { timeout: 5000, encoding: 'utf-8' });
            const lines = gpuOut.trim().split('\n').filter(Boolean);
            gpuInfo = lines.map((line) => {
                const parts = line.split(',').map(s => s.trim());
                return {
                    index: parseInt(parts[0] || '0'),
                    name: parts[1] || '',
                    gpuUtil: parts[2] || '',
                    memUsed: parts[3] || '',
                    memTotal: parts[4] || '',
                    temp: parts[5] || '',
                };
            });
        }
        catch { /* ignore */ }
        res.json({
            success: true,
            model: {
                name: 'mindspace-2',
                parameters: 13110528, // fixed for this architecture
                type: 'transformer',
            },
            training: {
                isRunning,
                totalEpochs,
                bestLoss: bestLoss !== null ? bestLoss : latestCheckpoint.loss ?? null,
                bestAccuracy: bestLoss !== null ? bestAcc : latestCheckpoint.accuracy ?? null,
                currentTier: currentTierLabel,
                currentTierIndex: currentTierIdx,
                totalTiers: TIER_NAMES.length,
                completedTierCount: completedTiers.length,
                tierProgress,
                logProgress: logProgress || {
                    epoch: latestCheckpoint.epoch ?? 0,
                    maxEpoch: latestCheckpoint.epoch ?? 50,
                    step: latestCheckpoint.step ?? 0,
                    maxStep: 0,
                    loss: latestCheckpoint.loss ?? null,
                    accuracy: latestCheckpoint.accuracy ?? null,
                },
                recentLog: logLines.slice(-20),
            },
            checkpoints: {
                total: checkpointCount,
                latest: {
                    step: latestCheckpoint.step ?? 0,
                    loss: latestCheckpoint.loss ?? null,
                    accuracy: latestCheckpoint.accuracy ?? null,
                    timestamp: latestCheckpoint.timestamp ?? null,
                    epoch: latestCheckpoint.epoch ?? 0,
                },
                history: lossTrend.slice(-100), // last 100 checkpoints
            },
            datasheets: {
                total: totalDatasheets,
                totalLines,
            },
            // ── GPU + dual training info ──
            gpuInfo,
            train13m: stats13m,
            train350m: stats350m,
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
export default router;
