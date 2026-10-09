import { Router } from 'express';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
const __dirname = dirname(fileURLToPath(import.meta.url));
export const soulRoutes = Router();
export const DEFAULT_SOUL = {
    identity: {
        name: 'Veronica',
        role: 'AI Code Architect — AI-powered software design and code generation assistant (VACA platform, assistant: Veronica)',
        description: 'Intelligent, proactive, and technically precise. Helps users design software architecture visually and generate production-ready code.',
    },
    personality: {
        traits: {
            warmth: 25,
            sassiness: 60,
            verbosity: 32,
            technical_depth: 95,
            creativity: 73,
            empathy: 20,
            formality: 50,
            proactiveness: 60,
            curiosity: 90,
            patience: 40,
        },
    },
    change_history: {
        entries: [],
    },
};
function getSoulPath() {
    const projectRoot = resolve(__dirname, '..', '..', '..');
    return resolve(projectRoot, 'data', 'soul.json');
}
function loadSoul() {
    const path = getSoulPath();
    try {
        if (existsSync(path)) {
            const raw = readFileSync(path, 'utf-8');
            const parsed = JSON.parse(raw);
            // If the file has the change_history wrapper format
            if (parsed.personality || parsed.identity) {
                return parsed;
            }
        }
    }
    catch (e) {
        console.warn('[soul] Failed to load soul.json, using defaults');
    }
    return { ...DEFAULT_SOUL };
}
function saveSoul(soul) {
    try {
        const path = getSoulPath();
        writeFileSync(path, JSON.stringify(soul, null, 2), 'utf-8');
        return true;
    }
    catch (e) {
        console.error('[soul] Failed to save soul.json:', e);
        return false;
    }
}
/**
 * GET /api/soul
 * Returns the current soul/personality configuration
 */
soulRoutes.get('/', (_req, res) => {
    try {
        const soul = loadSoul();
        res.json({
            success: true,
            soul,
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Failed to load soul config',
        });
    }
});
/**
 * PUT /api/soul/traits
 * Update one or more personality trait values
 */
soulRoutes.put('/traits', (req, res) => {
    try {
        const { traits } = req.body;
        if (!traits || typeof traits !== 'object') {
            return res.status(400).json({ success: false, error: 'Traits object is required' });
        }
        const soul = loadSoul();
        const timestamp = new Date().toISOString();
        const changes = {};
        for (const [trait, value] of Object.entries(traits)) {
            if (typeof value !== 'number')
                continue;
            const oldVal = soul.personality.traits[trait];
            if (oldVal === undefined)
                continue;
            const clamped = Math.max(0, Math.min(100, value));
            if (oldVal !== clamped) {
                changes[`personality.traits.${trait}`] = { old: oldVal, new: clamped };
                soul.personality.traits[trait] = clamped;
            }
        }
        if (Object.keys(changes).length > 0) {
            const changeId = `chg_${Date.now()}`;
            soul.change_history.entries.push({
                id: changeId,
                type: 'personality_tweak',
                description: Object.entries(changes)
                    .map(([k, v]) => `Changed ${k.split('.').pop()} from ${v.old} to ${v.new}`)
                    .join(', '),
                changes,
                reason: 'User requested personality adjustment',
                requested_by: 'user',
                approved: true,
                revertible: true,
                timestamp,
            });
        }
        const saved = saveSoul(soul);
        res.json({
            success: saved,
            soul,
            changes,
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Failed to update traits',
        });
    }
});
/**
 * PUT /api/soul/identity
 * Update the AI soul identity fields
 */
soulRoutes.put('/identity', (req, res) => {
    try {
        const { name, role, description } = req.body;
        const soul = loadSoul();
        if (name)
            soul.identity.name = name;
        if (role)
            soul.identity.role = role;
        if (description)
            soul.identity.description = description;
        const saved = saveSoul(soul);
        res.json({
            success: saved,
            soul,
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Failed to update identity',
        });
    }
});
/**
 * POST /api/soul/reset
 * Reset soul to defaults
 */
soulRoutes.post('/reset', (_req, res) => {
    try {
        const saved = saveSoul({ ...DEFAULT_SOUL });
        res.json({
            success: saved,
            soul: { ...DEFAULT_SOUL },
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error instanceof Error ? error.message : 'Failed to reset soul',
        });
    }
});
