/**
 * Planner write path — Python build end-to-end (real toolchain).
 *
 * A smaller companion to plannerGoE2E.test.ts: it drives the SAME chat
 * pipeline (`generatePlanFiles`, mocked LLM) for a Python plan and asserts the
 * shared whole-project gate (`python3 -m py_compile`) really compiles the
 * generated file. It is the cheap, always-available counterpart to the Go case
 * and guards the same class of bug — a language-agnostic deterministic pass
 * mangling language-specific source (e.g. the phantom-npm-import stripper once
 * deleting Go's `import "fmt"`).
 *
 * `python3` is used for the gate; the test self-skips if it is unavailable.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import fs from 'fs';
import path from 'path';
import { spawnSync } from 'child_process';
vi.mock('../ai/translator.js', () => {
    class AITranslator {
        async reason() {
            return JSON.stringify({
                files: [
                    {
                        path: 'main.py',
                        content: 'def main():\n    print("hello from vaca")\n\n\nif __name__ == "__main__":\n    main()\n',
                    },
                ],
            });
        }
        async reasonFast() { return ''; }
    }
    return {
        AITranslator,
        askOtherLlm: async () => '',
        askConductor: async () => '',
        classifyCodeComplexity: () => 'simple',
        ModelTier: {},
    };
});
import { generatePlanFiles } from './codePlanner.js';
const PY_REQUEST = 'Build a Python CLI that prints hello';
const PY_PLAN = {
    files: [{ path: 'main.py', summary: 'Python program entry point', language: 'python' }],
    questions: [],
};
function hasTool(bin) {
    try {
        return spawnSync(bin, ['--version'], { stdio: 'ignore' }).status === 0;
    }
    catch {
        return false;
    }
}
describe('planner write path — Python build end-to-end', () => {
    let exportDir;
    afterEach(() => {
        if (!exportDir)
            return;
        try {
            const exportsRoot = path.join(process.cwd(), 'exports');
            if (exportDir.startsWith(exportsRoot))
                fs.rmSync(exportDir, { recursive: true, force: true });
        }
        catch { /* best-effort */ }
        exportDir = undefined;
    });
    it.runIf(hasTool('python3'))('passes a REAL `python3 -m py_compile` for a generated Python plan', async () => {
        const res = await generatePlanFiles(PY_REQUEST, PY_PLAN, undefined, 20_000);
        expect(res, 'planner returned no result').not.toBeNull();
        exportDir = res?.exportDir;
        expect(res.files.some((f) => f.path === 'main.py' && f.content.includes('def main'))).toBe(true);
        const pyGate = (res.languageGates || []).find((g) => g.language === 'python');
        expect(pyGate, 'no Python language gate in the result').toBeDefined();
        expect(pyGate.clean, `py_compile failed: ${pyGate?.errors.join(' | ')}`).toBe(true);
        expect(res.stubFailures ?? []).toEqual([]);
    }, 60_000);
});
