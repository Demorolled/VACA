import { describe, it, expect, afterEach, afterAll, vi } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';
import { learningEngine } from './learningEngine.js';
import { knowledgeStore } from './knowledgeStore.js';
// Redirect the knowledge store to a throwaway dir BEFORE the module-level
// singleton is constructed. `vi.hoisted` is moved above the static imports, so
// `knowledgeStore` (imported below) reads it and never touches the real
// `backend/knowledge/patterns.json`. These tests add REAL patterns — without
// this they polluted the committed store (observed live: a run truncated it).
const KB_DIR = vi.hoisted(() => {
    const base = process.env.TMPDIR || process.env.TEMP || '/tmp';
    const dir = `${base}/vaca-kb-le-${process.pid}-${Date.now()}`;
    process.env.VACA_KNOWLEDGE_DIR = dir;
    return dir;
});
afterAll(() => {
    try {
        fs.rmSync(KB_DIR, { recursive: true, force: true });
    }
    catch { /* non-fatal */ }
});
// Clean, non-stub TypeScript that passes the isQualityCode gate — the same
// shape of file the write/blueprint paths learn from.
const CLEAN_TS = `export interface Task {
  id: string;
  title: string;
  done: boolean;
}

export class TaskStore {
  private tasks: Task[] = [];
  add(task: Task): void {
    this.tasks.push(task);
  }
  list(): Task[] {
    return [...this.tasks];
  }
}
`;
function makeProject(overrides) {
    return {
        id: 'proj_test',
        name: 'Test Project',
        targetOS: 'linux',
        nodes: [
            {
                id: 'n1',
                type: 'logic',
                position: { x: 0, y: 0 },
                data: { label: 'storage', description: 'Store', status: 'pending', language: 'typescript' },
            },
        ],
        edges: [],
        createdAt: new Date(),
        updatedAt: new Date(),
        ...overrides,
    };
}
// The store is a process-lifetime singleton writing to the temp dir pinned
// above. Track the pre-test state and clean up exactly the patterns the test
// added (and remove the file if the test process created it) so store + disk
// return to their prior state.
const STORE_PATH = path.join(KB_DIR, 'patterns.json');
function snapshotIds() {
    return new Set(knowledgeStore.getAll().map((p) => p.id));
}
function addedPatterns(before) {
    return knowledgeStore.getAll().filter((p) => !before.has(p.id));
}
function cleanup(before, existedBefore) {
    for (const p of addedPatterns(before))
        knowledgeStore.deletePattern(p.id);
    if (!existedBefore && fs.existsSync(STORE_PATH)) {
        try {
            fs.unlinkSync(STORE_PATH);
        }
        catch {
            /* non-fatal */
        }
    }
}
describe('learningEngine.learnFromFiles (write path)', () => {
    afterEach(() => {
        delete process.env.AUTO_LEARN_DISABLED;
    });
    it('stores a node pattern + architecture pattern from a clean TS write', () => {
        const existedBefore = fs.existsSync(STORE_PATH);
        const before = snapshotIds();
        const entries = learningEngine.learnFromFiles({
            projectName: 'a todo cli app',
            files: [{ path: 'src/storage.ts', content: CLEAN_TS }],
        });
        try {
            // learnFromProject counts node patterns in its return; the full-app
            // architecture pattern is stored through the same funnel but uncounted.
            expect(entries.length).toBeGreaterThanOrEqual(1);
            expect(entries.some((e) => e.title.startsWith('storage - '))).toBe(true);
            const added = addedPatterns(before);
            expect(added.length).toBe(2); // node pattern + architecture
            expect(added.some((p) => p.nodeType === 'master')).toBe(true);
        }
        finally {
            cleanup(before, existedBefore);
        }
    });
    it('infers language and label from the file path', () => {
        const existedBefore = fs.existsSync(STORE_PATH);
        const before = snapshotIds();
        const entries = learningEngine.learnFromFiles({
            projectName: 'a helper app',
            files: [{ path: 'src/utils/format.ts', content: CLEAN_TS }],
        });
        try {
            const nodePattern = entries.find((e) => e.nodeType !== 'master');
            expect(nodePattern?.language).toBe('typescript');
            expect(nodePattern?.title).toContain('format');
            expect(nodePattern?.tags).toContain('logic');
        }
        finally {
            cleanup(before, existedBefore);
        }
    });
    it('returns nothing when the kill switch is on', () => {
        process.env.AUTO_LEARN_DISABLED = 'true';
        const entries = learningEngine.learnFromFiles({
            projectName: 'x',
            files: [{ path: 'src/a.ts', content: CLEAN_TS }],
        });
        expect(entries).toEqual([]);
    });
    it('returns nothing for empty file lists', () => {
        const entries = learningEngine.learnFromFiles({ projectName: 'x', files: [] });
        expect(entries).toEqual([]);
    });
    it('never learns from stub/placeholder content (quality gate)', () => {
        const existedBefore = fs.existsSync(STORE_PATH);
        const before = snapshotIds();
        const stub = '// TODO: Implement\nfunction placeholderFor(x: any) { return x; }\n';
        const entries = learningEngine.learnFromFiles({
            projectName: 'a stub app',
            files: [{ path: 'src/main.ts', content: stub }],
        });
        try {
            expect(entries).toEqual([]);
            expect(addedPatterns(before)).toEqual([]);
        }
        finally {
            cleanup(before, existedBefore);
        }
    });
});
describe('learningEngine.learnFromGeneratedFiles (canvas/blueprint path)', () => {
    it('stores patterns from validated generated files', () => {
        const existedBefore = fs.existsSync(STORE_PATH);
        const before = snapshotIds();
        const project = makeProject();
        const entries = learningEngine.learnFromGeneratedFiles(project, [
            { nodeId: 'n1', code: CLEAN_TS, validated: true },
        ]);
        try {
            expect(entries.some((e) => e.title.startsWith('storage - '))).toBe(true);
            expect(addedPatterns(before).length).toBe(2); // node + architecture
        }
        finally {
            cleanup(before, existedBefore);
        }
    });
    it('never mutates the caller project (learning works on a shallow copy)', () => {
        const existedBefore = fs.existsSync(STORE_PATH);
        const before = snapshotIds();
        const project = makeProject();
        const entries = learningEngine.learnFromGeneratedFiles(project, [
            { nodeId: 'n1', code: CLEAN_TS, validated: true },
        ]);
        try {
            expect(project.nodes[0].data.generatedCode).toBeUndefined();
            expect(project.nodes[0].data.status).toBe('pending');
        }
        finally {
            cleanup(before, existedBefore);
        }
    });
    it('does not populate nodes the files do not cover (only the architecture survives)', () => {
        const existedBefore = fs.existsSync(STORE_PATH);
        const before = snapshotIds();
        const project = makeProject();
        // file references an unknown nodeId → no node gets code → no node pattern,
        // but the joined full-app code still yields the architecture pattern.
        const entries = learningEngine.learnFromGeneratedFiles(project, [
            { nodeId: 'nope', code: CLEAN_TS, validated: true },
        ]);
        try {
            expect(entries).toEqual([]);
            const added = addedPatterns(before);
            expect(added.length).toBe(1);
            expect(added[0].nodeType).toBe('master');
        }
        finally {
            cleanup(before, existedBefore);
        }
    });
});
