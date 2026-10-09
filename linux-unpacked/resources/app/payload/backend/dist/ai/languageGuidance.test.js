import { describe, it, expect } from 'vitest';
import { languageGuidanceBlock } from './languageGuidance.js';
describe('languageGuidanceBlock', () => {
    it('gives Rust stdlib-only, main(), and no-crate guidance', () => {
        const b = languageGuidanceBlock('rust');
        expect(b).toContain('LANGUAGE GUIDANCE (Rust');
        expect(b).toContain('no external crates');
        expect(b).toContain('fn main()');
    });
    it('warns Java off System.console() and names the file-name rule', () => {
        const b = languageGuidanceBlock('java');
        expect(b).toContain('System.console()');
        expect(b).toContain('file name');
    });
    it('normalizes aliases (c++, c#, py, golang, rs)', () => {
        expect(languageGuidanceBlock('c++')).toContain('C++17');
        expect(languageGuidanceBlock('c#')).toContain('C#');
        expect(languageGuidanceBlock('py')).toContain('Python');
        expect(languageGuidanceBlock('golang')).toContain('Go 1.21');
        expect(languageGuidanceBlock('rs')).toContain('Rust');
    });
    it('is empty for an unknown or missing language', () => {
        expect(languageGuidanceBlock('brainfuck')).toBe('');
        expect(languageGuidanceBlock(undefined)).toBe('');
    });
    it('injects the Go module path so internal imports resolve under go build', () => {
        const b = languageGuidanceBlock('go', { goModuleName: 'my-app' });
        expect(b).toContain('module my-app');
        expect(b).toContain('my-app/internal/foo');
        expect(b).toContain('rejects it');
        // Only Go gets the module line.
        expect(languageGuidanceBlock('rust', { goModuleName: 'my-app' })).not.toContain('module my-app');
        // No module name → no module line (back-compat).
        expect(languageGuidanceBlock('go')).not.toContain('go.mod declares');
    });
});
