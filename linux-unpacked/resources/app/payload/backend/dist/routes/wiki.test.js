import { describe, it, expect } from 'vitest';
import { existsSync, readFileSync } from 'fs';
import { parseWikiSections, WIKI_PATH } from './wiki.js';
describe('parseWikiSections', () => {
    it('parses numbered sections wrapped by separators', () => {
        const text = [
            'preamble line',
            '======================================================================',
            '1. PROJECT OVERVIEW',
            '======================================================================',
            'Name: VACA',
            '',
            '======================================================================',
            '2. RUNNING SERVICES',
            '======================================================================',
            'Service: backend on :3001',
        ].join('\n');
        const sections = parseWikiSections(text);
        expect(sections).toHaveLength(2);
        expect(sections[0]).toEqual({ number: 1, title: 'PROJECT OVERVIEW', body: 'Name: VACA' });
        expect(sections[1]).toEqual({ number: 2, title: 'RUNNING SERVICES', body: 'Service: backend on :3001' });
    });
    it('does not mistake numbered body lists for section headers', () => {
        const text = [
            '======================================================================',
            '48. RECORDED FAILURE PATTERNS',
            '======================================================================',
            '1. PASSWORD MANAGERS (h07): the model regenerates a salt.',
            '2. CROSS-FILE PYTHON DRIFT (s19): main.py drifts.',
            '',
            '======================================================================',
            'END OF SECTION 48',
            '======================================================================',
        ].join('\n');
        const sections = parseWikiSections(text);
        expect(sections).toHaveLength(1);
        expect(sections[0].number).toBe(48);
        expect(sections[0].body).toContain('1. PASSWORD MANAGERS');
        expect(sections[0].body).toContain('2. CROSS-FILE PYTHON DRIFT');
        expect(sections[0].body).not.toContain('END OF SECTION');
    });
    it('ends a section without an END marker at the next header', () => {
        const text = [
            '======================================================================',
            '50. SECTION WITHOUT END MARKER',
            '======================================================================',
            'body line',
            '',
            '======================================================================',
            '51. NEXT SECTION',
            '======================================================================',
            'next body',
        ].join('\n');
        const sections = parseWikiSections(text);
        expect(sections).toHaveLength(2);
        expect(sections[0]).toEqual({ number: 50, title: 'SECTION WITHOUT END MARKER', body: 'body line' });
        expect(sections[1].body).toBe('next body');
    });
    it('handles headers with no leading separator (hand-appended sections) and wrapped titles', () => {
        const text = [
            '======================================================================',
            '48. RECORDED FAILURE PATTERNS',
            '======================================================================',
            '1. PASSWORD MANAGERS (h07): body list must NOT be a header.',
            '2. CROSS-FILE PYTHON DRIFT (s19): also not a header.',
            '',
            '49. IN-APP BUILD LADDER PANEL — no leading separator',
            '    wrapped title line',
            'body of 49',
            '',
            '50. PER-FILE EXPORT STUB PATTERN (reversi)',
            'body of 50',
            '',
            '51. AI-TURN COLOR BUG (reversi)',
            'body of 51',
        ].join('\n');
        const sections = parseWikiSections(text);
        const nums = sections.map((s) => s.number);
        expect(nums).toEqual([48, 49, 50, 51]);
        expect(sections[1].title).toBe('IN-APP BUILD LADDER PANEL — no leading separator');
        // No-separator headers keep the single title line; the indented
        // continuation lands in the body (nothing is lost).
        expect(sections[1].body).toContain('wrapped title line');
        expect(sections[1].body).toContain('body of 49');
        expect(sections[3].body).toBe('body of 51');
        // Body lists inside 48 stay inside 48.
        expect(sections[0].body).toContain('1. PASSWORD MANAGERS');
        expect(sections[0].body).toContain('2. CROSS-FILE PYTHON DRIFT');
    });
});
describe('real wiki file', () => {
    it('exists and parses into the expected sections', () => {
        // Same resolution as wiki.ts WIKI_PATH: backend/src/routes -> repo root
        expect(existsSync(WIKI_PATH)).toBe(true);
        const text = readFileSync(WIKI_PATH, 'utf-8');
        const sections = parseWikiSections(text);
        expect(sections.length).toBeGreaterThanOrEqual(50);
        // First section is the project overview; newest is the session-history update.
        expect(sections[0].number).toBe(1);
        expect(sections.some((s) => s.number === 52 && /SESSION-HISTORY|SESSION HISTORY/.test(s.title))).toBe(true);
    });
});
