import { describe, it, expect } from 'vitest';
import { mapOcrSeverity, mapOcrCategory, toReviewComment, normalizeOcrOutput, isOcrSkipped, sanitizeRelPath, } from './ocrReviewer.js';
describe('mapOcrSeverity', () => {
    it('maps known severities into the internal enum', () => {
        expect(mapOcrSeverity('critical')).toBe('critical');
        expect(mapOcrSeverity('blocker')).toBe('critical');
        expect(mapOcrSeverity('high')).toBe('high');
        expect(mapOcrSeverity('medium')).toBe('medium');
        expect(mapOcrSeverity('moderate')).toBe('medium');
        expect(mapOcrSeverity('low')).toBe('low');
        expect(mapOcrSeverity('minor')).toBe('low');
        expect(mapOcrSeverity('info')).toBe('info');
        expect(mapOcrSeverity('nit')).toBe('info');
    });
    it('is case/whitespace tolerant and falls back to medium', () => {
        expect(mapOcrSeverity('  HIGH ')).toBe('high');
        expect(mapOcrSeverity('unknown-severity')).toBe('medium');
        expect(mapOcrSeverity(undefined)).toBe('medium');
    });
});
describe('mapOcrCategory', () => {
    it('maps known categories into the internal enum', () => {
        expect(mapOcrCategory('bug')).toBe('bug');
        expect(mapOcrCategory('correctness')).toBe('bug');
        expect(mapOcrCategory('security')).toBe('security');
        expect(mapOcrCategory('performance')).toBe('performance');
        expect(mapOcrCategory('maintainability')).toBe('maintainability');
        expect(mapOcrCategory('test')).toBe('best-practice');
        expect(mapOcrCategory('style')).toBe('style');
        expect(mapOcrCategory('documentation')).toBe('documentation');
    });
    it('falls back to best-practice', () => {
        expect(mapOcrCategory('other')).toBe('best-practice');
        expect(mapOcrCategory(undefined)).toBe('best-practice');
    });
});
describe('toReviewComment', () => {
    it('converts an ocr comment into the internal shape', () => {
        const c = toReviewComment({
            path: 'src/data-store.ts',
            content: 'Missing null check on fetch result',
            suggestion_code: 'if (!data) return [];',
            existing_code: 'return data.items;',
            start_line: 42,
            end_line: 44,
            severity: 'high',
            category: 'bug',
        });
        expect(c).toMatchObject({
            path: 'src/data-store.ts',
            content: 'Missing null check on fetch result',
            severity: 'high',
            category: 'bug',
            startLine: 42,
            endLine: 44,
            suggestionCode: 'if (!data) return [];',
            existingCode: 'return data.items;',
        });
    });
    it('handles missing optional fields', () => {
        const c = toReviewComment({ path: 'a.ts', content: 'x' });
        expect(c.severity).toBe('medium');
        expect(c.category).toBe('best-practice');
        expect(c.startLine).toBe(0);
        expect(c.endLine).toBe(0);
        expect(c.suggestionCode).toBeUndefined();
        expect(c.existingCode).toBeUndefined();
    });
});
describe('normalizeOcrOutput', () => {
    it('parses a full scan payload into CodeReviewResult parts', () => {
        const n = normalizeOcrOutput({
            status: 'success',
            comments: [
                {
                    path: 'src/a.ts',
                    content: 'A critical bug',
                    severity: 'critical',
                    category: 'bug',
                    start_line: 1,
                    end_line: 2,
                },
                {
                    path: 'src/a.ts',
                    content: 'A style nit',
                    severity: 'low',
                    category: 'style',
                },
                {
                    path: 'src/b.ts',
                    content: 'Perf concern',
                    severity: 'medium',
                    category: 'performance',
                },
            ],
            summary: { files_reviewed: 2, comments: 3 },
            project_summary: 'Two files reviewed.',
            session_id: 'abc123',
        });
        expect(n.comments).toHaveLength(3);
        expect(n.summary).toMatchObject({
            filesReviewed: 2,
            totalComments: 3,
            criticalCount: 1,
            lowCount: 1,
            mediumCount: 1,
        });
        expect(n.perFile).toHaveLength(2);
        const a = n.perFile.find((p) => p.fileName === 'src/a.ts');
        expect(a.score).toBe('fail'); // has a critical
        const b = n.perFile.find((p) => p.fileName === 'src/b.ts');
        expect(b.score).toBe('warning'); // medium only
        expect(n.projectSummary).toBe('Two files reviewed.');
        expect(n.sessionId).toBe('abc123');
    });
    it('returns pass for files with zero comments', () => {
        const n = normalizeOcrOutput({ status: 'success', comments: [] });
        expect(n.comments).toHaveLength(0);
        expect(n.summary.totalComments).toBe(0);
        expect(n.summary.filesReviewed).toBe(0);
    });
    it('tolerates malformed / missing payloads', () => {
        expect(normalizeOcrOutput(null).comments).toEqual([]);
        expect(normalizeOcrOutput({}).summary.totalComments).toBe(0);
        expect(normalizeOcrOutput({ comments: 'nope' }).comments).toEqual([]);
    });
});
describe('isOcrSkipped', () => {
    it('flags skipped status (the empty-scan failure mode)', () => {
        expect(isOcrSkipped({ status: 'skipped' })).toBe(true);
        expect(isOcrSkipped({ status: 'skipped', message: 'No supported files changed.' })).toBe(true);
    });
    it('returns false for real scans', () => {
        expect(isOcrSkipped({ status: 'success', comments: [] })).toBe(false);
        expect(isOcrSkipped({ status: 'completed_with_warnings' })).toBe(false);
        expect(isOcrSkipped(null)).toBe(false);
        expect(isOcrSkipped({})).toBe(false);
    });
});
describe('sanitizeRelPath', () => {
    it('accepts safe relative paths', () => {
        expect(sanitizeRelPath('core-engine.ts')).toBe('core-engine.ts');
        expect(sanitizeRelPath('src/ui/panel.ts')).toBe('src/ui/panel.ts');
        expect(sanitizeRelPath('./data-store.ts')).toBe('data-store.ts');
    });
    it('rejects path traversal and absolute paths', () => {
        expect(sanitizeRelPath('../../etc/passwd')).toBeNull();
        expect(sanitizeRelPath('a/../../etc/passwd')).toBeNull();
        expect(sanitizeRelPath('/etc/passwd')).toBeNull();
        expect(sanitizeRelPath('C:/windows/evil.ts')).toBeNull();
        expect(sanitizeRelPath('..')).toBeNull();
        expect(sanitizeRelPath('')).toBeNull();
        expect(sanitizeRelPath('.')).toBeNull();
    });
});
