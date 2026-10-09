/**
 * Shared Context Store
 * ====================
 *
 * File-backed shared state that both the
 * terminal and GUI can read/write. Uses the same pattern as the existing
 * TTS config storage (read/write JSON file).
 *
 * The terminal watches this via polling. The GUI watches via polling.
 * Both write via POST /api/context.
 *
 * This implements Veronica's "Shared State Store (The Telepathy Method)."
 */
import { Router } from 'express';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join } from 'path';
/** Path to the shared context file */
const CACHE_DIR = join(import.meta.dirname, '..', '..', '.session_cache');
const CONTEXT_FILE = join(CACHE_DIR, 'context.json');
/** Ensure the cache directory exists */
function ensureCacheDir() {
    if (!existsSync(CACHE_DIR)) {
        mkdirSync(CACHE_DIR, { recursive: true });
    }
}
/** Load the full context from disk */
function loadContext() {
    ensureCacheDir();
    if (!existsSync(CONTEXT_FILE))
        return {};
    try {
        return JSON.parse(readFileSync(CONTEXT_FILE, 'utf-8'));
    }
    catch {
        // File corrupted — reset
        return {};
    }
}
/** Save the full context to disk */
function saveContext(context) {
    ensureCacheDir();
    writeFileSync(CONTEXT_FILE, JSON.stringify(context, null, 2), 'utf-8');
}
export const contextRoutes = Router();
/**
 * GET /api/context
 * Returns the full shared context.
 */
contextRoutes.get('/', (_req, res) => {
    const context = loadContext();
    res.json({ success: true, context });
});
/**
 * POST /api/context
 * Updates the shared context. Supports two modes:
 *
 * 1. Single key: { key: "theme", value: "neon-sunset" }
 * 2. Bulk update: { updates: { theme: "dark", volume: 0.8 } }
 *
 * Returns the full context after the update.
 */
contextRoutes.post('/', (req, res) => {
    const { key, value, updates } = req.body;
    const context = loadContext();
    if (key !== undefined && key !== null) {
        context[String(key)] = value;
    }
    if (updates && typeof updates === 'object' && !Array.isArray(updates)) {
        Object.assign(context, updates);
    }
    saveContext(context);
    res.json({ success: true, context });
});
/**
 * DELETE /api/context/:key
 * Remove a key from the shared context.
 */
contextRoutes.delete('/:key', (req, res) => {
    const { key } = req.params;
    const context = loadContext();
    delete context[key];
    saveContext(context);
    res.json({ success: true, context });
});
/**
 * GET /api/context/:key
 * Returns a single key from the shared context.
 */
contextRoutes.get('/:key', (req, res) => {
    const { key } = req.params;
    const context = loadContext();
    if (!(key in context)) {
        res.status(404).json({ success: false, error: `Key "${key}" not found` });
        return;
    }
    res.json({ success: true, key, value: context[key] });
});
