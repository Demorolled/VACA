import { describe, it, expect } from 'vitest';
import { runScaffoldExperiment, metricsFromOutcome } from './scaffoldExperiment.js';
import { scoreFilesAdherence, scoreVariant } from './scaffoldVariation.js';
const bp = {
    app_type: 'demo',
    description: 'a demo app',
    keywords: ['demo'],
    target_stack: { frontend: 'vanilla', backend: 'node', database: 'sqlite' },
    architecture_checklist: ['Input', 'Engine', 'Store', 'View'],
    wiring_graph: [
        { source_module: 'Input', destination_module: 'Engine', data_passed: 'data' },
        { source_module: 'Engine', destination_module: 'Store', data_passed: 'results' },
        { source_module: 'Store', destination_module: 'View', data_passed: 'state' },
    ],
};
/** A clean outcome: all files adherent, gates green, no drift. */
function clean(extra = {}) {
    return {
        files: [
            { path: 'engine.ts', content: 'export function runEngine(input: unknown): unknown { return input; }\n' },
            { path: 'store.ts', content: 'export const store = { value: 0 };\n' },
        ],
        tsCompileClean: true,
        renderSmoke: 'passed',
        cliSmoke: 'skipped',
        contractViolations: 0,
        driftMissing: 0,
        driftUnexpected: 0,
        ...extra,
    };
}
describe('metricsFromOutcome', () => {
    it('returns null for a failed build', () => {
        expect(metricsFromOutcome(null)).toBeNull();
    });
    it('maps a clean outcome to fully-adherent metrics', () => {
        const m = metricsFromOutcome(clean());
        expect(m.adherence).toBe(1);
        expect(m.fullyAdherent).toBe(2);
        expect(m.tscClean).toBe(true);
        expect(m.smokePassed).toBe(true);
    });
    it('treats a failed smoke as not passed', () => {
        const m = metricsFromOutcome(clean({ renderSmoke: 'failed' }));
        expect(m.smokePassed).toBe(false);
    });
    it('scores a non-TypeScript (Go) outcome instead of zeroing it', () => {
        const m = metricsFromOutcome({
            files: [
                { path: 'engine.go', content: 'package main\n\nfunc RunEngine(in string) string { return in }\n' },
                { path: 'store.go', content: 'package main\n\nfunc Store(v int) int { return v }\n' },
            ],
            tsCompileClean: true,
            renderSmoke: 'skipped',
            cliSmoke: 'passed',
            contractViolations: 0,
            driftMissing: 0,
            driftUnexpected: 0,
        });
        expect(m.adherence).toBe(1);
        expect(m.fullyAdherent).toBe(2);
    });
    it('ranks a real Go scaffold above a stubbed one', () => {
        const base = { tsCompileClean: true, renderSmoke: 'skipped', cliSmoke: 'passed', contractViolations: 0, driftMissing: 0, driftUnexpected: 0 };
        const good = metricsFromOutcome({ ...base, files: [{ path: 'engine.go', content: 'package main\n\nfunc Run(in string) string { return in }\n' }] });
        const bad = metricsFromOutcome({ ...base, files: [{ path: 'engine.go', content: 'package main\n// TODO: implement\n' }] });
        expect(scoreVariant(good)).toBeGreaterThan(scoreVariant(bad));
    });
});
describe('runScaffoldExperiment', () => {
    it('keeps the incumbent when no variant improves', async () => {
        const res = await runScaffoldExperiment({
            blueprint: bp,
            build: async () => clean(), // every variant identical
            margin: 0.25,
        });
        expect(res.ok).toBe(true);
        expect(res.incumbent.score).toBeGreaterThan(0);
        expect(res.variants.length).toBeGreaterThan(0);
        expect(res.winner).toBeNull();
        expect(res.adopted).toBe(false);
    });
    it('adopts a variant that measurably improves the scaffold', async () => {
        // The incumbent is BROKEN (phantom import → an adherence failure); every
        // variant is clean, so the best variant clears the margin.
        const broken = clean({
            files: [{ path: 'engine.ts', content: "import { x } from 'lodash';\nexport const engine = x;\n" }],
            contractViolations: 3,
            driftMissing: 2,
            driftUnexpected: 1,
            tsCompileClean: false,
        });
        const res = await runScaffoldExperiment({
            blueprint: bp,
            build: async (b) => (b === bp ? broken : clean()),
            margin: 0.25,
        });
        expect(res.adopted).toBe(true);
        expect(res.winner).not.toBeNull();
        expect(res.winner.score).toBeGreaterThan(res.incumbent.score);
    });
    it('does not adopt when the build throws (a failed variant cannot win)', async () => {
        const res = await runScaffoldExperiment({
            blueprint: bp,
            build: async (b) => {
                if (b === bp)
                    return clean();
                throw new Error('boom');
            },
        });
        expect(res.winner).toBeNull();
        expect(res.adopted).toBe(false);
        expect(res.variants.every((v) => !v.ok)).toBe(true);
    });
    it('records every proposed variant even when none wins', async () => {
        const res = await runScaffoldExperiment({ blueprint: bp, build: async () => clean(), maxVariants: 3 });
        expect(res.variants.length).toBeLessThanOrEqual(3);
        expect(res.variants.length).toBeGreaterThan(0);
    });
    it('respects the improvement margin (no adoption inside the noise band)', async () => {
        // Variants differ only by a tiny adherence delta (below the margin).
        const almost = clean({
            files: [{ path: 'engine.ts', content: 'export const engine = 1;\n' }],
        });
        const res = await runScaffoldExperiment({
            blueprint: bp,
            build: async () => almost,
            margin: 5, // huge margin → nothing can clear it
        });
        expect(res.adopted).toBe(false);
    });
});
describe('scoreFilesAdherence (backend mirror of the .mjs gate)', () => {
    it('scores a clean file 1.0', () => {
        const r = scoreFilesAdherence([{ path: 'a.ts', content: 'export const a = 1;\n' }]);
        expect(r.score).toBe(1);
        expect(r.fullyAdherent).toBe(1);
    });
    it('flags a phantom import and a default export', () => {
        const r = scoreFilesAdherence([
            { path: 'a.ts', content: "import { x } from 'lodash';\nexport default x;\n" },
        ]);
        expect(r.failures.no_phantom_imports).toBe(1);
        expect(r.failures.no_default_export).toBe(1);
        expect(r.score).toBeLessThan(1);
    });
    it('flags JSX in a .ts file but not in .tsx', () => {
        const jsx = 'export const C = () => <div>hi</div>;\n';
        expect(scoreFilesAdherence([{ path: 'a.ts', content: jsx }]).failures.no_jsx_in_ts).toBe(1);
        expect(scoreFilesAdherence([{ path: 'a.tsx', content: jsx }]).failures.no_jsx_in_ts).toBeUndefined();
    });
    it('flags a stub body', () => {
        const r = scoreFilesAdherence([{ path: 'a.ts', content: 'export function a() { throw new Error("Not implemented"); }\n' }]);
        expect(r.failures.not_stub).toBe(1);
    });
    it('flags a prose leak', () => {
        const r = scoreFilesAdherence([{ path: 'a.ts', content: "Here's the code you asked for:\nexport const a = 1;\n" }]);
        expect(r.failures.no_prose_leak).toBe(1);
    });
});
