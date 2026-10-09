import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { idleMonitor } from './idleMonitor.js';
// Redirect the KNOWLEDGE STORE to a throwaway dir BEFORE any static import is
// evaluated (the experimenter records accepted ideas as patterns; without this
// they land in the real backend/knowledge/patterns.json). `vi.hoisted` runs
// above the imports, so the store singleton constructed on import is isolated.
vi.hoisted(() => {
    const base = process.env.TMPDIR || process.env.TEMP || '/tmp';
    process.env.VACA_KNOWLEDGE_DIR = `${base}/vaca-kb-micro-${process.pid}-${Date.now()}`;
});
// Redirect the service's writes to throwaway dirs BEFORE the module is
// evaluated (module-level path constants read these env vars at import time).
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'micro-exp-test-'));
process.env.IDLE_EXPERIMENTER_DATA_DIR = path.join(tmp, 'data');
process.env.IDLE_EXPERIMENTER_EXPORTS_DIR = path.join(tmp, 'exports');
process.env.IDLE_EXPERIMENTER_TRAINING_DIR = path.join(tmp, 'training');
process.env.IDLE_EXPERIMENTER_UPLOADS_DIR = path.join(tmp, 'uploads');
process.env.IDLE_EXPERIMENTER_ORPO_DIR = path.join(tmp, 'orpo');
process.env.IDLE_EXPERIMENTER_ENABLED = '1';
let mod;
beforeAll(async () => {
    vi.resetModules();
    mod = await import('./microExperimenterService.js');
});
afterAll(() => {
    try {
        fs.rmSync(tmp, { recursive: true, force: true });
    }
    catch { /* best-effort */ }
    const kb = process.env.VACA_KNOWLEDGE_DIR;
    if (kb) {
        try {
            fs.rmSync(kb, { recursive: true, force: true });
        }
        catch { /* best-effort */ }
    }
});
const base = { bytes: 100, lines: 40, files: 2, genMs: 1000 };
describe('idle monitor', () => {
    it('reports not-idle right after activity, idle for a zero threshold', () => {
        idleMonitor.noteActivity('test');
        expect(idleMonitor.isIdle(86_400_000)).toBe(false);
        expect(idleMonitor.isIdle(0)).toBe(true);
        expect(idleMonitor.lastActivityAt).toBeTruthy();
    });
});
describe('micro experimenter — metrics & evaluation', () => {
    it('balanced composite score favors smaller + faster', () => {
        const improved = { ...base, bytes: 50, genMs: 500 };
        const worse = { ...base, bytes: 200, genMs: 2000 };
        expect(mod.composite(base, improved)).toBeLessThan(1);
        expect(mod.composite(base, worse)).toBeGreaterThan(1);
        expect(mod.composite(base, improved)).toBeCloseTo(0.5);
    });
    it('measure() counts bytes (utf8), non-blank lines, and file count', () => {
        const m = mod.measure([{ path: 'a.ts', content: 'a\nbb\n\n' }]);
        expect(m.bytes).toBe(6);
        expect(m.lines).toBe(2);
        expect(m.files).toBe(1);
    });
    it('normalizeForRewrite keeps planned + non-code artifacts only', () => {
        const gen = [
            { path: 'src/main.ts', content: 'x' },
            { path: 'index.html', content: '<html>' },
            { path: 'stray.xxx', content: 'junk' },
        ];
        expect(mod.normalizeForRewrite(gen, ['src/main.ts']).map(f => f.path)).toEqual(['src/main.ts', 'index.html']);
    });
    it('dominantLanguage reports the real language, not always typescript', () => {
        const one = (p) => [{ path: p, content: '' }];
        expect(mod.dominantLanguage(one('main.rs'))).toBe('rust');
        expect(mod.dominantLanguage(one('main.go'))).toBe('go');
        expect(mod.dominantLanguage(one('Main.java'))).toBe('java');
        expect(mod.dominantLanguage(one('Program.cs'))).toBe('csharp');
        expect(mod.dominantLanguage(one('app.py'))).toBe('python');
        expect(mod.dominantLanguage(one('index.php'))).toBe('php');
        expect(mod.dominantLanguage(one('main.rb'))).toBe('ruby');
        expect(mod.dominantLanguage(one('index.ts'))).toBe('typescript');
        expect(mod.dominantLanguage(one('index.html'))).toBe('html');
        expect(mod.dominantLanguage([{ path: 'main.rs', content: '' }, { path: 'src/a/a.rs', content: '' }])).toBe('rust');
    });
});
describe('micro experimenter — rewrite parsing', () => {
    it('parses { files: [...] } shape', () => {
        expect(mod.parseRewriteJson('{"files":[{"path":"a.ts","content":"exp()"}]}')).toEqual([{ path: 'a.ts', content: 'exp()' }]);
    });
    it('parses path->content map shape', () => {
        const out = mod.parseRewriteJson('here you go:\n{"a.ts":"const x=1;","b.ts":"const y=2;"}\ndone');
        expect(out).toHaveLength(2);
        expect(out?.[0]).toEqual({ path: 'a.ts', content: 'const x=1;' });
    });
    it('returns null for non-JSON garbage', () => {
        expect(mod.parseRewriteJson('I cannot do this')).toBeNull();
    });
    it('rewriteToCurrent constrains to the same file set and falls back missing files', () => {
        const current = [
            { path: 'a.ts', content: 'old-a' },
            { path: 'b.ts', content: 'old-b' },
        ];
        const rewritten = [
            { path: 'a.ts', content: 'new-a' },
            { path: 'spillover.ts', content: 'should-be-dropped' },
        ];
        const merged = mod.rewriteToCurrent(rewritten, current);
        expect(merged).toHaveLength(2);
        expect(merged.find(f => f.path === 'a.ts')?.content).toBe('new-a');
        expect(merged.find(f => f.path === 'b.ts')?.content).toBe('old-b');
        expect(merged.some(f => f.path === 'spillover.ts')).toBe(false);
    });
});
describe('micro experimenter — ideas DB + training export', () => {
    it('storeIdea persists, then exportTrainingData writes JSONL for the training pipeline', () => {
        const idea = {
            purpose: 'a tiny notes app',
            design: 'single in-memory store, one file',
            focus: ['smaller'],
            metrics: { bytes: 10, lines: 3, files: 1, genMs: 100 },
            baselineMetrics: base,
            composite: 0.5,
            exportsDir: path.join(tmp, 'exports', 'notes'),
            files: [{ path: 'main.ts', content: 'export const store = new Map()' }],
        };
        const stored = mod.microExperimenter.storeIdea(idea);
        expect(stored.id).toMatch(/^idea_/);
        expect(mod.microExperimenter.getIdeas()).toHaveLength(1);
        const out = mod.microExperimenter.exportTrainingData();
        expect('error' in out).toBe(false);
        if (!('error' in out)) {
            expect(out.count).toBe(1);
            expect(fs.existsSync(out.file)).toBe(true);
            const content = fs.readFileSync(out.file, 'utf-8');
            expect(content).toContain('main.ts');
            expect(content).toContain('micro-app-idea');
            expect(content).toContain('smaller');
            expect(fs.existsSync(out.upload)).toBe(true);
        }
    });
});
describe('micro experimenter — judge verdict parsing', () => {
    it('parses a clean JSON verdict', () => {
        expect(mod.parseJudgeVerdict('{"pass":false,"reason":"stub body"}')).toEqual({ pass: false, reason: 'stub body' });
        expect(mod.parseJudgeVerdict('{"pass":true,"reason":"solid"}')).toEqual({ pass: true, reason: 'solid' });
    });
    it('parses a bare `pass:` line and fenced JSON', () => {
        expect(mod.parseJudgeVerdict('```json\n{"pass": true, "reason": "ok"}\n```')).toEqual({ pass: true, reason: 'ok' });
        expect(mod.parseJudgeVerdict('pass: false — contains a stub')).toEqual({ pass: false, reason: '' });
    });
    it('returns null for garbage', () => {
        expect(mod.parseJudgeVerdict('I am not a verdict')).toBeNull();
    });
});
describe('micro experimenter — ORPO preference pairs', () => {
    it('exportOrpoPairs builds {instruction, chosen, rejected} from stored baseline files', () => {
        const idea = {
            purpose: 'a mini http server',
            design: 'route-lookup dispatch',
            focus: ['smaller', 'universal'],
            metrics: { bytes: 40, lines: 6, files: 1, genMs: 200 },
            baselineMetrics: base,
            composite: 0.35,
            exportsDir: path.join(tmp, 'exports', 'server'),
            files: [{ path: 'server.js', content: 'const routes={};http.createServer((req,res)=>res.end(routes[req.url]||routes["/"])).listen(3000);' }],
            baselineFiles: [{ path: 'server.js', content: 'const http=require("http");const server=http.createServer((req,res)=>{let body="<h1>Hello</h1>";res.writeHead(200,{"Content-Type":"text/html"});res.end(body);});server.listen(3000);' }],
        };
        mod.microExperimenter.storeIdea(idea);
        const out = mod.microExperimenter.exportOrpoPairs();
        expect('error' in out).toBe(false);
        if (!('error' in out)) {
            expect(out.count).toBeGreaterThanOrEqual(1);
            expect(fs.existsSync(out.file)).toBe(true);
            const content = fs.readFileSync(out.file, 'utf-8');
            expect(content).toContain('"instruction"');
            expect(content).toContain('"chosen"');
            expect(content).toContain('"rejected"');
            expect(content).toContain('http.createServer'); // chosen side carries the improved code
            expect(content).toContain('const server=http.createServer'); // rejected side carries the baseline
        }
    });
});
