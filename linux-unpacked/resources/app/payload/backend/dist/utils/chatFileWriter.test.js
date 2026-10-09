import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import fs from 'fs';
import os from 'os';
import path from 'path';
// Set the env BEFORE dynamically importing the module so CHAT_FILES_DIR
// resolves to the temp dir (static imports would be hoisted past this).
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-chat-files-test-'));
process.env.VACA_CHAT_FILES_DIR = TMP;
let writeChatFile;
let listChatFiles;
let CHAT_FILES_DIR;
beforeAll(async () => {
    const mod = await import('./chatFileWriter.js');
    writeChatFile = mod.writeChatFile;
    listChatFiles = mod.listChatFiles;
    CHAT_FILES_DIR = mod.CHAT_FILES_DIR;
    if (!fs.existsSync(CHAT_FILES_DIR))
        fs.mkdirSync(CHAT_FILES_DIR, { recursive: true });
});
afterAll(() => {
    fs.rmSync(TMP, { recursive: true, force: true });
});
describe('chatFileWriter', () => {
    it('uses the temp dir, not the real data dir', () => {
        expect(CHAT_FILES_DIR).toBe(TMP);
    });
    it('writes a file and returns path + bytes', () => {
        const r = writeChatFile('hello.txt', 'hello world');
        expect(r.fileName).toBe('hello.txt');
        expect(fs.existsSync(r.filePath)).toBe(true);
        expect(fs.readFileSync(r.filePath, 'utf-8')).toBe('hello world');
        expect(r.bytes).toBe(11);
    });
    it('creates sub-paths', () => {
        const r = writeChatFile('src/app.ts', 'export {}');
        expect(fs.existsSync(r.filePath)).toBe(true);
        expect(listChatFiles()).toContain('src/app.ts');
    });
    it('rejects unsafe names', () => {
        expect(() => writeChatFile('../escape.txt', 'x')).toThrow();
        expect(() => writeChatFile('noext', 'x')).toThrow();
    });
    it('strips drive letters safely (writes inside the root)', () => {
        const r = writeChatFile('C:/abs.txt', 'x');
        expect(r.fileName).toBe('abs.txt');
        expect(fs.existsSync(r.filePath)).toBe(true);
    });
    it('lists saved files', () => {
        writeChatFile('one.txt', '1');
        writeChatFile('two.txt', '2');
        const list = listChatFiles();
        expect(list).toContain('one.txt');
        expect(list).toContain('two.txt');
    });
});
