import { describe, it, expect } from 'vitest';
import { detectFileWriteRequest, sanitizeFileName, buildFileContentFromPrompt, buildFileContentFromMessages, } from './fileWriteDetector.js';
describe('sanitizeFileName', () => {
    it('keeps normal names and sub-paths', () => {
        expect(sanitizeFileName('app.py')).toBe('app.py');
        expect(sanitizeFileName('src/app.ts')).toBe('src/app.ts');
        expect(sanitizeFileName('notes.txt')).toBe('notes.txt');
    });
    it('normalizes backslashes and strips leading slashes/drives', () => {
        expect(sanitizeFileName('\\tmp\\x.py')).toBe('tmp/x.py');
        expect(sanitizeFileName('/abs/thing.js')).toBe('abs/thing.js');
        expect(sanitizeFileName('C:/evil.txt')).toBe('evil.txt');
    });
    it('rejects traversal and bogus names', () => {
        expect(sanitizeFileName('../secret.txt')).toBeNull();
        expect(sanitizeFileName('a/../../etc/passwd')).toBeNull();
        expect(sanitizeFileName('..')).toBeNull();
        expect(sanitizeFileName('file')).toBeNull(); // no extension
        expect(sanitizeFileName('the')).toBeNull(); // stopword
    });
    it('detects traversal-looking requests so they get a safe rejection', () => {
        const r = detectFileWriteRequest('create a file called ../../evil.txt with this content: pwned');
        // Detected as a file-write intent, then rejected by sanitizeFileName.
        expect(r).not.toBeNull();
        expect(sanitizeFileName(r.fileName)).toBeNull();
    });
});
describe('detectFileWriteRequest', () => {
    it('detects "create a file called X"', () => {
        const r = detectFileWriteRequest('create a file called app.py');
        expect(r?.fileName).toBe('app.py');
        expect(r?.hasInlineContent).toBe(false);
    });
    it('detects "write this to X: content"', () => {
        const r = detectFileWriteRequest('write this to notes.txt: buy milk');
        expect(r?.fileName).toBe('notes.txt');
        expect(r?.hasInlineContent).toBe(true);
        expect(r?.inlineContent).toBe('buy milk');
    });
    it('detects "create a file called X with this content: ..."', () => {
        const r = detectFileWriteRequest('create a file called app.py with this content: print("hello")');
        expect(r?.fileName).toBe('app.py');
        expect(r?.inlineContent).toBe('print("hello")');
    });
    it('extracts fenced code blocks', () => {
        const r = detectFileWriteRequest('create main.py with this content:\n```python\nprint(1)\n```');
        expect(r?.fileName).toBe('main.py');
        expect(r?.inlineContent).toContain('print(1)');
    });
    it('handles "save this as X"', () => {
        const r = detectFileWriteRequest('save this as config.yaml: port: 8080');
        expect(r?.fileName).toBe('config.yaml');
        expect(r?.inlineContent).toContain('port: 8080');
    });
    it('ignores questions about the capability', () => {
        expect(detectFileWriteRequest('can you create files?')).toBeNull();
        expect(detectFileWriteRequest('how do files work?')).toBeNull();
    });
    it('ignores non-file requests', () => {
        expect(detectFileWriteRequest('create a nice user interface')).toBeNull();
        expect(detectFileWriteRequest('tell me a joke')).toBeNull();
    });
    it('ignores overly long messages', () => {
        expect(detectFileWriteRequest('write this to x.txt: ' + 'a'.repeat(5000))).toBeNull();
    });
});
describe('buildFileContentFromPrompt', () => {
    it('uses inline content when present', () => {
        const req = { fileName: 'a.txt', hasInlineContent: true, inlineContent: 'hello' };
        expect(buildFileContentFromPrompt(req, 'create a file called a.txt: hello')).toBe('hello');
    });
    it('strips the trailing instruction line otherwise', () => {
        const req = { fileName: 'a.txt', hasInlineContent: false };
        expect(buildFileContentFromPrompt(req, 'line one\nline two\ncreate a file called a.txt')).toBe('line one\nline two');
    });
    it('returns empty for a bare instruction (never writes the instruction itself)', () => {
        const req = { fileName: 'app.py', hasInlineContent: false };
        expect(buildFileContentFromPrompt(req, 'create a file called app.py')).toBe('');
    });
});
describe('buildFileContentFromMessages', () => {
    it('uses inline content when present', () => {
        const req = { fileName: 'a.txt', hasInlineContent: true, inlineContent: 'xyz' };
        const msgs = [{ role: 'user', content: 'create a file called a.txt: xyz' }];
        expect(buildFileContentFromMessages(req, msgs)).toBe('xyz');
    });
    it('serializes prior messages when no inline content', () => {
        const req = { fileName: 'a.txt', hasInlineContent: false };
        const msgs = [
            { role: 'user', content: 'Here is the code' },
            { role: 'assistant', content: 'Got it' },
            { role: 'user', content: 'create a file called a.txt' },
        ];
        const out = buildFileContentFromMessages(req, msgs);
        expect(out).toContain('Here is the code');
        expect(out).toContain('Got it');
    });
    it('returns empty when nothing precedes the instruction', () => {
        const req = { fileName: 'a.txt', hasInlineContent: false };
        expect(buildFileContentFromMessages(req, [{ role: 'user', content: 'create a file called a.txt' }])).toBe('');
    });
});
