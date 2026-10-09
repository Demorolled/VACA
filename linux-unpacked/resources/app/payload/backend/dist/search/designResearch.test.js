import { describe, it, expect } from 'vitest';
import { formatResearchContext } from './designResearch.js';
function makeResearch(overrides = {}) {
    return {
        context: 'full report',
        webResults: [
            { title: 'Void Raiders on itch.io', url: 'https://example.com/void-raiders', content: 'Asteroids-style arcade space shooter with 25 campaign levels, escalating waves, ship weapons and scoring.' },
            { title: 'Second web hit', url: 'https://example.com/two', content: 'Another reference page.' },
            { title: 'Third web hit', url: 'https://example.com/three', content: 'Dropped by maxPerSource.' },
        ],
        githubResults: [
            { name: 'void-raiders', full_name: 'user/void-raiders', description: 'An arcade space shooter in Python', stars: 1234, url: 'https://github.com/user/void-raiders', language: 'Python', topics: ['game'], license: 'MIT' },
            { name: 'second-repo', full_name: 'user/second-repo', description: 'Another game', stars: 55, url: 'https://github.com/user/second-repo', language: 'JavaScript', topics: [], license: null },
        ],
        altResults: {
            projects: [
                { name: 'Space Invaders Clone', description: 'Classic arcade clone', category: 'gaming', stars: 99, url: 'https://alt.example/si' },
                { name: 'Second Alt', description: 'Open source alternative', category: 'gaming', stars: 10, url: 'https://alt.example/two' },
            ],
            matchedCategories: ['gaming'],
            totalFound: 2,
        },
        totalReferences: 7,
        ...overrides,
    };
}
describe('formatResearchContext', () => {
    it('includes web, github and open-source references', () => {
        const out = formatResearchContext(makeResearch());
        expect(out).toContain('Void Raiders on itch.io');
        expect(out).toContain('user/void-raiders');
        expect(out).toContain('Space Invaders Clone');
        expect(out).toContain('Use these as inspiration for designing the app architecture.');
    });
    it('caps each source at maxPerSource', () => {
        const out = formatResearchContext(makeResearch(), 1);
        expect(out).toContain('Void Raiders on itch.io');
        expect(out).not.toContain('Second web hit');
        expect(out).toContain('user/void-raiders');
        expect(out).not.toContain('user/second-repo');
        expect(out).toContain('Space Invaders Clone');
        expect(out).not.toContain('Second Alt');
    });
    it('handles empty results gracefully', () => {
        const out = formatResearchContext(makeResearch({
            webResults: [],
            githubResults: [],
            altResults: { projects: [], matchedCategories: [], totalFound: 0 },
            totalReferences: 0,
        }));
        expect(out).toContain('Reference designs found');
        expect(out).toContain('Use these as inspiration');
    });
});
