import { describe, it, expect } from 'vitest';
import { existsSync, readFileSync } from 'fs';
import { parseTodoList, TODO_PATH, todoRoutes } from './todo.js';
describe('parseTodoList', () => {
    it('parses sections with checkbox items and indented continuations', () => {
        const text = [
            'VACA + LLM — DEEP-SCAN TODO  (generated 2026-08-09)',
            '--------------------------------------------------------------------------------',
            'SECTION 1 — CRITICAL RISK (P0)',
            '--------------------------------------------------------------------------------',
            '[ ] 1.1 NO GIT HISTORY — the entire repo is untracked',
            '    every file, zero commits, no .gitignore coverage.',
            '    → git init, write a real .gitignore.',
            '',
            '[x] 1.3 Frontend was ~4% tested. **Now 161 tests.**',
            '    → Still untested: llmStore.',
            '',
            '--------------------------------------------------------------------------------',
            'SECTION 2 — LLM SERVING & MODEL (P0/P1)',
            '--------------------------------------------------------------------------------',
            '[ ] 2.1 Speculative decoding is OFF by default.',
            '',
            'EOF',
        ].join('\n');
        const { sections, summary, meta } = parseTodoList(text);
        expect(sections).toHaveLength(2);
        expect(sections[0]).toMatchObject({ number: 1, title: 'CRITICAL RISK (P0)', priority: 'P0' });
        expect(sections[1].title).toBe('LLM SERVING & MODEL (P0/P1)');
        expect(sections[1].priority).toBe('P0/P1');
        expect(sections[0].items).toHaveLength(2);
        expect(sections[0].items[0]).toEqual({
            id: '1.1',
            done: false,
            text: 'NO GIT HISTORY — the entire repo is untracked every file, zero commits, no .gitignore coverage. → git init, write a real .gitignore.',
        });
        expect(sections[0].items[1]).toMatchObject({ id: '1.3', done: true });
        expect(sections[0].items[1].text).toContain('**Now 161 tests.**');
        expect(sections[0].items[1].text).toContain('Still untested: llmStore.');
        // Summary counts.
        expect(summary.total).toBe(3);
        expect(summary.open).toBe(2);
        expect(summary.done).toBe(1);
        expect(summary.byPriority.P0).toEqual({ open: 1, total: 2 });
        expect(summary.byPriority['P0/P1']).toEqual({ open: 1, total: 1 });
        // Header block lands in meta, separators excluded.
        expect(meta.join('\n')).toContain('DEEP-SCAN TODO');
        expect(meta.join('\n')).not.toContain('SECTION 1');
    });
    it('does not mistake body numbered lists or blank lines for items', () => {
        const text = [
            'preamble',
            '--------------------------------------------------------------------------------',
            'SECTION 3 — CODEGEN QUALITY (P1)',
            '--------------------------------------------------------------------------------',
            '[ ] 3.1 Generated-app quality is 72.6% pass.',
            '      • Accessibility ~0/4 on nearly every app.',
            '      • 5 apps lose state on refresh.',
            '',
            'Section header line inside body: SECTION 9 — NOT A REAL SECTION',
            '--------------------------------------------------------------------------------',
            'EOF',
        ].join('\n');
        const { sections } = parseTodoList(text);
        expect(sections).toHaveLength(1);
        expect(sections[0].number).toBe(3);
        expect(sections[0].items).toHaveLength(1);
        expect(sections[0].items[0].text).toContain('Accessibility ~0/4');
        expect(sections[0].items[0].text).toContain('5 apps lose state on refresh.');
    });
    it('treats non-priority parentheticals as part of the title', () => {
        const text = [
            '--------------------------------------------------------------------------------',
            'SECTION 8 — QUICK WINS (do first, all < 1 hr)',
            '--------------------------------------------------------------------------------',
            '[ ] 8.1 git init.',
        ].join('\n');
        const { sections } = parseTodoList(text);
        expect(sections[0].priority).toBeNull();
        expect(sections[0].title).toBe('QUICK WINS (do first, all < 1 hr)');
        expect(sections[0].items).toHaveLength(1);
        expect(sections[0].items[0]).toMatchObject({ id: '8.1', done: false });
    });
});
describe('todo route — real file or graceful degradation', () => {
    // TODO fixes.txt is an OPTIONAL live artifact: the deep-scan file was
    // archived/removed once its items were knocked off, and VACA_TODO_PATH can
    // point anywhere. Exactly one of the two branches runs depending on whether
    // the file exists — the suite stays green either way while BOTH behaviors
    // (404-on-absent, parse-on-present) stay covered.
    it.skipIf(existsSync(TODO_PATH))('returns a clean 404 (never 500) when the todo file is absent', () => {
        expect(existsSync(TODO_PATH)).toBe(false);
        // Invoke the express route handler directly (todo.ts: the route degrades
        // to { success: false, error: 'Todo file not found' } when the file is
        // missing — it must never throw a 500).
        const stack = todoRoutes.stack;
        const layer = stack.find((l) => l.route?.path === '/');
        const handler = layer.route.stack[0].handle;
        let statusCode = 0;
        let body = null;
        const res = {
            status: (c) => { statusCode = c; return res; },
            json: (b) => { body = b; return res; },
        };
        handler({}, res);
        expect(statusCode).toBe(404);
        expect(body).toEqual({ success: false, error: 'Todo file not found' });
    });
    it.skipIf(!existsSync(TODO_PATH))('parses a real todo file into consistent sections and items', () => {
        // Same resolution as todo.ts TODO_PATH: backend/src/routes -> repo root.
        expect(existsSync(TODO_PATH)).toBe(true);
        const text = readFileSync(TODO_PATH, 'utf-8');
        const { sections, summary, meta } = parseTodoList(text);
        // The deep-scan has 8 sections, all present.
        expect(sections).toHaveLength(8);
        expect(sections.map((s) => s.number)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
        // Known items are present (states change as items get knocked off, so
        // assert presence, not done-ness — except 1.3 which was already [x] when
        // the file was written and stays done).
        const sec1 = sections.find((s) => s.number === 1);
        expect(sec1.items.some((i) => i.id === '1.1')).toBe(true);
        expect(sec1.items.find((i) => i.id === '1.3').done).toBe(true);
        // Section titles carry priorities.
        expect(sections[0].priority).toBe('P0');
        expect(sections[1].priority).toBe('P0/P1');
        // Sanity on summary: every item is counted exactly once.
        const counted = sections.reduce((n, s) => n + s.items.length, 0);
        expect(summary.total).toBe(counted);
        expect(summary.open + summary.done).toBe(summary.total);
        expect(summary.open).toBeGreaterThan(0);
        // Header block is captured as meta.
        expect(meta.join('\n')).toContain('DEEP-SCAN TODO');
        expect(meta.join('\n')).toContain('PRIORITY KEY');
    });
});
