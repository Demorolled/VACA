/**
 * Fast Preview Preference Routes — Global toggle for faster preview builds
 * ========================================================================
 *
 * When enabled, code generation skips sandbox validation and security scans
 * to deliver previews as fast as possible. The progress bar still streams.
 *
 * Config is persisted to data/fast-preview-preference.json
 */
import { Router } from 'express';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
const __dirname = dirname(fileURLToPath(import.meta.url));
// ─── Persistence ──────────────────────────────────────────────────────────
function getConfigPath() {
    const projectRoot = resolve(__dirname, '..', '..', '..');
    return resolve(projectRoot, 'data', 'fast-preview-preference.json');
}
const DEFAULT = {
    enabled: false,
    updatedAt: new Date().toISOString(),
};
function loadPreference() {
    const path = getConfigPath();
    try {
        if (existsSync(path)) {
            const raw = readFileSync(path, 'utf-8');
            const parsed = JSON.parse(raw);
            return {
                enabled: parsed.enabled === true,
                updatedAt: parsed.updatedAt || new Date().toISOString(),
            };
        }
    }
    catch (e) {
        console.warn('[fastPreview] Failed to load, using default:', e);
    }
    return { ...DEFAULT };
}
function savePreference(enabled) {
    const data = { enabled, updatedAt: new Date().toISOString() };
    try {
        writeFileSync(getConfigPath(), JSON.stringify(data, null, 2), 'utf-8');
    }
    catch (e) {
        console.error('[fastPreview] Failed to save:', e);
    }
    return data;
}
// ─── Routes ───────────────────────────────────────────────────────────────
export const fastPreviewPreferenceRoutes = Router();
/**
 * GET /api/fast-preview-preference
 * Returns whether fast preview mode is enabled.
 */
fastPreviewPreferenceRoutes.get('/', (_req, res) => {
    const config = loadPreference();
    res.json({
        success: true,
        enabled: config.enabled,
        updatedAt: config.updatedAt,
    });
});
/**
 * POST /api/fast-preview-preference
 * Body: { enabled: boolean }
 * Sets the fast preview mode.
 */
fastPreviewPreferenceRoutes.post('/', (req, res) => {
    try {
        const { enabled } = req.body;
        const valid = enabled === true || enabled === false;
        if (!valid) {
            return res.status(400).json({
                success: false,
                error: 'Invalid value. Must be a boolean (true/false).',
            });
        }
        const config = savePreference(enabled);
        console.log(`[fastPreview] Set fast preview mode to: ${enabled}`);
        res.json({
            success: true,
            enabled: config.enabled,
            updatedAt: config.updatedAt,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : 'Failed to set preference';
        res.status(500).json({ success: false, error: msg });
    }
});
