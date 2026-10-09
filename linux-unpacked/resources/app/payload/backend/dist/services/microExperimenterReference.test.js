import { describe, it, expect } from 'vitest';
import { MICRO_CATALOG, MICRO_BUILD_REFERENCES, buildReferenceSection, matchReference, } from './microExperimenterReference.js';
describe('micro experimenter reference catalog', () => {
    it('has the worked before→after examples with lessons (the original ten + Rust/C++)', () => {
        expect(MICRO_BUILD_REFERENCES.length).toBeGreaterThanOrEqual(10);
        // The non-TS seed patterns must be present.
        expect(MICRO_BUILD_REFERENCES.some((r) => r.language === 'rust')).toBe(true);
        expect(MICRO_BUILD_REFERENCES.some((r) => r.language === 'cpp')).toBe(true);
        for (const ref of MICRO_BUILD_REFERENCES) {
            expect(ref.baseline.length).toBeGreaterThan(0);
            expect(ref.improved.length).toBeGreaterThan(0);
            expect(ref.lesson.length).toBeGreaterThan(10);
            expect(ref.nodeType).toBeTruthy();
        }
    });
    it('catalog covers every new compiled / scripting language', () => {
        const langs = new Set(MICRO_CATALOG.map((e) => e.language));
        for (const l of ['go', 'rust', 'cpp', 'c', 'java', 'csharp', 'python', 'php', 'ruby', 'kotlin', 'swift']) {
            expect(langs.has(l), `catalog missing ${l}`).toBe(true);
        }
    });
    it('every catalog entry is backed by a reference (title matches)', () => {
        for (const entry of MICRO_CATALOG) {
            expect(matchReference(entry.purpose)?.id).toBe(entry.refId);
        }
    });
    it('matches by substring against the purpose', () => {
        expect(matchReference('a strong password strength checker tool')?.id).toBe('password-checker');
        expect(matchReference('simple media player please')?.id).toBe('simple-media-player');
    });
    it('builds a compact, injection-ready reference section', () => {
        const section = buildReferenceSection('a simple password strength checker CLI program in typescript', 'logic');
        expect(section).toContain('EMULATE THIS STYLE');
        expect(section).toContain('LESSON:');
        expect(section).toContain('IMPROVED VERSION');
    });
});
