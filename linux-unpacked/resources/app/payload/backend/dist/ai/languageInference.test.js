import { describe, it, expect } from 'vitest';
import { inferLanguageForGoal, inferDomainKind, detectExplicitLanguage, normalizeNodeLanguage, normalizeClientSideLanguages, } from './languageInference.js';
describe('inferLanguageForGoal — the countdown-timer→main.go fix', () => {
    it('plans a web app as TypeScript even when targetOS defaults to linux', () => {
        expect(inferLanguageForGoal('a simple countdown timer web app', 'A minimal browser-based countdown timer', 'linux')).toBe('typescript');
    });
    it('plans games as TypeScript', () => {
        expect(inferLanguageForGoal('a tic-tac-toe game', 'two player browser game', 'linux')).toBe('typescript');
    });
    it('plans web pages/dashboards/widgets as TypeScript', () => {
        for (const goal of ['a landing page for a startup', 'a weather dashboard', 'a pomodoro timer widget', 'an online store']) {
            expect(inferLanguageForGoal(goal, '', 'linux')).toBe('typescript');
        }
    });
    it('plans CLI tools as TypeScript (not Go)', () => {
        expect(inferLanguageForGoal('a command line todo list manager', 'CLI app', 'linux')).toBe('typescript');
        expect(inferLanguageForGoal('a terminal expense tracker', 'CLI tool', 'linux')).toBe('typescript');
    });
    it('keeps native languages for explicit OS targets without web/CLI keywords', () => {
        expect(inferLanguageForGoal('a file organizer', '', 'windows')).toBe('csharp');
        expect(inferLanguageForGoal('a system tray app', '', 'mac')).toBe('swift');
        expect(inferLanguageForGoal('a background daemon', '', 'linux')).toBe('go');
    });
    it('respects an explicit user language over the domain', () => {
        expect(inferLanguageForGoal('a todo list in Go', '', 'linux')).toBe('go');
        expect(inferLanguageForGoal('a countdown timer web app in Python', '', 'linux')).toBe('python');
    });
    it('does not misread "go" inside common phrases', () => {
        expect(inferLanguageForGoal('lets go build a todo app', '', 'linux')).toBe('typescript');
        expect(inferLanguageForGoal('a goal tracker app', '', 'linux')).toBe('go');
    });
    it('respects a global CLI-only UI preference', () => {
        expect(inferLanguageForGoal('a weather app', '', 'linux', 'cli')).toBe('typescript');
        expect(inferDomainKind('a weather app', '', 'cli')).toBe('cli');
    });
    it('falls back to the OS language for unknown text', () => {
        expect(inferLanguageForGoal('a batch file renamer utility', '', 'windows')).toBe('csharp');
        expect(inferLanguageForGoal('a file renamer utility', '', 'linux')).toBe('go');
    });
});
describe('detectExplicitLanguage', () => {
    it('detects named languages in goal and purpose', () => {
        expect(detectExplicitLanguage('a REST API in Rust', '')).toBe('rust');
        expect(detectExplicitLanguage('a scraper', 'using Python')).toBe('python');
        expect(detectExplicitLanguage('a c# console tool', '')).toBe('csharp');
    });
    it('returns null when no language is named', () => {
        expect(detectExplicitLanguage('a todo app', '')).toBeNull();
    });
});
describe('normalizeNodeLanguage', () => {
    it('keeps supported languages and natural formats', () => {
        expect(normalizeNodeLanguage('go', 'typescript')).toBe('go');
        expect(normalizeNodeLanguage('html', 'typescript')).toBe('html');
        expect(normalizeNodeLanguage('typescript', 'typescript')).toBe('typescript');
    });
    it('normalizes aliases', () => {
        expect(normalizeNodeLanguage('ts', 'go')).toBe('typescript');
        expect(normalizeNodeLanguage('py', 'typescript')).toBe('python');
    });
    it('collapses unknown/typo languages to the inferred language', () => {
        expect(normalizeNodeLanguage('pyton', 'typescript')).toBe('typescript');
        expect(normalizeNodeLanguage('jsx', 'go')).toBe('go');
        expect(normalizeNodeLanguage(undefined, 'go')).toBe('go');
    });
});
describe('normalizeClientSideLanguages', () => {
    it('forces every coding file of a browser app to TypeScript', () => {
        expect(normalizeClientSideLanguages(['go', 'python', 'typescript', 'html', 'css'])).toEqual([
            'typescript', 'typescript', 'typescript', 'html', 'css',
        ]);
    });
});
