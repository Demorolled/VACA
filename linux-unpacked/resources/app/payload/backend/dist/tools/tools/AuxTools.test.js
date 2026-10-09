import { describe, it, expect } from 'vitest';
import { countReviewFindings, resolveGitRoot } from './AuxTools.js';
import { mkdtempSync, writeFileSync, mkdirSync, rmSync, existsSync } from 'fs';
import { join, resolve } from 'path';
import { tmpdir } from 'os';
describe('countReviewFindings', () => {
    it('counts numbered findings (1. style)', () => {
        const review = [
            '1. **Security: Input validation missing (Critical)**',
            '   Line 4: add(1) called with one argument',
            '2. **Style: Magic number (Minor)**',
            '   Fix: extract a named constant',
        ].join('\n');
        expect(countReviewFindings(review)).toBe(2);
    });
    it('counts numbered findings with bracket severity (1) style)', () => {
        const review = [
            '1) [Minor] Generic function name',
            '2) [Major] No error handling',
        ].join('\n');
        expect(countReviewFindings(review)).toBe(2);
    });
    it('counts bullet findings when there is no numbered list', () => {
        const review = [
            '- Missing null check',
            '- Unhandled promise rejection',
            '• Hardcoded secret in config',
        ].join('\n');
        expect(countReviewFindings(review)).toBe(3);
    });
    it('returns 0 for prose-only output instead of a misleading count', () => {
        const review = 'The code looks fine overall. Minor improvements could be made to naming conventions.';
        expect(countReviewFindings(review)).toBe(0);
    });
    it('prefers the numbered count when fix blocks contain bullets', () => {
        const review = [
            '1. **Bug: crash on empty input**',
            '   Fix:',
            '   - Add a guard clause',
            '   - Return early',
            '2. **Perf: O(n^2) loop**',
            '   - Use a hash map instead',
        ].join('\n');
        expect(countReviewFindings(review)).toBe(2);
    });
    it('counts "Finding N:" / "Issue N:" labels when no list markers exist', () => {
        const review = [
            'Finding 1: Buffer overflow in parse()',
            'Issue 2: Unclosed connection leaked',
        ].join('\n');
        expect(countReviewFindings(review)).toBe(2);
    });
    it('does not miscount decimals/version numbers inside fix code blocks', () => {
        const review = [
            '1. **Bug: off-by-one in loop**',
            '   Fix:',
            '   ```javascript',
            '   const ratio = 0.5;',
            '   const pi = 3.14;',
            '   const v = 1.2;',
            '   ```',
        ].join('\n');
        expect(countReviewFindings(review)).toBe(1);
    });
    it('ignores decimal lines when no real numbered list exists', () => {
        const review = [
            'The ratio is 0.5 and the version is 1.2. No findings were formatted as a list here.',
        ].join('\n');
        expect(countReviewFindings(review)).toBe(0);
    });
});
describe('resolveGitRoot', () => {
    it('returns an explicit path unchanged', () => {
        expect(resolveGitRoot('/some/explicit/path')).toBe('/some/explicit/path');
    });
    it('walks up from the server CWD to the nearest repo root', () => {
        const root = resolveGitRoot();
        expect(root).toBeTruthy();
        expect(existsSync(join(root, '.git'))).toBe(true);
    });
    it('finds a repo above a deeply nested directory', () => {
        const tmp = mkdtempSync(join(tmpdir(), 'vaca-gitroot-'));
        mkdirSync(join(tmp, 'repo', 'a', 'b'), { recursive: true });
        writeFileSync(join(tmp, 'repo', '.git'), 'gitdir placeholder');
        const originalCwd = process.cwd();
        process.chdir(join(tmp, 'repo', 'a', 'b'));
        try {
            expect(resolveGitRoot()).toBe(resolve(join(tmp, 'repo')));
        }
        finally {
            process.chdir(originalCwd);
            rmSync(tmp, { recursive: true, force: true });
        }
    });
});
