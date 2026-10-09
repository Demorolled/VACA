import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { existsSync, unlinkSync } from 'fs';
const TMP = '/tmp/vaca-session-memory-test.json';
describe('sessionMemory — persistent notes', () => {
    let sm;
    beforeEach(async () => {
        try {
            unlinkSync(TMP);
        }
        catch { /* ignore */ }
        process.env.VACA_MEMORY_FILE = TMP;
        vi.resetModules();
        sm = (await import('./sessionMemory.js')).sessionMemory;
    });
    afterEach(() => {
        delete process.env.VACA_MEMORY_FILE;
        try {
            unlinkSync(TMP);
        }
        catch { /* ignore */ }
    });
    it('records a note and persists it to the memory file', () => {
        const note = sm.recordNote('Dark mode', 'User prefers dark mode UI.');
        expect(note.topic).toBe('Dark mode');
        expect(note.content).toBe('User prefers dark mode UI.');
        expect(sm.getNotes(10).length).toBe(1);
        expect(existsSync(TMP)).toBe(true);
    });
    it('survives a module reload (persisted to disk)', async () => {
        sm.recordNote('Merge apps', 'User wants to merge two apps into one.');
        vi.resetModules();
        const reloaded = (await import('./sessionMemory.js')).sessionMemory;
        const notes = reloaded.getNotes(10);
        expect(notes.length).toBe(1);
        expect(notes[0].topic).toBe('Merge apps');
    });
    it('includes notes in the memory prompt block', () => {
        sm.recordNote('Merge apps', 'User wants to merge two apps into one.');
        const block = sm.getMemoryPromptBlock();
        expect(block).toContain('PERSISTENT MEMORY');
        expect(block).toContain('Merge apps');
        expect(block).toContain('the write is performed by the platform');
    });
    it('includes note topics in getMemoryContext', () => {
        sm.recordNote('Dark mode', 'prefers dark mode');
        expect(sm.getMemoryContext()).toContain('Dark mode');
    });
    it('caps notes at 100', () => {
        for (let i = 0; i < 105; i++)
            sm.recordNote(`Note ${i}`, `content ${i}`);
        expect(sm.getNotes(200).length).toBe(100);
    });
    it('DEDUPES a note with the same topic (case-insensitive) instead of stacking', () => {
        const n1 = sm.recordNote('Dark mode', 'User prefers dark mode UI.');
        const n2 = sm.recordNote('dark mode', 'User prefers dark mode EVERYWHERE.');
        const notes = sm.getNotes(10);
        expect(notes.length).toBe(1);
        expect(notes[0].id).toBe(n1.id); // same id — updated in place, not a duplicate
        expect(notes[0].content).toBe('User prefers dark mode EVERYWHERE.');
        expect(n2.id).toBe(n1.id);
    });
    it('keeps DISTINCT topics separate (dedupe only merges same-topic notes)', () => {
        sm.recordNote('Dark mode', 'prefers dark mode');
        sm.recordNote('Font size', 'prefers larger fonts');
        expect(sm.getNotes(10).length).toBe(2);
    });
    it('deleteNote removes only the matching id and returns true/false', () => {
        const a = sm.recordNote('A', 'content a');
        const b = sm.recordNote('B', 'content b');
        expect(sm.deleteNote(a.id)).toBe(true);
        expect(sm.getNotes(10).map(n => n.id)).toEqual([b.id]);
        expect(sm.deleteNote('does-not-exist')).toBe(false);
    });
    it('snapshotNotes/restoreNotes round-trips the exact prior state', () => {
        sm.recordNote('Real A', 'real content');
        const snap = sm.snapshotNotes();
        sm.recordNote('Probe fact', 'turquoise probe');
        expect(sm.getNotes(10).length).toBe(2);
        sm.restoreNotes(snap);
        const after = sm.getNotes(10);
        expect(after.length).toBe(1);
        expect(after[0].topic).toBe('Real A');
    });
    it('clear() wipes notes', () => {
        sm.recordNote('A', 'B');
        sm.clear();
        expect(sm.getNotes(10).length).toBe(0);
    });
});
