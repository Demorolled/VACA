import { describe, it, expect } from 'vitest';
import { detectMemoryWriteRequest, deriveTopic, buildContentFromPrompt, buildContentFromMessages, } from './memoryWriteDetector.js';
describe('detectMemoryWriteRequest', () => {
    it('detects "write this into your wiki" → wiki', () => {
        const r = detectMemoryWriteRequest('write this into your wiki file');
        expect(r).not.toBeNull();
        expect(r.target).toBe('wiki');
    });
    it('detects "save this to your memory" → memory', () => {
        const r = detectMemoryWriteRequest('save this to your memory');
        expect(r).not.toBeNull();
        expect(r.target).toBe('memory');
        expect(r.hasInlineContent).toBe(false);
    });
    it('detects "put this in the wiki" → wiki', () => {
        expect(detectMemoryWriteRequest('put this in the wiki')?.target).toBe('wiki');
    });
    it('detects "add this to your notes" → memory', () => {
        expect(detectMemoryWriteRequest('add this to your notes')?.target).toBe('memory');
    });
    it('detects bare "remember this" with no inline content', () => {
        const r = detectMemoryWriteRequest('remember this');
        expect(r).not.toBeNull();
        expect(r.hasInlineContent).toBe(false);
    });
    it('detects "remember that <content>" with inline content', () => {
        const r = detectMemoryWriteRequest('remember that I like dark mode');
        expect(r).not.toBeNull();
        expect(r.hasInlineContent).toBe(true);
        expect(r.inlineContent).toContain('dark mode');
    });
    it('detects "write this to memory: <content>" inline content', () => {
        const r = detectMemoryWriteRequest('write this to memory: the user prefers terminal apps');
        expect(r).not.toBeNull();
        expect(r.hasInlineContent).toBe(true);
        expect(r.inlineContent).toContain('terminal');
    });
    it('does NOT guess fragments after the target phrase as inline content', () => {
        // "save this to memory about the project" refers to PRIOR context — the
        // trailing "about the project" must not be mistaken for the content.
        const r = detectMemoryWriteRequest('save this to memory about the project');
        expect(r).not.toBeNull();
        expect(r.hasInlineContent).toBe(false);
        expect(r.inlineContent).toBeUndefined();
    });
    it('ignores questions about the capability', () => {
        expect(detectMemoryWriteRequest('how do you write files to memory?')).toBeNull();
        expect(detectMemoryWriteRequest('can you write files?')).toBeNull();
        expect(detectMemoryWriteRequest('what is your memory?')).toBeNull();
    });
    it('ignores unrelated code-writing requests', () => {
        expect(detectMemoryWriteRequest('write a function that adds two numbers')).toBeNull();
        expect(detectMemoryWriteRequest('please write a file for my project')).toBeNull();
    });
    it('ignores empty or oversized input', () => {
        expect(detectMemoryWriteRequest('')).toBeNull();
        expect(detectMemoryWriteRequest('   ')).toBeNull();
        expect(detectMemoryWriteRequest('x'.repeat(5000))).toBeNull();
    });
});
describe('deriveTopic', () => {
    it('uses the first non-empty line, capped at 60 chars', () => {
        expect(deriveTopic('Merge two apps\ninto one', 'fallback')).toBe('Merge two apps');
        const long = deriveTopic('A'.repeat(100), 'fallback');
        expect(long.length).toBeLessThanOrEqual(60);
    });
    it('falls back to the default when content is empty', () => {
        expect(deriveTopic('', 'Memory note')).toBe('Memory note');
    });
});
describe('buildContentFromPrompt', () => {
    it('uses inline content when present', () => {
        const r = detectMemoryWriteRequest('remember that I prefer dark mode');
        expect(buildContentFromPrompt(r, 'remember that I prefer dark mode')).toContain('dark mode');
    });
    it('strips the trailing instruction line from history-style prompts', () => {
        const r = detectMemoryWriteRequest('write this into your wiki');
        const content = buildContentFromPrompt(r, 'User: The merge-apps idea\nAssistant: Here is the approach\nwrite this into your wiki');
        expect(content).toContain('merge-apps');
        expect(content).not.toContain('write this into your wiki');
    });
});
describe('buildContentFromMessages', () => {
    it('serializes prior messages when no inline content', () => {
        const r = detectMemoryWriteRequest('write this into your wiki');
        const msgs = [
            { role: 'user', content: 'Can you merge two apps?' },
            { role: 'assistant', content: 'Yes, here is the plan.' },
            { role: 'user', content: 'write this into your wiki' },
        ];
        const content = buildContentFromMessages(r, msgs);
        expect(content).toContain('merge two apps');
        expect(content).not.toContain('write this into your wiki');
    });
    it('uses inline content first', () => {
        const r = detectMemoryWriteRequest('remember that I like dark mode');
        const msgs = [
            { role: 'user', content: 'unrelated prior message' },
            { role: 'user', content: 'remember that I like dark mode' },
        ];
        expect(buildContentFromMessages(r, msgs)).toContain('dark mode');
    });
});
