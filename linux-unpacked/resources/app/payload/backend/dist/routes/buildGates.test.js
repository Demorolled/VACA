import { describe, it, expect, vi } from 'vitest';
import { buildWriteSummary, learnFromWrite } from './codePlanner.js';
import { NODE_TYPES, sanitizeNodes } from './architect.js';
import { PLAN_NODE_TYPES } from '../types.js';
import { sanitizeGoModuleName, runNonTsProjectGates, resolveGateLanguage, GATE_LANGUAGES, TOOLCHAINS, toolchainBin, detectToolchains } from '../sandbox/nonTsCompileGate.js';
import { learningEngine } from '../knowledge/learningEngine.js';
// ─────────────────────────────────────────────────────────────────────────
// buildWriteSummary — F3 (non-TS gate) + F5/F6/F11 (stub) + no-gate honesty
// ─────────────────────────────────────────────────────────────────────────
describe('buildWriteSummary — honest verdicts for the new gates', () => {
    const base = { successCount: 1, remainingTsc: 0, modeSuffix: '', fallbackNote: '' };
    it('⚠️ when a non-TS whole-project gate FAILED (tsc was blind to it)', () => {
        const s = buildWriteSummary({
            ...base,
            compileStatus: 'skipped',
            languageGates: [{ language: 'go', clean: false, errors: ['malformed import path "a 3d chess game": invalid char \' \''] }],
        });
        expect(s.startsWith('⚠️ Wrote 1 file — go compile gate FAILED')).toBe(true);
        expect(s).not.toContain('✅');
    });
    it('⚠️ when a stub/placeholder body shipped', () => {
        const s = buildWriteSummary({ ...base, compileStatus: 'skipped', stubFailures: ['src/main.go'] });
        expect(s).toContain('stub/placeholder file(s)');
        expect(s).not.toContain('✅');
    });
    it('⚠️ "compile NOT verified" when no gate ran (skipped + no smoke)', () => {
        const s = buildWriteSummary({ ...base, compileStatus: 'skipped' });
        expect(s).toContain('compile NOT verified');
        expect(s).not.toContain('✅');
    });
    it('✅ when the tsc gate is clean', () => {
        expect(buildWriteSummary({ ...base, compileStatus: 'clean' })).toBe('✅ Wrote 1 file successfully');
    });
    it('✅ when tsc is skipped but a behavioral smoke PASSED (single-file HTML)', () => {
        const s = buildWriteSummary({ ...base, compileStatus: 'skipped', renderSmoke: { status: 'passed', errors: [], detail: 'playable' } });
        expect(s).toBe('✅ Wrote 1 file successfully');
    });
    it('✅ when a non-TS gate ran and is clean', () => {
        const s = buildWriteSummary({ ...base, compileStatus: 'skipped', languageGates: [{ language: 'python', clean: true, errors: [] }] });
        expect(s).toBe('✅ Wrote 1 file successfully');
    });
});
// ─────────────────────────────────────────────────────────────────────────
// learnFromWrite — the self-poisoning window is closed: "not failed" ≠ "verified"
// ─────────────────────────────────────────────────────────────────────────
describe('learnFromWrite — unverified output never teaches the store', () => {
    const written = [{
            path: 'index.html',
            content: '<!DOCTYPE html><html><body><div id="b"></div><script>const b = document.getElementById("b");</script></body></html>',
            status: 'written',
        }];
    it('skips when the smoke gate NEVER RAN (unavailable box — the poisoning window)', () => {
        const spy = vi.spyOn(learningEngine, 'learnFromFiles').mockReturnValue([]);
        try {
            // compileStatus 'skipped' (HTML app), no language gates, no passed smoke.
            learnFromWrite('/tmp/export-test', 'build a checkers game', written, { compileStatus: 'skipped', remainingTsc: 0 });
            expect(spy).not.toHaveBeenCalled();
        }
        finally {
            spy.mockRestore();
        }
    });
    it('skips when a non-TS language gate FAILED', () => {
        const spy = vi.spyOn(learningEngine, 'learnFromFiles').mockReturnValue([]);
        try {
            learnFromWrite('/tmp/export-test', 'build a go cli', written, {
                compileStatus: 'skipped',
                remainingTsc: 0,
                languageGates: [{ language: 'go', clean: false, errors: ['boom'] }],
            });
            expect(spy).not.toHaveBeenCalled();
        }
        finally {
            spy.mockRestore();
        }
    });
    it('skips when a stub body was detected', () => {
        const spy = vi.spyOn(learningEngine, 'learnFromFiles').mockReturnValue([]);
        try {
            learnFromWrite('/tmp/export-test', 'build a todo app', written, {
                compileStatus: 'clean',
                remainingTsc: 0,
                stubFailures: ['src/main.ts'],
            });
            expect(spy).not.toHaveBeenCalled();
        }
        finally {
            spy.mockRestore();
        }
    });
    it('learns when the tsc gate is clean', () => {
        const spy = vi.spyOn(learningEngine, 'learnFromFiles').mockReturnValue([]);
        try {
            learnFromWrite('/tmp/export-test', 'build a todo app', written, { compileStatus: 'clean', remainingTsc: 0 });
            expect(spy).toHaveBeenCalledTimes(1);
        }
        finally {
            spy.mockRestore();
        }
    });
    it('learns when a clean non-TS gate vouches for a Go build', () => {
        const spy = vi.spyOn(learningEngine, 'learnFromFiles').mockReturnValue([]);
        try {
            learnFromWrite('/tmp/export-test', 'build a go cli', written, {
                compileStatus: 'skipped',
                remainingTsc: 0,
                languageGates: [{ language: 'go', clean: true, errors: [] }],
            });
            expect(spy).toHaveBeenCalledTimes(1);
        }
        finally {
            spy.mockRestore();
        }
    });
});
// ─────────────────────────────────────────────────────────────────────────
// Node-type vocabulary — one canonical list, no drift
// ─────────────────────────────────────────────────────────────────────────
describe('node-type vocabulary is unified', () => {
    it('architect NODE_TYPES equals the canonical PLAN_NODE_TYPES set', () => {
        expect([...NODE_TYPES].sort()).toEqual([...PLAN_NODE_TYPES].sort());
    });
    it('sanitizeNodes accepts the extended file-node types (gui-layout, ui-functions)', () => {
        const out = sanitizeNodes([
            { label: 'layout', description: 'x', type: 'gui-layout', language: 'typescript' },
            { label: 'controls', description: 'x', type: 'ui-functions', language: 'typescript' },
        ]);
        expect(out[0].type).toBe('gui-layout');
        expect(out[1].type).toBe('ui-functions');
    });
    it('sanitizeNodes still coerces an unknown type to logic', () => {
        expect(sanitizeNodes([{ label: 'x', description: '', type: 'wat', language: 'typescript' }])[0].type).toBe('logic');
    });
});
// ─────────────────────────────────────────────────────────────────────────
// Shared non-TS gate helpers
// ─────────────────────────────────────────────────────────────────────────
describe('sanitizeGoModuleName', () => {
    it('slugifies a raw project title (no spaces/commas)', () => {
        expect(sanitizeGoModuleName('A 3D chess game, with pieces!')).toBe('a-3d-chess-game-with-pieces');
    });
    it('falls back to untitled', () => {
        expect(sanitizeGoModuleName('!!!')).toBe('untitled');
    });
});
describe('runNonTsProjectGates', () => {
    it('returns no gates when there are no gateable files (zero cost for TS/HTML)', async () => {
        expect(await runNonTsProjectGates([{ relPath: 'src/a.ts', code: 'export const x = 1;', language: 'typescript' }], 'm')).toEqual([]);
    });
});
/**
 * Whether the GATE can resolve a language's toolchain. Uses the gate's own
 * `toolchainBin` (not PATH-only `hasTool`) so a toolchain installed into a
 * non-login dir (rustup `~/.cargo/bin`, swiftly `~/.local/share/swiftly/bin`,
 * `/snap/bin`) is correctly seen — otherwise these real-toolchain tests skip
 * on exactly the boxes where the toolchain IS available.
 */
