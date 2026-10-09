import { describe, it, expect } from 'vitest';
import { detectUnsupportedRequest, DECLINE_MESSAGE } from './capabilityBoundaryDetector.js';
describe('capabilityBoundaryDetector', () => {
    // ── unsupported: filesystem-wide scans / read-everything / wiki-sync ──
    it('declines "read all files in your system and update the wiki with anything newer"', () => {
        const r = detectUnsupportedRequest('read all files in your system, and update the wiki file with anything newer than whats within the wiki');
        expect(r).not.toBeNull();
        expect(r?.message).toContain("can't scan the whole filesystem");
    });
    it('declines "scan your whole filesystem and tell me everything"', () => {
        expect(detectUnsupportedRequest('scan your whole filesystem and tell me everything you find')).not.toBeNull();
    });
    it('declines "read every file on the computer"', () => {
        expect(detectUnsupportedRequest('read every file on the computer')).not.toBeNull();
    });
    it('declines "list all folders on my drive"', () => {
        expect(detectUnsupportedRequest('list all folders on my drive')).not.toBeNull();
    });
    it('declines "sync your wiki with anything newer"', () => {
        expect(detectUnsupportedRequest('sync your wiki with anything newer')).not.toBeNull();
    });
    it('declines "update your memory with all new content from my files"', () => {
        expect(detectUnsupportedRequest('update your memory with all new content from my files')).not.toBeNull();
    });
    // ── unsupported: shell command execution from chat ──
    it('declines "run the shell command ls -la"', () => {
        const r = detectUnsupportedRequest('Run the shell command ls -la and tell me the output');
        expect(r).not.toBeNull();
    });
    it('declines backtick commands like "run `git status`"', () => {
        expect(detectUnsupportedRequest('run `git status` and tell me what changed')).not.toBeNull();
    });
    it('declines "execute sudo apt install"', () => {
        expect(detectUnsupportedRequest('execute sudo apt install python3-pip')).not.toBeNull();
    });
    it('declines "open a terminal and run npm install"', () => {
        expect(detectUnsupportedRequest('open a terminal and run npm install')).not.toBeNull();
    });
    it('declines explicit "shell command" / "terminal command" phrasing', () => {
        expect(detectUnsupportedRequest('run a shell command to check disk usage')).not.toBeNull();
        expect(detectUnsupportedRequest('type this terminal command: df -h')).not.toBeNull();
    });
    it('does NOT decline advice questions like "how do I run X?"', () => {
        expect(detectUnsupportedRequest('how do I run npm install')).toBeNull();
        expect(detectUnsupportedRequest('how can I run a shell command in this app')).toBeNull();
        expect(detectUnsupportedRequest('what is the command to restart ollama')).toBeNull();
    });
    it('does NOT decline educational or indirect command questions', () => {
        expect(detectUnsupportedRequest('explain shell commands to me')).toBeNull();
        expect(detectUnsupportedRequest('how do shell commands work')).toBeNull();
        expect(detectUnsupportedRequest('please tell me how to run npm install')).toBeNull();
        expect(detectUnsupportedRequest('is there a way to run npm install')).toBeNull();
        expect(detectUnsupportedRequest('hey, how do I run git status')).toBeNull();
        expect(detectUnsupportedRequest('teach me shell commands')).toBeNull();
        expect(detectUnsupportedRequest('how to type a terminal command')).toBeNull();
        expect(detectUnsupportedRequest('how to enter a shell command')).toBeNull();
    });
    it('does NOT decline casual uses of the word "run"', () => {
        expect(detectUnsupportedRequest('run the tests to check they pass')).toBeNull();
        expect(detectUnsupportedRequest('can you run the app locally')).toBeNull();
    });
    // ── supported requests must NOT be declined ──
    it('does NOT decline depth questions like "read everything about X"', () => {
        expect(detectUnsupportedRequest('read everything about react hooks')).toBeNull();
        expect(detectUnsupportedRequest('tell me everything about file uploads')).toBeNull();
    });
    it('does NOT decline supported code searches', () => {
        expect(detectUnsupportedRequest('scan the code for permissionManager')).toBeNull();
        expect(detectUnsupportedRequest('search the code for sessionMemory')).toBeNull();
    });
    it('does NOT decline supported file reads', () => {
        expect(detectUnsupportedRequest('read backend/src/index.ts')).toBeNull();
        expect(detectUnsupportedRequest('what is in config.yaml')).toBeNull();
    });
    it('does NOT decline web searches or knowledge queries', () => {
        expect(detectUnsupportedRequest('search the web for how to deploy a vite app')).toBeNull();
        expect(detectUnsupportedRequest('what do you know about drag and drop folders')).toBeNull();
    });
    it('does NOT decline file writes, memory writes, or app launches', () => {
        expect(detectUnsupportedRequest('create a file called app.py with this content: print(1)')).toBeNull();
        expect(detectUnsupportedRequest('remember that I prefer dark mode')).toBeNull();
        expect(detectUnsupportedRequest('open firefox')).toBeNull();
    });
    it('does NOT decline greetings or casual chat', () => {
        expect(detectUnsupportedRequest('hello')).toBeNull();
        expect(detectUnsupportedRequest('how are you')).toBeNull();
    });
    it('exposes a helpful decline message listing real capabilities', () => {
        const msg = DECLINE_MESSAGE.toLowerCase();
        expect(msg).toContain('read a specific file');
        expect(msg).toContain('search the codebase');
        expect(msg).toContain('write to my memory or wiki');
        expect(msg).toContain("can't scan the whole filesystem");
    });
});
