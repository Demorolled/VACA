import { describe, it, expect } from 'vitest';
import { isStubBody } from './qualityGate.js';
describe('isStubBody — the F5 gate: stub/TODO bodies never ship as validated', () => {
    it('rejects markdown fences smuggled into code', () => {
        expect(isStubBody('```typescript\nexport const x = 1;\n```')).toBe(true);
    });
    it('rejects batched-response separators', () => {
        expect(isStubBody('---\nexport const x = 1;\n---\nexport const y = 2;')).toBe(true);
    });
    it('rejects prompt scaffolding echoed into the file', () => {
        expect(isStubBody('REAL FILE CONTENT\nexport const x = 1;')).toBe(true);
    });
    it('rejects stub/placeholder/not-implemented bodies', () => {
        expect(isStubBody('// TODO: implement\nfunction f() {}')).toBe(true);
        expect(isStubBody('function f() { throw new Error("not implemented"); }')).toBe(true);
        expect(isStubBody('// auto-generated placeholder')).toBe(true);
    });
    it('rejects ANY TODO/FIXME/XXX comment in a body (not just "TODO: Implement")', () => {
        expect(isStubBody('class Game { void play() { board.printBoard(); // TODO: Game loop logic\n } }')).toBe(true);
        expect(isStubBody('function f() {\n  // FIXME later\n  return compute();\n}')).toBe(true);
    });
    it('rejects a method whose body is a single placeholder return', () => {
        expect(isStubBody('class Board { boolean checkWin(char p) {\n  // check rows\n  return false;\n} }')).toBe(true);
        expect(isStubBody('public boolean isEmpty() { return true; }')).toBe(true);
        // ...but a real trivial getter returning a VALUE is fine.
        expect(isStubBody('class P { char getMark() { return mark; } }')).toBe(false);
        // ...and an if-block that returns false is NOT a placeholder body.
        expect(isStubBody('boolean f(int x) {\n  if (x < 0) { return false; }\n  return compute(x);\n}')).toBe(false);
    });
    it('rejects empty bodies and empty comment-only bodies', () => {
        expect(isStubBody('')).toBe(true);
        expect(isStubBody('  \n// nothing here yet\n')).toBe(true);
    });
    it('accepts real generated code', () => {
        expect(isStubBody('export class Timer {\n  start(): void { this.running = true; }\n}\n')).toBe(false);
    });
    it('accepts one-statement functions (NOT stubs) — Go + JS regression', () => {
        // The empty-body heuristic used to match any brace-free body, falsely
        // rejecting real code — a valid Go program failed the planner's stub gate.
        expect(isStubBody('func main() { fmt.Println("hi") }')).toBe(false);
        expect(isStubBody('function add(a, b) { return a + b; }')).toBe(false);
        // ...but a genuinely empty body is still a stub.
        expect(isStubBody('func main() {}')).toBe(true);
    });
});