const hasGateTool = (lang) => {
    const spec = TOOLCHAINS[lang];
    return !!spec && toolchainBin(lang) !== spec.bins[0];
};
describe('runNonTsProjectGates — real toolchain (self-skipping)', () => {
    it.runIf(hasGateTool('c'))('C gate: clean for valid code, failed for broken code', async () => {
        const good = await runNonTsProjectGates([{ relPath: 'main.c', code: '#include <stdio.h>\nint main(void){ printf("hi"); return 0; }\n', language: 'c' }], 'm');
        expect(good).toHaveLength(1);
        expect(good[0]).toMatchObject({ language: 'c', clean: true });
        const bad = await runNonTsProjectGates([{ relPath: 'main.c', code: 'int main(void){ return 0; }}\nextra\n', language: 'c' }], 'm');
        expect(bad[0].clean).toBe(false);
        expect(bad[0].errors.length).toBeGreaterThan(0);
    }, 60_000);
    it.runIf(hasGateTool('python'))('Python gate: clean for valid code, failed for broken code', async () => {
        const good = await runNonTsProjectGates([{ relPath: 'main.py', code: 'def f():\n    return 1\n\nif __name__ == "__main__":\n    f()\n', language: 'python' }], 'm');
        expect(good[0]).toMatchObject({ language: 'python', clean: true });
        const bad = await runNonTsProjectGates([{ relPath: 'main.py', code: 'def f(:\n    return 1\n', language: 'python' }], 'm');
        expect(bad[0].clean).toBe(false);
    }, 60_000);
    // The canvas path gates NODE files only; the scaffolder writes the entry
    // point afterwards. Without `scaffoldSuppliesEntry` a file set of pure
    // declarations is rejected as a library — measured live on a generated Swift
    // app that `swiftc` built and ran (exit 0) while the gate said otherwise.
    it.runIf(hasGateTool('python'))('entry-point fold is skipped when the scaffolder supplies the entry', async () => {
        const declarationsOnly = [{ relPath: 'src/store/store.py', code: 'def helper():\n    return 1\n', language: 'python' }];
        const gated = await runNonTsProjectGates(declarationsOnly, 'm');
        expect(gated[0].clean).toBe(false);
        expect(gated[0].errors.join(' ')).toContain('no runnable entry point');
        const scaffoldEntry = await runNonTsProjectGates(declarationsOnly, 'm', { scaffoldSuppliesEntry: true });
        expect(scaffoldEntry[0]).toMatchObject({ language: 'python', clean: true });
    }, 60_000);
    it.runIf(hasGateTool('cpp'))('C++ gate: clean for valid C++17, failed for broken code', async () => {
        const good = await runNonTsProjectGates([{ relPath: 'main.cpp', code: '#include <iostream>\nint main(){ std::cout << "hi"; return 0; }\n', language: 'cpp' }], 'm');
        expect(good[0]).toMatchObject({ language: 'cpp', clean: true });
        const bad = await runNonTsProjectGates([{ relPath: 'main.cpp', code: 'int main() { this is not c++ }\n', language: 'cpp' }], 'm');
        expect(bad[0].clean).toBe(false);
    }, 60_000);
    it.runIf(hasGateTool('rust'))('Rust gate: clean for valid code, failed for broken code', async () => {
        const good = await runNonTsProjectGates([{ relPath: 'main.rs', code: 'use std::io::{self, Read};\nfn main() { let mut s = String::new(); io::stdin().read_to_string(&mut s).unwrap(); println!("{}", s.len()); }\n', language: 'rust' }], 'm');
        expect(good[0]).toMatchObject({ language: 'rust', clean: true });
        const bad = await runNonTsProjectGates([{ relPath: 'main.rs', code: 'fn main( { let x = ; }\n', language: 'rust' }], 'm');
        expect(bad[0].clean).toBe(false);
    }, 120_000);
    it.runIf(hasGateTool('java'))('Java gate: clean for valid code, failed for broken code', async () => {
        const good = await runNonTsProjectGates([{ relPath: 'Main.java', code: 'import java.util.Scanner;\npublic class Main { public static void main(String[] a){ Scanner s = new Scanner(System.in); System.out.println(s.hasNextLine()); } }\n', language: 'java' }], 'm');
        expect(good[0]).toMatchObject({ language: 'java', clean: true });
        const bad = await runNonTsProjectGates([{ relPath: 'Main.java', code: 'public class Main { void x() { int = ; } }\n', language: 'java' }], 'm');
        expect(bad[0].clean).toBe(false);
    }, 120_000);
    it.runIf(hasGateTool('swift'))('Swift gate: clean for valid code, failed for broken code', async () => {
        const good = await runNonTsProjectGates([{ relPath: 'Main.swift', code: 'import Foundation\nprint("hello")\n', language: 'swift' }], 'm');
        expect(good[0]).toMatchObject({ language: 'swift', clean: true });
        const bad = await runNonTsProjectGates([{ relPath: 'Main.swift', code: 'let x = \n', language: 'swift' }], 'm');
        expect(bad[0].clean).toBe(false);
    }, 180_000);
    it.runIf(hasGateTool('kotlin'))('Kotlin gate: clean for valid code, failed for broken code', async () => {
        const good = await runNonTsProjectGates([{ relPath: 'Main.kt', code: 'fun main() { println("hi") }\n', language: 'kotlin' }], 'm');
        expect(good[0]).toMatchObject({ language: 'kotlin', clean: true });
        const bad = await runNonTsProjectGates([{ relPath: 'Main.kt', code: 'fun main( { }\n', language: 'kotlin' }], 'm');
        expect(bad[0].clean).toBe(false);
    }, 180_000);
    it.runIf(hasGateTool('csharp'))('C# gate: clean for valid code, failed for broken code', async () => {
        // Regression: toolchainBin returns an ABSOLUTE dotnet path, so the gate must
        // detect dotnet by basename. A bare-name check ran `dotnet -target:library`
        // and failed every valid project with "Could not execute …".
        const good = await runNonTsProjectGates([{ relPath: 'Program.cs', code: 'using System;\nclass Program { static void Main() { Console.WriteLine("hi"); } }\n', language: 'csharp' }], 'm');
        expect(good[0]).toMatchObject({ language: 'csharp', clean: true });
        const bad = await runNonTsProjectGates([{ relPath: 'Program.cs', code: 'class Program { static void Main() { int x = ; } }\n', language: 'csharp' }], 'm');
        expect(bad[0].clean).toBe(false);
        expect(bad[0].errors.length).toBeGreaterThan(0);
    }, 180_000);
    it('rejects a build that compiles but has NO runnable entry point', async () => {
        // A Python file of bare functions parses (py_compile passes) but cannot be
        // run — the exact fragment the dry run produced for a "Python CLI" request.
        // The entry gate must fail it even when the compile gate is clean.
        const gates = await runNonTsProjectGates([{ relPath: 'main.py', code: 'def check(s):\n    return s == s[::-1]\n', language: 'python' }], 'm');
        const py = gates.find((g) => g.language === 'python');
        expect(py?.clean).toBe(false);
        expect(py?.errors.join(' ')).toMatch(/no runnable entry point/i);
    });
    it('accepts a script language once a top-level entry statement exists', async () => {
        const gates = await runNonTsProjectGates([{ relPath: 'index.php', code: '<?php\nfunction parse($p) { return [$p]; }\nforeach (parse("x") as $r) { echo $r; }\n', language: 'php' }], 'm');
        // PHP is only checked when the toolchain is present; otherwise the gate is an
        // honest unavailable-failure and the entry error is not the reason.
        const php = gates.find((g) => g.language === 'php');
        if (php && php.clean)
            expect(php.errors).toEqual([]);
    });
    it('an unavailable toolchain is a FAILED gate, never a silent pass', async () => {
        // A language with no toolchain on essentially any CI box.
        const gates = await runNonTsProjectGates([{ relPath: 'App.swift', code: 'let x = 1\n', language: 'swift' }], 'm');
        expect(gates).toHaveLength(1);
        if (!hasGateTool('swift')) {
            expect(gates[0].clean).toBe(false);
            expect(gates[0].errors[0]).toContain('not installed');
        }
    });
});
describe('toolchain detection + platform-aware binary resolution', () => {
    it('every gate language has a toolchain spec with install hints for Windows + Linux', () => {
        for (const lang of GATE_LANGUAGES) {
            const spec = TOOLCHAINS[lang];
            expect(spec.bins.length).toBeGreaterThan(0);
            expect(spec.install.linux.length).toBeGreaterThan(0);
            expect(spec.install.windows.length).toBeGreaterThan(0);
        }
    });
    it('toolchainBin resolves to a path whose basename is one of the candidate binaries', () => {
        for (const lang of GATE_LANGUAGES) {
            const resolved = toolchainBin(lang);
            const base = resolved.split(/[\\/]/).pop() || '';
            expect(TOOLCHAINS[lang].bins.some((b) => base === b || base === `${b}.exe`)).toBe(true);
        }
    });
    it('detectToolchains reports a status for every language (available or not)', async () => {
        const statuses = await detectToolchains();
        expect(statuses.map((s) => s.language).sort()).toEqual([...GATE_LANGUAGES].sort());
        for (const s of statuses) {
            expect(typeof s.available).toBe('boolean');
            expect(s.bin.length).toBeGreaterThan(0);
            expect(s.version.length).toBeGreaterThan(0);
        }
    });
});
describe('resolveGateLanguage — one mapping for every gateable language', () => {
    it('covers every requested language', () => {
        for (const lang of ['rust', 'c', 'cpp', 'java', 'csharp', 'swift', 'kotlin', 'php', 'ruby', 'go', 'python']) {
            expect(GATE_LANGUAGES).toContain(lang);
        }
    });
    it('maps extensions when the declared language is missing', () => {
        expect(resolveGateLanguage(undefined, 'src/main.rs')).toBe('rust');
        expect(resolveGateLanguage(undefined, 'main.c')).toBe('c');
        expect(resolveGateLanguage(undefined, 'main.cpp')).toBe('cpp');
        expect(resolveGateLanguage(undefined, 'Main.java')).toBe('java');
        expect(resolveGateLanguage(undefined, 'Program.cs')).toBe('csharp');
        expect(resolveGateLanguage(undefined, 'App.swift')).toBe('swift');
        expect(resolveGateLanguage(undefined, 'Main.kt')).toBe('kotlin');
        expect(resolveGateLanguage(undefined, 'index.php')).toBe('php');
        expect(resolveGateLanguage(undefined, 'app.rb')).toBe('ruby');
    });
    it('normalizes aliases', () => {
        expect(resolveGateLanguage('golang', 'x.go')).toBe('go');
        expect(resolveGateLanguage('c++', 'x')).toBe('cpp');
        expect(resolveGateLanguage('C#', 'x')).toBe('csharp');
        expect(resolveGateLanguage('py', 'x')).toBe('python');
        expect(resolveGateLanguage('rs', 'x')).toBe('rust');
    });
    it('trusts a declared language over a mismatched extension', () => {
        expect(resolveGateLanguage('rust', 'src/main.rs')).toBe('rust');
    });
    it('returns null for languages this module does not gate', () => {
        expect(resolveGateLanguage('typescript', 'a.ts')).toBeNull();
        expect(resolveGateLanguage(undefined, 'index.html')).toBeNull();
        expect(resolveGateLanguage(undefined, 'styles.css')).toBeNull();
    });
});
