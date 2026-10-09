import { describe, it, expect, afterEach } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { ProjectStore } from './projects.js';
import { projectGraphSignature } from '../layers/fileGenerator.js';
import { resolveCachedGeneration } from '../routes/export.js';
// ═══════════════════════════════════════════════════════════════════════════
// Fixtures & helpers
// ═══════════════════════════════════════════════════════════════════════════
const tmpDirs = [];
function makeTmpStore() {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-db-cache-test-'));
    tmpDirs.push(dir);
    const file = path.join(dir, 'projects.json');
    return {
        store: new ProjectStore(file),
        file,
        cacheFile: path.join(dir, 'generation-cache.json'),
        dir,
    };
}
function node(id, label, opts = {}) {
    return {
        id,
        type: opts.type ?? 'logic',
        position: { x: 0, y: 0 },
        // Runtime nodes carry the architecture type in data.type (the static
        // NodeData type omits it) — the signature reads it, so cast it through.
        data: {
            label,
            description: opts.description ?? '',
            status: 'pending',
            type: opts.type ?? 'logic',
            language: opts.language ?? 'typescript',
        },
    };
}
function makeProject(overrides = {}) {
    return {
        id: 'p-cache-test',
        name: 'cache-test-app',
        targetOS: 'linux',
        nodes: [],
        edges: [],
        createdAt: new Date(),
        updatedAt: new Date(),
        ...overrides,
    };
}
function cacheEntry(sig, fileCount = 1, marker = 'v1') {
    return {
        sig,
        result: {
            files: Array.from({ length: fileCount }, (_, i) => ({
                fileName: `file-${i}.ts`,
                language: 'typescript',
                code: `// ${marker}\nexport const x${i} = ${i};`,
                nodeId: `n${i}`,
                nodeLabel: `file-${i}.ts`,
                dependencies: [],
                exports: [`x${i}`],
                errors: [],
                validated: true,
            })),
            totalChars: 10,
            totalErrors: 0,
            validatedCount: fileCount,
            failedCount: 0,
            tsCompileClean: true,
            contractViolations: 0,
            projectId: 'p-cache-test',
        },
        at: Date.now(),
    };
}
/** Plain map-backed getter for exercising resolveCachedGeneration in isolation. */
function mapGetter(map) {
    return (id) => map.get(id);
}
afterEach(() => {
    for (const dir of tmpDirs.splice(0)) {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});
// ═══════════════════════════════════════════════════════════════════════════
// 1. Sidecar persistence — keyed by project id, never inside projects.json
// ═══════════════════════════════════════════════════════════════════════════
describe('generation cache (ProjectStore sidecar)', () => {
    it('is keyed by project id and never written into projects.json', () => {
        const { store, file } = makeTmpStore();
        store.create({ id: 'p1', name: 'app', targetOS: 'linux', nodes: [], edges: [] });
        // The marker lives inside the generated-code payload — if any part of the
        // cache ever leaked into the project blob, it would appear in the JSON.
        store.setGenerationCache('p1', cacheEntry('sig-1', 1, 'generated-code-v1'));
        expect(store.getGenerationCache('p1')).toBeDefined();
        expect(store.getGenerationCache('p1')?.sig).toBe('sig-1');
        // projects.json must stay clean (the ballooning-projects.json risk).
        const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
        expect(Object.keys(raw[0])).not.toContain('lastGeneration');
        expect(JSON.stringify(raw)).not.toContain('generated-code-v1');
        expect(JSON.stringify(raw)).not.toContain('sig-1');
    });
    it('persists the entry to the sidecar file, keyed by project id', () => {
        const { store, cacheFile } = makeTmpStore();
        store.create({ id: 'p1', name: 'app', targetOS: 'linux', nodes: [], edges: [] });
        store.setGenerationCache('p1', cacheEntry('sig-1', 1, 'generated-code-v1'));
        const sidecar = JSON.parse(fs.readFileSync(cacheFile, 'utf8'));
        expect(sidecar['p1']).toBeDefined();
        expect(sidecar['p1'].sig).toBe('sig-1');
        expect(JSON.stringify(sidecar)).toContain('generated-code-v1');
    });
    it('is writable: re-setting replaces the previous entry', () => {
        const { store } = makeTmpStore();
        store.create({ id: 'p1', name: 'app', targetOS: 'linux', nodes: [], edges: [] });
        store.setGenerationCache('p1', cacheEntry('sig-a', 1, 'first'));
        store.setGenerationCache('p1', cacheEntry('sig-b', 2, 'second'));
        const cached = store.getGenerationCache('p1');
        expect(cached?.sig).toBe('sig-b');
        expect(cached?.result.files).toHaveLength(2);
        expect(JSON.stringify(store.getAll()[0])).not.toContain('sig-a');
    });
});
// ═══════════════════════════════════════════════════════════════════════════
// 2. Lifecycle — survives update(), survives restart, cleaned up on delete
// ═══════════════════════════════════════════════════════════════════════════
describe('generation cache lifecycle across ProjectStore operations', () => {
    it('survives update() (cache lives in the store, keyed by id)', () => {
        const { store } = makeTmpStore();
        store.create({ id: 'p1', name: 'app', targetOS: 'linux', nodes: [], edges: [] });
        store.setGenerationCache('p1', cacheEntry('sig-1'));
        store.update('p1', { name: 'renamed' });
        expect(store.getById('p1')?.name).toBe('renamed');
        expect(store.getGenerationCache('p1')?.sig).toBe('sig-1');
    });
    it('survives a backend restart: a fresh store on the same files reads the sidecar', () => {
        const { store, file } = makeTmpStore();
        store.create({ id: 'p1', name: 'app', targetOS: 'linux', nodes: [], edges: [] });
        store.setGenerationCache('p1', cacheEntry('sig-1', 1, 'byte-identical-code'));
        store.update('p1', { name: 'renamed' });
        // Simulates the backend restarting: brand-new store, same files on disk.
        const fresh = new ProjectStore(file);
        expect(fresh.getById('p1')?.name).toBe('renamed');
        const cached = fresh.getGenerationCache('p1');
        expect(cached?.sig).toBe('sig-1');
        // The generated code itself is byte-identical to what was cached.
        expect(cached?.result.files[0].code).toContain('// byte-identical-code');
    });
    it('recovers after a corrupt sidecar file (retries instead of staying disabled)', () => {
        const { store, file, cacheFile } = makeTmpStore();
        store.create({ id: 'p1', name: 'app', targetOS: 'linux', nodes: [], edges: [] });
        // Simulate a crash mid-write: the sidecar is partial/corrupt JSON.
        fs.writeFileSync(cacheFile, '{ "p1": "truncated', 'utf8');
        // Reads must not throw — they just see no cache.
        expect(store.getGenerationCache('p1')).toBeUndefined();
        // A later set rewrites the file; the cache recovers and survives a restart.
        store.setGenerationCache('p1', cacheEntry('sig-1'));
        expect(store.getGenerationCache('p1')?.sig).toBe('sig-1');
        const fresh = new ProjectStore(file);
        expect(fresh.getGenerationCache('p1')?.sig).toBe('sig-1');
    });
    it('prunes sidecar entries for projects that no longer exist (e.g. manual projects.json reset)', () => {
        const { store, file, cacheFile } = makeTmpStore();
        store.create({ id: 'p1', name: 'app', targetOS: 'linux', nodes: [], edges: [] });
        store.setGenerationCache('p1', cacheEntry('sig-1'));
        // Simulate projects.json being reset/wiped while the sidecar survives.
        fs.writeFileSync(file, '[]', 'utf8');
        const fresh = new ProjectStore(file);
        expect(fresh.getGenerationCache('p1')).toBeUndefined();
        // The orphan was pruned from the sidecar on load.
        const sidecar = JSON.parse(fs.readFileSync(cacheFile, 'utf8'));
        expect(sidecar['p1']).toBeUndefined();
    });
    it('delete() removes the project from the sidecar', () => {
        const { store, file, cacheFile } = makeTmpStore();
        store.create({ id: 'p1', name: 'a', targetOS: 'linux', nodes: [], edges: [] });
        store.create({ id: 'p2', name: 'b', targetOS: 'linux', nodes: [], edges: [] });
        store.setGenerationCache('p1', cacheEntry('sig-1'));
        store.setGenerationCache('p2', cacheEntry('sig-2'));
        store.delete('p1');
        const sidecar = JSON.parse(fs.readFileSync(cacheFile, 'utf8'));
        expect(sidecar['p1']).toBeUndefined();
        expect(sidecar['p2']).toBeDefined();
        // A fresh store (post-restart) agrees: p1's cache is gone, p2's remains.
        const fresh = new ProjectStore(file);
        expect(fresh.getGenerationCache('p1')).toBeUndefined();
        expect(fresh.getGenerationCache('p2')?.sig).toBe('sig-2');
    });
});
// ═══════════════════════════════════════════════════════════════════════════
// 3. export.ts reuse decision — keyed by projectGraphSignature
// ═══════════════════════════════════════════════════════════════════════════
describe('export.ts resolveCachedGeneration (keyed by projectGraphSignature)', () => {
    it('projectGraphSignature is stable regardless of node array order', () => {
        const nodesA = [node('n1', 'timer-input.ts'), node('n2', 'timer-logic.ts')];
        const nodesB = [node('n2', 'timer-logic.ts'), node('n1', 'timer-input.ts')];
        expect(projectGraphSignature(makeProject({ nodes: nodesA })))
            .toBe(projectGraphSignature(makeProject({ nodes: nodesB })));
    });
    it('projectGraphSignature changes when the graph changes', () => {
        const sigBase = projectGraphSignature(makeProject({
            nodes: [node('n1', 'timer-input.ts')],
            edges: [],
        }));
        // Added node
        expect(projectGraphSignature(makeProject({
            nodes: [node('n1', 'timer-input.ts'), node('n2', 'timer-logic.ts')],
        }))).not.toBe(sigBase);
        // Edited node label/description
        expect(projectGraphSignature(makeProject({
            nodes: [node('n1', 'timer-input.ts', { description: 'changed' })],
        }))).not.toBe(sigBase);
        // Changed targetOS
        expect(projectGraphSignature(makeProject({ nodes: [node('n1', 'timer-input.ts')], targetOS: 'windows' })))
            .not.toBe(sigBase);
        // Added edge
        expect(projectGraphSignature(makeProject({
            nodes: [node('n1', 'timer-input.ts'), node('n2', 'timer-logic.ts')],
            edges: [{ id: 'e1', source: 'n1', target: 'n2' }],
        }))).not.toBe(sigBase);
    });
    it('returns the cached entry when the signature still matches', () => {
        const project = makeProject({ nodes: [node('n1', 'timer-input.ts')] });
        const sig = projectGraphSignature(project);
        const cache = new Map([[project.id, cacheEntry(sig)]]);
        const cached = resolveCachedGeneration(project, {}, mapGetter(cache));
        expect(cached).toBeDefined();
        expect(cached?.sig).toBe(sig);
    });
    it('returns undefined when the graph changed since generation (stale cache)', () => {
        const project = makeProject({ nodes: [node('n1', 'timer-input.ts')] });
        const cache = new Map([[project.id, cacheEntry(projectGraphSignature(project))]]);
        // The user adds a node to the canvas → new signature → cache must be discarded.
        project.nodes.push(node('n2', 'timer-logic.ts'));
        expect(resolveCachedGeneration(project, {}, mapGetter(cache))).toBeUndefined();
    });
    it('returns undefined when regenerate: true is forced, even if the signature matches', () => {
        const project = makeProject({ nodes: [node('n1', 'timer-input.ts')] });
        const cache = new Map([[project.id, cacheEntry(projectGraphSignature(project))]]);
        expect(resolveCachedGeneration(project, { regenerate: true }, mapGetter(cache))).toBeUndefined();
    });
    it('returns undefined when the cached result produced no files', () => {
        const project = makeProject({ nodes: [node('n1', 'timer-input.ts')] });
        const cache = new Map([[project.id, cacheEntry(projectGraphSignature(project), 0)]]);
        expect(resolveCachedGeneration(project, {}, mapGetter(cache))).toBeUndefined();
    });
    it('full flow: generation → export reuses → canvas edit → export regenerates and re-caches', () => {
        // Simulate /api/generate/:id/files storing the cache...
        const project = makeProject({ nodes: [node('n1', 'timer-input.ts')] });
        const cache = new Map();
        const sig1 = projectGraphSignature(project);
        cache.set(project.id, cacheEntry(sig1));
        // .../api/export reuses it unchanged.
        expect(resolveCachedGeneration(project, {}, mapGetter(cache))?.sig).toBe(sig1);
        // User edits the canvas → the export must NOT reuse the stale result.
        project.nodes.push(node('n2', 'timer-logic.ts'));
        const sig2 = projectGraphSignature(project);
        expect(resolveCachedGeneration(project, {}, mapGetter(cache))).toBeUndefined();
        // The export regenerates and re-caches under the new signature; the next
        // export reuses again.
        cache.set(project.id, cacheEntry(sig2));
        expect(resolveCachedGeneration(project, {}, mapGetter(cache))?.sig).toBe(sig2);
    });
});
