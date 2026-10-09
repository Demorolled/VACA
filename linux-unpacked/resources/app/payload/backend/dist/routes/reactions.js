/**
 * Chat Reaction Routes — server-side persistence for message reactions
 * ======================================================================
 *
 * Previously reactions lived only in localStorage (`ai-reactions`), so they
 * never left the device. This module moves the source of truth to the backend
 * (data/chat-reactions.json) so counts sync across devices/browsers.
 *
 * Identity model: there is no auth in VACA, so each client generates a stable
 * anonymous userId (kept in localStorage) and sends it with every request.
 * The server stores per-message: aggregate counts + a userId -> emoji map, so
 * un-react and switch-reaction semantics are computed server-side and stay
 * consistent no matter which device last wrote.
 *
 * API:
 *   GET  /api/reactions/:messageId?userId=<id>  -> { counts, user }
 *   POST /api/reactions/:messageId              -> { emoji, userId } toggle
 */
import { Router } from 'express';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
const __dirname = dirname(fileURLToPath(import.meta.url));
// ─── Known reactions (must match frontend/src/components/MessageReactions.tsx) ───
export const REACTIONS = ['❤️', '👍', '😕', '🚀', '😡', '😂', '🤩'];
// ─── Persistence ──────────────────────────────────────────────────────────
function getDataPath() {
    const projectRoot = resolve(__dirname, '..', '..', '..');
    return resolve(projectRoot, 'data', 'chat-reactions.json');
}
function loadStore() {
    const path = getDataPath();
    try {
        if (existsSync(path)) {
            const parsed = JSON.parse(readFileSync(path, 'utf-8'));
            if (parsed && typeof parsed === 'object')
                return parsed;
        }
    }
    catch (e) {
        console.warn('[reactions] Failed to load store, starting empty:', e);
    }
    return {};
}
function saveStore(store) {
    try {
        writeFileSync(getDataPath(), JSON.stringify(store, null, 2), 'utf-8');
    }
    catch (e) {
        console.error('[reactions] Failed to save store:', e);
    }
}
function emptyState() {
    return { counts: {}, users: {} };
}
// ─── Pure toggle logic (unit-tested) ──────────────────────────────────────
/**
 * Apply a reaction toggle for one user on one message. Mirrors the original
 * client semantics exactly: clicking your active emoji un-reacts, clicking a
 * different emoji switches. Returns a NEW state (inputs are not mutated).
 */
export function applyReaction(state, userId, emoji) {
    const s = state && state.counts && state.users
        ? { counts: { ...state.counts }, users: { ...state.users } }
        : emptyState();
    const current = s.users[userId];
    if (current === emoji) {
        // Un-react
        delete s.users[userId];
        const cur = (s.counts[emoji] ?? 0) - 1;
        if (cur > 0)
            s.counts[emoji] = cur;
        else
            delete s.counts[emoji];
    }
    else {
        // Remove any previous reaction, then add the new one
        if (current) {
            const prev = (s.counts[current] ?? 0) - 1;
            if (prev > 0)
                s.counts[current] = prev;
            else
                delete s.counts[current];
        }
        s.users[userId] = emoji;
        s.counts[emoji] = (s.counts[emoji] ?? 0) + 1;
    }
    return s;
}
// ─── Routes ───────────────────────────────────────────────────────────────
export const reactionsRoutes = Router();
/**
 * GET /api/reactions/:messageId?userId=<id>
 * Returns the aggregate counts for a message plus the requesting user's own
 * reaction (null if they haven't reacted).
 */
reactionsRoutes.get('/:messageId', (req, res) => {
    try {
        const { messageId } = req.params;
        const userId = typeof req.query.userId === 'string' ? req.query.userId : '';
        const state = loadStore()[messageId] || emptyState();
        res.json({
            success: true,
            data: {
                counts: state.counts || {},
                user: userId && state.users ? (state.users[userId] ?? null) : null,
            },
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : 'Failed to load reactions';
        res.status(500).json({ success: false, error: msg });
    }
});
/**
 * POST /api/reactions/:messageId
 * Body: { emoji: string, userId: string }
 * Toggles the user's reaction on the message and returns the updated state.
 */
reactionsRoutes.post('/:messageId', (req, res) => {
    try {
        const { messageId } = req.params;
        const { emoji, userId } = (req.body || {});
        if (typeof userId !== 'string' || !userId.trim()) {
            return res.status(400).json({ success: false, error: 'userId is required.' });
        }
        if (typeof emoji !== 'string' || !REACTIONS.includes(emoji)) {
            return res.status(400).json({
                success: false,
                error: `emoji must be one of: ${REACTIONS.join(' ')}`,
            });
        }
        const uid = userId.trim().slice(0, 128);
        const store = loadStore();
        store[messageId] = applyReaction(store[messageId], uid, emoji);
        saveStore(store);
        res.json({
            success: true,
            data: {
                counts: store[messageId].counts,
                user: store[messageId].users[uid] ?? null,
            },
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : 'Failed to save reaction';
        res.status(500).json({ success: false, error: msg });
    }
});
