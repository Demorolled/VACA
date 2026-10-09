import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { existsSync, readFileSync, readdirSync, writeFileSync, rmSync } from 'fs';
import path from 'path';
const TMP_DIR = '/tmp/vaca-planmap-test';
// ── The design these tests map ────────────────────────────────────────────────
// Mirrors what the canvas sends: real node ids, a master node with a declared
// purpose, a node with no purpose yet, a node with co-worker answers, and a
// wiring that says the Encrypted Store and the Editor View both feed Notes Core.
const NODES = [
    {
        id: 'node_1',
        type: 'logic',
        label: 'Notes Core',
        description: 'owns the note model and exposes CRUD',
        language: 'typescript',
        isMaster: true,
        qa: [
            {
                q: 'What data does the Notes Core store besides the notes?',
                a: 'Only notes and their tags. No accounts, no sync state.',
            },
        ],
    },
    { id: 'node_2', type: 'ui', label: 'Editor View', description: 'markdown editor pane', language: 'typescript' },
    { id: 'node_3', type: 'database', label: 'Encrypted Store', language: 'rust' },
];
const EDGES = [
    { source: 'node_2', target: 'node_1', label: 'editor reads/writes notes' },
    { source: 'node_3', target: 'node_1', label: 'persists notes' },
];
describe('planMap', () => {
    let pm;
    let pf;
    beforeEach(async () => {
        rmSync(TMP_DIR, { recursive: true, force: true });
        process.env.VACA_PLANS_DIR = TMP_DIR;
        vi.resetModules();
        pm = await import('./planMap.js');
        pf = await import('./planFile.js');
    });
    afterEach(() => {
        delete process.env.VACA_PLANS_DIR;
        rmSync(TMP_DIR, { recursive: true, force: true });
    });
    const mapDirFor = (name) => path.join(TMP_DIR, pf.safePlanName(name), 'map');
    it('maps each node to a file named the way a build would name it', () => {
        const rec = pm.writePlanMap({
            projectName: 'Note Taking App',
            goal: 'A desktop note-taking app',
            nodes: NODES,
            edges: EDGES,
        });
        expect(rec.dirName).toBe('Note_Taking_App');
        const byLabel = Object.fromEntries(rec.files.map((f) => [f.label, f.file]));
        // Extension follows the node's own language, not one global default.
        expect(byLabel['Notes Core']).toBe('notes-core.ts');
        expect(byLabel['Editor View']).toBe('editor-view.ts');
        expect(byLabel['Encrypted Store']).toBe('encrypted-store.rs');
        expect(rec.entryFile).toBe('notes-core.ts');
        expect(existsSync(path.join(mapDirFor('Note Taking App'), 'notes-core.ts'))).toBe(true);
        expect(existsSync(path.join(mapDirFor('Note Taking App'), 'wiring.md'))).toBe(true);
        expect(existsSync(path.join(mapDirFor('Note Taking App'), 'map.json'))).toBe(true);
    });
    it('wires the map the same direction the code would: target depends on source', () => {
        const rec = pm.writePlanMap({ projectName: 'W', goal: 'g', nodes: NODES, edges: EDGES });
        const core = rec.files.find((f) => f.label === 'Notes Core');
        const store = rec.files.find((f) => f.label === 'Encrypted Store');
        expect(core.dependsOn.sort()).toEqual(['editor-view.ts', 'encrypted-store.rs']);
        expect(core.dependedOnBy).toEqual([]);
        expect(store.dependsOn).toEqual([]);
        expect(store.dependedOnBy).toEqual(['notes-core.ts']);
    });
    it('writes no code — only a header carrying purpose, answers and wiring', () => {
        pm.writePlanMap({ projectName: 'H', goal: 'g', nodes: NODES, edges: EDGES });
        const file = readFileSync(path.join(mapDirFor('H'), 'notes-core.ts'), 'utf-8');
        expect(file).toContain('Purpose: owns the note model and exposes CRUD');
        // The co-worker answers travel with the node into its file.
        expect(file).toContain('Q: What data does the Notes Core store besides the notes?');
        expect(file).toContain('A: Only notes and their tags. No accounts, no sync state.');
        expect(file).toContain('Depends on: editor-view.ts, encrypted-store.rs');
        // Every line is a comment: this is a map, not a program.
        for (const line of file.split('\n').filter((l) => l.trim())) {
            expect(line.startsWith('//')).toBe(true);
        }
    });
    it('marks a node with no declared purpose instead of implying it has one', () => {
        pm.writePlanMap({ projectName: 'P', goal: 'g', nodes: NODES, edges: EDGES });
        const file = readFileSync(path.join(mapDirFor('P'), 'encrypted-store.rs'), 'utf-8');
        expect(file).toContain('Purpose: (no purpose declared yet)');
    });
    it('uses the language\'s own comment syntax in a non-brace language', () => {
        pm.writePlanMap({ projectName: 'R', goal: 'g', nodes: NODES, edges: EDGES });
        const rust = readFileSync(path.join(mapDirFor('R'), 'encrypted-store.rs'), 'utf-8');
        // Rust uses // like TS — the prefix must still be valid there.
        expect(rust.split('\n').filter((l) => l.trim()).every((l) => l.startsWith('//'))).toBe(true);
        const py = pm.writePlanMap({
            projectName: 'Py',
            goal: 'g',
            nodes: [{ id: 'p1', type: 'logic', label: 'Worker', language: 'python', isMaster: true }],
            edges: [],
        });
        expect(py.files[0].file).toBe('worker.py');
        const pyFile = readFileSync(path.join(mapDirFor('Py'), 'worker.py'), 'utf-8');
        // "#" comments in Python — a "//" header there would be a syntax error the
        // moment the file gained code.
        expect(pyFile.split('\n').filter((l) => l.trim()).every((l) => l.startsWith('#'))).toBe(true);
    });
    it('is deterministic: the same design maps to identical bytes', () => {
        pm.writePlanMap({ projectName: 'D', goal: 'g', nodes: NODES, edges: EDGES });
        const first = readFileSync(path.join(mapDirFor('D'), 'notes-core.ts'), 'utf-8');
        const rec2 = pm.writePlanMap({ projectName: 'D', goal: 'g', nodes: NODES, edges: EDGES });
        const second = readFileSync(path.join(mapDirFor('D'), 'notes-core.ts'), 'utf-8');
        expect(second).toBe(first);
        expect(rec2.removed).toEqual([]);
    });
    it('gives two nodes that sanitise to the same name separate files', () => {
        // "Auth" and "auth" both sanitise to auth.ts — one would overwrite the other.
        const rec = pm.writePlanMap({
            projectName: 'Clash',
            goal: 'g',
            nodes: [
                { id: 'a', type: 'logic', label: 'Auth', isMaster: true },
                { id: 'b', type: 'logic', label: 'auth' },
                { id: 'c', type: 'logic', label: 'AUTH' },
            ],
            edges: [{ source: 'a', target: 'b' }],
        });
        const names = rec.files.map((f) => f.file);
        expect(new Set(names).size).toBe(3);
        expect(names).toContain('auth.ts');
        expect(names).toContain('auth-2.ts');
        expect(names).toContain('auth-3.ts');
        expect(readdirSync(mapDirFor('Clash')).filter((f) => f.startsWith('auth')).length).toBe(3);
    });
    it('removes the files of nodes deleted from the design, and nothing else', () => {
        pm.writePlanMap({ projectName: 'Shrink', goal: 'g', nodes: NODES, edges: EDGES });
        // Something the user left in the map folder themselves.
        const mine = path.join(mapDirFor('Shrink'), 'my-notes.txt');
        writeFileSync(mine, 'do not delete me', 'utf-8');
        const rec = pm.writePlanMap({
            projectName: 'Shrink',
            goal: 'g',
            nodes: [NODES[0], NODES[1]],
            edges: [EDGES[0]],
        });
        expect(rec.removed).toEqual(['encrypted-store.rs']);
        expect(existsSync(path.join(mapDirFor('Shrink'), 'encrypted-store.rs'))).toBe(false);
        expect(existsSync(path.join(mapDirFor('Shrink'), 'notes-core.ts'))).toBe(true);
        // The mapper only ever deletes files its own previous map.json listed.
        expect(existsSync(mine)).toBe(true);
    });
    it('counts the answered questions per file', () => {
        const rec = pm.writePlanMap({ projectName: 'QA', goal: 'g', nodes: NODES, edges: EDGES });
        expect(rec.files.find((f) => f.label === 'Notes Core').answers).toBe(1);
        expect(rec.files.find((f) => f.label === 'Editor View').answers).toBe(0);
    });
    it('ignores edges pointing at nodes that are not in the design', () => {
        const rec = pm.writePlanMap({
            projectName: 'Dangling',
            goal: 'g',
            nodes: [NODES[0]],
            edges: [{ source: 'ghost', target: 'node_1' }, { source: 'node_1', target: 'ghost' }],
        });
        expect(rec.files[0].dependsOn).toEqual([]);
        expect(rec.files[0].dependedOnBy).toEqual([]);
    });
    it('lists every mapped file and the unwired ones in wiring.md', () => {
        pm.writePlanMap({ projectName: 'Wire', goal: 'A note app', nodes: NODES, edges: [EDGES[0]] });
        const md = readFileSync(path.join(mapDirFor('Wire'), 'wiring.md'), 'utf-8');
        expect(md).toContain('# Wiring map — Wire');
        expect(md).toContain('**What it is:** A note app');
        expect(md).toContain('`notes-core.ts` **(entry)**');
        expect(md).toContain('no code generated');
        // Encrypted Store has no wiring at all now, so it must be called out.
        expect(md).toContain('## Not wired to anything yet');
        expect(md).toContain('`encrypted-store.rs`');
    });
    it('reports whether a design has already been mapped', () => {
        expect(pm.planMapExists('Never Mapped')).toBe(false);
        // A name needing sanitisation must be found under the SAME directory the
        // writer used — if the two sanitised differently, the autosave refresh
        // would look in a folder that does not exist and silently never run.
        pm.writePlanMap({ projectName: 'My App!', goal: 'g', nodes: NODES, edges: EDGES });
        expect(existsSync(path.join(TMP_DIR, 'My_App', 'map', 'map.json'))).toBe(true);
        expect(pm.planMapExists('My App!')).toBe(true);
        expect(pm.planMapExists('  My App!  ')).toBe(true);
        // A genuinely different design is not reported as mapped.
        expect(pm.planMapExists('My Other App')).toBe(false);
        // KNOWN LIMITATION (pre-existing, inherited from safePlanName via
        // savePlanGraph/savePlanFile — not introduced here): the folder name is a
        // slug, so two project names that slug the same way share one folder.
        // Pinned deliberately so the behaviour is a decision on the record rather
        // than a surprise the first time someone names two plans "My App" and
        // "My App!".
        expect(pm.planMapExists('My App')).toBe(true);
    });
    it('does not require the plan graph to exist first', () => {
        // Mapping must work from an unsaved design (the canvas sends live state).
        const rec = pm.writePlanMap({ projectName: 'Fresh', goal: '', nodes: NODES, edges: [] });
        expect(rec.files).toHaveLength(3);
        expect(existsSync(path.join(TMP_DIR, 'Fresh', 'map', 'map.json'))).toBe(true);
    });
    it('writes map.json a later run can read back', () => {
        const rec = pm.writePlanMap({ projectName: 'Durable', goal: 'g', nodes: NODES, edges: EDGES });
        const parsed = JSON.parse(readFileSync(path.join(mapDirFor('Durable'), 'map.json'), 'utf-8'));
        expect(parsed.entryFile).toBe(rec.entryFile);
        expect(parsed.files).toHaveLength(3);
        expect(parsed.files[0].file).toBe(rec.files[0].file);
    });
});
