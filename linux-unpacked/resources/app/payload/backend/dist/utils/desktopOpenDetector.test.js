import { describe, it, expect } from 'vitest';
import { detectDesktopOpenRequest } from './desktopOpenDetector.js';
function appOf(text) {
    const r = detectDesktopOpenRequest(text);
    return r && r.kind === 'app' ? r.app : undefined;
}
describe('detectDesktopOpenRequest', () => {
    it('detects "open firefox"', () => {
        const r = detectDesktopOpenRequest('open firefox');
        expect(r).toEqual({ kind: 'app', app: 'firefox', matched: 'firefox' });
    });
    it('resolves the typo "firefix" → firefox (no more echoing the typo)', () => {
        const r = detectDesktopOpenRequest('open firefix');
        expect(r?.kind).toBe('app');
        expect(r && r.kind === 'app' ? r.app : undefined).toBe('firefox');
    });
    it('handles articles and qualifiers', () => {
        expect(appOf('open the browser')).toBe('browser');
        expect(appOf('open the web browser named firefox')).toBe('firefox');
        expect(appOf('please launch the calculator')).toBe('calculator');
        expect(appOf('open up the terminal')).toBe('terminal');
    });
    it('detects urls', () => {
        const r = detectDesktopOpenRequest('open https://example.com');
        expect(r).toEqual({ kind: 'url', url: 'https://example.com' });
        expect(detectDesktopOpenRequest('go to www.github.com')?.kind).toBe('url');
    });
    it('ignores questions about opening', () => {
        expect(detectDesktopOpenRequest('how do I open firefox?')).toBeNull();
        expect(detectDesktopOpenRequest('what does open mean?')).toBeNull();
        expect(detectDesktopOpenRequest('can you tell me how to open apps?')).toBeNull();
    });
    it('ignores non-open text and unknown apps', () => {
        expect(detectDesktopOpenRequest('open the server config file')).toBeNull();
        expect(detectDesktopOpenRequest('explain the merge feature')).toBeNull();
        expect(detectDesktopOpenRequest('')).toBeNull();
    });
});
