import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { mkdtempSync, writeFileSync, rmSync, existsSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import { getRegistry } from '../tools/ToolRegistry.js';
import { fileSystemTools } from '../tools/tools/FileSystemTool.js';
import { runChatTool, truncateMid, tokenizeQuery, matchWikiSections } from './chatToolRunner.js';
let tmpDir = '';
beforeAll(() => {
    tmpDir = mkdtempSync(join(tmpdir(), 'chat-tool-runner-'));
    // Register the real file tools so the runner executes them for real.
    getRegistry().registerAll(...fileSystemTools);
});
afterAll(() => {
    if (tmpDir && existsSync(tmpDir))
        rmSync(tmpDir, { recursive: true, force: true });
});
describe('chatToolRunner', () => {
    it('reads a real file and puts the REAL content in the context block', async () => {
        const filePath = join(tmpDir, 'sample.txt');
        writeFileSync(filePath, 'hello from the runner test\nline two\n', 'utf-8');
        const out = await runChatTool({
            tool: 'read_file',
            input: { path: filePath },
            display: `file: ${filePath}`,
        });
        expect(out.handled).toBe(true);
        expect(out.tool).toBe('read_file');
        expect(out.contextBlock).toContain('[REAL FILE CONTENT');
        expect(out.contextBlock).toContain('hello from the runner test');
        expect(out.contextBlock).toContain('line two');
    });
    it('reports honestly when the file does not exist (no fabrication)', async () => {
        const out = await runChatTool({
            tool: 'read_file',
            input: { path: join(tmpDir, 'does-not-exist.ts') },
            display: 'file: does-not-exist.ts',
        });
        expect(out.handled).toBe(true);
        expect(out.contextBlock).toContain('FAILED');
        expect(out.contextBlock).toContain('could not be read');
    });
    it('searches a real directory and returns actual matches', async () => {
        const dir = join(tmpDir, 'search-me');
        const { mkdirSync } = await import('fs');
        mkdirSync(dir, { recursive: true });
        writeFileSync(join(dir, 'a.ts'), 'const zorpToken = 42;\n', 'utf-8');
        writeFileSync(join(dir, 'b.txt'), 'nothing here\n', 'utf-8');
        const out = await runChatTool({
            tool: 'search_file',
            input: { pattern: 'zorpToken', path: dir, maxResults: 10 },
            display: 'code search: "zorpToken"',
        });
        expect(out.handled).toBe(true);
        expect(out.contextBlock).toContain('[REAL CODE SEARCH');
        expect(out.contextBlock).toContain('zorpToken');
        expect(out.contextBlock).toContain('a.ts');
    });
    it('truncateMid keeps head + tail and marks the cut', () => {
        const long = 'x'.repeat(10000);
        const out = truncateMid(long, 1000);
        expect(out.length).toBeLessThan(1100);
        expect(out).toContain('[truncated');
        expect(out.startsWith('xxxxx')).toBe(true);
        expect(out.endsWith('xxxxx')).toBe(true);
    });
    it('truncateMid passes through short strings unchanged', () => {
        expect(truncateMid('short', 1000)).toBe('short');
    });
});
// ── Tokenized query + wiki-section matching (added Aug 14: knowledge_query
//    now retrieves wiki sections, not just code patterns) ──
const SECTIONS = [
    { number: 58, title: 'TODO 2.1 DONE — SPECULATIVE DECODING BRANDING DROPPED', body: 'draft mode is NOT an accelerator, measurements, llama.cpp' },
    { number: 59, title: 'SESSION UPDATE — VOID RAIDER GAME BUILDS + BLUEPRINT RESEARCH INJECTION', body: 'Four full builds of the arcade space-shooter void raider. 7B model cannot produce a playable game loop; wave manager, enemy AI, combat engine, game renderer. Java CLI, canvas, ship controls.' },
    { number: 3, title: 'RUNTIME TOOLS', body: 'Node.js, npm, Python, TypeScript versions' },
];
describe('tokenizeQuery', () => {
    it('splits a natural-language query into words', () => {
        const tokens = tokenizeQuery('what do you know about building arcade games');
        expect(tokens).toContain('arcade');
        expect(tokens).toContain('building');
    });
    it('drops short tokens but keeps 3+ char words', () => {
        expect(tokenizeQuery('do you know')).toEqual(['you', 'know']);
    });
});
describe('matchWikiSections', () => {
    it('ranks sections by token hits — §59 wins for an arcade-games query', () => {
        const hits = matchWikiSections(SECTIONS, 'building arcade games', 2);
        expect(hits.length).toBeGreaterThan(0);
        expect(hits[0].number).toBe(59);
    });
    it('returns fewer than max when few sections match', () => {
        const hits = matchWikiSections(SECTIONS, 'node npm runtime', 2);
        expect(hits.length).toBe(1);
        expect(hits[0].number).toBe(3);
    });
    it('returns empty for a query with no matches', () => {
        const hits = matchWikiSections(SECTIONS, 'quantum entanglement physics', 2);
        expect(hits).toEqual([]);
    });
    it('handles an empty query', () => {
        expect(matchWikiSections(SECTIONS, '')).toEqual([]);
    });
});
