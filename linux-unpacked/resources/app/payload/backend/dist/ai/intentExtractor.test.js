import { describe, it, expect } from 'vitest';
import { extractIntent, formatIntentSection, isLowConfidenceIntent, mergeIntentSpecs } from './intentExtractor.js';
describe('extractIntent', () => {
    it('extracts goal/features/language for the chess request', () => {
        const s = extractIntent('make a complete chess game with an AI player and drag and drop pieces');
        expect(s.goal).toContain('chess game');
        expect(s.goal).toContain('AI player');
        expect(s.coreFeatures).toContain('AI opponent');
        expect(s.coreFeatures).toContain('drag-and-drop');
        expect(s.uiStyle).toContain('game');
    });
    it('strips politeness and "make me a" fillers', () => {
        const s = extractIntent('can you please build me a todo app for my family');
        expect(s.goal).toBe('todo app for my family');
        expect(s.targetUser).toBe('my family');
        expect(s.coreFeatures).toContain('todo / task list');
    });
    it('detects language, ui style and target user from an explicit request', () => {
        const s = extractIntent('I want a dark-themed python web scraper for developers');
        expect(s.language).toBe('python');
        expect(s.uiStyle).toContain('web');
        expect(s.uiStyle).toContain('dark');
        expect(s.targetUser).toBe('developers');
        expect(s.coreFeatures).toContain('web scraping');
    });
    it('detects CLI style and contextual language', () => {
        const s = extractIntent('make a terminal pomodoro timer in rust');
        expect(s.uiStyle).toBe('cli');
        expect(s.language).toBe('rust');
        expect(s.coreFeatures).toContain('timing (timer/countdown)');
    });
    it('classifies "stand alone, not a web browser based build" as DESKTOP, not web', () => {
        // Regression: the bare word "browser" used to win and VACA planned a
        // React/Express web stack for an explicitly non-web request.
        const s = extractIntent('build me a chess game, standalone not a web browser based build');
        expect(s.uiStyle).toContain('desktop');
        expect(s.uiStyle).not.toContain('web');
    });
    it('still classifies plain web requests as web', () => {
        const s = extractIntent('make a to-do list website with accounts');
        expect(s.uiStyle).toContain('web');
    });
    it('detects "go" only with context, not as a verb', () => {
        expect(extractIntent('make a chess engine in go').language).toBe('go');
        expect(extractIntent('go make me a todo app').language).toBe('');
    });
    it('does not confuse java/javascript', () => {
        expect(extractIntent('build a java app').language).toBe('java');
        expect(extractIntent('build a javascript app').language).toBe('javascript');
    });
    it('cuts "for X" at stop words ("for kids with ai" → "kids")', () => {
        const s = extractIntent('make a math game for kids with ai');
        expect(s.targetUser).toBe('kids');
    });
    it('bails on cardinal quantifiers ("for two players")', () => {
        const s = extractIntent('make a chess game for two players');
        expect(s.targetUser).toBe('');
    });
    it('does not treat "for me" as a target user', () => {
        const s = extractIntent('make a chess game for me');
        expect(s.targetUser).toBe('');
        expect(s.goal).toBe('chess game');
    });
    it('infers html for interactive GUI apps and python for data work', () => {
        expect(extractIntent('a quiz app').language).toBe('html');
        expect(extractIntent('a web scraper that exports csv').language).toBe('python');
    });
    it('handles non-string / empty input without throwing', () => {
        const s = extractIntent('');
        expect(s).toEqual({ goal: '', targetUser: '', coreFeatures: [], uiStyle: '', language: '' });
        expect(extractIntent(undefined)).toEqual(s);
    });
});
describe('formatIntentSection', () => {
    it('renders a compact block with every populated field', () => {
        const s = extractIntent('make a chess game in rust');
        const block = formatIntentSection(s);
        expect(block).toContain('UNDERSTOOD INTENT');
        expect(block).toContain('Goal: chess game');
        expect(block).toContain('Preferred language: rust');
        expect(block).toContain('Treat this as your understanding');
    });
    it('returns empty string for an empty spec', () => {
        expect(formatIntentSection(extractIntent(''))).toBe('');
    });
});
describe('isLowConfidenceIntent (Phase 3 fast-coder refinement gate)', () => {
    it('flags a spec with no language, no ui style, and <2 core features', () => {
        const s = { goal: 'something to help plan trips', targetUser: 'my family', coreFeatures: [], uiStyle: '', language: '' };
        expect(isLowConfidenceIntent(s)).toBe(true);
    });
    it('does NOT flag a spec that found a language or ui style', () => {
        expect(isLowConfidenceIntent(extractIntent('make a complete chess game with an AI player'))).toBe(false); // html + game + AI opponent
        expect(isLowConfidenceIntent(extractIntent('build a rust cli tool'))).toBe(false); // rust + cli
    });
    it('does NOT flag a spec with 2+ core features even without language/ui', () => {
        const s = { goal: 'x', targetUser: '', coreFeatures: ['todo / task list', 'persistent storage'], uiStyle: '', language: '' };
        expect(isLowConfidenceIntent(s)).toBe(false);
    });
});
describe('mergeIntentSpecs (fill-the-gaps)', () => {
    it('keeps rule-based values where present', () => {
        const base = { goal: 'chess game', targetUser: '', coreFeatures: ['AI opponent'], uiStyle: 'game', language: 'html' };
        const refined = { goal: 'totally different', targetUser: 'my kids', coreFeatures: ['drag-and-drop'], uiStyle: 'web, dark', language: 'python' };
        expect(mergeIntentSpecs(base, refined)).toEqual({
            goal: 'chess game', targetUser: 'my kids', coreFeatures: ['AI opponent'], uiStyle: 'game', language: 'html',
        });
    });
    it('fills empty fields from the refined spec', () => {
        const base = { goal: 'help plan trips', targetUser: '', coreFeatures: [], uiStyle: '', language: '' };
        const refined = { goal: '', targetUser: 'my family', coreFeatures: ['trip planning'], uiStyle: 'web', language: 'html' };
        expect(mergeIntentSpecs(base, refined)).toEqual({
            goal: 'help plan trips', targetUser: 'my family', coreFeatures: ['trip planning'], uiStyle: 'web', language: 'html',
        });
    });
    it('does not let an empty refined spec clobber rule hits', () => {
        const base = extractIntent('make a chess game in rust');
        const empty = { goal: '', targetUser: '', coreFeatures: [], uiStyle: '', language: '' };
        expect(mergeIntentSpecs(base, empty)).toEqual(base);
    });
});
