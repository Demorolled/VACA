import { describe, it, expect, vi, beforeEach } from 'vitest';
import { codeReviewer } from './CodeReviewer.js';
// Stub the LLM-backed fix loop so the fix branch is testable without model calls.
vi.mock('../sandbox/errorCorrection.js', () => ({
    runErrorCorrection: vi.fn(async (req) => ({
        finalCode: `FIXED ${req.code}`,
        attempts: [{ message: 'mock attempt' }],
        success: true,
    })),
}));
const CONTEXT = { projectName: 'test', appGoal: 'test app' };
function makeReview(perFile) {
    return {
        success: true,
        comments: perFile.flatMap((pf) => pf.severities.map((severity, i) => ({
            path: pf.fileName,
            content: `finding ${i}`,
            severity,
            category: 'bug',
            startLine: i,
            endLine: i,
        }))),
        summary: { filesReviewed: perFile.length, totalComments: 0, criticalCount: 0, highCount: 0, mediumCount: 0, lowCount: 0, infoCount: 0 },
        perFile: perFile.map((pf) => ({
            fileName: pf.fileName,
            nodeLabel: pf.fileName,
            nodeId: pf.fileName,
            score: 'warning',
            summary: '',
            comments: pf.severities.map((severity, i) => ({
                path: pf.fileName,
                content: `finding ${i}`,
                severity,
                category: 'bug',
                startLine: i,
                endLine: i,
            })),
        })),
    };
}
const FILE = {
    fileName: 'a.ts',
    code: 'export const a = 1;',
    nodeId: 'n1',
    nodeLabel: 'a.ts',
    language: 'typescript',
};
describe('fixFromReview (extracted from reviewAndFix)', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });
    it('returns [] when there are no critical/high comments (no LLM calls)', async () => {
        const review = makeReview([{ fileName: 'a.ts', severities: ['medium', 'low'] }]);
        const fixes = await codeReviewer.fixFromReview([FILE], review, CONTEXT);
        expect(fixes).toEqual([]);
    });
    it('returns [] when the file is not found in the supplied files', async () => {
        const review = makeReview([{ fileName: 'b.ts', severities: ['critical'] }]);
        const fixes = await codeReviewer.fixFromReview([FILE], review, CONTEXT);
        expect(fixes).toEqual([]);
    });
    it('returns [] for an empty review result', async () => {
        const empty = {
            success: true,
            comments: [],
            summary: { filesReviewed: 0, totalComments: 0, criticalCount: 0, highCount: 0, mediumCount: 0, lowCount: 0, infoCount: 0 },
            perFile: [],
        };
        const fixes = await codeReviewer.fixFromReview([FILE], empty, CONTEXT);
        expect(fixes).toEqual([]);
    });
    it('fixes files with critical comments via runErrorCorrection', async () => {
        const review = makeReview([{ fileName: 'a.ts', severities: ['critical'] }]);
        const fixes = await codeReviewer.fixFromReview([FILE], review, CONTEXT);
        expect(fixes).toHaveLength(1);
        expect(fixes[0]).toMatchObject({
            fileName: 'a.ts',
            originalCode: FILE.code,
            fixAttempts: 1,
            success: true,
        });
        expect(fixes[0].fixedCode).toContain('FIXED');
    });
    it('fixes files with high comments only when minSeverity is high', async () => {
        const review = makeReview([{ fileName: 'a.ts', severities: ['high'] }]);
        // Default minSeverity is 'critical' — high-only findings are NOT fixed.
        expect(await codeReviewer.fixFromReview([FILE], review, CONTEXT)).toEqual([]);
        // With minSeverity 'high' they are.
        const fixes = await codeReviewer.fixFromReview([FILE], review, CONTEXT, { minSeverity: 'high' });
        expect(fixes).toHaveLength(1);
        expect(fixes[0].success).toBe(true);
    });
    it('surfaces a failure when runErrorCorrection throws', async () => {
        const { runErrorCorrection } = await import('../sandbox/errorCorrection.js');
        runErrorCorrection.mockRejectedValueOnce(new Error('boom'));
        const review = makeReview([{ fileName: 'a.ts', severities: ['critical'] }]);
        const fixes = await codeReviewer.fixFromReview([FILE], review, CONTEXT);
        expect(fixes).toHaveLength(1);
        expect(fixes[0]).toMatchObject({ fileName: 'a.ts', success: false, fixAttempts: 0 });
        expect(fixes[0].fixedCode).toBe(FILE.code); // unchanged on failure
    });
});
