/**
 * Todo routes — serve the deep-scan todo list (TODO fixes.txt) to the
 * frontend so the chat's "open the todo list" opens a REAL view of it
 * instead of the LLM just claiming one (same pattern as the wiki window).
 *
 * GET /api/todo → { success, sections: [{ number, title, priority, items }],
 *                   summary, meta, lastUpdated }
 *
 * File format:
 *   ================ ... (header block — captured as `meta`)
 *   VACA + LLM — DEEP-SCAN TODO  (generated 2026-08-09)
 *   ================ ...
 *   What was checked: ...      ← meta continues until the first SECTION
 *   PRIORITY KEY: ...
 *   ---------------- ...
 *   SECTION 1 — CRITICAL RISK (P0)
 *   ---------------- ...
 *   [ ] 1.1 NO GIT HISTORY — ...
 *       every file, zero commits, ...   ← indented continuation lines
 *   [x] 1.3 ...  (checked item → done: true)
 *   ---------------- ...
 *   SECTION 2 — LLM SERVING & MODEL (P0/P1)
 *   ...
 */
import { Router } from 'express';
import { readFileSync, existsSync, statSync } from 'fs';
import { resolve } from 'path';
// Resolve to the repo ROOT (3 levels up from backend/src/routes — the same
// convention as WIKI_PATH in internalKnowledge.ts). The previous 4-level
// resolve pointed at the repo's PARENT directory, so the route could never
// find a TODO fixes.txt placed at the repo root as documented.
export const TODO_PATH = process.env.VACA_TODO_PATH ||
    resolve(import.meta.dirname, '..', '..', '..', 'TODO fixes.txt');
const SECTION_HEADER = /^SECTION\s+(\d{1,2})\s*[—-]\s*(.+)$/i;
const ITEM_LINE = /^\[([ xX])\]\s+(\d+\.\d+)\s+(.*)$/;
const PRIORITY_TAG = /\(([^)]*)\)/;
function priorityOf(title) {
    const m = title.match(PRIORITY_TAG);
    const tag = m ? m[1].trim().toUpperCase() : '';
    // Only treat recognizable priority tags as priorities (P0 / P1 / P2 or
    // combos like "P0/P1") — other parentheticals stay part of the title.
    return /^(?:P\d+(?:\s*\/\s*P\d+)*)$/.test(tag) ? tag : null;
}
/**
 * Parse the todo list into numbered sections with checkbox items. Item
 * continuation lines are indented (start with whitespace) and are folded into
 * the current item's text; blank lines separate items. Everything before the
 * first SECTION header is captured as free-form `meta` (what was checked,
 * baseline health, priority key).
 */
export function parseTodoList(text) {
    const lines = text.split('\n');
    const sections = [];
    const meta = [];
    let current = null;
    let currentItem = null;
    for (const line of lines) {
        const header = line.match(SECTION_HEADER);
        if (header) {
            // Finalize previous section/item.
            if (currentItem && current)
                current.items.push(currentItem);
            currentItem = null;
            current = {
                number: parseInt(header[1], 10),
                title: header[2].trim(),
                priority: priorityOf(header[2]),
                items: [],
            };
            sections.push(current);
            continue;
        }
        const item = line.match(ITEM_LINE);
        if (item) {
            if (currentItem && current)
                current.items.push(currentItem);
            currentItem = {
                id: item[2],
                text: item[3].trim(),
                done: item[1].toLowerCase() === 'x',
            };
            continue;
        }
        if (currentItem && current) {
            // Indented continuation of the current item; blank lines separate items.
            if (line.trim() !== '' && /^\s/.test(line)) {
                currentItem.text += ' ' + line.trim().replace(/\s+/g, ' ');
            }
            continue;
        }
        if (!current) {
            // Header block — capture everything before the first SECTION header.
            const t = line.trim();
            if (t && t !== 'EOF')
                meta.push(t);
        }
    }
    if (currentItem && current)
        current.items.push(currentItem);
    const summary = { total: 0, open: 0, done: 0, byPriority: {} };
    for (const s of sections) {
        for (const it of s.items) {
            summary.total += 1;
            if (it.done)
                summary.done += 1;
            else
                summary.open += 1;
        }
        const key = s.priority || 'OTHER';
        if (!summary.byPriority[key])
            summary.byPriority[key] = { open: 0, total: 0 };
        for (const it of s.items) {
            summary.byPriority[key].total += 1;
            if (!it.done)
                summary.byPriority[key].open += 1;
        }
    }
    return { sections, summary, meta };
}
export const todoRoutes = Router();
todoRoutes.get('/', (_req, res) => {
    try {
        if (!existsSync(TODO_PATH)) {
            res.status(404).json({ success: false, error: 'Todo file not found' });
            return;
        }
        const text = readFileSync(TODO_PATH, 'utf-8');
        const { sections, summary, meta } = parseTodoList(text);
        let lastUpdated = null;
        try {
            lastUpdated = statSync(TODO_PATH).mtime.toISOString();
        }
        catch {
            // mtime unavailable — omit
        }
        res.json({ success: true, sections, summary, meta, lastUpdated });
    }
    catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});
