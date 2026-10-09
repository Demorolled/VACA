import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { mkdtempSync, writeFileSync, rmSync, readFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { tmpdir } from 'os';
let tmpFile = '';
let mod;
beforeAll(async () => {
    tmpFile = join(mkdtempSync(join(tmpdir(), 'vaca-verified-capture-')), 'verified-generations.jsonl');
    // Env must be set BEFORE the module is imported (path is computed at load).
    process.env.VACA_VERIFIED_CAPTURE_FILE = tmpFile;
    mod = await import('./verifiedGenerationCapture.js');
});
afterAll(() => {
    delete process.env.VACA_VERIFIED_CAPTURE_FILE;
    if (tmpFile)
        rmSync(tmpFile, { recursive: true, force: true });
});
function makeFile(overrides = {}) {
    return {
        fileName: 'main.ts',
        language: 'typescript',
        code: 'export function add(a: number, b: number): number {\n  return a + b;\n}\n\nexport function main(): void {\n  console.log(add(1, 2));\n}\n',
        nodeId: 'node-1',
        nodeLabel: 'Math Engine',
        dependencies: [],
        exports: ['add', 'main'],
        errors: [],
        validated: true,
        ...overrides,
    };
}
function makeProject(overrides = {}) {
    return {
        id: 'p1',
        name: 'calc-app',
        targetOS: 'linux',
        nodes: [
            { id: 'master-1', type: 'master', data: { appGoal: 'a calculator app', appPurpose: 'add two numbers', label: 'Master' } },
            { id: 'node-1', type: 'logic', data: { label: 'Math Engine', description: 'arithmetic core', language: 'typescript' } },
        ],
        edges: [],
        createdAt: new Date(),
        updatedAt: new Date(),
        ...overrides,
    };
}
describe('verifiedGenerationCapture', () => {
    it('builds a training row in the captured-verified format for a verified file', () => {
        const rows = mod.buildVerifiedRows(makeProject(), [makeFile()], { tsCompileClean: true });
        expect(rows).toHaveLength(1);
        const row = rows[0];
        expect(row.output).toContain('export function add');
        expect(row.source).toBe('verified-generation:calc-app');
        expect(row.instruction).toContain('Project goal: a calculator app');
        expect(row.instruction).toContain('PLANNED FILES:');
        expect(row.instruction).toContain('- main.ts (typescript) — Math Engine');
        expect(row.instruction).toContain("Generate the COMPLETE file 'main.ts'");
        expect(row.instruction).toContain('Node type: logic');
        expect(row.instruction).toContain('Purpose: arithmetic core');
        expect(row.input).toBe('');
    });
    it('skips the preview HTML wrapper and non-node files', () => {
        const wrapper = makeFile({ fileName: 'index.html', nodeId: '', language: 'html', validated: false });
        const rows = mod.buildVerifiedRows(makeProject(), [makeFile(), wrapper], { tsCompileClean: true });
        expect(rows).toHaveLength(1);
    });
    it('skips files that did not pass validation', () => {
        const bad = makeFile({ errors: ['TS2345: type error (line 3)'], validated: false });
        expect(mod.buildVerifiedRows(makeProject(), [bad], { tsCompileClean: false })).toHaveLength(0);
    });
    it('captures TS files when the compile-check was clean even if sandbox was unavailable', () => {
        const stale = makeFile({ errors: ['Sandbox validation unavailable'], validated: false });
        const rows = mod.buildVerifiedRows(makeProject(), [stale], { tsCompileClean: true });
        expect(rows).toHaveLength(1);
    });
    it('skips tiny files and stub-ridden files', () => {
        const tiny = makeFile({ code: '// hi' });
        const stub = makeFile({ nodeId: 'node-2', nodeLabel: 'X', code: '// TODO: Implement X\nexport function x() { throw new Error("not implemented"); }' });
        const rows = mod.buildVerifiedRows(makeProject(), [tiny, stub], { tsCompileClean: true });
        expect(rows).toHaveLength(0);
    });
    it('skips shell placeholders (untyped any[] + JSON round-trip, no imports)', () => {
        const shell = makeFile({
            nodeId: 'node-2',
            nodeLabel: 'Game State',
            fileName: 'game-state.ts',
            code: 'export class GameState {\n  state_and_events: any[];\n  gameData: string;\n  constructor(gameAndEvents: any[], gameData: string) { this.state_and_events = gameAndEvents; this.gameData = gameData; }\n  update(result: any): void { this.state_and_events.push(result); this.gameData = JSON.stringify(this.state_and_events); }\n  getData(): any[] { return JSON.parse(this.gameData); }\n}\n',
        });
        const rows = mod.buildVerifiedRows(makeProject(), [shell], { tsCompileClean: true });
        expect(rows).toHaveLength(0);
    });
    it('skips files that echo other modules\' filename headers as comments', () => {
        const echoed = makeFile({
            nodeId: 'node-2',
            nodeLabel: 'Game State',
            fileName: 'game-state.ts',
            code: '// Game State.ts\n// Game Engine.ts\n// AI Opponent.ts\nexport class GameState {\n  cards: string[] = [];\n  shuffle(): void { this.cards.reverse(); }\n}\n',
        });
        const rows = mod.buildVerifiedRows(makeProject(), [echoed], { tsCompileClean: true });
        expect(rows).toHaveLength(0);
    });
    it('appends to the capture file and is idempotent (no duplicates on re-run)', () => {
        const project = makeProject();
        const files = [makeFile()];
        const first = mod.captureVerifiedGeneration(project, files, { tsCompileClean: true });
        expect(first.captured).toBe(1);
        const second = mod.captureVerifiedGeneration(project, files, { tsCompileClean: true });
        expect(second.captured).toBe(0);
        expect(second.skipped).toBe(1);
        const lines = readFileSync(tmpFile, 'utf-8').trim().split('\n').filter(Boolean);
        expect(lines).toHaveLength(1);
    });
    it('appends NEW rows on later runs without repeating old ones', () => {
        const project = makeProject();
        mod.captureVerifiedGeneration(project, [makeFile()], { tsCompileClean: true });
        const secondFile = makeFile({ nodeId: 'node-2', nodeLabel: 'UI Shell', fileName: 'ui.ts', code: 'export function render(): string {\n  return "<div>hi</div>";\n}\n' });
        const projectWithNode = makeProject();
        projectWithNode.nodes.push({ id: 'node-2', type: 'ui', data: { label: 'UI Shell', language: 'typescript' } });
        const res = mod.captureVerifiedGeneration(projectWithNode, [makeFile(), secondFile], { tsCompileClean: true });
        expect(res.captured).toBe(1); // only the new file is fresh
        const lines = readFileSync(tmpFile, 'utf-8').trim().split('\n').filter(Boolean);
        expect(lines).toHaveLength(2);
        expect(tmpFile).toBe(mod.VERIFIED_CAPTURE_FILE);
    });
    it('embeds blueprint constraints into the instruction and tags the source (blueprint-driven builds)', () => {
        const bpCtx = 'APP TYPE: todo_app\nTARGET STACK: frontend=React\nARCHITECTURE CHECKLIST:\n  - ui_screens\n  - task_store\nWIRING GRAPH:\n  - ui_screens \u2192 task_store : requests';
        const rows = mod.buildVerifiedRows(makeProject(), [makeFile()], { tsCompileClean: true, blueprintContext: bpCtx, sourceTag: 'blueprint-verified:todo_app' });
        expect(rows).toHaveLength(1);
        expect(rows[0].instruction).toContain('BLUEPRINT CONSTRAINTS (MANDATORY):');
        expect(rows[0].instruction).toContain('APP TYPE: todo_app');
        expect(rows[0].instruction).toContain('WIRING GRAPH:');
        expect(rows[0].instruction).toContain('THIS FILE\'S MODULE: "Math Engine"');
        expect(rows[0].instruction).toContain("Generate the COMPLETE file 'main.ts'");
        expect(rows[0].source).toBe('blueprint-verified:todo_app:calc-app');
    });
    it('captures blueprint-tagged rows into the shared capture file', () => {
        const bpCtx = 'APP TYPE: todo_app\nARCHITECTURE CHECKLIST:\n  - ui_screens\n  - task_store';
        const project = makeProject({ name: 'todo-app-blueprint' });
        const res = mod.captureVerifiedGeneration(project, [makeFile()], {
            tsCompileClean: true,
            blueprintContext: bpCtx,
            sourceTag: 'blueprint-verified:todo_app',
        });
        expect(res.captured).toBe(1);
        const lines = readFileSync(tmpFile, 'utf-8').trim().split('\n').filter(Boolean);
        const last = JSON.parse(lines[lines.length - 1]);
        expect(last.source).toBe('blueprint-verified:todo_app:todo-app-blueprint');
        expect(last.instruction).toContain('BLUEPRINT CONSTRAINTS (MANDATORY):');
        // Idempotent on re-run (same blueprint + files).
        const again = mod.captureVerifiedGeneration(project, [makeFile()], {
            tsCompileClean: true,
            blueprintContext: bpCtx,
            sourceTag: 'blueprint-verified:todo_app',
        });
        expect(again.captured).toBe(0);
        expect(again.skipped).toBe(1);
    });
});
describe('captureVerifiedSidecar (chat path → shared loop)', () => {
    function makeSidecarExport(files, sidecarOverrides = {}) {
        const dir = mkdtempSync(join(tmpdir(), 'vaca-sidecar-'));
        for (const f of files) {
            const abs = join(dir, f.path);
            mkdirSync(dirname(abs), { recursive: true });
            writeFileSync(abs, f.code, 'utf-8');
        }
        const sidecar = {
            version: 1,
            createdAt: new Date().toISOString(),
            request: 'build me a calculator',
            intent: { goal: 'a calculator', language: 'typescript' },
            questions: [],
            answers: {},
            planFiles: files.map((f) => ({ path: f.path, summary: 'math core', language: 'typescript', exports: ['add'] })),
            mode: 'one-shot',
            libraryContext: 'REFERENCE: calculator patterns',
            files: files.map((f) => f.path),
            ...sidecarOverrides,
        };
        writeFileSync(join(dir, '_training.json'), JSON.stringify(sidecar, null, 2), 'utf-8');
        return dir;
    }
    const CLEAN = 'export function add(a: number, b: number): number {\n  return a + b;\n}\n\nexport function main(): void {\n  console.log(add(1, 2));\n}\n';
    it('captures a tsc-clean sidecar export into the shared file with the Python-row format', async () => {
        const dir = makeSidecarExport([{ path: 'src/math.ts', code: CLEAN }]);
        const res = await mod.captureVerifiedSidecar(dir, { tsCompileClean: true });
        expect(res.captured).toBe(1);
        const lines = readFileSync(tmpFile, 'utf-8').trim().split('\n').filter(Boolean);
        const row = JSON.parse(lines[lines.length - 1]);
        expect(row.source).toBe('captured-verified');
        expect(row.instruction).toContain('User request: build me a calculator');
        expect(row.instruction).toContain('UNDERSTOOD INTENT: Goal: a calculator | Language: typescript');
        expect(row.instruction).toContain('PLANNED FILES:');
        expect(row.instruction).toContain('- src/math.ts (typescript) — math core');
        expect(row.instruction).toContain("Generate the COMPLETE file 'src/math.ts'");
        expect(row.input).toContain('REFERENCE: calculator patterns');
        expect(row.output).toContain('export function add');
        // sidecar is stamped so the Python gate skips it — one loop, no duplicates
        const stamped = JSON.parse(readFileSync(join(dir, '_training.json'), 'utf-8'));
        expect(stamped.capturedAt).toBeTruthy();
        expect(stamped.status).toBe('captured');
        rmSync(dir, { recursive: true, force: true });
    });
    it('skips an already-captured sidecar', async () => {
        // Distinct request so the shared-file dedupe (from the earlier test) is not what skips it.
        const dir = makeSidecarExport([{ path: 'src/math.ts', code: CLEAN }], { request: 'build me a timer' });
        await mod.captureVerifiedSidecar(dir, { tsCompileClean: true });
        const second = await mod.captureVerifiedSidecar(dir, { tsCompileClean: true });
        expect(second.captured).toBe(0);
        expect(second.reasons['already-captured']).toBe(1);
        rmSync(dir, { recursive: true, force: true });
    });
    it('skips exports with no ts files (html-only)', async () => {
        const dir = makeSidecarExport([{ path: 'index.html', code: '<!doctype html><html><body>hi</body></html>' }]);
        const res = await mod.captureVerifiedSidecar(dir, { tsCompileClean: true });
        expect(res.captured).toBe(0);
        expect(res.reasons['no-ts']).toBe(1);
        rmSync(dir, { recursive: true, force: true });
    });
    it('skips stubs, tiny files, JSX-in-ts and prose', async () => {
        const dir = makeSidecarExport([
            { path: 'a.ts', code: '// TODO: Implement a — this needs to actually do something\nexport function a() { throw new Error("not implemented"); }' },
            { path: 'b.ts', code: '// hi' },
            { path: 'c.ts', code: 'export function render(): string {\n  const name = "app";\n  return <div className={name}>Hello, world! This is a longer line of text.</div>;\n}\n' },
            { path: 'd.ts', code: 'Note: this file does a thing.\nexport const y = 1;\n// padding padding padding padding padding padding padding padding padding padding\n' },
        ]);
        const res = await mod.captureVerifiedSidecar(dir, { tsCompileClean: true });
        expect(res.captured).toBe(0);
        expect(res.reasons['stub']).toBe(1);
        expect(res.reasons['tiny']).toBe(1);
        expect(res.reasons['jsx-in-ts']).toBe(1);
        expect(res.reasons['prose']).toBe(1);
        rmSync(dir, { recursive: true, force: true });
    });
    it('skips shell placeholders (untyped any[] + JSON round-trip)', async () => {
        const dir = makeSidecarExport([
            { path: 'src/state.ts', code: 'export class GameState {\n  state: any[];\n  blob: string;\n  constructor(x: any[], blob: string) { this.state = x; this.blob = blob; }\n  update(r: any): void { this.state.push(r); this.blob = JSON.stringify(this.state); }\n  get(): any[] { return JSON.parse(this.blob); }\n}\n' },
        ]);
        const res = await mod.captureVerifiedSidecar(dir, { tsCompileClean: true });
        expect(res.captured).toBe(0);
        expect(res.reasons['shell']).toBe(1);
        rmSync(dir, { recursive: true, force: true });
    });
    it('dedupes against rows already in the shared file (same instruction+output)', async () => {
        const d1 = makeSidecarExport([{ path: 'src/math.ts', code: CLEAN }]);
        await mod.captureVerifiedSidecar(d1, { tsCompileClean: true });
        // a brand-new, un-stamped sidecar with identical request + plan + file content
        const d2 = makeSidecarExport([{ path: 'src/math.ts', code: CLEAN }]);
        const res = await mod.captureVerifiedSidecar(d2, { tsCompileClean: true });
        expect(res.captured).toBe(0);
        expect(res.reasons['duplicate']).toBe(1);
        rmSync(d1, { recursive: true, force: true });
        rmSync(d2, { recursive: true, force: true });
    });
});
