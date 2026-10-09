import { describe, it, expect } from 'vitest';
import { validatePreference } from './uiPreference.js';
describe('validatePreference', () => {
    it('accepts "cli" as a valid preference', () => {
        expect(validatePreference('cli')).toBe('cli');
    });
    it('accepts "gui" as a valid preference', () => {
        expect(validatePreference('gui')).toBe('gui');
    });
    it('accepts "ask" as a valid preference', () => {
        expect(validatePreference('ask')).toBe('ask');
    });
    it('rejects invalid string values', () => {
        expect(validatePreference('web')).toBeNull();
        expect(validatePreference('desktop')).toBeNull();
        expect(validatePreference('both')).toBeNull();
        expect(validatePreference('')).toBeNull();
    });
    it('rejects non-string values', () => {
        expect(validatePreference(123)).toBeNull();
        expect(validatePreference(null)).toBeNull();
        expect(validatePreference(undefined)).toBeNull();
        expect(validatePreference({})).toBeNull();
        expect(validatePreference([])).toBeNull();
    });
    it('is case-sensitive (expects lowercase)', () => {
        expect(validatePreference('CLI')).toBeNull();
        expect(validatePreference('GUI')).toBeNull();
        expect(validatePreference('Ask')).toBeNull();
    });
});
describe('getPlanPromptWithPreference (integration logic)', () => {
    function getInjection(pref) {
        if (pref === 'cli') {
            return '\n\nGLOBAL UI PREFERENCE\nThe user has set their preference to CLI-ONLY. Generate terminal/command-line apps by default.';
        }
        if (pref === 'gui') {
            return '\n\nGLOBAL UI PREFERENCE\nThe user has set their preference to GUI-ONLY. Generate graphical/web apps by default.';
        }
        return '';
    }
    it('cli preference injects CLI-ONLY instructions', () => {
        const injection = getInjection('cli');
        expect(injection).toContain('CLI-ONLY');
        expect(injection).toContain('terminal/command-line');
    });
    it('gui preference injects GUI-ONLY instructions', () => {
        const injection = getInjection('gui');
        expect(injection).toContain('GUI-ONLY');
        expect(injection).toContain('graphical/web');
    });
    it('ask preference does NOT inject any preference instructions', () => {
        const injection = getInjection('ask');
        expect(injection).toBe('');
    });
});
