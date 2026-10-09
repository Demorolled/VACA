import { describe, it, expect } from 'vitest';
import { scoreVariant, isImprovement, isValidVariant, splitModule, mergeModules, addWiring, refineContract, addLeafModule, generateVariants, describeScoredVariant, scoreFilesAdherence, } from './scaffoldVariation.js';
const base = {
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
const clone = (b) => ({
    ...b,
    keywords: [...b.keywords],
    target_stack: { ...b.target_stack },
    architecture_checklist: [...b.architecture_checklist],
    wiring_graph: b.wiring_graph.map((w) => ({ ...w })),
});
describe('isValidVariant', () => {
    it('accepts a well-formed blueprint', () => {
        expect(isValidVariant(base)).toBe(true);
    });
    it('rejects duplicate checklist labels', () => {
        const b = clone(base);
        b.architecture_checklist = ['A', 'A', 'B'];
        expect(isValidVariant(b)).toBe(false);
    });
    it('rejects a dangling wiring endpoint', () => {
        const b = clone(base);
        b.wiring_graph.push({ source_module: 'Ghost', destination_module: 'Engine', data_passed: 'x' });
        expect(isValidVariant(b)).toBe(false);
    });
    it('rejects a blueprint with fewer than two modules', () => {
        const b = clone(base);
        b.architecture_checklist = ['Only'];
        b.wiring_graph = [];
        expect(isValidVariant(b)).toBe(false);
    });
});
describe('splitModule', () => {
    it('splits a module and reroutes its outbound contracts through the new one', () => {
        const v = splitModule(base, 'Engine', 'EngineCore');
        expect(v).not.toBeNull();
        expect(v.op).toBe('split_module');
        expect(v.blueprint.architecture_checklist).toContain('EngineCore');
        // Original now feeds the new module…
        expect(v.blueprint.wiring_graph).toContainEqual(expect.objectContaining({ source_module: 'Engine', destination_module: 'EngineCore' }));
        // …and the new module carries the old Engine → Store edge.
        expect(v.blueprint.wiring_graph).toContainEqual(expect.objectContaining({ source_module: 'EngineCore', destination_module: 'Store' }));
        expect(isValidVariant(v.blueprint)).toBe(true);
    });
    it('does not mutate the input blueprint', () => {
        const before = JSON.stringify(base);
        splitModule(base, 'Engine', 'EngineCore');
        expect(JSON.stringify(base)).toBe(before);
    });
    it('returns null for an unknown module or an existing name', () => {
        expect(splitModule(base, 'Nope', 'X')).toBeNull();
        expect(splitModule(base, 'Engine', 'Store')).toBeNull();
    });
    it('returns null when the module has no outbound wiring (would be a leaf)', () => {
        expect(splitModule(base, 'View', 'ViewCore')).toBeNull();
    });
});
describe('mergeModules', () => {
    it('folds one module into another and drops the merge-created self-edge', () => {
        const v = mergeModules(base, 'Engine', 'Store', 'EngineAndStore');
        expect(v.op).toBe('merge_modules');
        expect(v.blueprint.architecture_checklist).not.toContain('Store');
        expect(v.blueprint.architecture_checklist).toContain('EngineAndStore');
        // Engine→Store became a self-edge and must be gone.
        expect(v.blueprint.wiring_graph.some((w) => w.source_module === w.destination_module)).toBe(false);
        expect(isValidVariant(v.blueprint)).toBe(true);
    });
    it('returns null when the two modules are the same or missing', () => {
        expect(mergeModules(base, 'Engine', 'Engine')).toBeNull();
        expect(mergeModules(base, 'Engine', 'Ghost')).toBeNull();
    });
});
describe('addWiring / refineContract / addLeafModule', () => {
    it('adds a contract between two existing modules', () => {
        const v = addWiring(base, 'Input', 'View', 'render_state');
        expect(v.blueprint.wiring_graph).toContainEqual(expect.objectContaining({ source_module: 'Input', destination_module: 'View', data_passed: 'render_state' }));
    });
    it('refuses a duplicate edge and a self-edge', () => {
        expect(addWiring(base, 'Input', 'Engine', 'x')).toBeNull();
        expect(addWiring(base, 'Input', 'Input', 'x')).toBeNull();
    });
    it('refines an existing contract label', () => {
        const v = refineContract(base, 'Input', 'Engine', 'raw_input');
        const edge = v.blueprint.wiring_graph.find((w) => w.source_module === 'Input' && w.destination_module === 'Engine');
        expect(edge.data_passed).toBe('raw_input');
    });
    it('returns null when the label is unchanged or the edge is missing', () => {
        expect(refineContract(base, 'Input', 'Engine', 'data')).toBeNull();
        expect(refineContract(base, 'Input', 'View', 'x')).toBeNull();
    });
    it('adds a leaf module wired from an existing source', () => {
        const v = addLeafModule(base, 'Validator', 'Engine', 'checks');
        expect(v.blueprint.architecture_checklist).toContain('Validator');
        expect(v.blueprint.wiring_graph).toContainEqual(expect.objectContaining({ source_module: 'Engine', destination_module: 'Validator' }));
    });
    it('returns null for a duplicate name or unknown source', () => {
        expect(addLeafModule(base, 'Store', 'Engine')).toBeNull();
        expect(addLeafModule(base, 'New', 'Ghost')).toBeNull();
    });
});
describe('generateVariants', () => {
    it('proposes only valid, unique, bounded variants', () => {
        const vs = generateVariants(base, { max: 4 });
        expect(vs.length).toBeGreaterThan(0);
        expect(vs.length).toBeLessThanOrEqual(4);
        for (const v of vs) {
            expect(isValidVariant(v.blueprint)).toBe(true);
            expect(v.rationale.length).toBeGreaterThan(0);
        }
        expect(new Set(vs.map((v) => v.id)).size).toBe(vs.length);
    });
    it('refines generic contract labels first (cheap, high-signal)', () => {
        const vs = generateVariants(base, { max: 10 });
        expect(vs.some((v) => v.op === 'refine_contract')).toBe(true);
    });
    it('uses proposed names for the split and leaf variants', () => {
        const vs = generateVariants(base, { max: 10, proposedNames: ['EngineCore', 'Validator'] });
        const split = vs.find((v) => v.op === 'split_module');
        expect(split?.blueprint.architecture_checklist).toContain('EngineCore');
        expect(vs.some((v) => v.op === 'add_leaf_module')).toBe(true);
    });
});
describe('scoreVariant / isImprovement', () => {
    const good = {
        tscClean: true, smokePassed: true, adherence: 1, fullyAdherent: 5,
        driftMissing: 0, driftUnexpected: 0, contractViolations: 0, fileCount: 5,
    };
    const bad = {
        tscClean: false, smokePassed: false, adherence: 0.4, fullyAdherent: 1,
        driftMissing: 2, driftUnexpected: 1, contractViolations: 4, fileCount: 5,
    };
    it('scores a clean, adherent build above a broken one', () => {
        expect(scoreVariant(good)).toBeGreaterThan(scoreVariant(bad));
    });
    it('scores a failed build (null metrics) at 0', () => {
        expect(scoreVariant(null)).toBe(0);
    });
    it('requires a margin to count as an improvement (noise band)', () => {
        const inc = mkScored('a', good);
        const barely = mkScored('b', { ...good, adherence: good.adherence - 0.01 });
        expect(isImprovement(barely, inc)).toBe(false);
        const clear = mkScored('c', { ...good, adherence: 1, fileCount: 5 });
        // Clear improvement must also exceed the margin.
        const better = mkScored('d', { ...good, adherence: 1, contractViolations: 0 });
        expect(isImprovement(clear, inc)).toBe(false); // equal score, no margin
        expect(isImprovement(better, mkScored('e', { ...good, adherence: 0.5 }))).toBe(true);
    });
    it('never treats a failed build as an improvement', () => {
        const failed = { id: 'x', op: 'add_wiring', rationale: '', blueprint: base, metrics: null, score: 0, ok: false };
        expect(isImprovement(failed, mkScored('ok', good))).toBe(false);
    });
    it('describeScoredVariant summarizes metrics', () => {
        const line = describeScoredVariant(mkScored('v', good));
        expect(line).toContain('adherence=1.000');
        expect(line).toContain('tsc=clean');
    });
});
describe('scoreFilesAdherence (language-aware)', () => {
    it('keeps the original seven checks for TypeScript', () => {
        const r = scoreFilesAdherence([
            { path: 'src/a/a.ts', content: 'export function a(): number { return 1; }\n' },
            { path: 'src/b/b.ts', content: 'export const b = 2;\n' },
        ]);
        expect(r.score).toBe(1);
        expect(r.fullyAdherent).toBe(2);
        expect(r.failures.no_phantom_imports).toBeUndefined();
    });
    it('scores a clean file in every new language as adherent', () => {
        const files = [
            { path: 'main.go', content: 'package main\n\nfunc Add(a int, b int) int {\n\treturn a + b\n}\n' },
            { path: 'lib.rs', content: 'pub fn add(a: i32, b: i32) -> i32 {\n    a + b\n}\n' },
            { path: 'app.py', content: 'def add(a, b):\n    return a + b\n' },
            { path: 'util.cpp', content: 'int add(int a, int b) {\n    return a + b;\n}\n' },
            { path: 'Calc.java', content: 'public class Calc {\n    public static int add(int a, int b) { return a + b; }\n}\n' },
            { path: 'Calc.cs', content: 'public class Calc {\n    public static int Add(int a, int b) { return a + b; }\n}\n' },
            { path: 'math.php', content: '<?php\nfunction add($a, $b) {\n    return $a + $b;\n}\n' },
            { path: 'math.rb', content: 'def add(a, b)\n  a + b\nend\n' },
            { path: 'Calc.kt', content: 'fun add(a: Int, b: Int): Int {\n    return a + b\n}\n' },
            { path: 'Calc.swift', content: 'func add(_ a: Int, _ b: Int) -> Int {\n    return a + b\n}\n' },
        ];
        const r = scoreFilesAdherence(files);
        expect(r.score).toBe(1);
        expect(r.fullyAdherent).toBe(files.length);
    });
    it('flags a non-TS stub without judging it by TS-only rules', () => {
        const r = scoreFilesAdherence([
            { path: 'main.go', content: 'package main\n\nfunc main() {}\n// TODO: implement\n' },
        ]);
        expect(r.failures.not_stub).toBe(1);
        // TS-only check names never leak into a Go score.
        expect(r.failures.no_phantom_imports).toBeUndefined();
        expect(r.failures.no_jsx_in_ts).toBeUndefined();
    });
    it('ranks a real non-TS file above a stub (the loop can discriminate)', () => {
        const good = scoreFilesAdherence([
            { path: 'main.go', content: 'package main\n\nfunc Add(a int, b int) int { return a + b }\n' },
        ]);
        const bad = scoreFilesAdherence([
            { path: 'main.go', content: 'package main\n// TODO: implement\n' },
        ]);
        expect(good.score).toBeGreaterThan(bad.score);
    });
});
describe('imports_resolve (compiled-language wiring)', () => {
    it('Go: passes when an internal import names a directory that exists', () => {
        const r = scoreFilesAdherence([
            { path: 'main.go', content: 'package main\n\nimport "myapp/src/engine"\n\nfunc main() { engine.Run() }\n' },
            { path: 'src/engine/engine.go', content: 'package engine\n\nfunc Run() { println("hi") }\n' },
        ]);
        expect(r.failures.imports_resolve).toBeUndefined();
    });
    it('Go: fails when an internal import names a missing directory', () => {
        const r = scoreFilesAdherence([
            { path: 'main.go', content: 'package main\n\nimport "myapp/src/missing"\n\nfunc main() { println("hi") }\n' },
        ]);
        expect(r.failures.imports_resolve).toBe(1);
    });
    it('Rust: fails a dangling #[path] mod and passes a resolvable one', () => {
        const bad = scoreFilesAdherence([
            { path: 'main.rs', content: '#[path = "src/game/game.rs"]\nmod game;\n\nfn main() { println!("hi"); }\n' },
        ]);
        expect(bad.failures.imports_resolve).toBe(1);
        const good = scoreFilesAdherence([
            { path: 'main.rs', content: '#[path = "src/game/game.rs"]\nmod game;\n\nfn main() { println!("hi"); }\n' },
            { path: 'src/game/game.rs', content: 'pub fn run() { println!("hi"); }\n' },
        ]);
        expect(good.failures.imports_resolve).toBeUndefined();
    });
    it('Java: allows JDK imports, fails an import with no matching file', () => {
        const ok = scoreFilesAdherence([
            { path: 'Main.java', content: 'import java.util.Scanner;\npublic class Main { public static void main(String[] a) { new Scanner(System.in); } }\n' },
        ]);
        expect(ok.failures.imports_resolve).toBeUndefined();
        const bad = scoreFilesAdherence([
            { path: 'Main.java', content: 'import com.acme.Missing;\npublic class Main { public static void main(String[] a) { System.out.println(1); } }\n' },
        ]);
        expect(bad.failures.imports_resolve).toBe(1);
    });
    it('C#: allows System usings and declared namespaces, fails an undeclared one', () => {
        const ok = scoreFilesAdherence([
            { path: 'Program.cs', content: 'using System;\nclass Program { static void Main() { Console.WriteLine(1); } }\n' },
            { path: 'Lib.cs', content: 'namespace App.Lib { class Util { } }\n' },
            { path: 'App.cs', content: 'using App.Lib;\nclass App { static void Main() { System.Console.WriteLine(1); } }\n' },
        ]);
        expect(ok.failures.imports_resolve).toBeUndefined();
        const bad = scoreFilesAdherence([
            { path: 'Program.cs', content: 'using Acme.Missing;\nclass Program { static void Main() { Console.WriteLine(1); } }\n' },
        ]);
        expect(bad.failures.imports_resolve).toBe(1);
    });
});
function mkScored(id, metrics) {
    return { id, op: 'add_wiring', rationale: '', blueprint: base, metrics, score: scoreVariant(metrics), ok: true };
}
