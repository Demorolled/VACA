import { describe, it, expect } from 'vitest';
import * as os from 'os';
import { runProjectGates, runNonTsGatesWithRepair, sanitizeNonTsSource } from './nonTsRepair.js';
const tsContracts = [
    { path: 'src/game.ts', summary: '', language: 'typescript', exports: ['checkWin'], uses: [] },
];
describe('runProjectGates (shared non-TS + stub + contract-aware gate)', () => {
    it('flags a planned export whose body is a single placeholder return', async () => {
        const files = [{ path: 'src/game.ts', content: 'export function checkWin(): boolean { return false; }' }];
        const res = await runProjectGates('game', files, tsContracts);
        expect(res.stubFailures.some((s) => s.includes("'checkWin'"))).toBe(true);
    });
    it('accepts a real implementation', async () => {
        const files = [{ path: 'src/game.ts', content: 'export function checkWin(): boolean { return computeWinner() !== null; }' }];
        const res = await runProjectGates('game', files, tsContracts);
        expect(res.stubFailures).toEqual([]);
    });
    it('accepts a real PYTHON implementation (indented body, no braces)', async () => {
        // The brace-based body classifier found nothing in a .py file, so every
        // planned export came back 'absent' — which the gate reports as
        // "not implemented" for non-TS languages. Real Python nodes were rejected.
        const pyContracts = [
            { path: 'src/converter/converter.py', summary: '', language: 'python', exports: ['celsius_to_fahrenheit'], uses: [] },
        ];
        const files = [{
                path: 'src/converter/converter.py',
                content: 'def celsius_to_fahrenheit(celsius: float) -> float:\n    return (celsius * 9/5) + 32\n',
            }];
        const res = await runProjectGates('temp converter', files, pyContracts);
        expect(res.stubFailures).toEqual([]);
    });
    it('still flags a Python export whose body is only `pass`', async () => {
        const pyContracts = [
            { path: 'src/converter/converter.py', summary: '', language: 'python', exports: ['convert'], uses: [] },
        ];
        const files = [{ path: 'src/converter/converter.py', content: 'def convert(value):\n    pass\n' }];
        const res = await runProjectGates('temp converter', files, pyContracts);
        expect(res.stubFailures.some((s) => s.includes("'convert'"))).toBe(true);
    });
});
describe('sanitizeNonTsSource — Go node files never claim `package main`', () => {
    it('rewrites `package main` to the node directory package when there is no func main()', () => {
        const src = 'package main\n\nfunc reverseString(s string) string { return s }\n';
        const fixed = sanitizeNonTsSource(src, 'go', 'src/cli/cli.go');
        expect(fixed).toContain('package cli');
        expect(fixed).not.toContain('package main');
    });
    it('leaves a real Go program (func main) alone', () => {
        const prog = 'package main\n\nfunc main() { println("hi") }\n';
        expect(sanitizeNonTsSource(prog, 'go', 'src/cli/cli.go')).toBeNull();
    });
    it('falls back to `app` for an unusable directory name', () => {
        const src = 'package main\n\nfunc f() {}\n';
        expect(sanitizeNonTsSource(src, 'go', 'src/2d/render.go')).toContain('package app');
    });
});
describe('runNonTsGatesWithRepair (shared repair loop, injected LLM)', () => {
    it('repairs a stub body and clears the failure', async () => {
        const files = [{ path: 'src/game.ts', content: 'export function checkWin(): boolean { return false; }' }];
        let calls = 0;
        const res = await runNonTsGatesWithRepair({
            request: 'game',
            files,
            contractFiles: tsContracts,
            exportDir: os.tmpdir(),
            timeoutMs: 5_000,
            canRepair: () => true,
            consumeRepair: () => { calls += 1; },
            repairCall: async () => 'export function checkWin(): boolean { return scanBoard() !== null; }',
        });
        expect(calls).toBeGreaterThan(0);
        expect(res.stubFailures).toEqual([]);
        expect(files[0].content).toContain('scanBoard');
    });
    it('stops after one round when the LLM makes no change', async () => {
        const files = [{ path: 'src/game.ts', content: 'export function checkWin(): boolean { return false; }' }];
        const res = await runNonTsGatesWithRepair({
            request: 'game',
            files,
            contractFiles: tsContracts,
            exportDir: os.tmpdir(),
            timeoutMs: 5_000,
            canRepair: () => true,
            consumeRepair: () => { },
            repairCall: async () => '', // no usable rewrite
        });
        expect(res.rounds).toBe(1);
        expect(res.stubFailures.length).toBeGreaterThan(0);
    });
});
