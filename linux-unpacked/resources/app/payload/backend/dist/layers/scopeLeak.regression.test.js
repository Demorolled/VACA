import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'fs';
import { join } from 'path';
import { findScopeLeaks } from './fileGenerator.js';
const ROOT = join(__dirname, '..', '..', '..');
const SESSIONS = join(ROOT, 'data', 'teacher', 'sessions');
function sessionFile(seq, fileName) {
    const d = JSON.parse(readFileSync(join(SESSIONS, `${seq}.json`), 'utf-8'));
    const f = d.files.find((x) => x.fileName === fileName);
    if (!f)
        throw new Error(`missing ${fileName} in seq ${seq}`);
    return f.code;
}
describe('findScopeLeaks — real teacher-session regression', () => {
    it('catches the seq-8 checkers render-view (undeclared boardState/currentPlayer)', () => {
        const leaks = findScopeLeaks(sessionFile(8, 'render-view.ts'));
        expect(leaks.some((l) => l.includes('boardState'))).toBe(true);
        expect(leaks.some((l) => l.includes('currentPlayer'))).toBe(true);
    });
    it('catches the seq-12 stopwatch (timerInterval declared in a sibling handler)', () => {
        const leaks = findScopeLeaks(sessionFile(12, 'user-interface.ts'));
        expect(leaks.some((l) => l.includes('timerInterval'))).toBe(true);
    });
    it('catches the seq-13 tip-calculator inline onclick (module-local function)', () => {
        const leaks = findScopeLeaks(sessionFile(13, 'user-interface.ts'));
        expect(leaks.some((l) => l.includes('appendNumber') && l.includes('onclick'))).toBe(true);
    });
    it('stays clean on the teacher-fixed checkers render-view', () => {
        const fixed = '/tmp/checkers-render-view-fixed.ts';
        if (!existsSync(fixed))
            return; // only meaningful when the fix file exists
        expect(findScopeLeaks(readFileSync(fixed, 'utf-8'))).toEqual([]);
    });
    it('stays clean on the teacher-fixed checkers game-controller', () => {
        const fixed = '/tmp/checkers-game-controller-fixed.ts';
        if (!existsSync(fixed))
            return;
        expect(findScopeLeaks(readFileSync(fixed, 'utf-8'))).toEqual([]);
    });
    it('stays clean on the teacher-fixed stopwatch user-interface', () => {
        const fixed = '/tmp/sw-user-interface-fixed.ts';
        if (!existsSync(fixed))
            return;
        expect(findScopeLeaks(readFileSync(fixed, 'utf-8'))).toEqual([]);
    });
    it('stays clean on the teacher-fixed password-generator user-interface', () => {
        const fixed = '/tmp/pg-user-interface-fixed.ts';
        if (!existsSync(fixed))
            return;
        expect(findScopeLeaks(readFileSync(fixed, 'utf-8'))).toEqual([]);
    });
    it('stays clean on the teacher-fixed calculator user-interface', () => {
        const fixed = '/tmp/calc-user-interface-fixed.ts';
        if (!existsSync(fixed))
            return;
        expect(findScopeLeaks(readFileSync(fixed, 'utf-8'))).toEqual([]);
    });
    it('stays clean on the teacher-fixed tip-calculator user-interface', () => {
        const fixed = '/tmp/tip-user-interface-fixed.ts';
        if (!existsSync(fixed))
            return;
        expect(findScopeLeaks(readFileSync(fixed, 'utf-8'))).toEqual([]);
    });
    it('seq-14 data-store: flags convert() with sibling-module guidance, not value', () => {
        const code = sessionFile(14, 'data-store.ts');
        const ctx = {
            selfLabel: 'data_store',
            deps: ['input_handler'],
            allExports: new Map([
                ['core_engine', ['convert', 'getConversionRate']],
                ['input_handler', ['handleInput']],
                ['data_store', ['handleConversion', 'ConversionResult']],
            ]),
        };
        const leaks = findScopeLeaks(code, ctx);
        // The param `value` must NOT be a false positive (it is a function param).
        expect(leaks.some((l) => l.includes("'value'"))).toBe(false);
        // `convert` must be flagged as owned by a NON-dependency sibling.
        const convert = leaks.find((l) => l.includes("'convert'"));
        expect(convert).toBeTruthy();
        expect(convert).toContain('exported by core-engine.ts');
        expect(convert).toContain('CANNOT import it');
    });
    it('tells the model to import a name its dependency exports', () => {
        const code = `import { handleInput } from '../input-handler/input-handler.ts';
export function useIt(): void { handleSomething(); }`;
        const ctx = {
            selfLabel: 'data_store',
            deps: ['input_handler'],
            allExports: new Map([
                ['input_handler', ['handleInput', 'handleSomething']],
                ['data_store', ['useIt']],
            ]),
        };
        const leaks = findScopeLeaks(code, ctx);
        const hit = leaks.find((l) => l.includes('handleSomething'));
        expect(hit).toBeTruthy();
        expect(hit).toContain('IS exported by your dependency');
        expect(hit).toContain('WRITE the import for it');
    });
});
