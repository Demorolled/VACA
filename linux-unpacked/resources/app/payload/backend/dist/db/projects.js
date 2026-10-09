import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
// ── Disk persistence ──────────────────────────────────────────────────────
// Projects live in memory for speed, but are mirrored to a JSON file so a
// backend restart does not wipe them. The frontend keeps the project id in
// localStorage; without persistence that id goes stale the moment the backend
// restarts, and every generation/scaffold call fails with "Project not found"
// (404). The mirror is loaded once at startup and rewritten on each mutation.
const DEFAULT_DATA_DIR = fileURLToPath(new URL('../../data', import.meta.url));
const DEFAULT_PROJECTS_FILE = join(DEFAULT_DATA_DIR, 'projects.json');
function loadFromDisk(projectsFile) {
    const map = new Map();
    try {
        if (!existsSync(projectsFile))
            return map;
        const raw = readFileSync(projectsFile, 'utf8');
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed))
            return map;
        for (const p of parsed) {
            if (!p || typeof p.id !== 'string')
                continue;
            map.set(p.id, {
                ...p,
                // Dates serialize to ISO strings — re-hydrate them back to Date.
                createdAt: p.createdAt ? new Date(p.createdAt) : new Date(),
                updatedAt: p.updatedAt ? new Date(p.updatedAt) : new Date(),
            });
        }
    }
    catch (err) {
        console.warn('[projects] Failed to load projects from disk:', err instanceof Error ? err.message : err);
    }
    return map;
}
function persistToDisk(projects, projectsFile) {
    try {
        mkdirSync(dirname(projectsFile), { recursive: true });
        writeFileSync(projectsFile, JSON.stringify(Array.from(projects.values()), null, 2));
    }
    catch (err) {
        console.warn('[projects] Failed to persist projects:', err instanceof Error ? err.message : err);
    }
}
// ── Per-project generation cache (sidecar) ────────────────────────────────
// The last generation result is cached per project so an export reuses the
// exact code the user reviewed instead of regenerating a different
// (non-deterministic) codebase. The cache is keyed by project id and mirrored
// to a small sidecar JSON file NEXT TO projects.json — never inside it, so
// projects.json stays small — which keeps exports byte-identical even across
// backend restarts. The sidecar path is derived per-store from the projects
// file (so tests with temp stores get isolated sidecars).
export class ProjectStore {
    projects;
    projectsFile;
    // Generation-cache sidecar: map of project id → cached generation entry,
    // lazily loaded from disk and mirrored on every mutation.
    cacheFile;
    cacheLoaded = false;
    cacheWarned = false;
    cacheMap = new Map();
    constructor(projectsFile) {
        // Tests inject a temp file so they never touch the live store; the default
        // mirrors projects to backend/data/projects.json (survives restarts).
        this.projectsFile = projectsFile || DEFAULT_PROJECTS_FILE;
        this.cacheFile = join(dirname(this.projectsFile), 'generation-cache.json');
        this.projects = loadFromDisk(this.projectsFile);
    }
    // ── Generation cache ──
    loadCache() {
        if (this.cacheLoaded)
            return;
        try {
            if (existsSync(this.cacheFile)) {
                const parsed = JSON.parse(readFileSync(this.cacheFile, 'utf8'));
                if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                    for (const [id, entry] of Object.entries(parsed))
                        this.cacheMap.set(id, entry);
                }
            }
            this.cacheLoaded = true;
        }
        catch (err) {
            // Corrupt/partial file (e.g. a crash mid-write). Warn once but leave
            // cacheLoaded false so a later successful persist rewrites the file and
            // the next access retries — the cache must not stay disabled all session.
            if (!this.cacheWarned) {
                this.cacheWarned = true;
                console.warn('[projects] Failed to load generation cache from disk:', err instanceof Error ? err.message : err);
            }
            return;
        }
        // Prune sidecar entries whose project no longer exists (e.g. a manual
        // projects.json reset bypassed delete()) so orphaned entries can't inflate
        // the file forever.
        const orphans = [];
        for (const id of this.cacheMap.keys()) {
            if (!this.projects.has(id))
                orphans.push(id);
        }
        if (orphans.length > 0) {
            for (const id of orphans)
                this.cacheMap.delete(id);
            this.persistCache();
        }
    }
    persistCache() {
        try {
            mkdirSync(dirname(this.cacheFile), { recursive: true });
            writeFileSync(this.cacheFile, JSON.stringify(Object.fromEntries(this.cacheMap), null, 2));
        }
        catch (err) {
            console.warn('[projects] Failed to persist generation cache:', err instanceof Error ? err.message : err);
        }
    }
    /**
     * Read the cached generation for a project (lazy-loaded from the sidecar).
     * Returns undefined when nothing was cached yet or the project was deleted.
     */
    getGenerationCache(id) {
        this.loadCache();
        return this.cacheMap.get(id);
    }
    /**
     * Cache a generation result for a project and mirror it to the sidecar so a
     * later export (even after a restart) reuses the exact code the user saw.
     */
    setGenerationCache(id, value) {
        this.loadCache();
        this.cacheMap.set(id, value);
        this.persistCache();
    }
    getAll() {
        return Array.from(this.projects.values());
    }
    getById(id) {
        return this.projects.get(id);
    }
    create(data) {
        const now = new Date();
        const project = {
            ...data,
            createdAt: now,
            updatedAt: now,
        };
        this.projects.set(data.id, project);
        persistToDisk(this.projects, this.projectsFile);
        return project;
    }
    update(id, updates) {
        const project = this.projects.get(id);
        if (!project)
            return undefined;
        const updated = {
            ...project,
            ...updates,
            updatedAt: new Date(),
        };
        this.projects.set(id, updated);
        persistToDisk(this.projects, this.projectsFile);
        return updated;
    }
    delete(id) {
        const existed = this.projects.delete(id);
        if (existed) {
            persistToDisk(this.projects, this.projectsFile);
            // Drop the project's cached generation from the sidecar too, so deleted
            // projects never leave stale entries behind.
            this.loadCache();
            if (this.cacheMap.delete(id))
                this.persistCache();
        }
        return existed;
    }
}
export const projects = new ProjectStore();
