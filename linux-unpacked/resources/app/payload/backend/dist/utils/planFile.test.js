import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { existsSync, readdirSync, readFileSync, writeFileSync, mkdirSync, rmSync } from 'fs';
import path from 'path';
const TMP_DIR = '/tmp/vaca-plans-test';
describe('planFile', () => {
    let pf;
    beforeEach(async () => {
        rmSync(TMP_DIR, { recursive: true, force: true });
        process.env.VACA_PLANS_DIR = TMP_DIR;
        vi.resetModules();
        pf = await import('./planFile.js');
    });
    afterEach(() => {
        delete process.env.VACA_PLANS_DIR;
        rmSync(TMP_DIR, { recursive: true, force: true });
    });
    it('safePlanName strips unsafe chars and spaces', () => {
        expect(pf.safePlanName('My App!')).toBe('My_App');
        expect(pf.safePlanName('Weather  Dashboard')).toBe('Weather_Dashboard');
        expect(pf.safePlanName('!!!')).toBe('untitled-plan');
        expect(pf.safePlanName('  ')).toBe('untitled-plan');
    });
    it('formatPlanFile produces a complete plan text file', () => {
        const text = pf.formatPlanFile({
            projectName: 'Todo App',
            ideas: 'Build a todo app with streaks.',
            guidance: 'Start with a list view.',
            questions: 'Mobile or desktop?',
            updatedAt: '2026-08-03T00:00:00.000Z',
        });
        expect(text).toContain('PLAN: Todo App');
        expect(text).toContain('Status: PLANNED');
        expect(text).toContain('Build a todo app with streaks.');
        expect(text).toContain('Start with a list view.');
        expect(text).toContain('Mobile or desktop?');
        expect(text).toContain('Auto-saved by VACA Plan Mode');
    });
    it('savePlanFile writes to the plans dir and returns a record', () => {
        const rec = pf.savePlanFile({
            projectName: 'Weather Dashboard',
            ideas: 'Show forecasts from an API.',
        });
        expect(rec.fileName).toBe('Weather_Dashboard.txt');
        expect(rec.filePath).toContain(TMP_DIR);
        expect(existsSync(rec.filePath)).toBe(true);
        expect(rec.projectName).toBe('Weather Dashboard');
    });
    it('listPlanFiles finds saved plans', () => {
        pf.savePlanFile({ projectName: 'Alpha App', ideas: 'a' });
        pf.savePlanFile({ projectName: 'Beta App', ideas: 'b' });
        const plans = pf.listPlanFiles();
        expect(plans.length).toBe(2);
        expect(plans.some(p => p.fileName === 'Alpha_App.txt')).toBe(true);
        expect(plans.some(p => p.fileName === 'Beta_App.txt')).toBe(true);
    });
    it('readPlanFile returns content by name', () => {
        pf.savePlanFile({ projectName: 'My Plan', ideas: 'The idea!' });
        const read = pf.readPlanFile('My Plan');
        expect(read).not.toBeNull();
        expect(read.content).toContain('The idea!');
        expect(pf.readPlanFile('Does Not Exist')).toBeNull();
    });
    it('saving the same name updates the same file', () => {
        pf.savePlanFile({ projectName: 'Same', ideas: 'v1' });
        pf.savePlanFile({ projectName: 'Same', ideas: 'v2' });
        const files = readdirSync(TMP_DIR).filter(f => f.endsWith('.txt'));
        expect(files.length).toBe(1);
        const read = pf.readPlanFile('Same');
        expect(read.content).toContain('v2');
    });
    // ── Big Plan Mode: graph round trip ────────────────────────────────────────
    //
    // The design on the canvas is worthless if it cannot come back. These tests
    // pin the whole loop the UI depends on: autosave writes a folder, reopen reads
    // it, and the co-worker's questions + the user's answers survive the trip.
    describe('plan graph round trip', () => {
        const NODES = [
            {
                id: 'node_1',
                type: 'logic',
                label: 'Notes Core',
                description: 'holds notes, exposes CRUD',
                language: 'typescript',
                isMaster: true,
                qa: [
                    {
                        q: 'What data does the Notes Core store besides the notes?',
                        a: 'Only notes and their tags. No accounts, no sync.',
                        at: '2026-09-15T02:30:00.000Z',
                    },
                ],
            },
            { id: 'node_3', type: 'database', label: 'Encrypted Store', language: 'rust' },
        ];
        const EDGES = [
            { source: 'node_3', target: 'node_1', label: 'persists notes' },
        ];
        it('saves a graph as a folder and reads nodes, edges and answers back intact', () => {
            const rec = pf.savePlanGraph({
                projectName: 'Note Taking App',
                goal: 'A desktop note-taking app with encrypted storage',
                nodes: NODES,
                edges: EDGES,
            });
            // The folder (not a flat .txt) is what makes reloading possible at all.
            expect(rec.dirName).toBe('Note_Taking_App');
            expect(existsSync(path.join(TMP_DIR, 'Note_Taking_App', 'graph.json'))).toBe(true);
            expect(existsSync(path.join(TMP_DIR, 'Note_Taking_App', 'plan.md'))).toBe(true);
            expect(rec.nodeCount).toBe(2);
            expect(rec.edgeCount).toBe(1);
            const back = pf.readPlanGraph('Note Taking App');
            expect(back).not.toBeNull();
            expect(back.goal).toBe('A desktop note-taking app with encrypted storage');
            expect(back.nodes).toHaveLength(2);
            expect(back.edges).toHaveLength(1);
            const master = back.nodes.find((n) => n.isMaster);
            expect(master?.label).toBe('Notes Core');
            expect(master?.description).toBe('holds notes, exposes CRUD');
            expect(master?.language).toBe('typescript');
            // The answers are the part that would silently vanish if the graph were
            // written without them — a reopened plan would then autosave the answers
            // out of existence.
            expect(master?.qa).toHaveLength(1);
            expect(master.qa[0].a).toBe('Only notes and their tags. No accounts, no sync.');
            const edge = back.edges[0];
            expect(edge.source).toBe('node_3');
            expect(edge.target).toBe('node_1');
            expect(edge.label).toBe('persists notes');
        });
        it('renders the questions and answers into plan.md against their node', () => {
            pf.savePlanGraph({
                projectName: 'Note Taking App',
                goal: 'A desktop note-taking app',
                nodes: NODES,
                edges: EDGES,
            });
            const md = readFileSync(path.join(TMP_DIR, 'Note_Taking_App', 'plan.md'), 'utf-8');
            expect(md).toContain('PLAN: Note Taking App');
            expect(md).toContain('● Notes Core [logic/typescript]');
            // The answer sits under the node it belongs to, not in a loose section.
            const coreIdx = md.indexOf('Notes Core');
            const qIdx = md.indexOf('Q: What data does the Notes Core store');
            const aIdx = md.indexOf('A: Only notes and their tags.');
            expect(qIdx).toBeGreaterThan(coreIdx);
            expect(aIdx).toBeGreaterThan(qIdx);
            // An unanswered node still lists its name and the wiring section follows.
            expect(md).toContain('- Encrypted Store [database/rust]');
            expect(md).toContain('Encrypted Store -> Notes Core  (persists notes)');
        });
        it('listPlanGraphs lists saved designs with counts, newest first', () => {
            pf.savePlanGraph({ projectName: 'Alpha', goal: 'a', nodes: NODES, edges: EDGES });
            pf.savePlanGraph({ projectName: 'Beta', goal: 'b', nodes: [NODES[0]], edges: [] });
            const graphs = pf.listPlanGraphs();
            expect(graphs.map((g) => g.dirName).sort()).toEqual(['Alpha', 'Beta']);
            const alpha = graphs.find((g) => g.dirName === 'Alpha');
            expect(alpha.projectName).toBe('Alpha');
            expect(alpha.nodeCount).toBe(2);
            expect(alpha.edgeCount).toBe(1);
            expect(alpha.updatedAt).not.toBe('');
            const beta = graphs.find((g) => g.dirName === 'Beta');
            expect(beta.nodeCount).toBe(1);
            expect(beta.edgeCount).toBe(0);
            // Newest first: the design you were just working on is the one the
            // resume banner offers.
            for (let i = 1; i < graphs.length; i++) {
                expect(graphs[i - 1].updatedAt >= graphs[i].updatedAt).toBe(true);
            }
        });
        it('listPlanGraphs skips entries that are not readable designs', () => {
            pf.savePlanGraph({ projectName: 'Real', goal: 'g', nodes: NODES, edges: EDGES });
            // A folder with no graph.json (mid-write, or never a plan graph).
            mkdirSync(path.join(TMP_DIR, 'Half_Written'), { recursive: true });
            writeFileSync(path.join(TMP_DIR, 'Half_Written', 'plan.md'), 'partial', 'utf-8');
            // A folder whose graph.json is corrupt.
            mkdirSync(path.join(TMP_DIR, 'Corrupt'), { recursive: true });
            writeFileSync(path.join(TMP_DIR, 'Corrupt', 'graph.json'), '{not json', 'utf-8');
            // A stray file where a folder would be.
            writeFileSync(path.join(TMP_DIR, 'stray.txt'), 'x', 'utf-8');
            const names = pf.listPlanGraphs().map((g) => g.dirName);
            expect(names).toEqual(['Real']);
        });
        it('readPlanGraph sanitizes the name instead of walking the path', () => {
            pf.savePlanGraph({ projectName: 'Safe', goal: 'g', nodes: NODES, edges: EDGES });
            // A raw join would escape PLANS_DIR here.
            expect(pf.readPlanGraph('../../etc/passwd')).toBeNull();
            expect(pf.readPlanGraph('..')).toBeNull();
            expect(pf.safePlanName('My/App')).toBe('MyApp');
            // An unknown but safe name is simply absent, not an error.
            expect(pf.readPlanGraph('Does Not Exist')).toBeNull();
        });
        it('re-saving a graph rewrites the same folder rather than duplicating it', () => {
            pf.savePlanGraph({ projectName: 'Twice', goal: 'v1', nodes: NODES, edges: EDGES });
            pf.savePlanGraph({ projectName: 'Twice', goal: 'v2', nodes: [NODES[1]], edges: [] });
            const dirs = readdirSync(TMP_DIR).filter((d) => d === 'Twice');
            expect(dirs).toHaveLength(1);
            const back = pf.readPlanGraph('Twice');
            expect(back.goal).toBe('v2');
            expect(back.nodes).toHaveLength(1);
            expect(pf.listPlanGraphs()).toHaveLength(1);
        });
    });
});
