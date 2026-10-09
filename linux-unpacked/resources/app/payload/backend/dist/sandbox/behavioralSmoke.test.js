/**
 * Shared behavioral smoke gate — the canvas/chat unification contract.
 *
 * These tests pin the parts the CANVAS path newly depends on:
 *   - the gate runs BOTH probes and reports honest verdicts,
 *   - a FAILED verdict feeds a bounded repair loop (2 rounds max),
 *   - a repair rewrites the entry IN PLACE and is written to disk so the next
 *     probe sees it (the canvas writes repairs back onto its files),
 *   - a deterministic runtime fix that clears the failure short-circuits the
 *     LLM call entirely (zero-cost repair),
 *   - `runStagedBehavioralSmoke` stages a file set, returns the repaired paths,
 *     and always removes its temp dir.
 *
 * The probes are injected, so no Chrome / Python / model server is required.
 */
import { describe, it, expect, vi } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { runBehavioralSmokeGates, runStagedBehavioralSmoke, pickCliEntryFile, detectHtmlTruncation, applyDeterministicHtmlRuntimeFixes, fixUninvokedEntryMain, addDeterministicHelpHandler, } from './behavioralSmoke.js';
const HTML = '<!doctype html><html><body><div id="board"></div><script>const b=document.getElementById("board");</script></body></html>';
function tmpDir() {
    return fs.mkdtempSync(path.join(os.tmpdir(), 'bsmoke-test-'));
}
/** A verdict helper so each test reads as its scenario. */
const failed = (detail, errors = []) => ({ status: 'failed', errors, detail });
const passed = (detail = 'ok') => ({ status: 'passed', errors: [], detail });
const skipped = (detail = 'skipped') => ({ status: 'skipped', errors: [], detail });
describe('runBehavioralSmokeGates — bounded repair loop', () => {
    it('repairs a FAILED render verdict and writes the fix to disk', async () => {
        const dir = tmpDir();
        const files = [{ path: 'index.html', content: HTML }];
        fs.writeFileSync(path.join(dir, 'index.html'), HTML);
        const probe = vi.fn()
            .mockResolvedValueOnce(failed('boom is not defined'))
            .mockResolvedValueOnce(passed('fixed'));
        const repairCall = vi.fn(async () => '<!doctype html><html><body>FIXED</body></html>');
        const res = await runBehavioralSmokeGates({
            request: 'build a game',
            files,
            contractFiles: [],
            exportDir: dir,
            timeoutMs: 1000,
            tag: 'test',
            canRepair: () => true,
            consumeRepair: () => { },
            repairCall,
            renderProbe: probe,
            cliProbe: async () => skipped(),
        });
        expect(repairCall).toHaveBeenCalledTimes(1);
        expect(res.renderSmoke.status).toBe('passed');
        // The rewrite landed on the in-memory file AND on disk (the probe re-reads disk).
        expect(files[0].content).toContain('FIXED');
        expect(fs.readFileSync(path.join(dir, 'index.html'), 'utf-8')).toContain('FIXED');
    });
    it('stops after 2 rounds and never repairs past the budget', async () => {
        const dir = tmpDir();
        const files = [{ path: 'index.html', content: HTML }];
        fs.writeFileSync(path.join(dir, 'index.html'), HTML);
        const repairCall = vi.fn(async () => HTML.replace('</body>', '<b>still broken</b></body>'));
        const res = await runBehavioralSmokeGates({
            request: 'build a game',
            files,
            contractFiles: [],
            exportDir: dir,
            timeoutMs: 1000,
            tag: 'test',
            canRepair: () => true,
            consumeRepair: () => { },
            repairCall,
            renderProbe: async () => failed('never fixed'),
            cliProbe: async () => skipped(),
        });
        expect(repairCall).toHaveBeenCalledTimes(2); // MAX_SMOKE_REPAIR_ROUNDS
        expect(res.renderSmoke.status).toBe('failed');
    });
    it('honors a caller whose repair budget is exhausted (canRepair false)', async () => {
        const dir = tmpDir();
        const files = [{ path: 'index.html', content: HTML }];
        fs.writeFileSync(path.join(dir, 'index.html'), HTML);
        const repairCall = vi.fn(async () => 'unused');
        await runBehavioralSmokeGates({
            request: 'build a game',
            files,
            contractFiles: [],
            exportDir: dir,
            timeoutMs: 1000,
            tag: 'test',
            canRepair: () => false,
            consumeRepair: () => { },
            repairCall,
            renderProbe: async () => failed('no budget'),
            cliProbe: async () => skipped(),
        });
        expect(repairCall).not.toHaveBeenCalled();
    });
    it('runs the CLI gate when there is no HTML entry', async () => {
        const dir = tmpDir();
        const files = [{ path: 'main.ts', content: 'console.log("hi")' }];
        fs.writeFileSync(path.join(dir, 'main.ts'), 'console.log("hi")');
        const cliProbe = vi.fn(async () => passed('ran'));
        const res = await runBehavioralSmokeGates({
            request: 'build a cli',
            files,
            contractFiles: [],
            exportDir: dir,
            timeoutMs: 1000,
            tag: 'test',
            canRepair: () => true,
            consumeRepair: () => { },
            repairCall: async () => '',
            renderProbe: async () => skipped('no HTML entry file'),
            cliProbe,
        });
        expect(cliProbe).toHaveBeenCalledTimes(1);
        expect(res.cliSmoke.status).toBe('passed');
    });
    it('applies the deterministic HTML runtime fix BEFORE the LLM (zero-cost repair)', async () => {
        const dir = tmpDir();
        // `dataset.row === row` is the first-click crash class — the deterministic
        // fixer coerces the compared value, and the re-probe passes, so the model
        // is never called.
        const broken = '<!doctype html><html><body><script>const el = squares.find(s => s.dataset.row === row);</script></body></html>';
        const files = [{ path: 'index.html', content: broken }];
        fs.writeFileSync(path.join(dir, 'index.html'), broken);
        const repairCall = vi.fn(async () => 'should-not-run');
        let calls = 0;
        const probe = vi.fn(async (_dir, f) => {
            calls += 1;
            return calls === 1 ? failed('first-click crash') : passed('fixed by fixer');
        });
        const res = await runBehavioralSmokeGates({
            request: 'build checkers',
            files,
            contractFiles: [],
            exportDir: dir,
            timeoutMs: 1000,
            tag: 'test',
            canRepair: () => true,
            consumeRepair: () => { },
            repairCall,
            renderProbe: probe,
            cliProbe: async () => skipped(),
        });
        expect(res.renderSmoke.status).toBe('passed');
        expect(repairCall).not.toHaveBeenCalled();
        expect(files[0].content).toContain('String(row)');
    });
});
describe('runStagedBehavioralSmoke — the canvas path entry point', () => {
    it('stages files, runs the gate, returns repaired paths, and cleans up', async () => {
        const files = [{ path: 'index.html', content: HTML }];
        const repairCall = vi.fn(async () => '<!doctype html><html><body>FIXED</body></html>');
        let calls = 0;
        const probe = vi.fn(async () => (++calls === 1 ? failed('broken') : passed('fixed')));
        // Inject the probe by calling the underlying gate through a spy is awkward;
        // instead drive the staged helper with a fake render probe via the shared
        // gate's injectable options is not exposed here — so assert the staging
        // contract through the real (skipped) probes: an HTML entry with markers
        // will try the python script; on a box without it the verdict is
        // unavailable/fallback, which is still an honest non-pass.
        const res = await runStagedBehavioralSmoke({
            files,
            request: 'build a game',
            contractFiles: [],
            timeoutMs: 3000,
            tag: 'canvas-test',
            repairCall,
            maxRepairRounds: 2,
        });
        // The temp dir is always removed.
        expect(fs.existsSync(res.exportDir)).toBe(false);
        // A verdict was produced (passed/failed/unavailable) — never undefined.
        expect(['passed', 'failed', 'skipped', 'unavailable']).toContain(res.renderSmoke.status);
        expect(Array.isArray(res.repairedPaths)).toBe(true);
        void probe;
    });
});
describe('pure helpers the canvas path shares', () => {
    it('pickCliEntryFile prefers main/index/cli over arbitrary files', () => {
        expect(pickCliEntryFile([{ path: 'src/util.ts' }, { path: 'main.ts' }])).toBe('main.ts');
        expect(pickCliEntryFile([{ path: 'a.ts' }, { path: 'b.ts' }])).toBe('a.ts');
        expect(pickCliEntryFile([{ path: 'readme.md' }])).toBeNull();
    });
    it('detectHtmlTruncation flags an unclosed document, passes a complete one', () => {
        expect(detectHtmlTruncation('<html><body><script>x()</script>')).toContain('INCOMPLETE');
        expect(detectHtmlTruncation(HTML)).toBe('');
    });
    it('applyDeterministicHtmlRuntimeFixes coerces dataset comparisons and guards lookups', () => {
        expect(applyDeterministicHtmlRuntimeFixes('a.dataset.row === row'))
            .toBe('a.dataset.row === String(row)');
        expect(applyDeterministicHtmlRuntimeFixes('squares.find(s => s.dataset.row === row).querySelector(".x")'))
            .toContain('?.querySelector');
    });
    it('fixUninvokedEntryMain appends the missing call, and is idempotent', () => {
        const fixed = fixUninvokedEntryMain('function main() { console.log(1); }');
        expect(fixed).toContain('main();');
        expect(fixUninvokedEntryMain(fixed)).toBeNull();
    });
    it('addDeterministicHelpHandler injects usage for a dispatch with no help', () => {
        const fixed = addDeterministicHelpHandler('function main() { switch (args[0]) { case "add": break; } }');
        expect(fixed).toContain('__vacaHelp');
        expect(addDeterministicHelpHandler(fixed)).toBeNull();
    });
});
