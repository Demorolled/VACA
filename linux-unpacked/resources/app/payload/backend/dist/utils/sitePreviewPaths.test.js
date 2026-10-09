import { describe, it, expect } from 'vitest';
import path from 'path';
import { sanitizeSiteRelPath, mimeForPath, resolveSitePreviewPath } from './sitePreviewPaths.js';
describe('sanitizeSiteRelPath', () => {
    it('keeps normal relative paths', () => {
        expect(sanitizeSiteRelPath('index.html')).toBe('index.html');
        expect(sanitizeSiteRelPath('tools/shared-card-renderer.js')).toBe('tools/shared-card-renderer.js');
        expect(sanitizeSiteRelPath('a/b/c/d.css')).toBe('a/b/c/d.css');
        expect(sanitizeSiteRelPath('tools/')).toBe('tools');
        expect(sanitizeSiteRelPath('a/b/')).toBe('a/b');
    });
    it('normalizes backslashes (Windows-style paths)', () => {
        expect(sanitizeSiteRelPath('tools\\style.css')).toBe('tools/style.css');
    });
    it('strips leading slashes and drive letters', () => {
        expect(sanitizeSiteRelPath('/index.html')).toBe('index.html');
        expect(sanitizeSiteRelPath('//a/b')).toBe('a/b');
        expect(sanitizeSiteRelPath('C:/evil.txt')).toBe('evil.txt');
    });
    it('rejects path traversal', () => {
        expect(sanitizeSiteRelPath('../secret.txt')).toBeNull();
        expect(sanitizeSiteRelPath('../../etc/passwd')).toBeNull();
        expect(sanitizeSiteRelPath('a/../../b')).toBeNull();
        expect(sanitizeSiteRelPath('..')).toBeNull();
    });
    it('rejects empty and dot paths', () => {
        expect(sanitizeSiteRelPath('')).toBeNull();
        expect(sanitizeSiteRelPath('.')).toBeNull();
        expect(sanitizeSiteRelPath('   ')).toBe('   '); // whitespace is not a traversal risk
    });
    it('rejects non-string input', () => {
        expect(sanitizeSiteRelPath(null)).toBeNull();
        expect(sanitizeSiteRelPath(undefined)).toBeNull();
        expect(sanitizeSiteRelPath(42)).toBeNull();
    });
});
describe('mimeForPath', () => {
    it('maps common extensions', () => {
        expect(mimeForPath('index.html')).toContain('text/html');
        expect(mimeForPath('app.js')).toContain('javascript');
        expect(mimeForPath('style.css')).toContain('text/css');
        expect(mimeForPath('data.json')).toContain('application/json');
        expect(mimeForPath('icon.svg')).toContain('image/svg+xml');
        expect(mimeForPath('pic.png')).toContain('image/png');
    });
    it('falls back to octet-stream for unknown extensions', () => {
        expect(mimeForPath('file.xyz')).toBe('application/octet-stream');
        expect(mimeForPath('noext')).toBe('application/octet-stream');
    });
});
describe('resolveSitePreviewPath', () => {
    const root = path.join(process.cwd(), '.test-preview-root');
    it('resolves inside root', () => {
        const p = resolveSitePreviewPath(root, 'index.html');
        expect(p).toBe(path.join(root, 'index.html'));
    });
    it('returns null for traversal attempts', () => {
        expect(resolveSitePreviewPath(root, '../outside.txt')).toBeNull();
        expect(resolveSitePreviewPath(root, 'a/../../outside.txt')).toBeNull();
    });
    it('returns null for empty paths', () => {
        expect(resolveSitePreviewPath(root, '')).toBeNull();
    });
});
