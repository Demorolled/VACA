import { describe, it, expect } from 'vitest';
import { execFileSync } from 'child_process';
import { runSandbox } from './dockerRunner.js';
const has = (bin, args = ['--version']) => {
    try {
        execFileSync(bin, args, { stdio: 'ignore' });
        return true;
    }
    catch {
        return false;
    }
};
const hasGcc = has('gcc');
describe('local sandbox validation is honest about what it can check', () => {
    it('reports a language it has no checker for as SKIPPED — never as broken', async () => {
        // Kotlin has no local single-file checker here. The old code fell back to
        // the TypeScript config, wrote the Kotlin source to `index.ts` and returned
        // a wall of TS1005 "errors" for a file tsc cannot read.
        const res = await runSandbox('fun main() { println("hi") }', 'kotlin');
        expect(res.skipped).toBe(true);
        expect(res.errors).toEqual([]);
        expect(res.reason).toContain('kotlin');
    });
    it.skipIf(!hasGcc)('checks C with the real C compiler, and its diagnostics are C diagnostics', async () => {
        const ok = await runSandbox('#include <stdio.h>\nint main(void) { printf("hi\\n"); return 0; }\n', 'c');
        expect(ok.success).toBe(true);
        expect(ok.errors).toEqual([]);
        const bad = await runSandbox('int main(void) { return 0\n', 'c');
        expect(bad.success).toBe(false);
        const text = bad.errors.join('\n');
        expect(text).toMatch(/error/i);
        // The regression this guards: non-TS files were compiled by tsc and
        // reported TS-code diagnostics that had nothing to do with the source.
        expect(text).not.toMatch(/TS\d{4}/);
        expect(text).not.toContain('index.ts');
    });
    it('never stages a non-TS file under a TypeScript entry name', async () => {
        const res = await runSandbox('int main(void) { return 0; }\n', 'c');
        expect(res.output).not.toContain('.ts');
        expect((res.errors || []).join('\n')).not.toContain('.ts');
    });
});
