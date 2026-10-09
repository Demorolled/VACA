import { describe, it, expect } from 'vitest';
import { detectChatToolRequest } from './chatToolDetector.js';
describe('chatToolDetector', () => {
    // ── read_file ──
    it('detects "read <file>"', () => {
        const r = detectChatToolRequest('read backend/src/index.ts');
        expect(r?.tool).toBe('read_file');
        expect(r?.input.path).toBe('backend/src/index.ts');
    });
    it('detects "show me the contents of <file>"', () => {
        const r = detectChatToolRequest('show me the contents of package.json');
        expect(r?.tool).toBe('read_file');
        expect(r?.input.path).toBe('package.json');
    });
    it('detects "what is in <file>"', () => {
        const r = detectChatToolRequest('what is in config.yaml');
        expect(r?.tool).toBe('read_file');
        expect(r?.input.path).toBe('config.yaml');
    });
    it('detects "can you read <file>?" (polite form)', () => {
        const r = detectChatToolRequest('can you read frontend/vite.config.ts?');
        expect(r?.tool).toBe('read_file');
        expect(r?.input.path).toBe('frontend/vite.config.ts');
    });
    it('detects "tell me what is in <file>"', () => {
        const r = detectChatToolRequest('tell me what is in backend/src/utils/chatFileWriter.ts');
        expect(r?.tool).toBe('read_file');
    });
    it('detects "open <file path>" as a read (not an app launch)', () => {
        const r = detectChatToolRequest('open src/utils/chatToolDetector.ts');
        expect(r?.tool).toBe('read_file');
    });
    it('detects "what does <file> do"', () => {
        const r = detectChatToolRequest('what does app.py do');
        expect(r?.tool).toBe('read_file');
        expect(r?.input.path).toBe('app.py');
    });
    it('extracts the path when the read is followed by a request ("read X and tell me what it does")', () => {
        const r = detectChatToolRequest('read backend/src/index.ts and tell me what it does');
        expect(r?.tool).toBe('read_file');
        expect(r?.input.path).toBe('backend/src/index.ts');
    });
    it('reads "my file called X" phrasing', () => {
        const r = detectChatToolRequest('read my file called config.yaml');
        expect(r?.tool).toBe('read_file');
        expect(r?.input.path).toBe('config.yaml');
    });
    // ── search_file ──
    it('detects "search the code for <x>"', () => {
        const r = detectChatToolRequest('search the code for permissionManager');
        expect(r?.tool).toBe('search_file');
        expect(r?.input.pattern).toBe('permissionManager');
    });
    it('detects "find where <x> is used"', () => {
        const r = detectChatToolRequest('find where sessionMemory is used');
        expect(r?.tool).toBe('search_file');
        expect(r?.input.pattern).toBe('sessionMemory');
    });
    it('detects "grep <x>"', () => {
        const r = detectChatToolRequest('grep getMemoryPromptBlock');
        expect(r?.tool).toBe('search_file');
        expect(r?.input.pattern).toBe('getMemoryPromptBlock');
    });
    it('detects "search the codebase for <x>"', () => {
        const r = detectChatToolRequest('search the codebase for writeChatFile');
        expect(r?.tool).toBe('search_file');
    });
    it('detects natural-language "search the code for how X is configured"', () => {
        const r = detectChatToolRequest('Search the backend code for how the LLM client base URL is configured');
        expect(r?.tool).toBe('search_file');
        expect(typeof r?.input.pattern).toBe('string');
        expect(String(r?.input.pattern).length).toBeGreaterThanOrEqual(2);
    });
    it('detects scoped "search <dir> for <x>"', () => {
        const r = detectChatToolRequest('search backend/src for baseURL');
        expect(r?.tool).toBe('search_file');
        expect(r?.input.path).toBe('backend/src');
        expect(r?.input.pattern).toBe('baseURL');
    });
    it('detects "find where <x> is configured"', () => {
        const r = detectChatToolRequest('find where baseURL is configured');
        expect(r?.tool).toBe('search_file');
        expect(r?.input.pattern).toBe('baseURL');
    });
    it('detects multi-word bare "search for how sessionMemory works"', () => {
        const r = detectChatToolRequest('search for how sessionMemory works');
        expect(r?.tool).toBe('search_file');
        expect(r?.input.pattern).toBe('sessionMemory');
    });
    it('detects 2-char identifiers like "search the code for fs"', () => {
        const r = detectChatToolRequest('search the code for fs');
        expect(r?.tool).toBe('search_file');
        expect(r?.input.pattern).toBe('fs');
    });
    it('does NOT intercept casual "search for <English phrase>" chat', () => {
        expect(detectChatToolRequest('search for a good restaurant nearby')).toBeNull();
        expect(detectChatToolRequest('search for how to improve my sleep')).toBeNull();
    });
    it('does NOT intercept "search npm for X" as a code search', () => {
        const r = detectChatToolRequest('search npm for express');
        // "npm" has no path separator, and the phrase is all-lowercase → stays in chat.
        expect(r).toBeNull();
    });
    // ── web_search ──
    it('detects "search the web for <x>"', () => {
        const r = detectChatToolRequest('search the web for how to deploy a vite app');
        expect(r?.tool).toBe('web_search');
        expect(r?.input.query).toContain('deploy');
    });
    it('detects "google <x>"', () => {
        const r = detectChatToolRequest('google react useState');
        expect(r?.tool).toBe('web_search');
        expect(r?.input.query).toContain('react');
    });
    it('detects "look up <x> on the web"', () => {
        const r = detectChatToolRequest('look up ollama on the web');
        expect(r?.tool).toBe('web_search');
    });
    it('detects "find information about <x>"', () => {
        const r = detectChatToolRequest('find information about llama.cpp');
        expect(r?.tool).toBe('web_search');
    });
    // ── knowledge_query ──
    it('detects "what do you know about <x>"', () => {
        const r = detectChatToolRequest('what do you know about drag and drop folders');
        expect(r?.tool).toBe('knowledge_query');
        expect(r?.input.query).toContain('drag and drop');
    });
    it('detects "do you have any patterns for <x>"', () => {
        const r = detectChatToolRequest('do you have any patterns for authentication');
        expect(r?.tool).toBe('knowledge_query');
        expect(r?.input.query).toContain('authentication');
    });
    it('detects "search your knowledge base for <x>"', () => {
        const r = detectChatToolRequest('search your knowledge base for file uploads');
        expect(r?.tool).toBe('knowledge_query');
    });
    it('detects "what does your knowledge base say about <x>" (P4)', () => {
        const r = detectChatToolRequest('what does your knowledge base say about round 6 of training');
        expect(r?.tool).toBe('knowledge_query');
        expect(r?.input.query).toContain('round 6');
    });
    it('detects "what does the KB say about <x>" (P4)', () => {
        const r = detectChatToolRequest('what does the kb say about qlora');
        expect(r?.tool).toBe('knowledge_query');
    });
    it('detects "look up <x> in your knowledge base" (P4)', () => {
        const r = detectChatToolRequest('look up sql injection in your knowledge base');
        expect(r?.tool).toBe('knowledge_query');
    });
    it('detects "what does your wiki say about <x>" (P4)', () => {
        const r = detectChatToolRequest('what does your wiki say about session memory');
        expect(r?.tool).toBe('knowledge_query');
    });
    it('still runs a web search when "wiki" is merely mentioned (no deferral regression)', () => {
        const r = detectChatToolRequest('search the web for how wikis work');
        expect(r?.tool).toBe('web_search');
        const r2 = detectChatToolRequest('search the web for a bible verse about patience');
        expect(r2?.tool).toBe('web_search');
    });
    // ── false positives must NOT be intercepted ──
    it('does NOT intercept file-write requests (handled by fileWriteDetector)', () => {
        expect(detectChatToolRequest('create a file called app.py with this content: print(1)')).toBeNull();
        expect(detectChatToolRequest('write this to notes.txt: backup the folder')).toBeNull();
    });
    it('does NOT intercept memory-write requests', () => {
        expect(detectChatToolRequest('remember that I prefer dark mode')).toBeNull();
    });
    it('does NOT intercept app launches', () => {
        expect(detectChatToolRequest('open firefox')).toBeNull();
        expect(detectChatToolRequest('open the calculator app')).toBeNull();
    });
    it('does NOT intercept greetings or casual chat', () => {
        expect(detectChatToolRequest('hello')).toBeNull();
        expect(detectChatToolRequest('how are you')).toBeNull();
        expect(detectChatToolRequest('tell me a joke')).toBeNull();
    });
    it('does NOT intercept non-file "read/show me X" phrasing', () => {
        expect(detectChatToolRequest('read my mind')).toBeNull();
        expect(detectChatToolRequest('show me the calculator')).toBeNull();
    });
    it('does NOT intercept date/time queries', () => {
        expect(detectChatToolRequest('what time is it')).toBeNull();
    });
});
